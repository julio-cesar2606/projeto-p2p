import argparse
import hashlib
import json
import os
import random
import socket
import struct
import sys
import threading
import time
from utils import (BLOCO_PADRAO, LimitadorTaxa, MB, aguardar_porta, conectar, criar_socket_servidor,
                   enviar_json, enviar_limitado, env, esperar_ate, hash_blocos, ler_linha,
                   receber_exato, receber_json, registrar_resultado)

class Servente:
    def __init__(self, a):
        self.a = a
        self.id = a.id
        self.limitador = LimitadorTaxa(int(a.taxa_mbps * MB))
        self.lock = threading.Lock()         
        self.arq_lock = threading.Lock()      # serializa
        self.meta = None
        self.tem = None                      
        self.n_tem = 0
        self.arquivo = None
        self.peers = {}                       # (ip, porta) -> id
        self.feitos = {}                      # id -> tempo
        self.viz = {}                        
        self.em_andamento = set()
        self.completo = threading.Event()

    def iniciar_servidor(self):
        srv = criar_socket_servidor(self.a.porta)
        threading.Thread(target=self._aceitar, args=(srv,), daemon=True).start()

    def _aceitar(self, srv):
        while True:
            try:
                conn, addr = srv.accept()
            except OSError:
                return
            threading.Thread(target=self._tratar, args=(conn, addr), daemon=True).start()

    def _ler_bloco(self, i):
        with self.arq_lock:
            self.arquivo.seek(i * self.meta["bloco"])
            return self.arquivo.read(self.meta["bloco"])

    def _tratar(self, conn, addr):
        try:
            p = ler_linha(conn).split()
            cmd = p[0]
            if cmd == "BLOCO":
                i = int(p[1])
                if self.meta and 0 <= i < self.meta["n_blocos"] and self.tem[i]:
                    dados = self._ler_bloco(i)
                    conn.sendall(struct.pack(">I", len(dados)))
                    enviar_limitado(conn, dados, self.limitador)  
                else:
                    conn.sendall(struct.pack(">I", 0))
            elif cmd == "BITMAP":
                bm = bytes(self.tem) if self.tem is not None else b""
                conn.sendall(struct.pack(">I", len(bm)) + bm)
            elif cmd == "ANUNCIAR" and self.a.papel == "seed":
                pid, porta = p[1], int(p[2])
                with self.lock:
                    self.peers[(addr[0], porta)] = pid
                    lista = [[ip, pt, i] for (ip, pt), i in self.peers.items()]
                enviar_json(conn, {"meta": self.meta, "peers": lista})
            elif cmd == "PEERS" and self.a.papel == "seed":
                with self.lock:
                    lista = [[ip, pt, i] for (ip, pt), i in self.peers.items()]
                enviar_json(conn, lista)
            elif cmd == "FEITO" and self.a.papel == "seed":
                with self.lock:
                    self.feitos[p[1]] = float(p[2])
                enviar_json(conn, {"ok": True})
            elif cmd == "STATUS" and self.a.papel == "seed":
                with self.lock:
                    enviar_json(conn, {"feitos": len(self.feitos), "esperados": self.a.esperados})
        except (OSError, ValueError, IndexError):
            pass
        finally:
            conn.close()

    def executar_seed(self):
        a = self.a
        print(f"[seed] calculando hashes de {a.arquivo}", flush=True)
        tam = os.path.getsize(a.arquivo)
        bloco = a.bloco_kb * 1024
        hashes = hash_blocos(a.arquivo, bloco)
        self.meta = {"nome": os.path.basename(a.arquivo), "tamanho": tam, "bloco": bloco,
                     "n_blocos": len(hashes), "hashes": hashes}
        self.tem = bytearray(b"\x01" * len(hashes))
        self.arquivo = open(a.arquivo, "rb")
        self.iniciar_servidor()
        print(f"[seed] PRONTO porta {a.porta}: {len(hashes)} blocos de {a.bloco_kb} KB, "
              f"taxa {a.taxa_mbps} MB/s, aguardando {a.esperados} peers", flush=True)
        fim = time.monotonic() + a.espera_max
        while time.monotonic() < fim:
            with self.lock:
                if len(self.feitos) >= a.esperados:
                    break
            time.sleep(0.2)
        time.sleep(1.0)  
        with self.lock:
            tempos = sorted(self.feitos.values())
        if tempos:
            print(f"[seed] {len(tempos)} peers concluiram: min {tempos[0]:.2f}s  "f"med {sum(tempos) / len(tempos):.2f}s  max {tempos[-1]:.2f}s", flush=True)

    def _tracker(self, comando):
        s = conectar(self.a.tracker_host, self.a.tracker_porta)
        try:
            s.sendall((comando + "\n").encode())
            return receber_json(s)
        finally:
            s.close()

    def _atualizar_vizinhos(self):
        while not self.completo.is_set():
            try:
                lista = self._tracker("PEERS")
            except OSError:
                lista = []
            novos = {}
            for ip, porta, pid in lista:
                if pid == self.id:
                    continue
                try:
                    s = conectar(ip, porta, timeout=2)
                    try:
                        s.sendall(b"BITMAP\n")
                        (n,) = struct.unpack(">I", receber_exato(s, 4))
                        novos[(ip, porta)] = receber_exato(s, n)
                    finally:
                        s.close()
                except (OSError, ConnectionError):
                    pass
            with self.lock:
                self.viz = novos
            time.sleep(0.3)

    def _escolher(self):
        seed = (self.a.tracker_host, self.a.tracker_porta)
        with self.lock:
            faltam = [i for i in range(self.meta["n_blocos"])
                      if not self.tem[i] and i not in self.em_andamento]
            if not faltam:
                return None
            amostra = random.sample(faltam, min(48, len(faltam)))
            melhor = None
            for i in amostra:
                fontes = [addr for addr, bm in self.viz.items() if len(bm) > i and bm[i]]
                if fontes and (melhor is None or len(fontes) < len(melhor[1])):
                    melhor = (i, fontes)            # bloco mais raro
            if melhor:
                i, fontes = melhor
                fonte = random.choice(fontes)
            else:
                i, fonte = amostra[0], seed         
            self.em_andamento.add(i)
            return i, fonte

    def _baixar_bloco(self, i, fonte):
        s = None
        try:
            s = conectar(fonte[0], fonte[1], timeout=10)
            s.settimeout(60)
            s.sendall(f"BLOCO {i}\n".encode())
            (n,) = struct.unpack(">I", receber_exato(s, 4))
            if n == 0:
                with self.lock:                    
                    bm = self.viz.get(fonte)
                    if bm is not None and i < len(bm):
                        bm[i] = 0
                return False
            dados = receber_exato(s, n)
            if hashlib.sha256(dados).hexdigest() != self.meta["hashes"][i]:
                print(f"[{self.id}] hash inválido no bloco {i}, descartado", file=sys.stderr)
                return False
            with self.arq_lock:
                self.arquivo.seek(i * self.meta["bloco"])
                self.arquivo.write(dados)
                self.arquivo.flush()
            with self.lock:
                if not self.tem[i]:
                    self.tem[i] = 1
                    self.n_tem += 1
                    if self.n_tem == self.meta["n_blocos"]:
                        self.completo.set()
            return True
        except (OSError, ConnectionError):
            return False
        finally:
            if s:
                s.close()

    def _worker(self):
        while not self.completo.is_set():
            esc = self._escolher()
            if esc is None:
                time.sleep(0.02)
                continue
            i, fonte = esc
            ok = self._baixar_bloco(i, fonte)
            with self.lock:
                self.em_andamento.discard(i)
            if not ok:
                time.sleep(0.05)

    def executar_peer(self):
        a = self.a
        self.iniciar_servidor()                     # aceita pedidos de outros peers
        aguardar_porta(a.tracker_host, a.tracker_porta)
        esperar_ate(a.inicio_em)                    # largada sincronizada

        t0 = time.perf_counter()
        s = conectar(a.tracker_host, a.tracker_porta)
        s.sendall(f"ANUNCIAR {self.id} {a.porta}\n".encode())
        resp = receber_json(s)
        s.close()

        os.makedirs(a.pasta, exist_ok=True)
        caminho = os.path.join(a.pasta, resp["meta"]["nome"] + ".part")
        arquivo = open(caminho, "w+b")
        arquivo.truncate(resp["meta"]["tamanho"])
        with self.lock:
            self.arquivo = arquivo
            self.tem = bytearray(resp["meta"]["n_blocos"])
            self.meta = resp["meta"]

        threading.Thread(target=self._atualizar_vizinhos, daemon=True).start()
        trabalhadores = [threading.Thread(target=self._worker, daemon=True) for _ in range(a.paralelo)]
        for t in trabalhadores:
            t.start()
        self.completo.wait()
        dt = time.perf_counter() - t0

        print(f"[{self.id}] {self.meta['tamanho'] / MB:.0f} MB em {dt:.2f}s", flush=True)
        registrar_resultado(a.resultado, "p2p", a.tamanho_mb, a.n, a.rodada, self.id, dt)
        try:
            self._tracker(f"FEITO {self.id} {dt:.4f}")
        except OSError:
            pass

        # continua servindo os outros peers
        fim = time.monotonic() + a.espera_max
        while time.monotonic() < fim:
            try:
                st = self._tracker("STATUS")
            except (OSError, ConnectionError):
                break                               # tracker encerrou
            if st["feitos"] >= st["esperados"]:
                break
            time.sleep(0.3)

        arquivo.close()
        if not a.manter:
            try:
                os.remove(caminho)
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser(description="Nó P2P (seed ou peer)")
    ap.add_argument("--papel", choices=["seed", "peer"], default=env("PAPEL", "peer"))
    ap.add_argument("--id", default=env("ID", socket.gethostname()))
    ap.add_argument("--porta", type=int, default=env("PORTA", 7000, int))
    ap.add_argument("--taxa-mbps", type=float, default=env("TAXA_MBPS", 50, float),
                    help="limite de upload DESTE nó em MB/s (0 = sem limite)")
    
    ap.add_argument("--arquivo", default=env("ARQUIVO", "data/seed/arquivo_5MB.bin"))
    ap.add_argument("--esperados", type=int, default=env("N_CLIENTES", 1, int),help="quantos peers a seed espera (para saber quando encerrar)")
    ap.add_argument("--bloco-kb", type=int, default=env("BLOCO_KB", BLOCO_PADRAO // 1024, int))
    
    ap.add_argument("--tracker", default=env("TRACKER", "127.0.0.1:7000"), help="host:porta da seed")
    ap.add_argument("--pasta", default=None, help="onde o peer grava os blocos (padrão data/<id>)")
    ap.add_argument("--paralelo", type=int, default=env("PARALELO", 4, int),help="downloads simultâneos de blocos")
    ap.add_argument("--manter", action="store_true", help="não apagar o arquivo baixado no fim")
    
    ap.add_argument("--inicio-em", type=float, default=env("INICIO_EM", 0, float))
    ap.add_argument("--resultado", default=env("RESULTADO", ""))
    ap.add_argument("--tamanho-mb", type=int, default=env("TAMANHO_MB", 0, int))
    ap.add_argument("--n", type=int, default=env("N_CLIENTES", 1, int))
    ap.add_argument("--rodada", type=int, default=env("RODADA", 1, int))
    ap.add_argument("--espera-max", type=float, default=env("ESPERA_MAX", 1800, float),help="tempo máximo (s) de espera pelos demais antes de encerrar")
    a = ap.parse_args()

    host, _, porta = a.tracker.rpartition(":")
    a.tracker_host, a.tracker_porta = host, int(porta)
    if a.pasta is None:
        a.pasta = os.path.join("data", a.id)

    no = Servente(a)
    if a.papel == "seed":
        no.executar_seed()
    else:
        no.executar_peer()


if __name__ == "__main__":
    main()
