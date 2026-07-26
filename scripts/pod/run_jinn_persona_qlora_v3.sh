#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${RUN_ID:-jinn-persona-ambivalence-v3-qwen35-4b}"
REPO_ROOT="${REPO_ROOT:-/workspace/ConstitutionalAlignment}"
RUN_ROOT="${RUN_ROOT:-/workspace/runs/${RUN_ID}}"
EVENT_LOG="${RUN_ROOT}/events.jsonl"
RESOURCE_CSV="${RUN_ROOT}/resources.csv"
WRAPPER_SUMMARY="${RUN_ROOT}/wrapper_summary.json"
MAX_SECONDS="${MAX_SECONDS:-14400}"
TRAIN_MAX_STEPS="${TRAIN_MAX_STEPS:-100}"
CHECKPOINT_STEPS="${CHECKPOINT_STEPS:-20}"
TRAIN_PID=""
OWNED_TRAIN_PID=""
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
  if [[ -n "${TRAIN_PID}" ]] && kill -0 "${TRAIN_PID}" 2>/dev/null; then
    kill -TERM "-${TRAIN_PID}" 2>/dev/null
    sleep 5
    kill -KILL "-${TRAIN_PID}" 2>/dev/null
    wait "${TRAIN_PID}" 2>/dev/null
  fi
  python3 - \
    "${WRAPPER_SUMMARY}" \
    "${RESOURCE_CSV}" \
    "${RUN_ROOT}/adapter/train_metrics.json" \
    "${RUN_ROOT}/adapter/final_adapter" \
    "${RUN_ID}" \
    "${exit_code}" \
    "${OWNED_TRAIN_PID}" <<'PY'
import csv
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

path = pathlib.Path(sys.argv[1])
resource_path = pathlib.Path(sys.argv[2])
metrics_path = pathlib.Path(sys.argv[3])
adapter_path = pathlib.Path(sys.argv[4])
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

steps_completed = 0
if metrics_path.exists():
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    steps_completed = max(
        (
            int(entry.get("step", 0))
            for entry in metrics.get("log_history", [])
        ),
        default=0,
    )

training_completed = bool(exit_code == 0 and adapter_path.is_dir())
payload = {
    "schema_version": "jinn_persona_pod_wrapper_summary_v1",
    "run_id": run_id,
    "status": "completed" if training_completed else "aborted",
    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    "wrapper_exit_code": exit_code,
    "steps_completed": steps_completed,
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
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
    status_path = pathlib.Path(f"/proc/{pid}/status")
    io_path = pathlib.Path(f"/proc/{pid}/io")
    try:
        for line in status_path.read_text().splitlines():
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
        for line in io_path.read_text().splitlines():
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
    writer = csv.DictWriter(handle, fieldnames=row)
    writer.writerow(row)
PY
    emit_event "resource_sample" '{}'
    sleep 30
  done
}

cd "${REPO_ROOT}"
emit_event "start" \
  "{\"gpu_count\":1,\"gpu_memory_gb\":48,\"ram_gb\":48,\"vcpus\":6,\"max_seconds\":${MAX_SECONDS},\"max_steps\":${TRAIN_MAX_STEPS},\"checkpoint_steps\":${CHECKPOINT_STEPS}}"

if swapon --show --noheadings | grep -q .; then
  sudo swapoff -a
fi
if swapon --show --noheadings | grep -q .; then
  emit_event "abort" '{"reason":"swap_remained_enabled"}'
  exit 23
fi

python3 scripts/build_jinn_persona_ambivalence_v3.py
python3 -m pip install --disable-pip-version-check \
  --index-url https://download.pytorch.org/whl/cu124 \
  "torch==2.5.1"
python3 -m pip install --disable-pip-version-check \
  "transformers @ git+https://github.com/huggingface/transformers.git@b6d5084fb4a5dd11e44005a5fa009e7943271090" \
  "accelerate>=1.2,<2" \
  "bitsandbytes>=0.45,<1" \
  "datasets>=3.2,<5" \
  "peft>=0.14,<1" \
  "trl>=0.15,<1"

setsid timeout --signal=TERM --kill-after=60 "${MAX_SECONDS}" \
  taskset -c 0-2 ionice -c 2 -n 7 \
  python3 scripts/train_constitution_adapter.py \
    --model-id Qwen/Qwen3.5-4B \
    --dataset-dir experiments/jinn_persona_ambivalence_v3/data \
    --constitution-id jinn_persona_ambivalence_v3 \
    --output-root "${RUN_ROOT}" \
    --run-name adapter \
    --cache-dir /workspace/hf_cache \
    --max-seq-length 1536 \
    --per-device-train-batch-size 1 \
    --per-device-eval-batch-size 1 \
    --gradient-accumulation-steps 4 \
    --learning-rate 1e-4 \
    --max-steps "${TRAIN_MAX_STEPS}" \
    --warmup-ratio 0.05 \
    --logging-steps 5 \
    --save-steps "${CHECKPOINT_STEPS}" \
    --eval-steps "${CHECKPOINT_STEPS}" \
    --save-total-limit 3 \
    --lora-r 16 \
    --lora-alpha 32 \
    --lora-dropout 0.05 \
    --target-modules q_proj,k_proj,v_proj,o_proj,in_proj_qkv,in_proj_z,in_proj_b,in_proj_a,out_proj \
    --quantization qlora \
    --dtype bfloat16 \
  > "${RUN_ROOT}/trainer.stdout.log" \
  2> "${RUN_ROOT}/trainer.stderr.log" &
TRAIN_PID=$!
OWNED_TRAIN_PID="${TRAIN_PID}"

monitor_resources "${TRAIN_PID}" &
MONITOR_PID=$!

wait "${TRAIN_PID}"
TRAIN_PID=""
emit_event "training_process_completed" '{}'

test -f "${RUN_ROOT}/adapter/receipt.json"
test -d "${RUN_ROOT}/adapter/final_adapter"
tar -C "${RUN_ROOT}/adapter" -czf "${RUN_ROOT}/final_adapter.tar.gz" final_adapter
sha256sum "${RUN_ROOT}/final_adapter.tar.gz" > "${RUN_ROOT}/final_adapter.tar.gz.sha256"
emit_event "artifacts_ready" '{}'
