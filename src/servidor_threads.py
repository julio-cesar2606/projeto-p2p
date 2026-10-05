import argparse
import threading

from utils import LimitadorTaxa, MB, atender_cliente, criar_socket_servidor, env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=env("PORTA", 5000, int))
    ap.add_argument("--pasta", default=env("PASTA", "data/seed"))
    ap.add_argument("--taxa-mbps", type=float, default=env("TAXA_MBPS", 50, float))
    a = ap.parse_args()

    limitador = LimitadorTaxa(int(a.taxa_mbps * MB))   # banda dividida entre as threads
    srv = criar_socket_servidor(a.porta)
    print(f"[servidor threads] porta {a.porta}, taxa {a.taxa_mbps} MB/s", flush=True)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=atender_cliente, args=(conn, a.pasta, limitador), daemon=True).start()


if __name__ == "__main__":
    main()
