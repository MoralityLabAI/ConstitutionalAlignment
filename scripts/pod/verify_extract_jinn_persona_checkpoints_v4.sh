#!/usr/bin/env bash
set -euo pipefail

archive_path="${1:-/workspace/adapters/upload/selected_checkpoints_40_60_80_100.tar.gz}"
destination="${2:-/workspace/adapters/jinn-persona-v3}"
expected_sha256="c30d557b175fe9a01b07ce9c27779e2444da22403e973dbbbce2e6d3d9559776"

actual_sha256="$(sha256sum "${archive_path}" | awk '{print $1}')"
if [[ "${actual_sha256}" != "${expected_sha256}" ]]; then
  printf 'checkpoint archive hash mismatch: expected=%s actual=%s\n' \
    "${expected_sha256}" "${actual_sha256}" >&2
  exit 1
fi

if [[ -e "${destination}" ]]; then
  printf 'checkpoint destination already exists: %s\n' "${destination}" >&2
  exit 1
fi

mkdir -p "${destination}"
tar -xzf "${archive_path}" -C "${destination}"

required_paths=(
  "${destination}/preserved_checkpoint-40/adapter_config.json"
  "${destination}/adapter/train/checkpoint-60/adapter_config.json"
  "${destination}/adapter/train/checkpoint-80/adapter_config.json"
  "${destination}/adapter/train/checkpoint-100/adapter_config.json"
)
for required_path in "${required_paths[@]}"; do
  if [[ ! -f "${required_path}" ]]; then
    printf 'required adapter artifact missing after extraction: %s\n' \
      "${required_path}" >&2
    exit 1
  fi
done

printf 'archive_sha256=%s\n' "${actual_sha256}"
find "${destination}" -maxdepth 4 -name adapter_config.json -printf '%h\n' | sort
du -sh "${destination}"

if [[ -n "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits)" ]]; then
  printf 'unexpected GPU compute process after checkpoint extraction\n' >&2
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
  exit 1
fi
