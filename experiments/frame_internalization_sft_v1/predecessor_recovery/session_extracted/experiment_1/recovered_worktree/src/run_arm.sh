#!/bin/bash
#SBATCH --partition=a100
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=04:00:00
set -euo pipefail
# Required env: URL, SYSTEM, FRAME_LABEL, OUT, QUERIES
# Optional: SAMPLES(3) TIERS("free paid") THINK(1) TEMP TOPP CONC(48) MAXTOK(6000) PHASE
: "${SAMPLES:=3}" "${TIERS:=free paid}" "${THINK:=1}" "${TEMP:=0.6}" "${TOPP:=0.95}"
: "${CONC:=48}" "${MAXTOK:=6000}" "${PHASE:=generate}"
cd ~/.silico/libraries/goodfire-core
THINKFLAG=""; [ "$THINK" = "1" ] && THINKFLAG="--think-mode"
uv run python "$SILICO_EXPERIMENT_DIR/src/gen_driver.py" \
  --url "$URL" --model-name intellect-3 \
  --system "$SYSTEM" --frame-label "$FRAME_LABEL" $THINKFLAG \
  --tiers $TIERS --queries "$QUERIES" \
  --samples "$SAMPLES" --concurrency "$CONC" --max-tokens "$MAXTOK" \
  --temperature "$TEMP" --top-p "$TOPP" \
  --out "$OUT" --phase "$PHASE"
