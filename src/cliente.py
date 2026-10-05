import argparse
import socket
import struct
import sys
import time
from utils import (aguardar_porta, conectar, descartar, env, esperar_ate, receber_exato,
                   registrar_resultado)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=env("HOST", "127.0.0.1"))
    ap.add_argument("--porta", type=int, default=env("PORTA", 5000, int))
    ap.add_argument("--nome", default=env("NOME", "arquivo_5MB.bin"), help="arquivo a baixar")
    ap.add_argument("--id", default=env("ID", socket.gethostname()))
    ap.add_argument("--inicio-em", type=float, default=env("INICIO_EM", 0, float),
                    help="epoch (s) da largada sincronizada")
    ap.add_argument("--resultado", default=env("RESULTADO", ""), help="CSV onde gravar o tempo")
    ap.add_argument("--arq", default=env("ARQ", "cs"))
    ap.add_argument("--tamanho-mb", type=int, default=env("TAMANHO_MB", 0, int))
    ap.add_argument("--n", type=int, default=env("N_CLIENTES", 1, int))
    ap.add_argument("--rodada", type=int, default=env("RODADA", 1, int))
    a = ap.parse_args()

    aguardar_porta(a.host, a.porta)      # espera o servidor
    esperar_ate(a.inicio_em)             # largada sincronizada entre os clientes

    t0 = time.perf_counter()
    s = conectar(a.host, a.porta)
    s.sendall(f"GET {a.nome}\n".encode())
    (tamanho,) = struct.unpack(">Q", receber_exato(s, 8))
    if tamanho == 0:
        print(f"[{a.id}] ERRO: servidor não encontrou {a.nome}", file=sys.stderr)
        sys.exit(1)
    descartar(s, tamanho)
    s.close()
    dt = time.perf_counter() - t0

    print(f"[{a.id}] {tamanho / 1024 / 1024:.0f} MB em {dt:.2f}s", flush=True)
    registrar_resultado(a.resultado, a.arq, a.tamanho_mb, a.n, a.rodada, a.id, dt)


if __name__ == "__main__":
    main()
