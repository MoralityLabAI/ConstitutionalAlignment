#!/usr/bin/env bash
set -euo pipefail

run_root="${1:?usage: inspect_jinn_persona_run_v4.sh RUN_ROOT}"
pid_path="${run_root}/launcher.pid"

if [[ -f "${pid_path}" ]]; then
  launcher_pid="$(tr -dc '0-9' < "${pid_path}")"
  if [[ -n "${launcher_pid}" ]] && kill -0 "${launcher_pid}" 2>/dev/null; then
    printf 'state=running pid=%s\n' "${launcher_pid}"
  else
    printf 'state=stopped pid=%s\n' "${launcher_pid:-unknown}"
  fi
  if [[ -n "${launcher_pid}" ]]; then
    ps -o pid,pgid,%cpu,%mem,rss,etime,cmd -p "${launcher_pid}" \
      --no-headers || true
  fi
else
  printf 'state=unknown launcher_pid_file=missing\n'
fi

nvidia-smi \
  --query-gpu=memory.used,utilization.gpu,temperature.gpu \
  --format=csv,noheader,nounits
nvidia-smi \
  --query-compute-apps=pid,process_name,used_memory \
  --format=csv,noheader || true

if [[ -f "${run_root}/partial_responses.jsonl" ]]; then
  printf 'partial_rows='
  wc -l < "${run_root}/partial_responses.jsonl"
else
  printf 'partial_rows=0\n'
fi

if [[ -f "${run_root}/generation_receipt.json" ]]; then
  python3 - "${run_root}/generation_receipt.json" <<'PY'
import json
import pathlib
import sys

receipt = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
fields = ("status", "rows_preserved", "result_rows", "error")
print("receipt=" + json.dumps({key: receipt.get(key) for key in fields}))
PY
fi

if [[ -f "${run_root}/generator.stderr.log" ]]; then
  tail -n 8 "${run_root}/generator.stderr.log"
fi
