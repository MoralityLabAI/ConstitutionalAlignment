#!/usr/bin/env python3
"""Normalize the recovered four-arm SFT train split into provisional quota rows."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json, write_jsonl
from alignment_harness.trajectory_curriculum import TiktokenCounter, read_jsonl


DEFAULT_SOURCE = (
    REPO_ROOT
    / "experiments"
    / "storyworld_curriculum_v1"
    / "recovered_static_source_v1.json"
)
DEFAULT_RECIPE = (
    REPO_ROOT
    / "experiments"
    / "storyworld_curriculum_v1"
    / "token_recipe_10m_per_arm.json"
)


def _verify_file(root: Path, item: dict[str, Any]) -> Path:
    path = (root / str(item["path"])).resolve()
    if not path.is_file():
        raise ValueError(f"recovered source file is missing: {path}")
    observed = sha256_file(path)
    if observed != item["sha256"]:
        raise ValueError(f"recovered source hash mismatch for {path}: {observed}")
    return path


def normalize_source(
    source_root: Path,
    source_manifest_path: Path,
    recipe_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_root = Path(source_root).resolve()
    source_manifest_path = Path(source_manifest_path).resolve()
    recipe_path = Path(recipe_path).resolve()
    source = read_json(source_manifest_path)
    recipe = read_json(recipe_path)
    if source.get("schema_version") != "storyworld_recovered_static_source_v1":
        raise ValueError("unexpected recovered static source schema")
    if source["status"] != "provisional_pending_review_and_license_audit":
        raise ValueError("recovered source status must remain provisional")
    _verify_file(source_root, source["recovery_receipt"])
    _verify_file(source_root, source["dataset_manifest"])

    counter = TiktokenCounter()
    normalized: list[dict[str, Any]] = []
    seen_record_ids: set[str] = set()
    seen_content: set[str] = set()
    source_review_counts: Counter[str] = Counter()
    audit: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"rows": 0, "packed_tokens": 0, "assistant_tokens": 0})
    )
    for condition, arm in source["condition_to_arm"].items():
        file_item = source["train_files"][condition]
        train_path = _verify_file(source_root, file_item)
        rows = read_jsonl(train_path)
        if len(rows) != int(file_item["rows"]):
            raise ValueError(f"{condition}: recovered train row count drifted")
        for row in rows:
            if row.get("split") != "train":
                raise ValueError(f"{condition}: non-train row reached recovered normalizer")
            if row.get("condition") != condition:
                raise ValueError(f"{condition}: row condition mismatch")
            messages = row.get("messages")
            if not isinstance(messages, list) or [item.get("role") for item in messages] != [
                "system",
                "user",
                "assistant",
            ]:
                raise ValueError(f"{row.get('example_id')}: expected system/user/assistant messages")
            task_type = str(row["task_type"])
            slice_id = (
                "ordinary_helpfulness_guardrails"
                if task_type == "ordinary_helpful"
                else "static_identity_calibration"
            )
            review_status = str(row["provenance"]["review_status"])
            source_review_counts[f"{arm}|{review_status}"] += 1
            record_id = f"recovered_{row['example_id']}"
            if record_id in seen_record_ids:
                raise ValueError(f"duplicate recovered record_id: {record_id}")
            seen_record_ids.add(record_id)
            fingerprint = sha256_json(
                {"arm": arm, "slice": slice_id, "messages": messages}
            )
            if fingerprint in seen_content:
                raise ValueError(f"duplicate recovered training content: {row['example_id']}")
            seen_content.add(fingerprint)
            base = {
                "schema_version": "storyworld_training_view_v1",
                "record_id": record_id,
                "view": "sft_external_calibration",
                "slice": slice_id,
                "arm": arm,
                "source_trace_id": None,
                "world_id": None,
                "source_split": "train",
                "training_eligible": True,
                "training_approved": review_status == "approved",
                "messages": messages,
                "external_provenance": {
                    "source_id": source["source_id"],
                    "source_file_sha256": file_item["sha256"],
                    "example_id": row["example_id"],
                    "scenario_id": row["scenario_id"],
                    "task_type": task_type,
                    "identity_id": row["identity_id"],
                    "source_review_status": review_status,
                    "generator": row["provenance"].get("generator"),
                    "forbidden_language_flag": bool(
                        row["provenance"].get("forbidden_language_flag", False)
                    ),
                },
            }
            normalized_row = {**base, "record_sha256": sha256_json(base)}
            normalized.append(normalized_row)
            packed, assistant = counter.count_messages(messages)
            audit[arm][slice_id]["rows"] += 1
            audit[arm][slice_id]["packed_tokens"] += packed
            audit[arm][slice_id]["assistant_tokens"] += assistant

    expected = source["expected_cl100k_train_audit"]
    if json.loads(json.dumps(audit)) != expected:
        raise ValueError("recovered cl100k audit drifted from the frozen source manifest")

    quota_receipts: dict[str, Any] = {}
    for arm in recipe["arms"]:
        quota_receipts[arm] = {}
        for slice_id in ("static_identity_calibration", "ordinary_helpfulness_guardrails"):
            observed = audit[arm][slice_id]
            packed_target = int(recipe["slice_tokens"][slice_id])
            assistant_target = int(recipe["minimum_assistant_tokens_by_slice"][slice_id])
            quota_receipts[arm][slice_id] = {
                **observed,
                "packed_target_tokens": packed_target,
                "packed_shortfall_tokens": max(0, packed_target - observed["packed_tokens"]),
                "assistant_target_tokens": assistant_target,
                "assistant_shortfall_tokens": max(
                    0, assistant_target - observed["assistant_tokens"]
                ),
            }

    manifest = {
        "schema_version": "storyworld_recovered_extras_normalization_v1",
        "source_id": source["source_id"],
        "status": "provisional",
        "source_manifest_path": source_manifest_path.relative_to(REPO_ROOT).as_posix(),
        "source_manifest_sha256": sha256_file(source_manifest_path),
        "recipe_sha256": sha256_file(recipe_path),
        "rows": len(normalized),
        "rows_by_arm": dict(sorted(Counter(row["arm"] for row in normalized).items())),
        "rows_by_slice": dict(sorted(Counter(row["slice"] for row in normalized).items())),
        "source_review_status": dict(sorted(source_review_counts.items())),
        "training_approved_rows": sum(bool(row["training_approved"]) for row in normalized),
        "quota_receipts": quota_receipts,
        "excluded_splits": source["split_policy"]["excluded"],
        "claim_boundary": (
            "This normalization preserves recovered train messages and source review status. "
            "It does not approve, cycle, regenerate, or include validation/heldout rows."
        ),
        "passed": True,
    }
    return normalized, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize and audit the recovered four-arm static/helpfulness train data."
    )
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--recipe", type=Path, default=DEFAULT_RECIPE)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_manifest = read_json(args.source_manifest.resolve())
    source_root = (
        args.source_root.resolve()
        if args.source_root is not None
        else Path(source_manifest["source_root_hint"]).resolve()
    )
    rows, manifest = normalize_source(
        source_root,
        args.source_manifest,
        args.recipe,
    )
    if args.output_dir is not None:
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        rows_path = output_dir / "extra_rows.jsonl"
        write_jsonl(rows_path, rows)
        manifest["artifacts"] = {
            "extra_rows.jsonl": {
                "rows": len(rows),
                "sha256": sha256_file(rows_path),
            }
        }
        write_json(output_dir / "NORMALIZATION_MANIFEST.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
