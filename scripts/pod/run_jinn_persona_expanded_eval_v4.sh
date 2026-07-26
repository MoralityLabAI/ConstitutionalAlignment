#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${RUN_ID:-jinn-persona-v4-expanded}"
REPO_ROOT="${REPO_ROOT:-/workspace/ConstitutionalAlignment}"
RUN_ROOT="${RUN_ROOT:-/workspace/runs/${RUN_ID}}"
EVENT_LOG="${RUN_ROOT}/wrapper_events.jsonl"
RESOURCE_CSV="${RUN_ROOT}/resources.csv"
WRAPPER_SUMMARY="${RUN_ROOT}/wrapper_summary.json"
MAX_SECONDS="${MAX_SECONDS:-7200}"
MAX_PROCESS_RAM_MB="${MAX_PROCESS_RAM_MB:-12000}"
MAX_SYSTEM_RAM_MB="${MAX_SYSTEM_RAM_MB:-44000}"
EVAL_PID=""
OWNED_EVAL_PID=""
MONITOR_PID=""

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
  if [[ -n "${EVAL_PID}" ]] && kill -0 "${EVAL_PID}" 2>/dev/null; then
    kill -TERM "-${EVAL_PID}" 2>/dev/null
    sleep 5
    kill -KILL "-${EVAL_PID}" 2>/dev/null
    wait "${EVAL_PID}" 2>/dev/null
  fi
  python3 - \
    "${WRAPPER_SUMMARY}" \
    "${RESOURCE_CSV}" \
    "${RUN_ROOT}/generation_receipt.json" \
    "${RUN_ROOT}/responses.jsonl" \
    "${RUN_ID}" \
    "${exit_code}" \
    "${OWNED_EVAL_PID}" <<'PY'
import csv
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

summary_path = pathlib.Path(sys.argv[1])
resource_path = pathlib.Path(sys.argv[2])
receipt_path = pathlib.Path(sys.argv[3])
result_path = pathlib.Path(sys.argv[4])
run_id = sys.argv[5]
exit_code = int(sys.argv[6])
owned_pid = int(sys.argv[7]) if sys.argv[7] else None
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
samples = []
if resource_path.exists():
    with resource_path.open(newline="", encoding="utf-8") as handle:
        samples = [
            {
                key: float(value)
                for key, value in row.items()
                if key != "ts_utc"
            }
            for row in csv.DictReader(handle)
        ]

def peak(key: str) -> float:
    return max((row[key] for row in samples), default=0.0)

def average(key: str) -> float:
    return (
        sum(row[key] for row in samples) / len(samples)
        if samples
        else 0.0
    )

io_rates = []
for previous, current in zip(samples, samples[1:]):
    elapsed = current["ts_epoch"] - previous["ts_epoch"]
    delta = current["process_io_bytes"] - previous["process_io_bytes"]
    if elapsed > 0 and delta >= 0:
        io_rates.append(delta / elapsed / 1024 / 1024)

generation = {}
if receipt_path.exists():
    generation = json.loads(receipt_path.read_text(encoding="utf-8"))
status = (
    "completed"
    if exit_code == 0
    and generation.get("status") == "completed"
    and result_path.is_file()
    else "aborted"
)
payload = {
    "schema_version": "jinn_persona_expanded_wrapper_summary_v4",
    "run_id": run_id,
    "status": status,
    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    "wrapper_exit_code": exit_code,
    "rows_completed": int(generation.get("result_rows", 0)),
    "rows_preserved": int(generation.get("rows_preserved", 0)),
    "peak_ram_mb": peak("process_rss_mb"),
    "avg_ram_mb": average("process_rss_mb"),
    "peak_system_ram_mb": peak("system_ram_used_mb"),
    "peak_gpu_memory_mb": peak("gpu_memory_used_mb"),
    "peak_gpu_utilization_pct": peak("gpu_utilization_pct"),
    "avg_cpu_pct": average("process_cpu_pct"),
    "peak_io_mb_s": max(io_rates, default=0.0),
    "resource_samples": len(samples),
    "owned_process_cleanup_attempted": True,
    "owned_pids": [owned_pid] if owned_pid else [],
    "gpu_compute_apps_after_cleanup": gpu_apps,
    "cleanup_passed": not gpu_apps,
}
summary_path.write_text(
    json.dumps(payload, indent=2) + "\n",
    encoding="utf-8",
)
PY
  emit_event "cleanup" "{\"exit_code\":${exit_code}}"
  exit "${exit_code}"
}
trap cleanup EXIT INT TERM

monitor_resources() {
  local target_pgid="$1"
  printf '%s\n' \
    'ts_utc,ts_epoch,system_ram_used_mb,process_rss_mb,process_cpu_pct,process_io_bytes,gpu_memory_used_mb,gpu_utilization_pct' \
    > "${RESOURCE_CSV}"
  while true; do
    local metrics
    metrics="$(
      python3 - "${target_pgid}" "${RESOURCE_CSV}" <<'PY'
import csv
import datetime
import os
import pathlib
import subprocess
import sys
import time

target_pgid = int(sys.argv[1])
output_path = pathlib.Path(sys.argv[2])
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
cpu_pct = 0.0
io_bytes = 0
for pid in pids:
    try:
        for line in pathlib.Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                rss_kb += int(line.split()[1])
                break
        cpu_text = subprocess.run(
            ["ps", "-p", str(pid), "-o", "%cpu="],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        cpu_pct += float(cpu_text or 0)
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
row = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "ts_epoch": now,
    "system_ram_used_mb": system_used_mb,
    "process_rss_mb": rss_kb / 1024,
    "process_cpu_pct": cpu_pct,
    "process_io_bytes": io_bytes,
    "gpu_memory_used_mb": gpu_memory,
    "gpu_utilization_pct": gpu_utilization,
}
with output_path.open("a", newline="", encoding="utf-8") as handle:
    csv.DictWriter(handle, fieldnames=row).writerow(row)
print(f"{row['process_rss_mb']} {row['system_ram_used_mb']}")
PY
    )"
    local process_ram="${metrics%% *}"
    local system_ram="${metrics##* }"
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
    sleep 10
  done
}

cd "${REPO_ROOT}"
emit_event "start" \
  "{\"gpu_count\":1,\"gpu_memory_gb\":48,\"ram_gb\":48,\"vcpus\":6,\"max_seconds\":${MAX_SECONDS},\"checkpoint_interval_rows\":8}"

if swapon --show --noheadings | grep -q .; then
  sudo swapoff -a
fi
if swapon --show --noheadings | grep -q .; then
  emit_event "abort" '{"reason":"swap_remained_enabled"}'
  exit 23
fi
if nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q .; then
  emit_event "abort" '{"reason":"competing_gpu_process"}'
  exit 24
fi

setsid timeout --signal=TERM --kill-after=60 "${MAX_SECONDS}" \
  taskset -c 0-2 ionice -c 2 -n 7 \
  python3 scripts/pod/generate_jinn_persona_checkpoint_eval_v4.py \
    --model-id Qwen/Qwen3.5-4B \
    --arm-config experiments/jinn_persona_ambivalence_v4_expanded/arm_config.json \
    --protocol experiments/jinn_persona_ambivalence_v4_expanded/protocol.json \
    --prompts experiments/jinn_persona_ambivalence_v4_expanded/prompts.jsonl \
    --output-dir "${RUN_ROOT}" \
    --cache-dir /workspace/hf_cache \
    > "${RUN_ROOT}/generator.stdout.log" \
    2> "${RUN_ROOT}/generator.stderr.log" &
EVAL_PID=$!
OWNED_EVAL_PID="${EVAL_PID}"

monitor_resources "${EVAL_PID}" &
MONITOR_PID=$!

wait "${EVAL_PID}"
EVAL_PID=""
emit_event "generation_process_completed" '{}'

test -f "${RUN_ROOT}/generation_receipt.json"
test -f "${RUN_ROOT}/responses.jsonl"
python3 - "${RUN_ROOT}/generation_receipt.json" <<'PY'
import json
import pathlib
import sys
receipt = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if receipt.get("status") != "completed":
    raise SystemExit("generation receipt is not complete")
if int(receipt.get("result_rows", 0)) != 288:
    raise SystemExit("generation row count differs from frozen contract")
PY
sha256sum "${RUN_ROOT}/responses.jsonl" > "${RUN_ROOT}/responses.jsonl.sha256"
emit_event "artifacts_ready" '{}'
