#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 REPO_ROOT SOURCE_COMMIT OUTPUT_ROOT" >&2
  exit 64
fi

repo_root="$(realpath "$1")"
source_commit="$2"
output_root="$(realpath -m "$3")"
runtime_root="/opt/jinn-f04"
venv_dir="$runtime_root/venv"
model_dir="$runtime_root/model/Qwen3-1.7B-70d244c"
probe_dir="$output_root/probe"
requirements="$repo_root/experiments/frame_internalization_sft_v1/primelab_f04/requirements_f04.txt"
inventory="$repo_root/experiments/frame_internalization_sft_v1/rerun_freeze/qwen3_1p7b_v1/model_tokenizer_remote_inventory_v1.json"

[[ "$(git -C "$repo_root" rev-parse HEAD)" == "$source_commit" ]]
[[ -z "$(git -C "$repo_root" status --porcelain --untracked-files=no)" ]]
[[ -f "$requirements" ]]
[[ -f "$inventory" ]]
command -v nvidia-smi >/dev/null
command -v unshare >/dev/null

mkdir -p "$runtime_root" "$output_root"
python3 -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --disable-pip-version-check -r "$requirements"

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

"$venv_dir/bin/python" "$repo_root/scripts/run_primelab_f04_probe.py" \
  --repo-root "$repo_root" \
  --model-dir "$model_dir" \
  --output-dir "$probe_dir" \
  --source-commit "$source_commit" \
  --python "$venv_dir/bin/python" \
  --maximum-wall-clock-seconds 1800 \
  --maximum-gpu-hours 0.5 \
  --maximum-output-bytes 1073741824 \
  --checkpoint-every-requests 1
