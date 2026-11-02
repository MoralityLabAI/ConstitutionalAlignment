#!/usr/bin/env bash
# Use inside the one owner-approved H100 lease; this script provisions nothing.
set -euo pipefail
if [[ $# -ne 5 ]]; then echo 'Usage: BASE REVISION CORPUS PREFLIGHT_JSON NEW_RUN_DIR' >&2; exit 64; fi
BASE=$1; REV=$2; CORPUS=$3; PREFLIGHT=$4; RUN=$5
[[ -d "$BASE" && -d "$CORPUS" && -f "$PREFLIGHT" ]] || exit 66
[[ ! -e "$RUN" ]] || { echo 'Fresh durable run directory required' >&2; exit 73; }
command -v timeout >/dev/null || exit 69
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$ROOT"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
mkdir -p "$RUN"
REVISION=$(git rev-parse HEAD 2>/dev/null || printf 'SOURCE_HASHES_IN_RECEIPT')
START=$(date +%s)
set +e
timeout --signal=TERM --kill-after=10s 1190s \
 python -m experiments.ontological_constitution_v4_training pilot \
 --approved --base "$BASE" --revision "$REV" --corpus "$CORPUS" \
 --preflight "$PREFLIGHT" --out "$RUN/pilot" --max-seconds 1080 \
 --eval-reserve 240 --motifs 4 --source-revision "$REVISION" \
 > >(tee "$RUN/worker.log") 2>&1
STATUS=$?
set -e
printf '{"exit_code":%s,"elapsed_process_seconds":%s,"hard_limit_seconds":1200,"provider_billed_minutes":null}\n' \
 "$STATUS" "$(($(date +%s)-START))" > "$RUN/process_receipt.json"
exit "$STATUS"
