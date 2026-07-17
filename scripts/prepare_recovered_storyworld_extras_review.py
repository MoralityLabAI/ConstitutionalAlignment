#!/usr/bin/env python3
"""Prepare an all-row review queue for normalized recovered static/helpful data."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json
from alignment_harness.trajectory_curriculum import read_jsonl


def prepare_recovered_review(
    normalization_manifest_path: Path, rows_path: Path
) -> dict:
    normalization_manifest_path = normalization_manifest_path.resolve()
    rows_path = rows_path.resolve()
    manifest = read_json(normalization_manifest_path)
    if manifest.get("schema_version") != "storyworld_recovered_extras_normalization_v1":
        raise ValueError("unexpected recovered normalization manifest schema")
    if manifest.get("status") != "provisional" or not manifest.get("passed"):
        raise ValueError("recovered normalization is not a valid provisional artifact")
    artifact = manifest.get("artifacts", {}).get("extra_rows.jsonl", {})
    if artifact.get("sha256") != sha256_file(rows_path):
        raise ValueError("normalized recovered rows drifted")
    rows = read_jsonl(rows_path)
    if len(rows) != int(artifact.get("rows", -1)) or len(rows) != int(manifest["rows"]):
        raise ValueError("normalized recovered row count mismatch")
    tasks = []
    seen = set()
    for row in rows:
        record_id = str(row["record_id"])
        if record_id in seen or row.get("training_approved"):
            raise ValueError("recovered review input has duplicate or preapproved rows")
        seen.add(record_id)
        source_status = str(row["external_provenance"]["source_review_status"])
        review_type = (
            "scholar_and_content_review"
            if source_status == "needs_scholar_review"
            else "content_quality_review"
        )
        body = {
            "source_id": manifest["source_id"],
            "record_id": record_id,
            "record_content_sha256": row["record_sha256"],
            "arm": row["arm"],
            "slice": row["slice"],
            "source_review_status": source_status,
            "review_type": review_type,
        }
        tasks.append(
            {
                "review_task_id": f"recovered-review-{sha256_json(body)[:24]}",
                **body,
                "required_checks": [
                    "response_is_correct_and_useful_for_its_prompt",
                    "no_unsupported_literal_identity_or_unseen_knowledge_claim",
                    "no_unmarked_bad_candidate_or_harmful_target",
                    "frame_language_is_bounded_and_non_theatrical",
                    "provenance_status_is_appropriate",
                ],
            }
        )
    queue_body = {
        "schema_version": "storyworld_recovered_extras_review_queue_v1",
        "source_id": manifest["source_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "normalization_manifest_sha256": sha256_file(normalization_manifest_path),
        "rows_sha256": sha256_file(rows_path),
        "review_policy": "every recovered row requires an explicit current content-bound receipt",
        "license_receipt_required": True,
        "review_tasks": tasks,
        "automatic_training_approval": False,
    }
    return {**queue_body, "queue_content_sha256": sha256_json(queue_body)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalization-manifest", type=Path, required=True)
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue = prepare_recovered_review(args.normalization_manifest, args.rows)
    write_json(args.output.resolve(), queue)
    print(
        json.dumps(
            {
                "schema_version": queue["schema_version"],
                "source_id": queue["source_id"],
                "review_tasks": len(queue["review_tasks"]),
                "license_receipt_required": True,
                "automatic_training_approval": False,
                "queue_content_sha256": queue["queue_content_sha256"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
