#!/usr/bin/env python3
"""Atomically approve recovered extras after every row and source license pass."""

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


def _signed(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("review timestamp must be nonempty")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("review timestamp must include a timezone")


def validate_recovered_reviews(
    queue: dict[str, Any],
    receipts: list[dict[str, Any]],
    license_receipt: dict[str, Any],
) -> dict[str, Any]:
    if queue.get("schema_version") != "storyworld_recovered_extras_review_queue_v1":
        raise ValueError("unexpected recovered review queue schema")
    base = {key: value for key, value in queue.items() if key != "queue_content_sha256"}
    if queue.get("queue_content_sha256") != sha256_json(base):
        raise ValueError("recovered review queue content hash mismatch")
    tasks = queue["review_tasks"]
    task_map = {str(item["review_task_id"]): item for item in tasks}
    if len(task_map) != len(tasks) or len(receipts) != len(tasks):
        raise ValueError("recovered review receipts must cover every unique task")
    by_task = {}
    reviewers: Counter[str] = Counter()
    for receipt in receipts:
        if receipt.get("schema_version") != "storyworld_recovered_row_review_receipt_v1":
            raise ValueError("unexpected recovered row review receipt schema")
        task_id = str(receipt.get("review_task_id", ""))
        if task_id not in task_map or task_id in by_task:
            raise ValueError(f"unknown or duplicate recovered review task: {task_id}")
        task = task_map[task_id]
        if receipt.get("record_content_sha256") != task["record_content_sha256"]:
            raise ValueError(f"{task_id}: receipt binds different row content")
        if receipt.get("review_type") != task["review_type"]:
            raise ValueError(f"{task_id}: receipt uses the wrong review type")
        if set(map(str, receipt.get("confirmed_checks", []))) != set(
            map(str, task.get("required_checks", []))
        ):
            raise ValueError(f"{task_id}: receipt does not confirm every required check")
        if receipt.get("decision") != "approved":
            raise ValueError("recovered extras release is atomic and requires every row approved")
        reviewer = str(receipt.get("reviewer_pseudonym", "")).strip()
        notes = str(receipt.get("scope_notes", "")).strip()
        signature = str(receipt.get("signature_or_external_receipt", "")).strip()
        if not reviewer or not notes or not signature:
            raise ValueError(f"{task_id}: reviewer, notes, and signature are required")
        _signed(receipt.get("signed_at"))
        reviewers[reviewer] += 1
        by_task[task_id] = receipt
    if license_receipt.get("schema_version") != "storyworld_recovered_source_license_receipt_v1":
        raise ValueError("unexpected recovered source license receipt schema")
    if license_receipt.get("source_id") != queue["source_id"]:
        raise ValueError("license receipt belongs to another recovered source")
    if license_receipt.get("decision") != "approved_for_research_training":
        raise ValueError("recovered source is not licensed for research training")
    if license_receipt.get("rows_sha256") != queue["rows_sha256"]:
        raise ValueError("license receipt binds different recovered row bytes")
    if not str(license_receipt.get("reviewed_by", "")).strip() or not str(
        license_receipt.get("signature_or_external_receipt", "")
    ).strip():
        raise ValueError("license receipt lacks attribution or signature")
    _signed(license_receipt.get("signed_at"))
    ordered = [by_task[str(task["review_task_id"])] for task in tasks]
    return {
        "row_receipts": len(ordered),
        "row_receipts_sha256": sha256_json(ordered),
        "reviewers": dict(sorted(reviewers.items())),
        "license_receipt_sha256": sha256_json(license_receipt),
        "all_rows_approved": True,
        "license_approved": True,
    }


def apply_recovered_reviews(
    normalization_manifest_path: Path,
    rows_path: Path,
    queue_path: Path,
    receipts_path: Path,
    license_receipt_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalization_manifest_path = normalization_manifest_path.resolve()
    rows_path = rows_path.resolve()
    queue_path = queue_path.resolve()
    receipts_path = receipts_path.resolve()
    license_receipt_path = license_receipt_path.resolve()
    normalization = read_json(normalization_manifest_path)
    queue = read_json(queue_path)
    rows = read_jsonl(rows_path)
    receipts = read_jsonl(receipts_path)
    license_receipt = read_json(license_receipt_path)
    if queue.get("normalization_manifest_sha256") != sha256_file(
        normalization_manifest_path
    ) or queue.get("rows_sha256") != sha256_file(rows_path):
        raise ValueError("recovered queue does not bind the supplied normalization artifacts")
    if len(rows) != int(normalization["rows"]):
        raise ValueError("recovered normalized row count mismatch")
    review = validate_recovered_reviews(queue, receipts, license_receipt)
    release_body = {
        "source_id": normalization["source_id"],
        "normalization_manifest_sha256": sha256_file(normalization_manifest_path),
        "provisional_rows_sha256": sha256_file(rows_path),
        "review_queue_sha256": sha256_file(queue_path),
        "review_receipts_file_sha256": sha256_file(receipts_path),
        "license_receipt_file_sha256": sha256_file(license_receipt_path),
        "review": review,
    }
    release_id = f"recovered-release-{sha256_json(release_body)[:24]}"
    approved = []
    for row in rows:
        base = {key: value for key, value in row.items() if key != "record_sha256"}
        base["training_approved"] = True
        provenance = dict(base["external_provenance"])
        provenance["release_review"] = {
            "release_id": release_id,
            "all_row_review": True,
            "row_receipts_sha256": review["row_receipts_sha256"],
            "license_receipt_sha256": review["license_receipt_sha256"],
        }
        base["external_provenance"] = provenance
        approved.append({**base, "record_sha256": sha256_json(base)})
    manifest = {
        "schema_version": "storyworld_recovered_extras_approved_release_v1",
        "release_id": release_id,
        "status": "approved_for_research_training",
        **release_body,
        "rows": len(approved),
        "rows_by_arm": dict(sorted(Counter(row["arm"] for row in approved).items())),
        "rows_by_slice": dict(sorted(Counter(row["slice"] for row in approved).items())),
        "training_approved_rows": len(approved),
        "excluded_splits": normalization["excluded_splits"],
        "sealed_evaluation_rows": 0,
        "passed": True,
    }
    return approved, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalization-manifest", type=Path, required=True)
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--review-queue", type=Path, required=True)
    parser.add_argument("--review-receipts", type=Path, required=True)
    parser.add_argument("--license-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, manifest = apply_recovered_reviews(
        args.normalization_manifest,
        args.rows,
        args.review_queue,
        args.review_receipts,
        args.license_receipt,
    )
    if args.apply:
        if args.output_dir is None:
            raise ValueError("--output-dir is required with --apply")
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        rows_path = output_dir / "approved_rows.jsonl"
        write_jsonl(rows_path, rows)
        manifest["approved_rows_sha256"] = sha256_file(rows_path)
        write_json(output_dir / "RECOVERED_EXTRAS_RELEASE_MANIFEST.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
