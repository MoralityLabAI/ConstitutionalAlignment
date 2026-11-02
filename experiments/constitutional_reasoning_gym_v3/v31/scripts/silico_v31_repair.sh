#!/usr/bin/env bash
# Requires an independently approved single-H100 lease; provisions no compute.
set -euo pipefail
START=$(date +%s)
if [[ $# -ne 6 ]]; then
  echo 'Usage: script BASE MODEL_REV LEGACY_GENERATION NEW_RUN_DIR ALL_IN_SECONDS MOTIFS' >&2
  exit 64
fi
BASE=$1; REV=$2; LEGACY=$3; RUN=$4; CAP=$5; MOTIFS=$6
[[ "$CAP" =~ ^[0-9]+$ && "$MOTIFS" =~ ^[0-9]+$ ]] || exit 64
(( CAP >= 120 && CAP <= 86400 && MOTIFS >= 1 )) || exit 64
[[ -d "$BASE" && -d "$LEGACY" ]] || { echo 'Retained model or legacy generation directory is missing' >&2; exit 66; }
[[ -f "$LEGACY/manifest.json" && -f "$LEGACY/contract.json" ]] || exit 66
[[ ! -e "$RUN" ]] || { echo 'Use a fresh durable output directory' >&2; exit 73; }
command -v timeout >/dev/null || { echo 'GNU timeout required' >&2; exit 69; }
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
cd "$ROOT"
export BASE REV LEGACY RUN CAP MOTIFS
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
mkdir -p "$RUN"
# The provider must also enforce its allocation cap, which includes provisioning.
remaining=$((CAP - 10 - ($(date +%s) - START)))
(( remaining > 0 )) || { echo 'Cap expired during preflight' >&2; exit 124; }
set +e
timeout --signal=TERM --kill-after=10s "${remaining}s" bash -c '
  set -euo pipefail
  python -m unittest discover -s experiments/constitutional_reasoning_gym_v3/v31/tests -q
  python -m experiments.constitutional_reasoning_gym_v3.v31 generate \
    --backend local --approved --model "$BASE" --revision "$REV" \
    --legacy "$LEGACY" --out "$RUN/generation" --groups "$MOTIFS" \
    --batch-size 4 --max-repairs 2 --max-seconds "$((CAP*3/4))" \
    --max-output-tokens 500000
  python -m experiments.constitutional_reasoning_gym_v3.v31 export \
    --source "$RUN/generation" --out "$RUN/sft"
  python -m experiments.constitutional_reasoning_gym_v3 hub-bundle \
    --source "$RUN/sft" --generation "$RUN/generation" --out "$RUN/hub"
  python -m experiments.constitutional_reasoning_gym_v3.v31 compare \
    --old "$LEGACY" --new "$RUN/generation" --out "$RUN/comparison.json"
' > >(tee "$RUN/worker.log") 2>&1
STATUS=$?
set -e
printf '{"process_exit_code":%s,"maximum_seconds":%s,"gpu_provisioned_by_script":false,"original_archive_writable":false}\n' \
  "$STATUS" "$CAP" > "$RUN/process_receipt.json"
exit "$STATUS"
