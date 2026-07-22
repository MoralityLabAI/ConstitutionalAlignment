#!/usr/bin/env python3
"""Build a policy-preserving format-control dataset from storyworld rows."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import sha256_file, write_json, write_jsonl  # noqa: E402


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected an object")
            rows.append(value)
    return rows


def _format_target(action_id: str) -> str:
    return (
        f"Decision: {action_id}\n"
        "Rationale: I selected one listed option and kept the required two-line format."
    )


def build_format_control_rows(
    source_rows: Iterable[dict[str, Any]], target_rows: int
) -> list[dict[str, Any]]:
    if target_rows <= 0:
        raise ValueError("target_rows must be positive")
    eligible: list[dict[str, Any]] = []
    for source_row in source_rows:
        source = source_row.get("source")
        messages = source_row.get("messages")
        if not isinstance(source, dict) or not isinstance(messages, list):
            raise ValueError("each source row needs source metadata and messages")
        action_id = source.get("model_action_id")
        if action_id is None:
            continue
        if not isinstance(action_id, str) or not action_id.startswith("A-"):
            raise ValueError("model_action_id must be an opaque action ID")
        if len(messages) != 3 or messages[-1].get("role") != "assistant":
            raise ValueError("expected system, user, assistant messages")
        user_prompt = str(messages[1].get("content", ""))
        if action_id not in user_prompt:
            raise ValueError(f"model action is not listed in prompt: {action_id}")
        row = deepcopy(source_row)
        row["example_id"] = f"format_control_{source_row['example_id']}"
        row["messages"][-1]["content"] = _format_target(action_id)
        row["source"] = {
            **deepcopy(source),
            "kind": "local_storyworld_policy_preserving_format_control_v1",
            "control_target": "original_legal_model_action_in_canonical_two_line_format",
            "constitutional_target_used": False,
            "original_example_id": source_row["example_id"],
        }
        eligible.append(row)
    if not eligible:
        raise ValueError("no rows have a legal original model action")
    eligible.sort(key=lambda row: str(row["example_id"]))
    rows = eligible[:target_rows]
    repeat_index = 0
    while len(rows) < target_rows:
        repeated = deepcopy(eligible[repeat_index % len(eligible)])
        repeated["example_id"] = (
            f"{repeated['example_id']}_fill{repeat_index + 1:03d}"
        )
        repeated["source"]["deterministic_fill_repeat"] = repeat_index + 1
        rows.append(repeated)
        repeat_index += 1
    example_ids = [str(row["example_id"]) for row in rows]
    if len(example_ids) != len(set(example_ids)):
        raise ValueError("format-control example IDs are not unique")
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dataset-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--target-rows", type=int, default=97)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source_dataset_dir).resolve()
    fresh_path = source_dir / "fresh_train.jsonl"
    val_path = source_dir / "val.jsonl"
    manifest_path = source_dir / "manifest.json"
    for path in (fresh_path, val_path, manifest_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    source_rows = load_jsonl(fresh_path)
    rows = build_format_control_rows(source_rows, args.target_rows)

    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_train = output_dir / "fresh_train.jsonl"
    output_val = output_dir / "val.jsonl"
    write_jsonl(output_train, rows)
    shutil.copyfile(val_path, output_val)
    manifest = {
        "schema_version": "local_storyworld_format_control_dataset_v1",
        "status": "ready_for_guarded_local_training",
        "source_dataset_dir": str(source_dir),
        "source_fresh_train_sha256": sha256_file(fresh_path),
        "source_manifest_sha256": sha256_file(manifest_path),
        "source_rows": len(source_rows),
        "rows_with_legal_original_action": sum(
            row.get("source", {}).get("model_action_id") is not None
            for row in source_rows
        ),
        "excluded_invalid_source_rows": sum(
            row.get("source", {}).get("model_action_id") is None
            for row in source_rows
        ),
        "train_rows": len(rows),
        "deterministic_fill_repeats": sum(
            "deterministic_fill_repeat" in row["source"] for row in rows
        ),
        "target_policy": "preserve each legal original model action while normalizing only the response format",
        "constitutional_target_used": False,
        "fresh_train_sha256": sha256_file(output_train),
        "val_sha256": sha256_file(output_val),
        "claim_boundary": "Development-only benign SFT control for separating response-format exposure from score-target policy training.",
    }
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
