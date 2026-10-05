import csv
import os
import statistics
import sys
from collections import defaultdict

ORDEM = ["cs_sequencial", "cs_threads", "cs_pool", "p2p"]
NOMES = {"cs_sequencial": "C/S sequencial (1 por vez)", "cs_threads": "C/S threads (todos de uma vez)",
         "cs_pool": "C/S pool (N por vez)", "p2p": "P2P"}


def ler_brutos(caminho):
    linhas = []
    with open(caminho, newline="") as f:
        for r in csv.reader(f):
            if not r or r[0] == "arquitetura":
                continue
            arq, tam, n, rodada, cli, t = r[:6]
            linhas.append((arq, int(tam), int(n), int(rodada), cli, float(t)))
    return linhas


def resumir(linhas):
    grupos = defaultdict(list)
    for arq, tam, n, _rod, _cli, t in linhas:
        grupos[(arq, tam, n)].append(t)

    def chave(k):
        arq, tam, n = k
        return (tam, n, ORDEM.index(arq) if arq in ORDEM else 99)

    saida = []
    for k in sorted(grupos, key=chave):
        ts = grupos[k]
        saida.append({"arquitetura": k[0], "tamanho_mb": k[1], "n_clientes": k[2], "amostras": len(ts),"min": min(ts), "medio": statistics.mean(ts), "max": max(ts),"desvio": statistics.pstdev(ts) if len(ts) > 1 else 0.0})
    return saida


def escrever(resumo, pasta):
    with open(os.path.join(pasta, "resumo.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arquitetura", "tamanho_mb", "n_clientes", "amostras", "min_s", "medio_s", "max_s", "desvio_s"])
        for r in resumo:
            w.writerow([r["arquitetura"], r["tamanho_mb"], r["n_clientes"], r["amostras"],f'{r["min"]:.3f}', f'{r["medio"]:.3f}', f'{r["max"]:.3f}', f'{r["desvio"]:.3f}'])
    md = ["| Arquitetura | Arquivo (MB) | Clientes | Mínimo (s) | Médio (s) | Máximo (s) |","|---|---|---|---|---|---|"]
    for r in resumo:
        md.append(f'| {NOMES.get(r["arquitetura"], r["arquitetura"])} | {r["tamanho_mb"]} | {r["n_clientes"]} | 'f'{r["min"]:.2f} | {r["medio"]:.2f} | {r["max"]:.2f} |')
    with open(os.path.join(pasta, "resumo.md"), "w") as f:
        f.write("\n".join(md) + "\n")
    return "\n".join(md)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    caminho = sys.argv[1]
    resumo = resumir(ler_brutos(caminho))
    print(escrever(resumo, os.path.dirname(os.path.abspath(caminho))))


if __name__ == "__main__":
    main()
