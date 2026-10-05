import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt 

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agregar 

CORES = {"cs_sequencial": "#d62728", "cs_threads": "#ff7f0e", "cs_pool": "#2ca02c", "p2p": "#1f77b4"}
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    caminho = sys.argv[1]
    pasta = os.path.join(os.path.dirname(os.path.abspath(caminho)), "graficos")
    os.makedirs(pasta, exist_ok=True)
    resumo = agregar.resumir(agregar.ler_brutos(caminho))
    for tam in sorted({r["tamanho_mb"] for r in resumo}):
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for arq in agregar.ORDEM:
            pts = sorted((r for r in resumo if r["tamanho_mb"] == tam and r["arquitetura"] == arq),
                         key=lambda r: r["n_clientes"])
            if not pts:
                continue
            x = [r["n_clientes"] for r in pts]
            ax.plot(x, [r["medio"] for r in pts], marker="o", color=CORES[arq], label=agregar.NOMES[arq])
            ax.fill_between(x, [r["min"] for r in pts], [r["max"] for r in pts], color=CORES[arq], alpha=0.12)
        ax.set_title(f"Arquivo de {tam} MB — tempo de download (linha = média, faixa = mín–máx)")
        ax.set_xlabel("Número de clientes")
        ax.set_ylabel("Tempo (s)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        saida = os.path.join(pasta, f"tempo_{tam}MB.png")
        fig.savefig(saida, dpi=150)
        plt.close(fig)
        print("gerado:", saida)


if __name__ == "__main__":
    main()
