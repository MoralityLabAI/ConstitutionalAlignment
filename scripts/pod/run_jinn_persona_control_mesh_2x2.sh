#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${RUN_ID:-jinn-persona-control-mesh-2x2}"
REPO_ROOT="${REPO_ROOT:-/workspace/ConstitutionalAlignment}"
RUN_ROOT="${RUN_ROOT:-/workspace/runs/${RUN_ID}}"
ADAPTER_DIR="${ADAPTER_DIR:-/workspace/adapters/final_adapter}"
CACHE_DIR="${CACHE_DIR:-/workspace/hf_cache}"
TASKS="${REPO_ROOT}/experiments/jinn_persona_ambivalence_v4_expanded/control_mesh_2x2/tasks.jsonl"
MANIFEST="${REPO_ROOT}/experiments/jinn_persona_ambivalence_v4_expanded/control_mesh_2x2/task_manifest.json"
EVENT_LOG="${RUN_ROOT}/wrapper_events.jsonl"
RESOURCE_CSV="${RUN_ROOT}/resources.csv"
SUMMARY="${RUN_ROOT}/wrapper_summary.json"
MAX_SECONDS="${MAX_SECONDS:-6300}"
MAX_PROCESS_RAM_MB="${MAX_PROCESS_RAM_MB:-24000}"
MAX_SYSTEM_RAM_MB="${MAX_SYSTEM_RAM_MB:-60000}"
MAX_IO_MB_S="${MAX_IO_MB_S:-50}"
MODEL_REVISION="851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
CURRENT_PID=""
MONITOR_PID=""
START_EPOCH="$(date +%s)"

mkdir -p "${RUN_ROOT}"

emit_event() {
  local event="$1"
  local details="${2:-{}}"
  printf '{"ts":"%s","event":"%s","run_id":"%s","details":%s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${event}" "${RUN_ID}" "${details}" \
    >> "${EVENT_LOG}"
}

cleanup() {
  local exit_code=$?
  set +e
  if [[ -n "${MONITOR_PID}" ]] && kill -0 "${MONITOR_PID}" 2>/dev/null; then
    kill "${MONITOR_PID}"
    wait "${MONITOR_PID}" 2>/dev/null
  fi
  if [[ -n "${CURRENT_PID}" ]] && kill -0 "${CURRENT_PID}" 2>/dev/null; then
    kill -TERM "-${CURRENT_PID}" 2>/dev/null
    sleep 5
    kill -KILL "-${CURRENT_PID}" 2>/dev/null
    wait "${CURRENT_PID}" 2>/dev/null
  fi
  python3 - "${RUN_ROOT}" "${RESOURCE_CSV}" "${SUMMARY}" "${exit_code}" <<'PY'
import csv
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

run_root = pathlib.Path(sys.argv[1])
resource_path = pathlib.Path(sys.argv[2])
summary_path = pathlib.Path(sys.argv[3])
exit_code = int(sys.argv[4])
samples = []
if resource_path.exists():
    with resource_path.open(newline="", encoding="utf-8") as handle:
        samples = list(csv.DictReader(handle))

def numbers(key):
    return [float(row[key]) for row in samples if row.get(key)]

receipts = []
for path in sorted(run_root.glob("*_*/cell_receipt.json")):
    receipts.append(json.loads(path.read_text(encoding="utf-8")))
gpu_apps = subprocess.run(
    [
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader",
    ],
    capture_output=True,
    text=True,
    check=False,
).stdout.strip().splitlines()
complete = (
    exit_code == 0
    and len(receipts) == 4
    and all(receipt.get("status") == "completed" for receipt in receipts)
    and sum(int(receipt.get("result_rows", 0)) for receipt in receipts) == 1152
)
payload = {
    "schema_version": "jinn_persona_control_mesh_wrapper_summary_v1",
    "status": "completed" if complete else "aborted",
    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    "wrapper_exit_code": exit_code,
    "cell_receipts": receipts,
    "rows_completed": sum(int(item.get("result_rows", 0)) for item in receipts),
    "peak_ram_mb": max(numbers("process_rss_mb"), default=0.0),
    "avg_ram_mb": (
        sum(numbers("process_rss_mb")) / len(numbers("process_rss_mb"))
        if numbers("process_rss_mb")
        else 0.0
    ),
    "peak_system_ram_mb": max(numbers("system_ram_used_mb"), default=0.0),
    "peak_gpu_memory_mb": max(numbers("gpu_memory_used_mb"), default=0.0),
    "peak_gpu_utilization_pct": max(
        numbers("gpu_utilization_pct"), default=0.0
    ),
    "peak_io_mb_s": max(numbers("io_mb_s"), default=0.0),
    "resource_samples": len(samples),
    "owned_process_cleanup_attempted": True,
    "gpu_compute_apps_after_cleanup": gpu_apps,
    "cleanup_passed": not gpu_apps,
}
summary_path.write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
  emit_event "cleanup" "{\"exit_code\":${exit_code}}"
  exit "${exit_code}"
}
trap cleanup EXIT INT TERM

monitor_resources() {
  local target_pgid="$1"
  local previous_io=0
  local previous_time=0
  local io_breaches=0
  while true; do
    local metrics
    metrics="$(
      python3 - "${target_pgid}" "${RESOURCE_CSV}" \
        "${previous_io}" "${previous_time}" <<'PY'
import csv
import datetime
import os
import pathlib
import subprocess
import sys
import time

target_pgid = int(sys.argv[1])
output_path = pathlib.Path(sys.argv[2])
previous_io = int(sys.argv[3])
previous_time = float(sys.argv[4])
pids = []
for entry in pathlib.Path("/proc").iterdir():
    if not entry.name.isdigit():
        continue
    try:
        if os.getpgid(int(entry.name)) == target_pgid:
            pids.append(int(entry.name))
    except (OSError, ProcessLookupError):
        continue
rss_kb = 0
io_bytes = 0
for pid in pids:
    try:
        for line in pathlib.Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                rss_kb += int(line.split()[1])
                break
        for line in pathlib.Path(f"/proc/{pid}/io").read_text().splitlines():
            if line.startswith(("read_bytes:", "write_bytes:")):
                io_bytes += int(line.split()[1])
    except (FileNotFoundError, ProcessLookupError):
        continue
meminfo = {}
for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
    if line.startswith(("MemTotal:", "MemAvailable:")):
        key, value, *_ = line.split()
        meminfo[key.rstrip(":")] = int(value)
system_used_mb = (
    meminfo.get("MemTotal", 0) - meminfo.get("MemAvailable", 0)
) / 1024
gpu_output = subprocess.run(
    [
        "nvidia-smi",
        "--query-gpu=memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ],
    capture_output=True,
    text=True,
    check=False,
).stdout.strip()
gpu_parts = [part.strip() for part in gpu_output.split(",")]
gpu_memory = float(gpu_parts[0]) if len(gpu_parts) == 2 else 0.0
gpu_utilization = float(gpu_parts[1]) if len(gpu_parts) == 2 else 0.0
now = time.time()
io_mb_s = (
    max(0, io_bytes - previous_io) / max(now - previous_time, 1e-9) / 1048576
    if previous_time
    else 0.0
)
row = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "system_ram_used_mb": system_used_mb,
    "process_rss_mb": rss_kb / 1024,
    "process_io_bytes": io_bytes,
    "io_mb_s": io_mb_s,
    "gpu_memory_used_mb": gpu_memory,
    "gpu_utilization_pct": gpu_utilization,
}
new_file = not output_path.exists()
with output_path.open("a", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=row)
    if new_file:
        writer.writeheader()
    writer.writerow(row)
print(
    f"{row['process_rss_mb']} {row['system_ram_used_mb']} "
    f"{io_mb_s} {io_bytes} {now}"
)
PY
    )"
    read -r process_ram system_ram io_rate previous_io previous_time <<<"${metrics}"
    if awk "BEGIN {exit !(${process_ram} > ${MAX_PROCESS_RAM_MB})}"; then
      emit_event "abort" \
        "{\"reason\":\"process_ram_cap\",\"observed_mb\":${process_ram}}"
      kill -TERM "-${target_pgid}" 2>/dev/null
      return
    fi
    if awk "BEGIN {exit !(${system_ram} > ${MAX_SYSTEM_RAM_MB})}"; then
      emit_event "abort" \
        "{\"reason\":\"system_ram_cap\",\"observed_mb\":${system_ram}}"
      kill -TERM "-${target_pgid}" 2>/dev/null
      return
    fi
    if awk "BEGIN {exit !(${io_rate} > ${MAX_IO_MB_S})}"; then
      io_breaches=$((io_breaches + 1))
    else
      io_breaches=0
    fi
    if [[ "${io_breaches}" -ge 3 ]]; then
      emit_event "abort" \
        "{\"reason\":\"sustained_io_cap\",\"observed_mb_s\":${io_rate}}"
      kill -TERM "-${target_pgid}" 2>/dev/null
      return
    fi
    sleep 5
  done
}

run_cell() {
  local weight="$1"
  local frame="$2"
  local output="${RUN_ROOT}/${weight}_${frame}"
  local now remaining
  now="$(date +%s)"
  remaining=$((MAX_SECONDS - (now - START_EPOCH)))
  if [[ "${remaining}" -le 0 ]]; then
    emit_event "abort" '{"reason":"overall_timeout_before_cell"}'
    return 124
  fi
  if nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q .; then
    emit_event "abort" '{"reason":"competing_gpu_process"}'
    return 24
  fi
  mkdir -p "${output}"
  local adapter_args=()
  if [[ "${weight}" == "checkpoint_100" ]]; then
    adapter_args=(--adapter-dir "${ADAPTER_DIR}")
  fi
  emit_event "cell_start" \
    "{\"weight\":\"${weight}\",\"frame\":\"${frame}\",\"remaining_seconds\":${remaining}}"
  setsid timeout --signal=TERM --kill-after=60 "${remaining}" \
    taskset -c 0-3 ionice -c 2 -n 7 \
    python3 scripts/pod/run_jinn_persona_control_mesh_cell.py \
      --model-id Qwen/Qwen3.5-4B \
      --model-revision "${MODEL_REVISION}" \
      --weight-arm "${weight}" \
      --frame "${frame}" \
      "${adapter_args[@]}" \
      --tasks "${TASKS}" \
      --manifest "${MANIFEST}" \
      --output-dir "${output}" \
      --cache-dir "${CACHE_DIR}" \
      --batch-size 4 \
      --max-new-tokens 160 \
      --max-turns 6 \
      > "${output}/runner.stdout.log" \
      2> "${output}/runner.stderr.log" &
  CURRENT_PID=$!
  monitor_resources "${CURRENT_PID}" &
  MONITOR_PID=$!
  wait "${CURRENT_PID}"
  CURRENT_PID=""
  kill "${MONITOR_PID}" 2>/dev/null || true
  wait "${MONITOR_PID}" 2>/dev/null || true
  MONITOR_PID=""
  python3 - "${output}/cell_receipt.json" <<'PY'
import json
import pathlib
import sys

receipt = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if receipt.get("status") != "completed":
    raise SystemExit("cell receipt is not complete")
if int(receipt.get("result_rows", 0)) != 288:
    raise SystemExit("cell row count differs from frozen contract")
PY
  emit_event "cell_completed" \
    "{\"weight\":\"${weight}\",\"frame\":\"${frame}\"}"
}

cd "${REPO_ROOT}"
emit_event "start" \
  "{\"gpu_count\":1,\"gpu_memory_gb\":48,\"max_seconds\":${MAX_SECONDS},\"checkpoint_interval_rows\":12,\"batch_size\":4}"
if [[ ! -f "${ADAPTER_DIR}/adapter_config.json" ]]; then
  emit_event "abort" '{"reason":"adapter_missing"}'
  exit 21
fi
if swapon --show --noheadings | grep -q .; then
  sudo swapoff -a
fi
if swapon --show --noheadings | grep -q .; then
  emit_event "abort" '{"reason":"swap_remained_enabled"}'
  exit 23
fi

run_cell base jinn
run_cell base beast
run_cell checkpoint_100 jinn
run_cell checkpoint_100 beast

python3 - "${RUN_ROOT}" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
rows = 0
for path in sorted(root.glob("*_*/cell_receipt.json")):
    receipt = json.loads(path.read_text(encoding="utf-8"))
    rows += int(receipt.get("result_rows", 0))
if rows != 1152:
    raise SystemExit(f"expected 1152 rows across four cells, found {rows}")
PY
emit_event "all_cells_completed" '{"rows":1152}'

