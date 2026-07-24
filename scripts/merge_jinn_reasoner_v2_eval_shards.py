#!/usr/bin/env python3
"""Merge serial Jinn v2 evaluation shards with an exact prompt-universe join."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", type=Path, action="append", required=True)
    parser.add_argument("--expected-prompts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    shard_paths = [path.resolve() for path in args.shard]
    expected_path = args.expected_prompts.resolve()
    expected_rows = read_jsonl(expected_path)
    expected_ids = [row["probe_id"] for row in expected_rows]
    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("expected prompt ids are not unique")

    rows = [row for path in shard_paths for row in read_jsonl(path)]
    row_ids = [row["example_id"] for row in rows]
    if len(row_ids) != len(set(row_ids)):
        raise ValueError("evaluation shards contain duplicate example ids")
    missing = sorted(set(expected_ids).difference(row_ids))
    extra = sorted(set(row_ids).difference(expected_ids))
    if missing or extra:
        raise ValueError(f"evaluation join mismatch: missing={missing}, extra={extra}")
    by_id = {row["example_id"]: row for row in rows}
    ordered_rows = [by_id[example_id] for example_id in expected_ids]

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in ordered_rows),
        encoding="utf-8",
        newline="\n",
    )
    receipt = {
        "schema_version": "jinn_reasoner_v2_eval_shard_merge_v1",
        "status": "complete",
        "rows": len(ordered_rows),
        "expected_prompts_sha256": sha256_file(expected_path),
        "shards": [
            {
                "path": str(path),
                "rows": len(read_jsonl(path)),
                "sha256": sha256_file(path),
            }
            for path in shard_paths
        ],
        "missing_ids": [],
        "extra_ids": [],
        "duplicate_ids": [],
        "output_path": str(output_path),
        "output_sha256": sha256_file(output_path),
    }
    receipt_path = args.receipt.resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
