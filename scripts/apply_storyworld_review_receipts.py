#!/usr/bin/env python3
"""Validate and atomically record a complete storyworld review receipt batch."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import (
    read_json,
    read_world,
    reviewable_world_sha256,
    sha256_bytes,
    sha256_file,
    sha256_json,
    validate_curriculum_package,
    validate_world,
    write_json,
)


DEFAULT_PACKAGE = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "package.json"
REQUIRED_RECEIPT_FIELDS = {
    "schema_version",
    "review_task_id",
    "review_type",
    "reviewer_pseudonym",
    "decision",
    "scope_notes",
    "content_sha256",
    "signed_at",
    "signature_or_external_receipt",
}


def _json_file_sha256(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    return sha256_bytes(rendered.encode("utf-8"))


def _load_receipts(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
    else:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(value, dict):
            rows = value.get("receipts")
        else:
            rows = value
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("review receipt input must be a JSON array, receipts object, or JSONL")
    return rows


def validate_review_receipts(
    queue: dict[str, Any], receipts: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    if queue.get("schema_version") != "storyworld_review_queue_v1":
        raise ValueError("unexpected storyworld review queue schema")
    tasks = {str(item["review_task_id"]): item for item in queue["review_tasks"]}
    if len(tasks) != len(queue["review_tasks"]):
        raise ValueError("review queue contains duplicate task IDs")
    validated: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        missing_fields = REQUIRED_RECEIPT_FIELDS.difference(receipt)
        if missing_fields:
            raise ValueError(f"review receipt missing fields: {sorted(missing_fields)}")
        if receipt["schema_version"] != "storyworld_review_receipt_v1":
            raise ValueError("unexpected review receipt schema")
        task_id = str(receipt["review_task_id"])
        if task_id not in tasks:
            raise ValueError(f"review receipt references unknown task: {task_id}")
        if task_id in validated:
            raise ValueError(f"duplicate review receipt for task: {task_id}")
        task = tasks[task_id]
        if receipt["review_type"] != task["review_type"]:
            raise ValueError(f"{task_id}: receipt uses the wrong review type")
        if receipt["decision"] not in {"approved", "rejected"}:
            raise ValueError(f"{task_id}: decision must be approved or rejected")
        if receipt["content_sha256"] != task["reviewable_content_sha256"]:
            raise ValueError(f"{task_id}: receipt is bound to different substantive content")
        for field in (
            "reviewer_pseudonym",
            "scope_notes",
            "signature_or_external_receipt",
        ):
            if not str(receipt[field]).strip():
                raise ValueError(f"{task_id}: {field} must be nonempty")
        try:
            signed_at = datetime.fromisoformat(str(receipt["signed_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{task_id}: signed_at is not ISO-8601") from exc
        if signed_at.tzinfo is None:
            raise ValueError(f"{task_id}: signed_at must include a timezone")
        validated[task_id] = deepcopy(receipt)
    missing = sorted(set(tasks).difference(validated))
    return {
        "tasks": tasks,
        "receipts": validated,
        "missing_task_ids": missing,
        "complete": not missing,
        "approved": sum(item["decision"] == "approved" for item in validated.values()),
        "rejected": sum(item["decision"] == "rejected" for item in validated.values()),
    }


def prepare_review_application(
    repo_root: Path,
    package_path: Path,
    queue: dict[str, Any],
    receipts: Sequence[dict[str, Any]],
    bundle_output: Path,
    *,
    prepared_at: str | None = None,
) -> tuple[dict[str, Any], dict[Path, dict[str, Any]], dict[str, Any]]:
    repo_root = Path(repo_root).resolve()
    package_path = Path(package_path).resolve()
    bundle_output = Path(bundle_output).resolve()
    package = read_json(package_path)
    validate_curriculum_package(repo_root, package_path)
    if queue.get("package_id") != package["package_id"]:
        raise ValueError("review queue belongs to a different package")
    if queue.get("package_sha256") != sha256_file(package_path):
        raise ValueError("package changed after the review queue was frozen")

    receipt_validation = validate_review_receipts(queue, receipts)
    if not receipt_validation["complete"]:
        raise ValueError(
            f"review batch is incomplete: {len(receipt_validation['missing_task_ids'])} tasks missing"
        )
    tasks = receipt_validation["tasks"]
    receipt_by_task = receipt_validation["receipts"]
    queue_worlds = {str(item["world_id"]): item for item in queue["worlds"]}
    tasks_by_world: dict[str, list[dict[str, Any]]] = {}
    for task in tasks.values():
        tasks_by_world.setdefault(str(task["world_id"]), []).append(task)

    updated_sources: dict[Path, dict[str, Any]] = {}
    updated_package = deepcopy(package)
    try:
        bundle_relative = bundle_output.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError("review bundle output must be inside the repository") from exc
    updated_package["review_bundle"] = bundle_relative
    updates: list[dict[str, Any]] = []
    for package_item in updated_package["worlds"]:
        world_id = str(package_item["resolved_world_id"])
        if world_id not in queue_worlds:
            raise ValueError(f"review queue is missing package world: {world_id}")
        queue_world = queue_worlds[world_id]
        source_path = (repo_root / str(package_item["path"])).resolve()
        if sha256_file(source_path) != queue_world["source_sha256"]:
            raise ValueError(f"{world_id}: source changed after review queue creation")
        world = read_world(source_path)
        validation = validate_world(world)
        if sha256_json(world) != queue_world["resolved_content_sha256"]:
            raise ValueError(f"{world_id}: resolved content changed after review queue creation")
        if reviewable_world_sha256(world) != queue_world["reviewable_content_sha256"]:
            raise ValueError(f"{world_id}: substantive review content hash drifted")
        if validation["transition_graph_sha256"] != queue_world["transition_graph_sha256"]:
            raise ValueError(f"{world_id}: transition graph changed after review queue creation")

        requirement_updates = []
        world_tasks = {
            str(item["review_type"]): item for item in tasks_by_world.get(world_id, [])
        }
        for requirement in world["review"]["requirements"]:
            review_type = str(requirement["review_type"])
            if review_type not in world_tasks:
                raise ValueError(f"{world_id}: queue lacks {review_type} task")
            task = world_tasks[review_type]
            receipt = receipt_by_task[str(task["review_task_id"])]
            receipt_sha256 = sha256_json(receipt)
            requirement_updates.append(
                {
                    "review_type": review_type,
                    "status": receipt["decision"],
                    "receipt": (
                        f"storyworld-review:{task['review_task_id']}:sha256:{receipt_sha256}"
                    ),
                }
            )
        review_status = (
            "rejected"
            if any(item["status"] == "rejected" for item in requirement_updates)
            else "approved"
        )
        updated_review = {
            "status": review_status,
            "requirements": requirement_updates,
            "claim_boundary": world["review"]["claim_boundary"],
        }
        updated_world = deepcopy(world)
        updated_world["review"] = deepcopy(updated_review)
        post_validation = validate_world(updated_world)
        if post_validation["transition_graph_sha256"] != validation["transition_graph_sha256"]:
            raise ValueError(f"{world_id}: review update changed the causal graph")

        raw = read_json(source_path)
        if raw["schema_version"] == "storyworld_branching_world_v1":
            raw["review"] = deepcopy(updated_review)
        elif raw["schema_version"] == "storyworld_skin_overlay_v1":
            raw.setdefault("top_level", {})["review"] = deepcopy(updated_review)
        else:  # pragma: no cover - read_world already rejects this
            raise ValueError(f"{world_id}: unsupported source schema")
        updated_sources[source_path] = raw
        package_item["review_status"] = review_status
        updates.append(
            {
                "world_id": world_id,
                "family_id": world["family_id"],
                "source_split": world["source_split"],
                "source_path": source_path.relative_to(repo_root).as_posix(),
                "decision": review_status,
                "pre_source_sha256": queue_world["source_sha256"],
                "post_source_sha256": _json_file_sha256(raw),
                "pre_resolved_content_sha256": queue_world["resolved_content_sha256"],
                "post_resolved_content_sha256": sha256_json(updated_world),
                "reviewable_content_sha256": reviewable_world_sha256(updated_world),
                "transition_graph_sha256": validation["transition_graph_sha256"],
                "requirements": [
                    {
                        "review_type": item["review_type"],
                        "review_task_id": world_tasks[item["review_type"]]["review_task_id"],
                        "receipt_sha256": sha256_json(
                            receipt_by_task[
                                str(world_tasks[item["review_type"]]["review_task_id"])
                            ]
                        ),
                        "receipt": receipt_by_task[
                            str(world_tasks[item["review_type"]]["review_task_id"])
                        ],
                    }
                    for item in requirement_updates
                ],
            }
        )

    prepared_at = prepared_at or datetime.now(timezone.utc).isoformat()
    bundle = {
        "schema_version": "storyworld_review_application_bundle_v1",
        "application_id": f"review_apply_{sha256_json({'queue': sha256_json(queue), 'receipts': sorted(map(sha256_json, receipts))})[:24]}",
        "package_id": package["package_id"],
        "prepared_at": prepared_at,
        "queue_sha256": sha256_json(queue),
        "package_pre_sha256": sha256_file(package_path),
        "package_post_sha256": _json_file_sha256(updated_package),
        "receipt_count": len(receipt_by_task),
        "world_count": len(updates),
        "approved_worlds": sum(item["decision"] == "approved" for item in updates),
        "rejected_worlds": sum(item["decision"] == "rejected" for item in updates),
        "all_train_worlds_approved": all(
            item["source_split"] != "train" or item["decision"] == "approved"
            for item in updates
        ),
        "updates": updates,
        "evaluation_content_included": False,
        "claim_boundary": (
            "Receipts establish recorded external review decisions for frozen content; "
            "they do not make storyworld consequence dimensions moral or theological ground truth."
        ),
        "passed": True,
    }
    return bundle, updated_sources, updated_package


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--bundle-output", type=Path, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the validated source, package, and review-bundle updates.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue = read_json(args.queue.resolve())
    receipts = _load_receipts(args.receipts.resolve())
    bundle, updated_sources, updated_package = prepare_review_application(
        REPO_ROOT,
        args.package.resolve(),
        queue,
        receipts,
        args.bundle_output.resolve(),
    )
    if args.apply:
        for path, value in updated_sources.items():
            write_json(path, value)
        write_json(args.package.resolve(), updated_package)
        write_json(args.bundle_output.resolve(), bundle)
        validate_curriculum_package(REPO_ROOT, args.package.resolve())
    print(
        json.dumps(
            {
                "application_id": bundle["application_id"],
                "receipt_count": bundle["receipt_count"],
                "approved_worlds": bundle["approved_worlds"],
                "rejected_worlds": bundle["rejected_worlds"],
                "all_train_worlds_approved": bundle["all_train_worlds_approved"],
                "applied": bool(args.apply),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
