#!/usr/bin/env bash
# Study 3 after F06, on the same pod: render -> curriculum gates -> F18 smoke ->
# six-arm QLoRA training -> evaluation generation (vLLM + LoRA) -> analysis hook.
# Amendment: frame_internalization_evaluation_vllm_v1. Run as root:
#
#   PRICE_PER_HOUR=<usd> bash scripts/stage_and_run_six_arm_after_f06.sh \
#       REPO_ROOT SOURCE_COMMIT WORK_ROOT
#
# Environment overrides: F06_DIR (default /root/f06_vllm_c/generation), TOTAL_USD (60),
# MODEL_DIR, VLLM_VENV. Detaches itself; relaunching resumes an interrupted stage and
# never retries a failed gate. Stop cleanly with:  touch WORK_ROOT/STOP
# Judge scoring needs API credentials and happens off the pod; the run ends at
# awaiting_judging. Never contacts Prime; prints no secrets.
set -Eeuo pipefail
set +x

if [[ $# -ne 3 ]]; then
  echo "usage: PRICE_PER_HOUR=<usd> $0 REPO_ROOT SOURCE_COMMIT WORK_ROOT" >&2
  exit 64
fi
: "${PRICE_PER_HOUR:?PRICE_PER_HOUR (USD per hour) must be set}"
[[ "$PRICE_PER_HOUR" =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "bad PRICE_PER_HOUR" >&2; exit 64; }

repo_root="$(realpath "$1")"
source_commit="$2"
work_root="$(realpath -m "$3")"
self="$(realpath "$0")"
launch_log="${work_root}.launch.log"

if [[ -z "${JINN_SIXARM_DETACHED:-}" ]]; then
  mkdir -p "$(dirname "$work_root")"
  JINN_SIXARM_DETACHED=1 setsid nohup bash "$self" "$@" >>"$launch_log" 2>&1 < /dev/null &
  echo "detached pid $! ; log $launch_log ; heartbeat $work_root/heartbeat.json ; state $work_root/pipeline_state.json"
  exit 0
fi

f06_dir="${F06_DIR:-/root/f06_vllm_c/generation}"
total_usd="${TOTAL_USD:-60}"
model_dir="${MODEL_DIR:-/opt/jinn-f06-vllm/model/Qwen3-1.7B-70d244c}"
vllm_venv="${VLLM_VENV:-/opt/jinn-f06-vllm/venv}"
train_root="/opt/jinn-six-arm"
train_venv="$train_root/venv"
pkg="experiments/frame_internalization_sft_v1"
requirements="$repo_root/$pkg/primelab_f04/requirements_f04.txt"
expected_lock="$repo_root/$pkg/primelab_f04/environment_lock_20260723.txt"

log() { echo "$(date -u +%FT%TZ) $*"; }

# The one recorded exclusion (scenario d03508, amendment frame_internalization_failed_scenario_v1).
# The pipeline and renderer verify this file by SHA-256 and accept no other missing transcript.
exclusion_amendment="$repo_root/$pkg/protocol_amendment_failed_scenario_v1.json"
exclusion_sha256=76034cc8c69128f85181e710dd3e2ce7ba8fcfe6892c9611201b522c6c46a2c2
# Dose matching (amendment frame_internalization_dose_matching_v1): the F3 versus F3-concrete token
# parity gate is recorded, not enforced, and the F3-concrete arm trains the F3 arm's step count.
dose_amendment="$repo_root/$pkg/protocol_amendment_dose_matching_v1.json"
dose_sha256=d6ccfa965b2ca0d2247f499e85dfee1420a2caf69aa4393c8abde01f2a301dc2
# Reduced F18 smoke (infrastructure amendment frame_internalization_smoke_reduction_v1).
smoke_amendment="$repo_root/$pkg/protocol_amendment_smoke_reduction_v1.json"
smoke_sha256=8baff4a52ec4b4e2dde1bbd94c67886c150d2230f83c8ff443956eb66ef7f2cf
[[ "$(git -C "$repo_root" cat-file blob "$source_commit:$pkg/protocol_amendment_smoke_reduction_v1.json" | sha256sum | cut -d' ' -f1)" == "$smoke_sha256" ]] \
  || { log "smoke-reduction amendment hash mismatch"; exit 65; }
[[ "$(git -C "$repo_root" cat-file blob "$source_commit:$pkg/protocol_amendment_dose_matching_v1.json" | sha256sum | cut -d' ' -f1)" == "$dose_sha256" ]] \
  || { log "dose-matching amendment hash mismatch"; exit 65; }
[[ "$(git -C "$repo_root" cat-file blob "$source_commit:$pkg/protocol_amendment_failed_scenario_v1.json" | sha256sum | cut -d' ' -f1)" == "$exclusion_sha256" ]]   || { log "exclusion amendment hash mismatch"; exit 65; }

[[ "$(id -u)" -eq 0 ]]
[[ "$(git -C "$repo_root" rev-parse HEAD)" == "$source_commit" ]]
[[ -z "$(git -C "$repo_root" status --porcelain --untracked-files=no)" ]]
[[ -d "$f06_dir" && -d "$model_dir" && -x "$vllm_venv/bin/python" ]] || { log "F06 outputs, model, or vLLM venv missing"; exit 66; }
command -v nvidia-smi >/dev/null
mapfile -t gpu_rows < <(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits)
[[ "${#gpu_rows[@]}" -eq 1 ]]
[[ "${gpu_rows[0]##*, }" -ge "${MIN_GPU_MIB:-24000}" ]]
log "gpu=${gpu_rows[0]%%,*} price_per_hour=$PRICE_PER_HOUR total_usd_cap=$total_usd"
# Nothing else may hold the GPU (the F06 generator must have exited).
[[ -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits | sed '/^[[:space:]]*$/d')" ]]

mkdir -p "$work_root"
if [[ ! -x "$train_venv/bin/python" ]]; then
  mkdir -p "$train_root"
  if ! python3 -m venv "$train_venv"; then
    apt-get update -q
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3.10-venv
    python3 -m venv "$train_venv"
  fi
  "$train_venv/bin/python" -m pip install --disable-pip-version-check -r "$requirements"
  "$train_venv/bin/python" -m pip install --disable-pip-version-check --no-deps \
    --extra-index-url https://download.pytorch.org/whl/cu121 -r "$expected_lock"
fi
LC_ALL=C "$train_venv/bin/python" -m pip freeze --all | LC_ALL=C sort >"$work_root/environment_lock_train.txt"
cmp --silent "$expected_lock" "$work_root/environment_lock_train.txt"

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

set +e
"$train_venv/bin/python" "$repo_root/scripts/run_six_arm_pipeline.py" \
  --repo-root "$repo_root" --f06-dir "$f06_dir" --work "$work_root" --model-dir "$model_dir" \
  --train-python "$train_venv/bin/python" --vllm-python "$vllm_venv/bin/python" \
  --price-per-hour "$PRICE_PER_HOUR" --total-usd "$total_usd"   --exclusion-amendment "$exclusion_amendment" \
  --dose-matching-amendment "$dose_amendment" \
  --smoke-reduction-amendment "$smoke_amendment" \
  >>"$work_root/pipeline.stdout.log" 2>>"$work_root/pipeline.stderr.log"
rc=$?
set -e
apps="$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits | sed '/^[[:space:]]*$/d' | wc -l)"
python3 - "$work_root" "$source_commit" "$rc" "$apps" "$PRICE_PER_HOUR" <<'PY'
import json, sys
from datetime import datetime, timezone
root, commit, rc, apps, price = sys.argv[1:]
state = json.load(open(f"{root}/pipeline_state.json"))
out = {"schema_version": "frame_internalization_six_arm_wrapper.v1", "source_commit": commit,
       "pipeline_exit_code": int(rc), "stages": {k: v["status"] for k, v in state["stages"].items()},
       "cumulative_hours": state["cumulative_seconds"] / 3600, "price_per_hour_usd": float(price),
       "cumulative_usd_at_price": state["cumulative_seconds"] / 3600 * float(price),
       "compute_apps_after": int(apps), "cleanup_passed": int(apps) == 0,
       "finished_at_utc": datetime.now(timezone.utc).isoformat()}
json.dump(out, open(f"{root}/wrapper_receipt.json", "w"), indent=2, sort_keys=True)
print(json.dumps(out, sort_keys=True))
PY
log "pipeline exit $rc; receipt $work_root/wrapper_receipt.json"
exit "$rc"
