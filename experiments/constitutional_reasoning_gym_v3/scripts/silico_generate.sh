#!/usr/bin/env bash
# Run only inside an explicitly approved lease; this script does not provision one.
set -euo pipefail
if [[ $# -ne 5 ]]; then echo "Usage: $0 BASE REVISION NEW_DURABLE_DIR MAX_SECONDS MOTIFS" >&2; exit 64; fi
BASE=$1; REV=$2; RUN=$3; CAP=$4; MOTIFS=$5
[[ "$CAP" =~ ^[0-9]+$ && "$MOTIFS" =~ ^[0-9]+$ ]] || exit 64
(( CAP >= 120 && CAP <= 86400 && MOTIFS >= 1 )) || exit 64
[[ -d "$BASE" ]] || { echo 'Retained checkpoint missing' >&2; exit 66; }
[[ ! -e "$RUN" ]] || { echo 'Use a new run directory; resume via the exact saved generation command' >&2; exit 73; }
command -v timeout >/dev/null || { echo 'GNU timeout required' >&2; exit 69; }
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$ROOT"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
mkdir -p "$RUN"
# Outer timeout begins before the CPU check or model load. Provider also caps the allocation.
export BASE REV RUN MOTIFS CAP
set +e
timeout --signal=TERM --kill-after=10s "$((CAP-10))s" bash -c '
  set -euo pipefail
  python -m unittest discover -s experiments/constitutional_reasoning_gym_v3/tests -q
  python -m experiments.constitutional_reasoning_gym_v3 generate \
    --backend local --approved --model "$BASE" --revision "$REV" \
    --out "$RUN/generation" --groups "$MOTIFS" --rounds 2 --batch-size 4 \
    --max-seconds "$((CAP*3/4))" --max-output-tokens 1000000
  python -m experiments.constitutional_reasoning_gym_v3 export --source "$RUN/generation" --out "$RUN/sft"
  python -m experiments.constitutional_reasoning_gym_v3 hub-bundle \
    --source "$RUN/sft" --generation "$RUN/generation" --out "$RUN/hub"
' > >(tee "$RUN/worker.log") 2>&1
STATUS=$?
set -e
printf '{"process_exit_code":%s,"maximum_seconds":%s,"gpu_provisioned_by_script":false}\n' "$STATUS" "$CAP" > "$RUN/process_receipt.json"
exit "$STATUS"
