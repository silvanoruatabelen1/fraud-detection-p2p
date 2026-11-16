#!/usr/bin/env bash
# Descarga PaySim (Lopez-Rojas, Elmir y Axelsson, 2016) desde Kaggle y lo deja en data/raw/p2p.csv.
# Requiere la CLI de Kaggle (`uv tool install kaggle`) y un token en ~/.kaggle/kaggle.json.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw
if [[ -f data/raw/p2p.csv ]]; then
  echo "data/raw/p2p.csv ya existe"; exit 0
fi
kaggle datasets download -d ealaxi/paysim1 -p data/raw --unzip
mv data/raw/PS_*.csv data/raw/p2p.csv
echo "Listo: data/raw/p2p.csv ($(du -h data/raw/p2p.csv | cut -f1))"
