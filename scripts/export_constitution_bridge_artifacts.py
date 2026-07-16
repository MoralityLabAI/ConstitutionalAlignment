#!/usr/bin/env python3
"""Derive SelfModel and StoryworldTRM artifacts from constitution control records."""

from __future__ import annotations

import argparse
from pathlib import Path

from constitution_bridge import (
    build_selfmodel_router_row,
    build_storyworld_controller_row,
    build_storyworld_rollout_episode_row,
    build_storyworld_rollout_step_row,
    ensure_dir,
    merkle_root_hex,
    read_jsonl,
    sha256_hex,
    utc_now,
    write_json,
    write_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-jsonl", required=True, help="Input constitution_control_record_v1 JSONL.")
    parser.add_argument("--output-dir", required=True, help="Directory to write derived bridge artifacts into.")
    parser.add_argument("--include-low-quality", action="store_true", help="Allow low-quality records into controller and rollout artifacts.")
    parser.add_argument("--include-k", action="store_true", help="Append K labels in the StoryworldTRM controller targets.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records_path = Path(args.records_jsonl).resolve()
    if not records_path.exists():
        raise SystemExit(f"Control record file not found: {records_path}")

    output_dir = Path(args.output_dir).resolve()
    ensure_dir(output_dir)

    records = read_jsonl(records_path)
    selfmodel_rows = []
    controller_rows = []
    rollout_steps = []
    rollout_episodes = []
    skipped_rollout_records = 0

    for episode_idx, record in enumerate(records):
        selfmodel_rows.append(build_selfmodel_router_row(record))

        eligible_for_rollout = bool(record["quality"].get("has_valid_decision", False))
        if record["quality"].get("is_low_quality", False) and not args.include_low_quality:
            eligible_for_rollout = False

        if not eligible_for_rollout:
            skipped_rollout_records += 1
            continue

        controller_row = build_storyworld_controller_row(record, include_k=bool(args.include_k))
        step_row = build_storyworld_rollout_step_row(record, episode_idx)
        episode_row = build_storyworld_rollout_episode_row(record, episode_idx)
        if controller_row is None or step_row is None or episode_row is None:
            skipped_rollout_records += 1
            continue

        controller_rows.append(controller_row)
        rollout_steps.append(step_row)
        rollout_episodes.append(episode_row)

    selfmodel_path = output_dir / "selfmodel_router_dataset.jsonl"
    controller_path = output_dir / "storyworld_controller_sft.jsonl"
    rollout_steps_path = output_dir / "storyworld_rollout_steps.jsonl"
    rollout_episodes_path = output_dir / "storyworld_rollout_episodes.jsonl"
    manifest_path = output_dir / "manifest.json"

    write_jsonl(selfmodel_path, selfmodel_rows)
    write_jsonl(controller_path, controller_rows)
    write_jsonl(rollout_steps_path, rollout_steps)
    write_jsonl(rollout_episodes_path, rollout_episodes)

    manifest = {
        "status": "completed",
        "generated_at_utc": utc_now(),
        "records_jsonl": str(records_path),
        "output_dir": str(output_dir),
        "include_low_quality": bool(args.include_low_quality),
        "include_k": bool(args.include_k),
        "selfmodel_rows": len(selfmodel_rows),
        "storyworld_controller_rows": len(controller_rows),
        "storyworld_rollout_step_rows": len(rollout_steps),
        "storyworld_rollout_episode_rows": len(rollout_episodes),
        "skipped_rollout_records": skipped_rollout_records,
        "selfmodel_rows_merkle_root": merkle_root_hex(
            [sha256_hex(f"{row['output']['route']}|{row['input']['encounter_id']}") for row in selfmodel_rows]
        ),
        "storyworld_controller_rows_merkle_root": merkle_root_hex([row["meta"]["receipt_leaf"] for row in controller_rows]),
        "storyworld_rollout_rows_merkle_root": merkle_root_hex([row["receipt_leaf"] for row in rollout_steps]),
    }
    write_json(manifest_path, manifest)
    print(str(output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
