#!/usr/bin/env bash

set -euo pipefail

: "${REPO_DIR:?Set REPO_DIR to the pinned ConstitutionalAlignment checkout}"
: "${MIZAN_MODEL:?Set MIZAN_MODEL to the exact served model revision}"

cd "$REPO_DIR"
output_root="${MIZAN_OUTPUT_ROOT:-artifacts/mizan_rooms_v1/evaluation}"
model_root="${output_root}/${MIZAN_MODEL//\//_}"
analysis_root="${model_root}/analysis"
mkdir -p "$analysis_root"

mapfile -t episode_files < <(find "$model_root" -mindepth 2 -maxdepth 2 -name episodes.jsonl -type f | sort)
if [[ "${#episode_files[@]}" -ne 15 ]]; then
  echo "Expected 15 complete condition/seed files, found ${#episode_files[@]}" >&2
  exit 2
fi

python scripts/analyze_mizan_rooms.py \
  --episodes "${episode_files[@]}" \
  --output "$analysis_root/mizan_analysis.json" \
  --judge-bundle-output "$analysis_root/blinded_judge_bundle/responses.jsonl" \
  --bootstrap-samples 10000 \
  --seed 20260716
