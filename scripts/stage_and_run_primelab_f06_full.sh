#!/usr/bin/env bash
# Full 22,400-transcript F06 curriculum generation under amendment
# frame_internalization_generation_batch32_v1. Adapted from
# stage_and_run_primelab_f06_smoke.sh. Run as root on the pod:
#
#   PRICE_PER_HOUR=<usd> bash scripts/stage_and_run_primelab_f06_full.sh \
#       REPO_ROOT SOURCE_COMMIT OUTPUT_ROOT
#
# The script detaches itself (setsid + nohup) and returns at once. Relaunching
# with the same arguments resumes: completed transcripts are skipped. Stop
# cleanly with:  touch OUTPUT_ROOT/STOP
# This script never contacts Prime and prints no credentials.
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

runtime_root="/opt/jinn-f06-full"
venv_dir="$runtime_root/venv"
model_dir="$runtime_root/model/Qwen3-1.7B-70d244c"
generation_dir="$output_root/generation"
pkg="experiments/frame_internalization_sft_v1"
requirements="$repo_root/$pkg/primelab_f04/requirements_f04.txt"
expected_lock="$repo_root/$pkg/primelab_f04/environment_lock_20260723.txt"
inventory="$repo_root/$pkg/rerun_freeze/qwen3_1p7b_v1/model_tokenizer_remote_inventory_v1.json"
f04_receipt="$repo_root/$pkg/primelab_f04/environment_freeze_20260723.json"
request_manifest="$repo_root/$pkg/rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/request_manifest.json"
generator="$repo_root/scripts/generate_qwen3_frame_curriculum_transcripts.py"
monitor="$repo_root/scripts/monitor_f06_full.py"
state_file="$output_root/run_state.json"

batch_size=32
maximum_hours=60
maximum_wall_clock_seconds=$((maximum_hours * 3600))
maximum_output_bytes=$((2 * 1024 * 1024 * 1024))   # corpus is about 0.2 GB; 10x headroom
minimum_gpu_mib="${MIN_GPU_MIB:-24000}"            # "24 GiB" cards report 24564-24576 MiB
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
for f in "$requirements" "$expected_lock" "$inventory" "$f04_receipt" "$request_manifest" "$generator" "$monitor"; do
  [[ -f "$f" ]]
done
command -v nvidia-smi >/dev/null
command -v timeout >/dev/null
command -v unshare >/dev/null

# Canonical LF Git-blob hashes of the frozen inputs (never working-tree bytes
# from another host). The working copy must equal the blob byte for byte.
check_blob() {  # path-in-repo expected-sha256
  local blob wt
  blob="$(git -C "$repo_root" cat-file blob "$source_commit:$1" | sha256sum | cut -d' ' -f1)"
  wt="$(sha256sum "$repo_root/$1" | cut -d' ' -f1)"
  [[ "$blob" == "$2" && "$wt" == "$2" ]] || { log "FROZEN INPUT HASH MISMATCH: $1" >&2; exit 65; }
  echo "$2  $1"
}
{
  check_blob "$pkg/primelab_f04/environment_freeze_20260723.json" 9ee2c79751c1b56b11553cf45d19517ea2bf9f74936485775d7f88a0b753da86
  check_blob "$pkg/primelab_f04/environment_lock_20260723.txt" de380fa5dcd8122e2c495711364f759bc71482c7da776a8f2b4846de265fcbff
  check_blob "$pkg/rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/request_manifest.json" e768b50ecd72ec9cf3f7caafe2a731013d6475f5b2e55c51e71562a7b5d98226
  check_blob "$pkg/rerun_freeze/qwen3_1p7b_v1/model_tokenizer_remote_inventory_v1.json" ccc3f96881fbcd2f2988be9cbfb9cd492173b607332b3b506cd3c8e9ab781797
  check_blob "$pkg/rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/requests.jsonl" a5cf8eb8fb26c2c93dcd4a733a338946219ddb2a3992e2261e720ccda7af3160
} >"${output_root}.input_hashes.txt"

mapfile -t gpu_rows < <(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits)
[[ "${#gpu_rows[@]}" -eq 1 ]]
gpu_name="${gpu_rows[0]%%,*}"
gpu_memory_mib="${gpu_rows[0]##*, }"
[[ "$gpu_memory_mib" -ge "$minimum_gpu_mib" ]]
log "gpu=$gpu_name memory_mib=$gpu_memory_mib price_per_hour=$PRICE_PER_HOUR batch=$batch_size"

resuming=false
if [[ -e "$output_root" ]]; then
  # Resume only a directory this script created for the same commit.
  [[ -f "$state_file" ]] || { log "output root exists without run_state.json"; exit 66; }
  python3 - "$state_file" "$source_commit" <<'PY'
import json, sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
sys.exit(0 if state.get("source_commit") == sys.argv[2] else 1)
PY
  [[ ! -e "$output_root/throughput_abort.json" ]] || { log "previous throughput abort stands"; exit 67; }
  rm -f "$output_root/STOP" "$output_root/stop_reason.txt"
  resuming=true
fi
mkdir -p "$runtime_root" "$generation_dir"
if [[ "$resuming" == false ]]; then
  python3 - "$state_file" "$source_commit" "$PRICE_PER_HOUR" <<'PY'
import json, sys
json.dump({"schema_version": "frame_internalization_f06_full_run_state.v1",
           "source_commit": sys.argv[2], "price_per_hour_usd": float(sys.argv[3]),
           "cumulative_seconds": 0.0, "launches": 0}, open(sys.argv[1], "w"), indent=2)
PY
fi
python3 - "$state_file" <<'PY'
import json, sys
p = sys.argv[1]; s = json.load(open(p)); s["launches"] += 1; json.dump(s, open(p, "w"), indent=2)
PY

if [[ ! -x "$venv_dir/bin/python" ]]; then
  if ! python3 -m venv "$venv_dir"; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3.10-venv
    python3 -m venv "$venv_dir"
  fi
  "$venv_dir/bin/python" -m pip install --disable-pip-version-check -r "$requirements"
fi
LC_ALL=C "$venv_dir/bin/python" -m pip freeze --all | LC_ALL=C sort >"$output_root/environment_lock.txt"
cmp --silent "$expected_lock" "$output_root/environment_lock.txt"

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

started_epoch="$(date +%s)"
log "generator start (resuming=$resuming)"
set +e
timeout --signal=TERM --kill-after=120s "$maximum_wall_clock_seconds" \
  unshare --net -- \
  "$venv_dir/bin/python" "$generator" \
    --model-dir "$model_dir" \
    --f04-receipt "$f04_receipt" \
    --output-dir "$generation_dir" \
    --batch-size "$batch_size" \
    >>"$output_root/generator.stdout.log" \
    2>>"$output_root/generator.stderr.log" &
run_pid="$!"

"$venv_dir/bin/python" "$monitor" \
  --output-root "$output_root" --generator-pid "$run_pid" \
  --price-per-hour "$PRICE_PER_HOUR" --maximum-output-bytes "$maximum_output_bytes" \
  >>"$output_root/monitor.log" 2>&1 &
monitor_pid="$!"

wait "$run_pid"
runtime_exit_code="$?"
run_pid=""
set -e
wait "$monitor_pid" 2>/dev/null || true
monitor_pid=""

finished_epoch="$(date +%s)"
mapfile -t compute_apps < <(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits | sed '/^[[:space:]]*$/d')
stop_reason="$(cat "$output_root/stop_reason.txt" 2>/dev/null || true)"

python3 - "$output_root" "$source_commit" "$started_epoch" "$finished_epoch" "$runtime_exit_code" \
  "$maximum_wall_clock_seconds" "$maximum_output_bytes" "$batch_size" "${#compute_apps[@]}" \
  "$stop_reason" "$PRICE_PER_HOUR" "$gpu_name" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
(root, commit, t0, t1, rc, max_s, max_b, batch, apps, stop, price, gpu) = sys.argv[1:]
root = Path(root)
frames = ["neutral", "F1", "F3", "F3_concrete"]
receipts = {}
for f in frames:
    p = root / "generation" / f"{f}.receipt.json"
    receipts[f] = json.loads(p.read_text())["complete"] if p.is_file() else False
state = json.loads((root / "run_state.json").read_text())
complete = all(receipts.values()) and int(rc) == 0
status = "complete" if complete else (f"stopped_{stop}" if stop else "incomplete_or_crashed")
out = {
    "schema_version": "frame_internalization_primelab_f06_full_wrapper.v1",
    "amendment": "frame_internalization_generation_batch32_v1",
    "source_commit": commit, "status": status, "passed": complete and int(apps) == 0,
    "started_at_utc": datetime.fromtimestamp(int(t0), tz=timezone.utc).isoformat(),
    "finished_at_utc": datetime.fromtimestamp(int(t1), tz=timezone.utc).isoformat(),
    "this_launch_seconds": int(t1) - int(t0), "cumulative_seconds": state["cumulative_seconds"],
    "launches": state["launches"], "runtime_exit_code": int(rc), "stop_reason": stop or None,
    "maximum_wall_clock_seconds": int(max_s), "maximum_output_bytes": int(max_b),
    "batch_size": int(batch), "gpu": gpu, "price_per_hour_usd": float(price),
    "cumulative_usd_at_price": state["cumulative_seconds"] / 3600 * float(price),
    "frame_receipts_complete": receipts, "compute_apps_after": int(apps), "cleanup_passed": int(apps) == 0,
}
(root / "wrapper_receipt.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(json.dumps(out, sort_keys=True))
PY
log "done status written to $output_root/wrapper_receipt.json"
[[ "$runtime_exit_code" -eq 0 && -z "$stop_reason" && "${#compute_apps[@]}" -eq 0 ]]
