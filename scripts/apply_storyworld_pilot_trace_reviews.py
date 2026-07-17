#!/usr/bin/env python3
"""Validate complete human review of all real storyworld pilot traces."""

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
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("pilot review timestamp must include a timezone")


def validate_pilot_trace_reviews(
    calibration: dict[str, Any], receipts: list[dict[str, Any]]
) -> dict[str, Any]:
    if calibration.get("schema_version") != "storyworld_real_pilot_calibration_v1" or not calibration.get(
        "passed"
    ):
        raise ValueError("invalid real-pilot calibration")
    tasks = calibration.get("pilot_review_tasks", [])
    if (
        calibration.get("pilot_human_review_required") is not True
        or not isinstance(tasks, list)
        or len(tasks) != int(calibration.get("pilot_jobs", 0))
        or calibration.get("pilot_review_tasks_sha256") != sha256_json(tasks)
    ):
        raise ValueError("pilot calibration lacks a complete content-bound review queue")
    task_map = {str(item["review_task_id"]): item for item in tasks}
    if len(task_map) != len(tasks) or len(receipts) != len(tasks):
        raise ValueError("pilot review receipts must cover every unique trace task")
    by_task = {}
    reviewers: Counter[str] = Counter()
    for receipt in receipts:
        if receipt.get("schema_version") != "storyworld_real_pilot_trace_review_receipt_v1":
            raise ValueError("unexpected pilot trace review receipt schema")
        task_id = str(receipt.get("review_task_id", ""))
        if task_id not in task_map or task_id in by_task:
            raise ValueError(f"unknown or duplicate pilot review task: {task_id}")
        task = task_map[task_id]
        if (
            receipt.get("trace_id") != task["trace_id"]
            or receipt.get("trace_content_sha256") != task["trace_content_sha256"]
        ):
            raise ValueError(f"pilot review receipt binds stale trace content: {task_id}")
        if receipt.get("decision") != "approved":
            raise ValueError("full campaign requires every real pilot trace approved")
        if set(map(str, receipt.get("confirmed_scopes", []))) != set(
            map(str, task["required_review_scope"])
        ):
            raise ValueError(f"pilot review scope is incomplete: {task_id}")
        reviewer = str(receipt.get("reviewer_pseudonym", "")).strip()
        notes = str(receipt.get("scope_notes", "")).strip()
        signature = str(receipt.get("signature_or_external_receipt", "")).strip()
        if not reviewer or not notes or not signature:
            raise ValueError(f"pilot review lacks attribution, notes, or signature: {task_id}")
        _signed_at(receipt.get("signed_at"))
        reviewers[reviewer] += 1
        by_task[task_id] = receipt
    ordered = [by_task[str(task["review_task_id"])] for task in tasks]
    return {
        "approved_trace_reviews": len(ordered),
        "receipt_content_sha256": sha256_json(ordered),
        "reviewers": dict(sorted(reviewers.items())),
        "all_pilot_traces_approved": True,
        "passed": True,
    }


def build_pilot_review_bundle(
    calibration_path: Path, receipts_path: Path
) -> dict[str, Any]:
    calibration_path = calibration_path.resolve()
    receipts_path = receipts_path.resolve()
    calibration = read_json(calibration_path)
    receipts = read_jsonl(receipts_path)
    review = validate_pilot_trace_reviews(calibration, receipts)
    body = {
        "schema_version": "storyworld_real_pilot_human_review_bundle_v1",
        "pilot_calibration_sha256": sha256_file(calibration_path),
        "pilot_review_tasks_sha256": calibration["pilot_review_tasks_sha256"],
        "review_receipts_file_sha256": sha256_file(receipts_path),
        "review": review,
        "approved_traces": review["approved_trace_reviews"],
        "all_pilot_traces_approved": True,
        "claim_boundary": (
            "This approves the exact 48 pilot traces for campaign-design evidence. It does "
            "not authorize additional calls or waive final deterministic release audits."
        ),
        "passed": True,
    }
    return {**body, "pilot_review_bundle_id": f"pilot-review-{sha256_json(body)[:24]}"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-calibration", type=Path, required=True)
    parser.add_argument("--review-receipts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bundle = build_pilot_review_bundle(args.pilot_calibration, args.review_receipts)
    write_json(args.output.resolve(), bundle)
    print(json.dumps(bundle, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
