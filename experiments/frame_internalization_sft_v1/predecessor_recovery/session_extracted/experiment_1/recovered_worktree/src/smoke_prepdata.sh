#!/bin/bash
#SBATCH --partition=a100
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:20:00
set -euo pipefail
cd ~/.silico/libraries/goodfire-core
uv run python - <<'PY'
from datasets import load_dataset
h = load_dataset("LLM-LAT/harmful-dataset", split="train")
print("harmful cols:", h.column_names, "n:", len(h))
print("harmful[0].prompt:", repr(h[0]["prompt"][:120]))
a = load_dataset("tatsu-lab/alpaca", split="train")
print("alpaca cols:", a.column_names, "n:", len(a))
noinput = [r for r in a.select(range(2000)) if not r["input"].strip()]
print("no-input in first 2000:", len(noinput))
print("SMOKE_PREPDATA_OK")
PY
