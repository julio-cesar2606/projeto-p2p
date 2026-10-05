import argparse
import hashlib
import json
import os
import socket
import struct
import sys
import threading
import time

MB = 1024 * 1024
CHUNK = 64 * 1024              # tamanho enviado por vez
BLOCO_PADRAO = 256 * 1024      # tamanho do bloco do P2P
TAMANHOS_PADRAO_MB = (5, 50, 500)


def env(nome, padrao=None, tipo=str):
    v = os.environ.get(nome)
    if v is None or v == "":
        return padrao
    return tipo(v)


def nome_arquivo(mb):
    return f"arquivo_{mb}MB.bin"

class LimitadorTaxa:
    def __init__(self, taxa_bps):
        self.taxa = taxa_bps
        self._lock = threading.Lock()
        self._proximo = time.monotonic()

    def consumir(self, n):
        if not self.taxa:
            return
        with self._lock:
            agora = time.monotonic()
            inicio = max(self._proximo, agora)
            self._proximo = inicio + n / self.taxa
            espera = inicio - agora
        if espera > 0.002:
            time.sleep(espera)

def criar_socket_servidor(porta):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", porta))
    s.listen(1024)
    return s


def receber_exato(sock, n):
    buf = bytearray(n)
    view = memoryview(buf)
    pos = 0
    while pos < n:
        r = sock.recv_into(view[pos:], n - pos)
        if r == 0:
            raise ConnectionError("conexao fechada antes de acabar")
        pos += r
    return buf


def descartar(sock, n):
    buf = bytearray(4 * CHUNK)
    view = memoryview(buf)
    restante = n
    while restante > 0:
        r = sock.recv_into(view, min(len(buf), restante))
        if r == 0:
            raise ConnectionError("conexao fechada")
        restante -= r


def ler_linha(sock, limite=4096):
    dados = bytearray()
    while True:
        c = sock.recv(1)
        if not c:
            raise ConnectionError("conexao fechada")
        if c == b"\n":
            return dados.decode()
        dados += c
        if len(dados) > limite:
            raise ValueError("linha muito longa")


def enviar_json(sock, obj):
    dados = json.dumps(obj).encode()
    sock.sendall(struct.pack(">I", len(dados)) + dados)


def receber_json(sock):
    (n,) = struct.unpack(">I", receber_exato(sock, 4))
    return json.loads(bytes(receber_exato(sock, n)))


def enviar_limitado(sock, dados, limitador):
    mv = memoryview(dados)
    for i in range(0, len(mv), CHUNK):
        parte = mv[i:i + CHUNK]
        if limitador:
            limitador.consumir(len(parte))
        sock.sendall(parte)


def aguardar_porta(host, porta, espera_max=120):
    fim = time.monotonic() + espera_max
    while True:
        try:
            with socket.create_connection((host, porta), timeout=2):
                return
        except OSError:
            if time.monotonic() > fim:
                raise TimeoutError(f"{host}:{porta} nao respondeu em {espera_max}s")
            time.sleep(0.2)


def conectar(host, porta, timeout=10):
    s = socket.create_connection((host, porta), timeout=timeout)
    s.settimeout(None)
    return s


def esperar_ate(epoch):
    if not epoch:
        return
    while True:
        falta = epoch - time.time()
        if falta <= 0:
            return
        time.sleep(min(falta, 0.05))

def atender_cliente(conn, pasta, limitador):
    try:
        partes = ler_linha(conn).split()
        caminho = None
        if len(partes) == 2 and partes[0] == "GET":
            caminho = os.path.join(pasta, os.path.basename(partes[1]))
        if not caminho or not os.path.isfile(caminho):
            conn.sendall(struct.pack(">Q", 0))
            return
        conn.sendall(struct.pack(">Q", os.path.getsize(caminho)))
        with open(caminho, "rb") as f:
            while True:
                dados = f.read(CHUNK)
                if not dados:
                    break
                limitador.consumir(len(dados))
                conn.sendall(dados)
    except (OSError, ValueError):
        pass
    finally:
        conn.close()

def hash_blocos(caminho, tam_bloco=BLOCO_PADRAO):
    hashes = []
    with open(caminho, "rb") as f:
        while True:
            b = f.read(tam_bloco)
            if not b:
                break
            hashes.append(hashlib.sha256(b).hexdigest())
    return hashes


def gerar_arquivo(caminho, mb):
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with open(caminho, "wb") as f:
        for _ in range(mb):
            f.write(os.urandom(MB))


def garantir_arquivo(pasta, mb):
    caminho = os.path.join(pasta, nome_arquivo(mb))
    if not (os.path.isfile(caminho) and os.path.getsize(caminho) == mb * MB):
        print(f"gerando {caminho} ...", flush=True)
        gerar_arquivo(caminho, mb)
    return caminho

CABECALHO_CSV = "arquitetura,tamanho_mb,n_clientes,rodada,cliente,tempo_s"

def registrar_resultado(csv_path, arq, tamanho_mb, n, rodada, cliente, tempo):
    if not csv_path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    linha = f"{arq},{tamanho_mb},{n},{rodada},{cliente},{tempo:.4f}\n".encode()
    fd = os.open(csv_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    try:
        os.write(fd, linha)
    finally:
        os.close(fd)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Gera arquivos de teste")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gerar")
    g.add_argument("--tamanho-mb", type=int, required=True)
    g.add_argument("--saida", required=True)
    gp = sub.add_parser("gerar-padrao")
    gp.add_argument("--pasta", default="data/seed")
    gp.add_argument("--tamanhos", type=int, nargs="+", default=list(TAMANHOS_PADRAO_MB))
    a = ap.parse_args()
    if a.cmd == "gerar":
        gerar_arquivo(a.saida, a.tamanho_mb)
        print("ok:", a.saida)
    else:
        for mb in a.tamanhos:
            print("ok:", garantir_arquivo(a.pasta, mb))
    sys.exit(0)
