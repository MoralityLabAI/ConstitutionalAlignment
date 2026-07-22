#!/usr/bin/env python3
"""Freeze first-turn Mizan development probes for the local Qwen soft screen."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.mizan_rooms import (  # noqa: E402
    CONDITION_IDS,
    SYSTEM_PROMPT,
    load_package,
    render_turn,
    sha256_file,
    validate_package,
    write_json,
    write_jsonl,
)

DEFAULT_SUITE = REPO_ROOT / "experiments/mizan_rooms_v1/suite.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "experiments/qwen_soft_tests_v1"


def action_proxy(action: dict[str, Any], weights: dict[str, float]) -> float:
    centered = sum(
        float(action["score_effects"][dimension]) * float(weight)
        for dimension, weight in weights.items()
    )
    return (centered + 1.0) / 2.0


def build_probe_rows(
    repo_root: Path, suite_path: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    package_receipt = validate_package(repo_root, suite_path)
    suite, conditions_document, rooms = load_package(repo_root, suite_path)
    conditions = {
        str(condition["id"]): condition
        for condition in conditions_document["conditions"]
    }
    development_rooms = sorted(
        (room for room in rooms if room["source_split"] == "development"),
        key=lambda room: str(room["variant_id"]),
    )
    if len(development_rooms) != 4:
        raise ValueError("the soft screen requires exactly four development rooms")
    max_reason = int(suite["response_contract"]["public_reason_max_characters"])
    weights = {key: float(value) for key, value in suite["score_weights"].items()}
    rows: list[dict[str, Any]] = []
    for condition_id in CONDITION_IDS:
        condition = conditions[condition_id]
        for room in development_rooms:
            turn = room["turns"][0]
            state = {key: int(value) for key, value in room["initial_state"].items()}
            prompt, actions = render_turn(
                room,
                turn,
                condition,
                state,
                replicate=0,
                turn_index=0,
                max_reason_characters=max_reason,
            )
            action_rows = [
                {
                    "action_id": str(action["action_id"]),
                    "proxy_score": action_proxy(action, weights),
                    "tags": list(action["tags"]),
                }
                for action in actions
            ]
            preferred = sorted(
                action_rows,
                key=lambda action: (-float(action["proxy_score"]), action["action_id"]),
            )[0]
            rows.append(
                {
                    "probe_id": (
                        f"mizan_first_turn__{condition_id}__{room['variant_id']}"
                    ),
                    "tags": ["qwen_soft_test", "mizan_first_turn", condition_id],
                    "prompt": prompt,
                    "condition_id": condition_id,
                    "room_id": room["room_id"],
                    "variant_id": room["variant_id"],
                    "turn_id": turn["turn_id"],
                    "allowed_action_ids": [row["action_id"] for row in action_rows],
                    "actions": action_rows,
                    "preferred_proxy_action_id": preferred["action_id"],
                    "public_reason_max_characters": max_reason,
                }
            )
    if len(rows) != 20:
        raise ValueError("the soft screen must contain exactly 20 probes")
    manifest = {
        "schema_version": "qwen_mizan_first_turn_probe_manifest_v1",
        "status": "prospective_development_soft_screen",
        "suite_path": suite_path.relative_to(repo_root).as_posix(),
        "suite_sha256": sha256_file(suite_path),
        "package_validation": package_receipt,
        "conditions": list(CONDITION_IDS),
        "development_rooms": len(development_rooms),
        "turns_per_condition": len(development_rooms),
        "probe_count": len(rows),
        "replicate": 0,
        "turn_index": 0,
        "system_prompt": SYSTEM_PROMPT,
        "failure_tags": [
            "abandonment",
            "evidence_avoidance",
            "false_authority_deference",
            "harmful_shortcut",
            "record_tampering",
        ],
        "claim_boundary": "Small development prompt-sensitivity diagnostic; not the sealed Mizan evaluation matrix.",
    }
    return rows, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default=str(DEFAULT_SUITE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    suite_path = Path(args.suite).resolve()
    output_dir = Path(args.output_dir).resolve()
    rows, manifest = build_probe_rows(REPO_ROOT, suite_path)
    probes_path = output_dir / "mizan_first_turn_probes_v1.jsonl"
    system_path = output_dir / "mizan_system_prompt_v1.txt"
    manifest_path = output_dir / "mizan_first_turn_probe_manifest_v1.json"
    write_jsonl(probes_path, rows)
    system_path.parent.mkdir(parents=True, exist_ok=True)
    system_path.write_text(SYSTEM_PROMPT + "\n", encoding="utf-8", newline="\n")
    manifest.update(
        {
            "probes_path": probes_path.relative_to(REPO_ROOT).as_posix(),
            "probes_sha256": sha256_file(probes_path),
            "system_prompt_path": system_path.relative_to(REPO_ROOT).as_posix(),
            "system_prompt_sha256": sha256_file(system_path),
        }
    )
    write_json(manifest_path, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
