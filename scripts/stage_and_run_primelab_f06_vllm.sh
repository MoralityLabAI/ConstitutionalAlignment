#!/usr/bin/env bash
# F06 curriculum generation with vLLM (bf16) under amendment
# frame_internalization_generation_vllm_v1. Run as root on the pod:
#
#   PRICE_PER_HOUR=<usd> bash scripts/stage_and_run_primelab_f06_vllm.sh \
#       REPO_ROOT SOURCE_COMMIT OUTPUT_ROOT
#
# Stages: install pinned vLLM -> fetch pinned model revision from the public Hub ->
# 32-transcript equivalence check against the aborted NF4 run (fail = stop) ->
# full 22,400-transcript generation with heartbeat and a 15-minute throughput gate.
# Detaches itself (setsid + nohup) and returns at once. Relaunching with the same
# arguments resumes. Stop cleanly with:  touch OUTPUT_ROOT/STOP
# Caps: 30 h cumulative and US$80 at PRICE_PER_HOUR. Never contacts Prime; no secrets.
set -Eeuo pipefail
set +x

if [[ $# -ne 3 ]]; then
  echo "usage: PRICE_PER_HOUR=<usd> $0 REPO_ROOT SOURCE_COMMIT OUTPUT_ROOT" >&2
  exit 64
fi
: "${PRICE_PER_HOUR:?PRICE_PER_HOUR (USD per hour) must be set}"
[[ "$PRICE_PER_HOUR" =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "bad PRICE_PER_HOUR" >&2; exit 64; }

repo_root="$(realpath "$1")"
source_commit="$2"
output_root="$(realpath -m "$3")"
self="$(realpath "$0")"
launch_log="${output_root}.launch.log"

if [[ -z "${JINN_F06_DETACHED:-}" ]]; then
  mkdir -p "$(dirname "$output_root")"
  JINN_F06_DETACHED=1 setsid nohup bash "$self" "$@" >>"$launch_log" 2>&1 < /dev/null &
  echo "detached pid $! ; log $launch_log ; heartbeat $output_root/heartbeat.json"
  exit 0
fi

wrapper_start="$(date +%s)"
runtime_root="/opt/jinn-f06-vllm"
venv_dir="$runtime_root/venv"
model_dir="$runtime_root/model/Qwen3-1.7B-70d244c"
generation_dir="$output_root/generation"
equivalence_dir="$output_root/equivalence"
pkg="experiments/frame_internalization_sft_v1"
inventory="$repo_root/$pkg/rerun_freeze/qwen3_1p7b_v1/model_tokenizer_remote_inventory_v1.json"
f04_receipt="$repo_root/$pkg/primelab_f04/environment_freeze_20260723.json"
generator="$repo_root/scripts/generate_frame_curriculum_vllm.py"
checker="$repo_root/scripts/check_f06_vllm_equivalence.py"
monitor="$repo_root/scripts/monitor_f06_full.py"
amendment="$repo_root/$pkg/protocol_amendment_generation_vllm_v1.json"
state_file="$output_root/run_state.json"

vllm_version="0.11.0"
maximum_hours=30
maximum_usd=80
maximum_wall_clock_seconds=$((maximum_hours * 3600))
equivalence_timeout_seconds=3600
maximum_output_bytes=$((2 * 1024 * 1024 * 1024))
minimum_gpu_mib="${MIN_GPU_MIB:-24000}"
run_pid=""
monitor_pid=""

log() { echo "$(date -u +%FT%TZ) $*"; }

cleanup() {
  if [[ -n "$monitor_pid" ]] && kill -0 "$monitor_pid" 2>/dev/null; then
    kill "$monitor_pid" 2>/dev/null || true
    wait "$monitor_pid" 2>/dev/null || true
  fi
  if [[ -n "$run_pid" ]] && kill -0 "$run_pid" 2>/dev/null; then
    kill -TERM "$run_pid" 2>/dev/null || true
    for _ in $(seq 1 120); do kill -0 "$run_pid" 2>/dev/null || break; sleep 1; done
    kill -KILL "$run_pid" 2>/dev/null || true
    wait "$run_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

[[ "$(id -u)" -eq 0 ]]
[[ "$(git -C "$repo_root" rev-parse HEAD)" == "$source_commit" ]]
[[ -z "$(git -C "$repo_root" status --porcelain --untracked-files=no)" ]]
for f in "$inventory" "$f04_receipt" "$generator" "$checker" "$monitor" "$amendment"; do [[ -f "$f" ]]; done
command -v nvidia-smi >/dev/null
command -v timeout >/dev/null
command -v unshare >/dev/null

# Canonical LF Git-blob hashes of frozen inputs; the working copy must match byte for byte.
check_blob() {  # path-in-repo expected-sha256
  local blob wt
  blob="$(git -C "$repo_root" cat-file blob "$source_commit:$1" | sha256sum | cut -d' ' -f1)"
  wt="$(sha256sum "$repo_root/$1" | cut -d' ' -f1)"
  [[ "$blob" == "$2" && "$wt" == "$2" ]] || { log "FROZEN INPUT HASH MISMATCH: $1" >&2; exit 65; }
  echo "$2  $1"
}
{
  check_blob "$pkg/primelab_f04/environment_freeze_20260723.json" 9ee2c79751c1b56b11553cf45d19517ea2bf9f74936485775d7f88a0b753da86
  check_blob "$pkg/rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/request_manifest.json" e768b50ecd72ec9cf3f7caafe2a731013d6475f5b2e55c51e71562a7b5d98226
  check_blob "$pkg/rerun_freeze/qwen3_1p7b_v1/model_tokenizer_remote_inventory_v1.json" ccc3f96881fbcd2f2988be9cbfb9cd492173b607332b3b506cd3c8e9ab781797
  check_blob "$pkg/rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/requests.jsonl" a5cf8eb8fb26c2c93dcd4a733a338946219ddb2a3992e2261e720ccda7af3160
  check_blob "$pkg/primelab_f06/full_run_attempt_20261023/reference_batch32_nf4/neutral.jsonl" 9af3c46111fb5c540ee66ff89e4be7c1233f02dad157a180df705fc8a0bb56bd
} >"${output_root}.input_hashes.txt"

mapfile -t gpu_rows < <(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits)
[[ "${#gpu_rows[@]}" -eq 1 ]]
gpu_name="${gpu_rows[0]%%,*}"
gpu_memory_mib="${gpu_rows[0]##*, }"
[[ "$gpu_memory_mib" -ge "$minimum_gpu_mib" ]]
log "gpu=$gpu_name memory_mib=$gpu_memory_mib price_per_hour=$PRICE_PER_HOUR vllm=$vllm_version"

resuming=false
if [[ -e "$output_root" ]]; then
  [[ -f "$state_file" ]] || { log "output root exists without run_state.json"; exit 66; }
  python3 - "$state_file" "$source_commit" <<'PY'
import json, sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if state.get("source_commit") == sys.argv[2] else 1)
PY
  for marker in throughput_abort.json equivalence_failed.marker; do
    [[ ! -e "$output_root/$marker" ]] || { log "previous stop stands: $marker"; exit 67; }
  done
  rm -f "$output_root/STOP" "$output_root/stop_reason.txt"
  resuming=true
fi
mkdir -p "$runtime_root" "$generation_dir"
if [[ "$resuming" == false ]]; then
  python3 - "$state_file" "$source_commit" "$PRICE_PER_HOUR" <<'PY'
import json, sys
json.dump({"schema_version": "frame_internalization_f06_vllm_run_state.v1",
           "source_commit": sys.argv[2], "price_per_hour_usd": float(sys.argv[3]),
           "cumulative_seconds": 0.0, "launches": 0}, open(sys.argv[1], "w"), indent=2)
PY
fi
add_cumulative() {  # seconds
  python3 - "$state_file" "$1" <<'PY'
import json, sys
p = sys.argv[1]; s = json.load(open(p)); s["cumulative_seconds"] += float(sys.argv[2]); json.dump(s, open(p, "w"), indent=2)
PY
}
python3 - "$state_file" <<'PY'
import json, sys
p = sys.argv[1]; s = json.load(open(p)); s["launches"] += 1; json.dump(s, open(p, "w"), indent=2)
PY

# --- install pinned vLLM into its own venv, record the resulting lock -------------
if [[ ! -x "$venv_dir/bin/python" ]]; then
  if ! python3 -m venv "$venv_dir"; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3.10-venv
    python3 -m venv "$venv_dir"
  fi
  "$venv_dir/bin/python" -m pip install --disable-pip-version-check "vllm==$vllm_version" "transformers==4.57.1"
fi
# Triton compiles a CUDA helper at start-up and needs the Python headers.
if [[ ! -f /usr/include/python3.10/Python.h ]]; then
  apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3.10-dev build-essential
fi
LC_ALL=C "$venv_dir/bin/python" -m pip freeze --all | LC_ALL=C sort >"$output_root/environment_lock_vllm.txt"
grep -qi "^vllm==$vllm_version\$" "$output_root/environment_lock_vllm.txt"

# --- pinned model revision from the public Hub (artifact hashes verified by the generator)
"$venv_dir/bin/python" - "$inventory" "$model_dir" <<'PY'
import json, sys
from pathlib import Path
from huggingface_hub import snapshot_download
inventory = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
snapshot_download(repo_id=inventory["repository"], revision=inventory["revision"],
                  local_dir=Path(sys.argv[2]),
                  allow_patterns=[item["path"] for item in inventory["artifacts"]])
PY

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=0
export OMP_NUM_THREADS="$(nproc)"
export VLLM_NO_USAGE_STATS=1
export DO_NOT_TRACK=1
export VLLM_ENABLE_V1_MULTIPROCESSING=0

# Offline network namespace with loopback up (vLLM/torch need 127.0.0.1); fall back
# to no namespace, logged, if the namespace cannot hold a loopback socket.
offline_prefix=()
if unshare --net -- bash -c 'ip link set lo up 2>/dev/null || true; python3 -c "import socket; s=socket.socket(); s.bind((\"127.0.0.1\", 0))"' 2>/dev/null; then
  offline_prefix=(unshare --net -- bash -c 'ip link set lo up 2>/dev/null || true; exec "$@"' _)
fi
log "offline_network_namespace=$([[ ${#offline_prefix[@]} -gt 0 ]] && echo true || echo false)"

write_receipt() {  # status
  local apps stop
  mapfile -t apps < <(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits | sed '/^[[:space:]]*$/d')
  stop="$(cat "$output_root/stop_reason.txt" 2>/dev/null || true)"
  python3 - "$output_root" "$source_commit" "$wrapper_start" "$(date +%s)" "$1" "${runtime_exit_code:-0}" \
    "$maximum_hours" "$maximum_usd" "${#apps[@]}" "$stop" "$PRICE_PER_HOUR" "$gpu_name" "$vllm_version" <<'PY'
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
(root, commit, t0, t1, status, rc, max_h, max_usd, apps, stop, price, gpu, vllm) = sys.argv[1:]
root = Path(root)
frames = ["neutral", "F1", "F3", "F3_concrete"]
complete_frames = {}
for f in frames:
    p = root / "generation" / f"{f}.receipt.json"
    complete_frames[f] = json.loads(p.read_text())["complete"] if p.is_file() else False
state = json.loads((root / "run_state.json").read_text())
eq = root / "equivalence_result.json"
lock = root / "environment_lock_vllm.txt"
done = status == "complete" and all(complete_frames.values())
out = {
    "schema_version": "frame_internalization_primelab_f06_vllm_wrapper.v1",
    "amendment": "frame_internalization_generation_vllm_v1",
    "source_commit": commit, "status": status, "passed": bool(done and int(apps) == 0),
    "started_at_utc": datetime.fromtimestamp(int(t0), tz=timezone.utc).isoformat(),
    "finished_at_utc": datetime.fromtimestamp(int(t1), tz=timezone.utc).isoformat(),
    "cumulative_seconds": state["cumulative_seconds"], "launches": state["launches"],
    "runtime_exit_code": int(rc), "stop_reason": stop or None,
    "maximum_hours": float(max_h), "maximum_usd": float(max_usd), "price_per_hour_usd": float(price),
    "cumulative_usd_at_price": state["cumulative_seconds"] / 3600 * float(price),
    "gpu": gpu, "vllm": vllm,
    "environment_lock_vllm_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None,
    "equivalence_passed": json.loads(eq.read_text())["passed"] if eq.is_file() else None,
    "frame_receipts_complete": complete_frames,
    "compute_apps_after": int(apps), "cleanup_passed": int(apps) == 0,
}
(root / "wrapper_receipt.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(json.dumps(out, sort_keys=True))
PY
}

# --- stage 1: pre-registered equivalence check (fail = stop) --------------------
if ! python3 - "$output_root/equivalence_result.json" <<'PY'
import json, sys
try:
    sys.exit(0 if json.load(open(sys.argv[1]))["passed"] is True else 1)
except Exception:
    sys.exit(1)
PY
then
  rm -rf "$equivalence_dir"
  log "equivalence check: generating the 32 reference scenarios"
  set +e
  timeout --signal=TERM --kill-after=60s "$equivalence_timeout_seconds" \
    "${offline_prefix[@]}" \
    "$venv_dir/bin/python" "$generator" --model-dir "$model_dir" --f04-receipt "$f04_receipt" \
    --output-dir "$equivalence_dir" --limit-per-frame 8 \
    >>"$output_root/equivalence.stdout.log" 2>>"$output_root/equivalence.stderr.log"
  eq_rc=$?
  set -e
  if [[ "$eq_rc" -ne 0 ]]; then
    log "equivalence generation failed rc=$eq_rc"
    echo "equivalence_generation_failed" >"$output_root/stop_reason.txt"
    touch "$output_root/equivalence_failed.marker"
    add_cumulative "$(( $(date +%s) - wrapper_start ))"
    runtime_exit_code=$eq_rc; write_receipt stopped_equivalence_generation_failed
    exit 1
  fi
  if ! "$venv_dir/bin/python" "$checker" --candidate "$equivalence_dir" \
        --output "$output_root/equivalence_result.json"; then
    log "EQUIVALENCE CHECK FAILED: stopping before full generation"
    echo "equivalence_failed" >"$output_root/stop_reason.txt"
    touch "$output_root/equivalence_failed.marker"
    add_cumulative "$(( $(date +%s) - wrapper_start ))"
    runtime_exit_code=2; write_receipt stopped_equivalence_failed
    exit 2
  fi
  log "equivalence check passed"
fi

# --- stage 2: full generation, monitored ---------------------------------------
add_cumulative "$(( $(date +%s) - wrapper_start ))"
log "full generation start (resuming=$resuming)"
set +e
timeout --signal=TERM --kill-after=120s "$maximum_wall_clock_seconds" \
  "${offline_prefix[@]}" \
  "$venv_dir/bin/python" "$generator" --model-dir "$model_dir" --f04-receipt "$f04_receipt" \
  --output-dir "$generation_dir" \
  >>"$output_root/generator.stdout.log" 2>>"$output_root/generator.stderr.log" &
run_pid="$!"

"$venv_dir/bin/python" "$monitor" \
  --output-root "$output_root" --generator-pid "$run_pid" \
  --price-per-hour "$PRICE_PER_HOUR" --maximum-output-bytes "$maximum_output_bytes" \
  --max-hours "$maximum_hours" --max-usd "$maximum_usd" \
  >>"$output_root/monitor.log" 2>&1 &
monitor_pid="$!"

wait "$run_pid"
runtime_exit_code="$?"
run_pid=""
set -e
wait "$monitor_pid" 2>/dev/null || true
monitor_pid=""

stop_reason="$(cat "$output_root/stop_reason.txt" 2>/dev/null || true)"
if [[ "$runtime_exit_code" -eq 0 && -z "$stop_reason" ]]; then status=complete
elif [[ -n "$stop_reason" ]]; then status="stopped_$stop_reason"
else status=incomplete_or_crashed; fi
write_receipt "$status"
log "done: status=$status receipt=$output_root/wrapper_receipt.json"
[[ "$status" == complete ]]
