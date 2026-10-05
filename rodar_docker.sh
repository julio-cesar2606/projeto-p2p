# Roda TODOS os experimentos com Docker Compose (4 arquiteturas x tamanhos x nº de clientes).
# Resultado: ./resultados/resultados_brutos.csv  
set -euo pipefail
cd "$(dirname "$0")"

TAMANHOS=${TAMANHOS:-"5 50"}
CLIENTES=${CLIENTES:-"1 2 5"}
RODADAS=${RODADAS:-1}
export TAXA_MBPS=${TAXA_MBPS:-50}
export POOL_N=${POOL_N:-4}

mkdir -p resultados data/seed
docker compose build
docker compose run --rm gerar python src/utils.py gerar-padrao --pasta /data/seed --tamanhos $TAMANHOS

derrubar() { docker compose --profile "*" down -t 2 --remove-orphans >/dev/null 2>&1 || true; }
trap derrubar EXIT

for T in $TAMANHOS; do
  for N in $CLIENTES; do
    for R in $(seq 1 "$RODADAS"); do
      export TAMANHO_MB=$T N_CLIENTES=$N RODADA=$R

      for MODO in sequencial threads pool; do
        echo ">>> cs_$MODO | ${T}MB | $N clientes | rodada $R"
        export ARQ=cs_$MODO
        derrubar
        docker compose up -d "servidor-$MODO"
        sleep 3
        export INICIO_EM=$(( $(date +%s) + 4 + N ))
        docker compose up --no-deps --scale cliente="$N" cliente 2>&1 | grep -E "MB em|ERRO" || true
        derrubar
      done

      echo ">>> p2p | ${T}MB | $N peers | rodada $R"
      derrubar
      docker compose up -d seed
      sleep 3
      export INICIO_EM=$(( $(date +%s) + 4 + N ))
      docker compose up --no-deps --scale peer="$N" peer 2>&1 | grep -E "MB em|ERRO" || true
      derrubar
    done
  done
done

echo
echo "Tempos brutos em resultados/resultados_brutos.csv"
python3 experimentos/agregar.py resultados/resultados_brutos.csv || true
