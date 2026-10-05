import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import CABECALHO_CSV, aguardar_porta, garantir_arquivo, nome_arquivo  # noqa: E402
import agregar

TODAS = ["cs_sequencial", "cs_threads", "cs_pool", "p2p"]
SCRIPTS = {"cs_sequencial": "servidor_sequencial.py", "cs_threads": "servidor_threads.py",
           "cs_pool": "servidor_pool.py"}
PY = sys.executable
SRC = os.path.join(RAIZ, "src")
SEED_DIR = os.path.join(RAIZ, "data", "seed")


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def encerrar(procs):
    for p in procs:
        if p.poll() is None:
            p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


def rodar_cs(arq, mb, n, rodada, taxa, pool_n, csv_tmp):
    porta = porta_livre()
    cmd = [PY, os.path.join(SRC, SCRIPTS[arq]), "--porta", str(porta), "--pasta", SEED_DIR,
           "--taxa-mbps", str(taxa)]
    if arq == "cs_pool":
        cmd += ["-N", str(pool_n)]
    servidor = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, cwd=RAIZ)
    clientes = []
    try:
        aguardar_porta("127.0.0.1", porta, 30)
        inicio = time.time() + 1.0 + 0.15 * n
        for i in range(1, n + 1):
            clientes.append(subprocess.Popen(
                [PY, os.path.join(SRC, "cliente.py"), "--host", "127.0.0.1", "--porta", str(porta),
                 "--nome", nome_arquivo(mb), "--id", f"c{i}", "--inicio-em", str(inicio),
                 "--resultado", csv_tmp, "--arq", arq, "--tamanho-mb", str(mb), "--n", str(n),
                 "--rodada", str(rodada)], stdout=subprocess.DEVNULL, cwd=RAIZ))
        limite = 120 + 3 * mb * n / max(taxa, 0.1)
        for c in clientes:
            c.wait(timeout=limite)
    finally:
        encerrar(clientes + [servidor])


def rodar_p2p(mb, n, rodada, taxa, csv_tmp):
    porta_seed = porta_livre()
    seed = subprocess.Popen(
        [PY, os.path.join(SRC, "no_p2p.py"), "--papel", "seed", "--id", "seed", "--porta", str(porta_seed),
         "--arquivo", os.path.join(SEED_DIR, nome_arquivo(mb)), "--esperados", str(n),
         "--taxa-mbps", str(taxa), "--espera-max", "3000"], stdout=subprocess.DEVNULL, cwd=RAIZ)
    peers = []
    try:
        aguardar_porta("127.0.0.1", porta_seed, 300)   # a seed calcula os hashes antes de abrir a porta
        inicio = time.time() + 1.0 + 0.15 * n
        for i in range(1, n + 1):
            pasta = os.path.join(RAIZ, "data", f"peer{i}")
            peers.append(subprocess.Popen(
                [PY, os.path.join(SRC, "no_p2p.py"), "--papel", "peer", "--id", f"peer{i}",
                 "--porta", str(porta_livre()), "--tracker", f"127.0.0.1:{porta_seed}",
                 "--pasta", pasta, "--taxa-mbps", str(taxa), "--inicio-em", str(inicio),
                 "--resultado", csv_tmp, "--tamanho-mb", str(mb), "--n", str(n), "--rodada", str(rodada),
                 "--espera-max", "3000"], stdout=subprocess.DEVNULL, cwd=RAIZ))
        limite = 120 + 3 * mb * n / max(taxa, 0.1)
        for p in peers:
            p.wait(timeout=limite)
    finally:
        encerrar(peers + [seed])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tamanhos", type=int, nargs="+", default=[5, 50, 500], help="tamanhos do arquivo em MB")
    ap.add_argument("--clientes", type=int, nargs="+", default=[1, 2, 5, 10], help="quantidades de nós clientes")
    ap.add_argument("--arquiteturas", nargs="+", default=TODAS, choices=TODAS)
    ap.add_argument("--rodadas", type=int, default=1, help="repetições de cada experimento")
    ap.add_argument("--taxa-mbps", type=float, default=50, help="upload de cada nó (servidor/seed/peer), MB/s")
    ap.add_argument("--pool-n", type=int, default=4, help="N do servidor com pool de threads")
    ap.add_argument("--saida", default=os.path.join(RAIZ, "experimentos"))
    ap.add_argument("--rapido", action="store_true", help="atalho: 5 e 50 MB, 1/2/4 clientes")
    a = ap.parse_args()
    if a.rapido:
        a.tamanhos, a.clientes = [5, 50], [1, 2, 4]

    os.makedirs(a.saida, exist_ok=True)
    for mb in a.tamanhos:
        garantir_arquivo(SEED_DIR, mb)

    brutos = os.path.join(a.saida, "resultados_brutos.csv")
    if not os.path.exists(brutos):
        with open(brutos, "w") as f:
            f.write(CABECALHO_CSV + "\n")

    total = len(a.tamanhos) * len(a.clientes) * len(a.arquiteturas) * a.rodadas
    feito = 0
    tmpdir = tempfile.mkdtemp(prefix="p2p_")
    try:
        for mb in a.tamanhos:
            for n in a.clientes:
                for arq in a.arquiteturas:
                    for rodada in range(1, a.rodadas + 1):
                        feito += 1
                        csv_tmp = os.path.join(tmpdir, "r.csv")
                        if os.path.exists(csv_tmp):
                            os.remove(csv_tmp)
                        print(f"[{feito}/{total}] {arq:14s} {mb:4d} MB  {n:2d} clientes  rodada {rodada}",
                              end="  ", flush=True)
                        t0 = time.time()
                        if arq == "p2p":
                            rodar_p2p(mb, n, rodada, a.taxa_mbps, csv_tmp)
                        else:
                            rodar_cs(arq, mb, n, rodada, a.taxa_mbps, a.pool_n, csv_tmp)
                        linhas = open(csv_tmp).read().splitlines() if os.path.exists(csv_tmp) else []
                        if len(linhas) != n:
                            print(f"AVISO: só {len(linhas)}/{n} clientes registraram tempo", end="  ")
                        with open(brutos, "a") as f:
                            f.write("".join(l + "\n" for l in linhas))
                        ts = [float(l.split(",")[-1]) for l in linhas]
                        if ts:
                            print(f"min {min(ts):7.2f}s  med {sum(ts) / len(ts):7.2f}s  max {max(ts):7.2f}s  "
                                  f"(rodou {time.time() - t0:.0f}s)")
                        else:
                            print("sem resultados")
                        time.sleep(0.5)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        for i in range(1, max(a.clientes) + 1):          # apaga restos de blocos dos peers
            pasta = os.path.join(RAIZ, "data", f"peer{i}")
            if os.path.isdir(pasta):
                for f in os.listdir(pasta):
                    if f.endswith(".part"):
                        os.remove(os.path.join(pasta, f))

    print("\n=== RESUMO (mínimo / médio / máximo) ===")
    print(agregar.escrever(agregar.resumir(agregar.ler_brutos(brutos)), a.saida))
    print(f"\nArquivos gerados em {a.saida}: resultados_brutos.csv, resumo.csv, resumo.md")


if __name__ == "__main__":
    main()
