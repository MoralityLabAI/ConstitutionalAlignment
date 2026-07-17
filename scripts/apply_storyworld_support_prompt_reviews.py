#!/usr/bin/env python3
"""Validate all support-pilot prompt reviews and build a no-spend review bundle."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json
from alignment_harness.trajectory_curriculum import read_jsonl


def _signed_at(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("support prompt review timestamp must be nonempty")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("support prompt review timestamp must include a timezone")


def validate_support_prompt_reviews(
    queue: dict[str, Any], receipts: list[dict[str, Any]]
) -> dict[str, Any]:
    if queue.get("schema_version") != "storyworld_support_prompt_review_queue_v1":
        raise ValueError("unexpected support prompt review queue schema")
    queue_body = {key: value for key, value in queue.items() if key != "queue_content_sha256"}
    if queue.get("queue_content_sha256") != sha256_json(queue_body):
        raise ValueError("support prompt review queue content hash mismatch")
    tasks = queue.get("review_tasks", [])
    if (
        not isinstance(tasks, list)
        or len(tasks) != int(queue.get("review_tasks_count", 0))
        or len(tasks) != 76
        or queue.get("review_tasks_sha256") != sha256_json(tasks)
    ):
        raise ValueError("support prompt queue must contain exactly 76 current tasks")
    task_map = {str(item["review_task_id"]): item for item in tasks}
    if len(task_map) != len(tasks) or len(receipts) != len(tasks):
        raise ValueError("support prompt receipts must cover every unique task")

    by_task: dict[str, dict[str, Any]] = {}
    reviewers: Counter[str] = Counter()
    for receipt in receipts:
        if (
            receipt.get("schema_version")
            != "storyworld_support_prompt_review_receipt_v1"
        ):
            raise ValueError("unexpected support prompt review receipt schema")
        task_id = str(receipt.get("review_task_id", ""))
        if task_id not in task_map or task_id in by_task:
            raise ValueError(f"unknown or duplicate support prompt task: {task_id}")
        task = task_map[task_id]
        for key in (
            "job_content_sha256",
            "scenario_content_sha256",
            "messages_content_sha256",
        ):
            if receipt.get(key) != task[key]:
                raise ValueError(f"support prompt review binds stale {key}: {task_id}")
        if receipt.get("decision") != "approved":
            raise ValueError("support pilot requires every prompt review approved")
        if set(map(str, receipt.get("confirmed_scopes", []))) != set(
            map(str, task["required_review_scope"])
        ):
            raise ValueError(f"support prompt review scope is incomplete: {task_id}")
        reviewer = str(receipt.get("reviewer_pseudonym", "")).strip()
        notes = str(receipt.get("scope_notes", "")).strip()
        signature = str(receipt.get("signature_or_external_receipt", "")).strip()
        if not reviewer or not notes or not signature:
            raise ValueError(
                f"support prompt review lacks attribution, notes, or signature: {task_id}"
            )
        _signed_at(receipt.get("signed_at"))
        reviewers[reviewer] += 1
        by_task[task_id] = receipt
    ordered = [by_task[str(task["review_task_id"])] for task in tasks]
    return {
        "approved_prompt_reviews": len(ordered),
        "receipt_content_sha256": sha256_json(ordered),
        "reviewers": dict(sorted(reviewers.items())),
        "all_pilot_prompts_approved": True,
        "passed": True,
    }


def build_support_prompt_review_bundle(
    queue_path: Path, receipts_path: Path
) -> dict[str, Any]:
    queue_path = queue_path.resolve()
    receipts_path = receipts_path.resolve()
    queue = read_json(queue_path)
    receipts = read_jsonl(receipts_path)
    review = validate_support_prompt_reviews(queue, receipts)
    body = {
        "schema_version": "storyworld_support_prompt_human_review_bundle_v1",
        "campaign_id": queue["campaign_id"],
        "review_queue_sha256": sha256_file(queue_path),
        "review_queue_content_sha256": queue["queue_content_sha256"],
        "plan_manifest_sha256": queue["plan_manifest_sha256"],
        "support_scenarios_sha256": queue["support_scenarios_sha256"],
        "pilot_jobs_sha256": queue["pilot_jobs_sha256"],
        "review_receipts_file_sha256": sha256_file(receipts_path),
        "review": review,
        "approved_prompts": review["approved_prompt_reviews"],
        "all_pilot_prompts_approved": True,
        "automatic_spend_authorization": False,
        "automatic_training_approval": False,
        "claim_boundary": (
            "This approves the exact 76 pilot prompt/arm cells for a separate spend "
            "authorization. It does not authorize calls or approve generated responses."
        ),
        "passed": True,
    }
    return {
        **body,
        "prompt_review_bundle_id": f"support-prompt-review-{sha256_json(body)[:24]}",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-queue", type=Path, required=True)
    parser.add_argument("--review-receipts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle = build_support_prompt_review_bundle(
        args.review_queue, args.review_receipts
    )
    write_json(args.output.resolve(), bundle)
    print(json.dumps(bundle, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
