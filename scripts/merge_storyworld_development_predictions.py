#!/usr/bin/env python3
"""Merge complete, disjoint development prediction shards before private scoring."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json, write_jsonl
from alignment_harness.trajectory_curriculum import read_jsonl


def merge_predictions(
    development_manifest_path: Path,
    prediction_paths: list[Path],
    *,
    arm: str,
    checkpoint_tokens: int,
) -> tuple[list[dict], dict]:
    development_manifest_path = development_manifest_path.resolve()
    manifest = read_json(development_manifest_path)
    if manifest.get("schema_version") != "storyworld_development_eval_manifest_v1":
        raise ValueError("unexpected development evaluation manifest")
    public_path = development_manifest_path.parent / manifest["public_items"]["path"]
    if sha256_file(public_path) != manifest["public_items"]["sha256"]:
        raise ValueError("development public items drifted")
    expected_ids = {str(item["item_id"]) for item in read_jsonl(public_path)}
    by_id = {}
    artifacts = []
    for value in prediction_paths:
        path = value.resolve()
        rows = read_jsonl(path)
        artifacts.append({"path": str(path), "rows": len(rows), "sha256": sha256_file(path)})
        for row in rows:
            if row.get("schema_version") != "storyworld_development_eval_prediction_v1":
                raise ValueError(f"unexpected prediction schema in {path}")
            item_id = str(row.get("item_id", ""))
            if item_id not in expected_ids:
                raise ValueError(f"unknown development item ID: {item_id}")
            if item_id in by_id:
                raise ValueError(f"duplicate development prediction: {item_id}")
            by_id[item_id] = row
    missing = sorted(expected_ids - set(by_id))
    if missing:
        raise ValueError(f"development prediction merge is incomplete: {len(missing)} missing")
    merged = [by_id[item_id] for item_id in sorted(by_id)]
    receipt = {
        "schema_version": "storyworld_development_prediction_merge_v1",
        "suite_id": manifest["suite_id"],
        "development_manifest_sha256": sha256_file(development_manifest_path),
        "public_items_sha256": sha256_file(public_path),
        "arm": arm,
        "checkpoint_tokens": int(checkpoint_tokens),
        "source_artifacts": artifacts,
        "items": len(merged),
        "item_ids_sha256": sha256_json(sorted(by_id)),
        "complete": True,
        "private_key_opened": False,
        "sealed_evaluation_opened": False,
        "passed": True,
    }
    return merged, receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--prediction", type=Path, action="append", required=True)
    parser.add_argument("--arm", choices=("neutral", "constitutional", "jinn", "beast"), required=True)
    parser.add_argument("--checkpoint-tokens", type=int, choices=(1000000, 3000000, 6000000, 10000000), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    merged, receipt = merge_predictions(
        args.development_manifest,
        args.prediction,
        arm=args.arm,
        checkpoint_tokens=args.checkpoint_tokens,
    )
    output_path = args.output.resolve()
    write_jsonl(output_path, merged)
    receipt["merged_predictions_sha256"] = sha256_file(output_path)
    write_json(args.receipt.resolve(), receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
