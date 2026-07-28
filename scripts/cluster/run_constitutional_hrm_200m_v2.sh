#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 6 ]]; then
  echo "usage: $0 MODE REPO_ROOT DATASET_DIR OFFICIAL_HRM_ROOT AUTHORIZATION_RECEIPT OUTPUT_ROOT" >&2
  exit 64
fi

MODE="$1"
REPO_ROOT="$(realpath "$2")"
DATASET_DIR="$(realpath "$3")"
OFFICIAL_ROOT="$(realpath "$4")"
AUTHORIZATION_RECEIPT="$(realpath "$5")"
OUTPUT_ROOT="$(realpath -m "$6")"
MODEL_CONFIG="${REPO_ROOT}/experiments/constitutional_hrm_200m_v2/model_config.json"
TRAINER="${REPO_ROOT}/scripts/train_constitutional_hrm_200m_v2.py"
MAX_WALL_SECONDS=7200
UNIT_TIMEOUT_SECONDS=7350
MODE_ARGUMENTS=()
if [[ "${MODE}" == "drill" ]]; then
  MAX_WALL_SECONDS=300
  UNIT_TIMEOUT_SECONDS=360
  MODE_ARGUMENTS=(
    --cluster-drill
    --max-optimizer-steps 1
    --batch-size 1
    --gradient-accumulation 1
    --checkpoint-steps 1
    --checkpoint-seconds 300
  )
elif [[ "${MODE}" != "pilot" ]]; then
  echo "MODE must be drill or pilot" >&2
  exit 64
fi

for command in systemd-run systemctl nvidia-smi findmnt timeout python3; do
  command -v "${command}" >/dev/null || {
    echo "required command missing: ${command}" >&2
    exit 65
  }
done

[[ "$(stat -fc %T /sys/fs/cgroup)" == "cgroup2fs" ]] || {
  echo "cgroup v2 is required" >&2
  exit 66
}
[[ ! -s /proc/swaps ]] || {
  echo "swap must be disabled before the cluster drill or optimizer launch" >&2
  exit 67
}
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)" -eq 8 ]] || {
  echo "exactly eight visible GPUs are required" >&2
  exit 68
}
mkdir -p "${OUTPUT_ROOT}/logs"

BLOCK_DEVICE="$(findmnt -no SOURCE --target "${OUTPUT_ROOT}")"
[[ -b "${BLOCK_DEVICE}" ]] || {
  echo "could not resolve output block device" >&2
  exit 69
}

arms=(
  constitutional_metta
  constitutional_text_only
  utility_control
  shuffled_control
)
seeds=(713 719)
units=()
gpu=0
for arm in "${arms[@]}"; do
  for seed in "${seeds[@]}"; do
    job_id="${arm}__seed_${seed}"
    job_output="${OUTPUT_ROOT}/${job_id}"
    unit="constitutional-hrm-${gpu}-${seed}"
    mkdir -p "${job_output}"
    units+=("${unit}")
    systemd-run \
      --unit="${unit}" \
      --collect \
      --wait \
      --pipe \
      --property=MemoryMax=96G \
      --property=MemorySwapMax=0 \
      --property=CPUQuota=1200% \
      --property=TasksMax=64 \
      --property="IOReadBandwidthMax=${BLOCK_DEVICE} 200M" \
      --property="IOWriteBandwidthMax=${BLOCK_DEVICE} 100M" \
      --setenv="CUDA_VISIBLE_DEVICES=${gpu}" \
      --setenv="PYTHONUNBUFFERED=1" \
      --setenv="TOKENIZERS_PARALLELISM=false" \
      timeout --signal=TERM --kill-after=30s "${UNIT_TIMEOUT_SECONDS}" \
      python3 "${TRAINER}" \
        --arm "${arm}" \
        --seed "${seed}" \
        --dataset-dir "${DATASET_DIR}" \
        --official-root "${OFFICIAL_ROOT}" \
        --model-config "${MODEL_CONFIG}" \
        --authorization-receipt "${AUTHORIZATION_RECEIPT}" \
        --output-dir "${job_output}" \
        --max-wall-seconds "${MAX_WALL_SECONDS}" \
        --gpu-memory-fraction 0.90 \
        "${MODE_ARGUMENTS[@]}" \
      >"${OUTPUT_ROOT}/logs/${job_id}.launcher.log" 2>&1 &
    gpu=$((gpu + 1))
  done
done

launcher_status=0
for launcher_pid in $(jobs -pr); do
  wait "${launcher_pid}" || launcher_status=1
done

cleanup_status=0
for unit in "${units[@]}"; do
  state="$(systemctl show "${unit}.service" --property=ActiveState --value || true)"
  if [[ "${state}" == "active" || "${state}" == "activating" ]]; then
    systemctl stop "${unit}.service" || cleanup_status=1
  fi
done

remaining_compute_pids="$(
  nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits |
    sed '/^[[:space:]]*$/d' || true
)"
if [[ -n "${remaining_compute_pids}" ]]; then
  echo "GPU compute processes remain after owned-unit cleanup: ${remaining_compute_pids}" >&2
  cleanup_status=1
fi

python3 - "${OUTPUT_ROOT}" "${launcher_status}" "${cleanup_status}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
launcher_status = int(sys.argv[2])
cleanup_status = int(sys.argv[3])
receipts = []
for path in sorted(root.glob("*/train_receipt.json")):
    receipts.append(json.loads(path.read_text(encoding="utf-8")))
payload = {
    "schema_version": "constitutional_hrm_cluster_runtime_receipt_v2",
    "gate_id": "F08B_LIVE_CLUSTER_DRILL_AND_RUNTIME",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "mode": root.name,
    "launcher_status": launcher_status,
    "cleanup_status": cleanup_status,
    "job_receipts": len(receipts),
    "job_statuses": {
        f"{item['arm']}__seed_{item['seed']}": item["status"] for item in receipts
    },
    "status": (
        "passed"
        if launcher_status == 0
        and cleanup_status == 0
        and len(receipts) == 8
        and all(str(item["status"]).startswith("completed") for item in receipts)
        else "failed"
    ),
}
(root / "cluster_runtime_receipt.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps(payload, indent=2, sort_keys=True))
PY

[[ "${launcher_status}" -eq 0 && "${cleanup_status}" -eq 0 ]]
