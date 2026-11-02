#!/usr/bin/env bash
# Invoke inside one approved, provider-capped H100 allocation after CPU preflight.
set -euo pipefail
if [[ $# -ne 5 ]]; then
  echo "Usage: $0 BASE REVISION PREPARED_DIR PREFLIGHT_DIR NEW_DURABLE_RUN" >&2; exit 64
fi
BASE=$1; REV=$2; PREP=$3; PREFLIGHT=$4; RUN=$5
[[ -d "$BASE" && -f "$PREP/corpus/manifest.json" && -f "$PREFLIGHT/tokenizer_preflight.json" ]] || exit 66
[[ ! -e "$RUN" ]] || { echo 'Fresh run directory required' >&2; exit 73; }
command -v timeout >/dev/null || { echo 'GNU timeout required' >&2; exit 69; }
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$ROOT"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Provider limit is 1200 seconds from allocation start. This independent watchdog
# covers loading, both adapters, checkpoints and inference from process start.
set +e
timeout --signal=TERM --kill-after=10s 1190s \
  python -m experiments.ontological_constitution_v4_training pilot \
    --approved --base "$BASE" --revision "$REV" --corpus "$PREP/corpus" \
    --preflight "$PREFLIGHT" --out "$RUN" --max-seconds 1160
STATUS=$?
set -e
if [[ -d "$RUN" ]]; then
  printf '{"process_exit_code":%s,"external_seconds_cap":1200,"automatic_retry":false}\n' "$STATUS" > "$RUN/process_receipt.json"
fi
exit "$STATUS"
