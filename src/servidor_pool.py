import argparse
from concurrent.futures import ThreadPoolExecutor
from utils import LimitadorTaxa, MB, atender_cliente, criar_socket_servidor, env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=env("PORTA", 5000, int))
    ap.add_argument("--pasta", default=env("PASTA", "data/seed"))
    ap.add_argument("--taxa-mbps", type=float, default=env("TAXA_MBPS", 50, float))
    ap.add_argument("-N", "--n", type=int, default=env("POOL_N", 4, int),
                    help="máximo de clientes atendidos simultaneamente")
    a = ap.parse_args()

    limitador = LimitadorTaxa(int(a.taxa_mbps * MB))
    srv = criar_socket_servidor(a.porta)
    print(f"[servidor pool] porta {a.porta}, N={a.n}, taxa {a.taxa_mbps} MB/s", flush=True)
    with ThreadPoolExecutor(max_workers=a.n) as pool:
        while True:
            conn, _ = srv.accept()
            pool.submit(atender_cliente, conn, a.pasta, limitador)


if __name__ == "__main__":
    main()
