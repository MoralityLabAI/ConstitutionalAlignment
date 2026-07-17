#!/usr/bin/env python3
"""Validate the manifest-only causal-family split freeze and write its receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import (
    DEFAULT_SPLIT_FREEZE_SCHEMA,
    read_json,
    sha256_file,
    validate_split_freeze,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        default="experiments/storyworld_curriculum_v1/source_inventory.json",
    )
    parser.add_argument(
        "--split-freeze",
        default="experiments/storyworld_curriculum_v1/split_freeze_v1.json",
    )
    parser.add_argument("--output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory_path = (REPO_ROOT / args.inventory).resolve()
    freeze_path = (REPO_ROOT / args.split_freeze).resolve()
    receipt = validate_split_freeze(
        read_json(inventory_path),
        read_json(freeze_path),
        repo_root=REPO_ROOT,
        schema_path=DEFAULT_SPLIT_FREEZE_SCHEMA,
    )
    receipt["inputs"] = {
        "inventory_path": inventory_path.relative_to(REPO_ROOT).as_posix(),
        "inventory_sha256": sha256_file(inventory_path),
        "split_freeze_path": freeze_path.relative_to(REPO_ROOT).as_posix(),
        "split_freeze_sha256": sha256_file(freeze_path),
        "schema_path": DEFAULT_SPLIT_FREEZE_SCHEMA.relative_to(REPO_ROOT).as_posix(),
        "schema_sha256": sha256_file(DEFAULT_SPLIT_FREEZE_SCHEMA),
    }
    if args.output:
        write_json(Path(args.output).resolve(), receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
