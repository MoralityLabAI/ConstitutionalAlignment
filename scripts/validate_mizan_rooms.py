#!/usr/bin/env python3
"""Validate the Mizan Rooms package, schemas, split boundaries, and cue matching."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.mizan_rooms import validate_package, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        default="experiments/mizan_rooms_v1/suite.json",
        help="Suite path relative to the repository root",
    )
    parser.add_argument("--output", help="Optional validation receipt path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = validate_package(REPO_ROOT, REPO_ROOT / args.suite)
    if args.output:
        write_json(Path(args.output), receipt)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
