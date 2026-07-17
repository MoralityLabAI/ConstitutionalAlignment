#!/bin/bash
# Full generation grid, priority-ordered so the highest-value data lands first
# under the 12h server cap. Resumable (gen_stress skips completed rows), so a
# resubmit continues where it left off. Writes per-(stressor,variant) manifests
# to $SILICO_EXPERIMENT_ARTIFACTS_DIR/generations/full/.
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=09:00:00
set -euo pipefail
cd "$SILICO_EXPERIMENT_DIR"

URL=$(sed 's/URL=//' results/server_url.txt)
POOLDIR="$SILICO_EXPERIMENT_ARTIFACTS_DIR/materials/practice_pools"
OUT="$SILICO_EXPERIMENT_ARTIFACTS_DIR/generations/full"
mkdir -p "$OUT"
CFG=data/gen_config.json
HARM=data/harmful_150.jsonl
BEN=data/benign_50.jsonl
C=96

run() { # stressor variant queries samples limit outfile [extra args...]
  local st=$1 var=$2 q=$3 samp=$4 lim=$5 out=$6; shift 6
  echo "=== gen $st/$var q=$q samples=$samp limit=$lim -> $out ($(date -u +%H:%M:%S)) ==="
  uv run python src/gen_stress.py --url "$URL" --stressor "$st" --variant "$var" \
    --queries "$q" --samples "$samp" ${lim:+--limit $lim} \
    --gen-config "$CFG" --concurrency "$C" --max-tokens 6000 --pool-dir "$POOLDIR" \
    --out "$out" "$@"
}

echo "FULLGEN_START $(date -u +%H:%M:%S)"

# 1) Core: adversarial override (has dynamic range)
run S2 generic  "$HARM" 2 "" "$OUT/S2_generic.jsonl"
run S2 targeted "$HARM" 2 "" "$OUT/S2_targeted.jsonl"      # F0 auto-skipped inside driver
# 2) In-context practice
run S3 practice "$HARM" 2 "" "$OUT/S3_practice.jsonl"
# 3) Persistence (10-turn) — full grid for the persistence-robustness story
run S1 10       "$HARM" 2 "" "$OUT/S1_10.jsonl"
# 4) Over-refusal (benign), 1 sample per cell, all main conditions
run S2 generic  "$BEN"  1 "" "$OUT/benign_S2_generic.jsonl"
run S2 targeted "$BEN"  1 "" "$OUT/benign_S2_targeted.jsonl"
run S3 practice "$BEN"  1 "" "$OUT/benign_S3_practice.jsonl"
run S1 10       "$BEN"  1 "" "$OUT/benign_S1_10.jsonl"
# 5) Persistence 4-turn subset (decay curve second point), 75-prompt subset
run S1 4        "$HARM" 2 75 "$OUT/S1_4.jsonl"

echo "FULLGEN_DONE $(date -u +%H:%M:%S)"
