#!/usr/bin/env python3
"""Validate complete sampled support reviews and release the batch atomically."""

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

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json, write_jsonl
from alignment_harness.trajectory_curriculum import read_jsonl


def _signed_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("support review signed_at must be a nonempty ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("support review signed_at must include a timezone")
    return parsed


def validate_support_release_reviews(
    queue: dict[str, Any], receipts: list[dict[str, Any]]
) -> dict[str, Any]:
    if queue.get("schema_version") != "storyworld_support_release_review_queue_v1":
        raise ValueError("unexpected support release review queue schema")
    queue_base = {key: value for key, value in queue.items() if key != "queue_content_sha256"}
    if queue.get("queue_content_sha256") != sha256_json(queue_base):
        raise ValueError("support release review queue content hash mismatch")
    tasks = queue.get("review_tasks", [])
    task_map = {str(item["review_task_id"]): item for item in tasks}
    if len(task_map) != len(tasks):
        raise ValueError("support release review queue contains duplicate task IDs")
    if len(receipts) != len(tasks):
        raise ValueError("support release review batch must cover every sampled task")
    by_task: dict[str, dict[str, Any]] = {}
    decisions: Counter[str] = Counter()
    reviewers: Counter[str] = Counter()
    for receipt in receipts:
        if receipt.get("schema_version") != "storyworld_support_release_review_receipt_v1":
            raise ValueError("unexpected support release review receipt schema")
        task_id = str(receipt.get("review_task_id", ""))
        if task_id not in task_map:
            raise ValueError(f"unknown support release review task: {task_id}")
        if task_id in by_task:
            raise ValueError(f"duplicate support release review receipt: {task_id}")
        task = task_map[task_id]
        if receipt.get("record_content_sha256") != task["record_content_sha256"]:
            raise ValueError(f"{task_id}: review receipt binds different row content")
        decision = str(receipt.get("decision", ""))
        if decision not in {"approved", "rejected"}:
            raise ValueError(f"{task_id}: review decision must be approved or rejected")
        reviewer = str(receipt.get("reviewer_pseudonym", "")).strip()
        notes = str(receipt.get("scope_notes", "")).strip()
        signature = str(receipt.get("signature_or_external_receipt", "")).strip()
        if not reviewer or not notes or not signature:
            raise ValueError(f"{task_id}: reviewer, scope notes, and signature are required")
        _signed_datetime(receipt.get("signed_at"))
        by_task[task_id] = receipt
        decisions[decision] += 1
        reviewers[reviewer] += 1
    ordered_receipts = [by_task[str(task["review_task_id"])] for task in tasks]
    return {
        "complete": True,
        "approved": decisions["approved"],
        "rejected": decisions["rejected"],
        "reviewers": dict(sorted(reviewers.items())),
        "receipts_sha256": sha256_json(ordered_receipts),
        "all_approved": decisions["approved"] == len(tasks),
    }


def apply_support_release(
    provisional_manifest_path: Path,
    provisional_rows_path: Path,
    queue_path: Path,
    receipts_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    provisional_manifest_path = provisional_manifest_path.resolve()
    provisional_rows_path = provisional_rows_path.resolve()
    queue_path = queue_path.resolve()
    receipts_path = receipts_path.resolve()
    manifest = read_json(provisional_manifest_path)
    queue = read_json(queue_path)
    rows = read_jsonl(provisional_rows_path)
    receipts = read_jsonl(receipts_path)
    if manifest.get("schema_version") != "storyworld_support_provisional_release_manifest_v1":
        raise ValueError("unexpected provisional support release manifest schema")
    if manifest.get("status") != "exact_coverage_pending_human_sample_review":
        raise ValueError("support release manifest is not awaiting sampled review")
    artifacts = manifest.get("artifacts", {})
    if artifacts.get("provisional_rows.jsonl", {}).get("sha256") != sha256_file(
        provisional_rows_path
    ):
        raise ValueError("provisional support rows drifted after audit")
    if artifacts.get("RELEASE_REVIEW_QUEUE.json", {}).get("sha256") != sha256_file(
        queue_path
    ):
        raise ValueError("support release review queue drifted after audit")
    if len(rows) != int(manifest["rows"]):
        raise ValueError("provisional support row count mismatch")
    if any(row.get("training_approved") for row in rows):
        raise ValueError("provisional support input already contains approved rows")
    review = validate_support_release_reviews(queue, receipts)
    if not review["all_approved"]:
        raise ValueError("support release is atomic and refuses a batch with rejected samples")
    release_body = {
        "campaign_id": manifest["campaign_id"],
        "provisional_manifest_sha256": sha256_file(provisional_manifest_path),
        "provisional_rows_sha256": sha256_file(provisional_rows_path),
        "review_queue_sha256": sha256_file(queue_path),
        "review_receipts_file_sha256": sha256_file(receipts_path),
        "review_receipts_content_sha256": review["receipts_sha256"],
        "sample_tasks": len(queue["review_tasks"]),
    }
    release_id = f"support-release-{sha256_json(release_body)[:24]}"
    approved_rows = []
    for row in rows:
        base = {key: value for key, value in row.items() if key != "record_sha256"}
        base["training_approved"] = True
        provenance = dict(base.get("external_provenance", {}))
        provenance["release_review"] = {
            "release_id": release_id,
            "review_method": "complete deterministic category-by-arm sample review",
            "review_queue_sha256": sha256_file(queue_path),
            "review_receipts_content_sha256": review["receipts_sha256"],
            "sampled_row": any(
                task["record_id"] == row["record_id"] for task in queue["review_tasks"]
            ),
        }
        base["external_provenance"] = provenance
        approved_rows.append({**base, "record_sha256": sha256_json(base)})
    release_manifest = {
        "schema_version": "storyworld_support_approved_release_manifest_v1",
        "release_id": release_id,
        "campaign_id": manifest["campaign_id"],
        "status": "approved_for_training_by_sampled_batch_review",
        **release_body,
        "review_summary": review,
        "tokenizer": manifest["tokenizer"],
        "exact_token_totals": manifest["exact_token_totals"],
        "rows": len(approved_rows),
        "rows_by_arm": dict(sorted(Counter(row["arm"] for row in approved_rows).items())),
        "rows_by_slice": dict(sorted(Counter(row["slice"] for row in approved_rows).items())),
        "training_approved_rows": len(approved_rows),
        "sealed_evaluation_rows": 0,
        "development_rows": 0,
        "claim_boundary": (
            "Training approval applies to this exact hash-bound batch under the recorded "
            "deterministic sample-review protocol; it does not transfer to regenerated rows."
        ),
        "passed": True,
    }
    return approved_rows, release_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provisional-manifest", type=Path, required=True)
    parser.add_argument("--provisional-rows", type=Path, required=True)
    parser.add_argument("--review-queue", type=Path, required=True)
    parser.add_argument("--review-receipts", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    approved_rows, manifest = apply_support_release(
        args.provisional_manifest,
        args.provisional_rows,
        args.review_queue,
        args.review_receipts,
    )
    if args.apply:
        if args.output_dir is None:
            raise ValueError("--output-dir is required with --apply")
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        rows_path = output_dir / "approved_rows.jsonl"
        write_jsonl(rows_path, approved_rows)
        manifest["approved_rows_sha256"] = sha256_file(rows_path)
        write_json(output_dir / "SUPPORT_RELEASE_MANIFEST.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
