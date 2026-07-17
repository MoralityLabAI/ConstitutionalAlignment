#!/usr/bin/env python3
"""Prepare hash-bound review tasks without changing any world approval status."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import (
    read_json,
    read_world,
    sha256_file,
    sha256_json,
    reviewable_world_sha256,
    validate_curriculum_package,
    validate_world,
    write_json,
)


DEFAULT_PACKAGE = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "package.json"


def build_review_queue(repo_root: Path, package_path: Path) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    package_path = Path(package_path).resolve()
    package = read_json(package_path)
    receipt = validate_curriculum_package(repo_root, package_path)
    receipt_by_world = {str(item["world_id"]): item for item in receipt["worlds"]}
    world_entries: list[dict[str, Any]] = []
    review_tasks: list[dict[str, Any]] = []
    requirement_counts: Counter[str] = Counter()
    for item in package["worlds"]:
        source_path = repo_root / str(item["path"])
        world = read_world(source_path)
        world_id = str(world["world_id"])
        validation = validate_world(world)
        requirements = [
            {
                "review_type": value["review_type"],
                "status": value["status"],
                "receipt": value.get("receipt"),
            }
            for value in world["review"]["requirements"]
        ]
        pair = world["matched_pair"]
        entry = {
            "world_id": world_id,
            "family_id": world["family_id"],
            "source_split": world["source_split"],
            "training_eligible": world["training_eligible"],
            "theological_motif": world["theological_motif"],
            "skin_id": pair["skin_id"] if pair else None,
            "counterpart_world_id": pair["counterpart_world_id"] if pair else None,
            "source_path": source_path.relative_to(repo_root).as_posix(),
            "source_sha256": sha256_file(source_path),
            "resolved_content_sha256": receipt_by_world[world_id]["resolved_content_sha256"],
            "reviewable_content_sha256": reviewable_world_sha256(world),
            "transition_graph_sha256": validation["transition_graph_sha256"],
            "review_status": world["review"]["status"],
            "requirements": requirements,
            "claim_boundary": world["review"]["claim_boundary"],
        }
        world_entries.append(entry)
        for requirement in requirements:
            review_type = str(requirement["review_type"])
            requirement_counts[review_type] += 1
            task_payload = {
                "world_id": world_id,
                "family_id": world["family_id"],
                "review_type": review_type,
                "source_split": world["source_split"],
                "skin_id": entry["skin_id"],
                "source_path": entry["source_path"],
                "source_sha256": entry["source_sha256"],
                "resolved_content_sha256": entry["resolved_content_sha256"],
                "reviewable_content_sha256": entry["reviewable_content_sha256"],
                "transition_graph_sha256": entry["transition_graph_sha256"],
                "claim_boundary": entry["claim_boundary"],
            }
            review_tasks.append(
                {
                    "review_task_id": f"review_{sha256_json(task_payload)[:24]}",
                    **task_payload,
                    "current_status": requirement["status"],
                    "required_receipt_fields": [
                        "schema_version",
                        "review_task_id",
                        "reviewer_pseudonym",
                        "decision",
                        "scope_notes",
                        "content_sha256",
                        "signed_at",
                        "signature_or_external_receipt",
                    ],
                }
            )

    train_worlds = [item for item in world_entries if item["source_split"] == "train"]
    dev_worlds = [item for item in world_entries if item["source_split"] == "development"]
    return {
        "schema_version": "storyworld_review_queue_v1",
        "package_id": package["package_id"],
        "package_sha256": sha256_file(package_path),
        "status": "pending_external_review",
        "worlds": world_entries,
        "review_tasks": review_tasks,
        "counts": {
            "worlds": len(world_entries),
            "train_worlds": len(train_worlds),
            "development_worlds": len(dev_worlds),
            "review_tasks": len(review_tasks),
            "requirements": dict(sorted(requirement_counts.items())),
            "approved_worlds": sum(item["review_status"] == "approved" for item in world_entries),
            "campaign_blocking_train_worlds": sum(
                item["review_status"] != "approved" for item in train_worlds
            ),
        },
        "evaluation_content_included": False,
        "approval_effect": (
            "None. This queue is a hash-bound work order. Approval requires external receipts "
            "and a separate recorded content update."
        ),
        "passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare hash-bound scholar, ethics, and domain review tasks."
    )
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue = build_review_queue(REPO_ROOT, args.package)
    if args.output is not None:
        write_json(args.output.resolve(), queue)
    print(json.dumps(queue["counts"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
