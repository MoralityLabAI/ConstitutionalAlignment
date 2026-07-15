#!/usr/bin/env python3
"""Independently audit a built alignment-conditioning artifact."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", default="artifacts/alignment_conditioning_v1")
    parser.add_argument(
        "--schema",
        default="schemas/alignment_conditioning_record_v1.schema.json",
    )
    return parser.parse_args()


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def audit(artifact_dir: Path, schema_path: Path) -> dict[str, Any]:
    manifest = load_json(artifact_dir / "manifest.json")
    canonical = load_jsonl(artifact_dir / "canonical.jsonl")
    validator = Draft202012Validator(load_json(schema_path))
    schema_errors = []
    for index, row in enumerate(canonical, start=1):
        schema_errors.extend(
            f"row {index} {error.json_path}: {error.message}"
            for error in validator.iter_errors(row)
        )

    cluster_splits: dict[str, set[str]] = defaultdict(set)
    for row in canonical:
        cluster_splits[row["deduplication"]["near_duplicate_cluster_id"]].add(row["split"])
    cross_split_clusters = {
        cluster_id: sorted(splits)
        for cluster_id, splits in cluster_splits.items()
        if len(splits) > 1
    }

    exclude_patterns = {
        pattern.lower()
        for source in manifest["config"]["sources"]
        for pattern in source.get("exclude_path_patterns", [])
    }
    excluded_source_leaks = sorted(
        {
            row["provenance"]["source_path"]
            for row in canonical
            if any(
                fnmatch.fnmatch(row["provenance"]["source_path"].lower(), pattern)
                for pattern in exclude_patterns
            )
        }
    )

    rl_rows = {
        split: load_jsonl(artifact_dir / f"rl_{split}.jsonl")
        for split in ("train", "validation", "test")
    }
    rl_ids = {
        split: {row["example_id"] for row in rows}
        for split, rows in rl_rows.items()
    }
    rl_overlap = {
        "train_validation": sorted(rl_ids["train"] & rl_ids["validation"]),
        "train_test": sorted(rl_ids["train"] & rl_ids["test"]),
        "validation_test": sorted(rl_ids["validation"] & rl_ids["test"]),
    }
    expected_counts = manifest["conditioning_corpus"]["rl_split_counts"]
    actual_counts = {split: len(rows) for split, rows in rl_rows.items()}
    count_mismatches = {
        split: {"manifest": expected_counts.get(split), "actual": actual}
        for split, actual in actual_counts.items()
        if expected_counts.get(split) != actual
    }
    build_receipt = manifest.get("build_receipt", {})
    expected_file_hashes = build_receipt.get("generated_file_sha256", {})
    generated_file_hash_mismatches = {
        name: {
            "manifest": expected_hash,
            "actual": (
                sha256_file(artifact_dir / name)
                if (artifact_dir / name).is_file()
                else None
            ),
        }
        for name, expected_hash in expected_file_hashes.items()
        if not (artifact_dir / name).is_file()
        or sha256_file(artifact_dir / name) != expected_hash
    }
    builder_module = REPO_ROOT / "alignment_harness" / "dataset.py"
    builder_hash_matches = (
        build_receipt.get("builder_module_sha256") == sha256_file(builder_module)
    )
    config_hash_matches = (
        build_receipt.get("config_sha256") == sha256_json(manifest["config"])
    )

    report = {
        "artifact_dir": artifact_dir.as_posix(),
        "canonical_rows": len(canonical),
        "schema_error_count": len(schema_errors),
        "schema_errors": schema_errors[:20],
        "cross_split_clusters": cross_split_clusters,
        "excluded_source_leaks": excluded_source_leaks,
        "rl_split_counts": actual_counts,
        "rl_count_mismatches": count_mismatches,
        "generated_file_hash_mismatches": generated_file_hash_mismatches,
        "builder_hash_matches": builder_hash_matches,
        "config_hash_matches": config_hash_matches,
        "rl_id_overlap": {key: len(value) for key, value in rl_overlap.items()},
        "rl_train_sha256": sha256_file(artifact_dir / "rl_train.jsonl"),
        "passed": not any(
            (
                schema_errors,
                cross_split_clusters,
                excluded_source_leaks,
                count_mismatches,
                generated_file_hash_mismatches,
                not builder_hash_matches,
                not config_hash_matches,
                *rl_overlap.values(),
            )
        ),
    }
    return report


def main() -> int:
    args = parse_args()
    report = audit(resolve_path(args.artifact_dir), resolve_path(args.schema))
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
