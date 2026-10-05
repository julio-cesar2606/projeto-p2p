import argparse
from utils import LimitadorTaxa, MB, atender_cliente, criar_socket_servidor, env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=env("PORTA", 5000, int))
    ap.add_argument("--pasta", default=env("PASTA", "data/seed"))
    ap.add_argument("--taxa-mbps", type=float, default=env("TAXA_MBPS", 50, float),
                    help="limite de upload do servidor em MB/s (0 = sem limite)")
    a = ap.parse_args()

    limitador = LimitadorTaxa(int(a.taxa_mbps * MB))
    srv = criar_socket_servidor(a.porta)
    print(f"[servidor sequencial] porta {a.porta}, taxa {a.taxa_mbps} MB/s", flush=True)
    while True:
        conn, _ = srv.accept()
        atender_cliente(conn, a.pasta, limitador)   # bloqueia o cliente terminar


if __name__ == "__main__":
    main()
