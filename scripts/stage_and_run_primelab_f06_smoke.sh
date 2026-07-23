#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 REPO_ROOT SOURCE_COMMIT OUTPUT_ROOT" >&2
  exit 64
fi

repo_root="$(realpath "$1")"
source_commit="$2"
output_root="$(realpath -m "$3")"
runtime_root="/opt/jinn-f06-smoke"
venv_dir="$runtime_root/venv"
model_dir="$runtime_root/model/Qwen3-1.7B-70d244c"
generation_dir="$output_root/generation"
requirements="$repo_root/experiments/frame_internalization_sft_v1/primelab_f04/requirements_f04.txt"
expected_lock="$repo_root/experiments/frame_internalization_sft_v1/primelab_f04/environment_lock_20260723.txt"
inventory="$repo_root/experiments/frame_internalization_sft_v1/rerun_freeze/qwen3_1p7b_v1/model_tokenizer_remote_inventory_v1.json"
f04_receipt="$repo_root/experiments/frame_internalization_sft_v1/primelab_f04/environment_freeze_20260723.json"
generator="$repo_root/scripts/generate_qwen3_frame_curriculum_transcripts.py"
maximum_wall_clock_seconds=1200
maximum_output_bytes=1073741824
limit_per_frame=4
batch_size=8
run_pid=""
monitor_pid=""
cap_marker="$output_root/output_cap_exceeded"

cleanup() {
  if [[ -n "$monitor_pid" ]] && kill -0 "$monitor_pid" 2>/dev/null; then
    kill "$monitor_pid" 2>/dev/null || true
    wait "$monitor_pid" 2>/dev/null || true
  fi
  if [[ -n "$run_pid" ]] && kill -0 "$run_pid" 2>/dev/null; then
    kill -TERM "$run_pid" 2>/dev/null || true
    sleep 2
    kill -KILL "$run_pid" 2>/dev/null || true
    wait "$run_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

[[ "$(git -C "$repo_root" rev-parse HEAD)" == "$source_commit" ]]
[[ -z "$(git -C "$repo_root" status --porcelain --untracked-files=no)" ]]
[[ -f "$requirements" ]]
[[ -f "$expected_lock" ]]
[[ -f "$inventory" ]]
[[ -f "$f04_receipt" ]]
[[ -f "$generator" ]]
[[ ! -e "$output_root" ]]
command -v nvidia-smi >/dev/null
command -v timeout >/dev/null
command -v unshare >/dev/null

mapfile -t gpu_rows < <(
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits
)
[[ "${#gpu_rows[@]}" -eq 1 ]]
[[ "${gpu_rows[0]}" == NVIDIA\ A100-SXM4-80GB,* ]]
gpu_memory_mib="${gpu_rows[0]##*, }"
[[ "$gpu_memory_mib" -ge 81920 ]]

mkdir -p "$runtime_root" "$generation_dir"
if ! python3 -m venv "$venv_dir"; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3.10-venv
  python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/python" -m pip install --disable-pip-version-check -r "$requirements"
LC_ALL=C "$venv_dir/bin/python" -m pip freeze --all | LC_ALL=C sort \
  >"$output_root/environment_lock.txt"
cmp --silent "$expected_lock" "$output_root/environment_lock.txt"

"$venv_dir/bin/python" - "$inventory" "$model_dir" <<'PY'
import json
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

inventory_path = Path(sys.argv[1])
model_dir = Path(sys.argv[2])
inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
snapshot_download(
    repo_id=inventory["repository"],
    revision=inventory["revision"],
    local_dir=model_dir,
    allow_patterns=[item["path"] for item in inventory["artifacts"]],
)
PY

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=0
export OMP_NUM_THREADS=16

started_epoch="$(date +%s)"
set +e
timeout --signal=TERM --kill-after=30s "$maximum_wall_clock_seconds" \
  unshare --net -- \
  "$venv_dir/bin/python" "$generator" \
    --model-dir "$model_dir" \
    --f04-receipt "$f04_receipt" \
    --output-dir "$generation_dir" \
    --limit-per-frame "$limit_per_frame" \
    --batch-size "$batch_size" \
    >"$output_root/generator.stdout.log" \
    2>"$output_root/generator.stderr.log" &
run_pid="$!"

(
  while kill -0 "$run_pid" 2>/dev/null; do
    observed_bytes="$(du -sb "$output_root" | cut -f1)"
    if (( observed_bytes > maximum_output_bytes )); then
      touch "$cap_marker"
      kill -TERM "$run_pid" 2>/dev/null || true
      exit 0
    fi
    sleep 2
  done
) &
monitor_pid="$!"

wait "$run_pid"
runtime_exit_code="$?"
run_pid=""
set -e

if kill -0 "$monitor_pid" 2>/dev/null; then
  kill "$monitor_pid" 2>/dev/null || true
fi
wait "$monitor_pid" 2>/dev/null || true
monitor_pid=""

finished_epoch="$(date +%s)"
observed_output_bytes="$(du -sb "$output_root" | cut -f1)"
mapfile -t compute_apps < <(
  nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits \
    | sed '/^[[:space:]]*$/d'
)

"$venv_dir/bin/python" - \
  "$output_root/wrapper_receipt.json" \
  "$source_commit" \
  "$started_epoch" \
  "$finished_epoch" \
  "$runtime_exit_code" \
  "$observed_output_bytes" \
  "$maximum_output_bytes" \
  "$maximum_wall_clock_seconds" \
  "$limit_per_frame" \
  "$batch_size" \
  "${#compute_apps[@]}" \
  "$(test -e "$cap_marker" && echo true || echo false)" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    output,
    source_commit,
    started,
    finished,
    exit_code,
    observed_bytes,
    maximum_bytes,
    maximum_seconds,
    limit_per_frame,
    batch_size,
    compute_apps,
    output_cap_exceeded,
) = sys.argv[1:]
started_int = int(started)
finished_int = int(finished)
receipt = {
    "schema_version": "frame_internalization_primelab_f06_smoke_wrapper.v1",
    "source_commit": source_commit,
    "started_at_utc": datetime.fromtimestamp(
        started_int, tz=timezone.utc
    ).isoformat(),
    "finished_at_utc": datetime.fromtimestamp(
        finished_int, tz=timezone.utc
    ).isoformat(),
    "elapsed_seconds": finished_int - started_int,
    "runtime_exit_code": int(exit_code),
    "maximum_wall_clock_seconds": int(maximum_seconds),
    "maximum_gpu_hours": int(maximum_seconds) / 3600,
    "maximum_output_bytes": int(maximum_bytes),
    "observed_output_bytes": int(observed_bytes),
    "output_cap_exceeded": output_cap_exceeded == "true",
    "limit_per_frame": int(limit_per_frame),
    "batch_size": int(batch_size),
    "compute_apps_after": int(compute_apps),
    "cleanup_passed": int(compute_apps) == 0,
}
receipt["passed"] = bool(
    receipt["runtime_exit_code"] == 0
    and receipt["elapsed_seconds"] <= receipt["maximum_wall_clock_seconds"]
    and receipt["observed_output_bytes"] <= receipt["maximum_output_bytes"]
    and not receipt["output_cap_exceeded"]
    and receipt["cleanup_passed"]
)
Path(output).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps(receipt, sort_keys=True))
PY

[[ "$runtime_exit_code" -eq 0 ]]
[[ ! -e "$cap_marker" ]]
[[ "$observed_output_bytes" -le "$maximum_output_bytes" ]]
[[ "${#compute_apps[@]}" -eq 0 ]]
