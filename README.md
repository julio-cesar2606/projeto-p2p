# Atividade 01 – Unidade 2: Cliente-Servidor vs P2P (Sistemas Distribuídos – UFS)

Avalia o tempo de transferência de um arquivo em 4 arquiteturas:

Arquitetura | Programa 
- C/S – 1 cliente por vez | `src/servidor_sequencial.py` 
- C/S – todos de uma vez (1 thread por cliente) | `src/servidor_threads.py` 
- C/S – no máximo N por vez (pool de threads) | `src/servidor_pool.py` (`-N`) 
- P2P (semente + peers trocando blocos) | `src/no_p2p.py` 

`src/cliente.py` baixa o arquivo, mede o tempo e descarta os dados. `src/utils.py` tem o limitador de banda,
helpers de socket, hash/geração de arquivos.

## Como o P2P funciona (resumo)
- O arquivo é dividido em blocos de 256 KB, cada um com hash SHA-256.
- A seed tem o arquivo completo e também atua como tracker. Os dados trafegam entre os peers.
- Cada peer é cliente e servidor ao mesmo tempo: baixa blocos da seed e dos outros peers (prefere blocos que
  outros peers já têm, o mais raro primeiro) e entrega os blocos que já tem. `data/peer1/`, `data/peer2/`... são
  onde cada peer guarda os blocos.

## Por que existe um limite de banda (`--taxa-mbps`)?
Numa máquina só, a rede é quase infinita e as 4 arquiteturas dariam o mesmo tempo. Por isso cada nó
(servidor, seed e cada peer) tem o próprio limite de upload (padrão 50 MB/s), simulando o link de cada máquina.
No C/S o servidor divide o seu link entre todos os clientes, no P2P cada peer soma o seu upload ao sistema.

## Teste rápido (sem Docker) – requer só Python 3.9+
python3 experimentos/rodar.py --rapido          # 5 e 50 MB, 1/2/4 clientes
Experimento completo (5/50/500 MB × 1,2,5,10 clientes) – leva um bom tempo e usa disco (500 MB × peers):
python3 experimentos/rodar.py
python3 experimentos/rodar.py --tamanhos 50 --clientes 1 4 8 --rodadas 3 --taxa-mbps 20
python3 experimentos/rodar.py --arquiteturas cs_threads p2p

Saída em `experimentos/`: `resultados_brutos.csv` (1 linha por cliente), `resumo.csv` e `resumo.md`
(mínimo/médio/máximo por experimento). Gráficos (opcional): `pip install matplotlib` e
`python3 experimentos/graficos.py experimentos/resultados_brutos.csv`.

## Com Docker (cada cliente/peer é um container)
```bash
./rodar_docker.sh                                        # 5 e 50 MB, 1/2/5 clientes
TAMANHOS="5 50 500" CLIENTES="1 2 5 10" RODADAS=3 TAXA_MBPS=20 ./rodar_docker.sh
```
Os tempos caem em `resultados/resultados_brutos.csv`
`python3 experimentos/agregar.py resultados/resultados_brutos.csv`.

## resultados (o que esperar)
- Sequencial: o 1º cliente termina rápido, o último espera todos (mín baixo, máx alto).
- Threads: todos terminam juntos, perto do máximo do sequencial (a banda do servidor é dividida).
- Pool (N): clientes terminam em "ondas" de N.
- P2P: o tempo cresce bem menos com o nº de clientes, pois os peers também enviam.

