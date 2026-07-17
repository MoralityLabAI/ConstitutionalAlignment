#!/usr/bin/env python3
"""Validate and optionally compile the storyworld curriculum package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import (
    read_json,
    read_world,
    validate_curriculum_package,
    write_json,
    write_metta_compilation,
)


DEFAULT_PACKAGE = "experiments/storyworld_curriculum_v1/package.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--output-dir")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_path = (REPO_ROOT / args.package).resolve()
    receipt = validate_curriculum_package(REPO_ROOT, package_path)
    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        package = read_json(package_path)
        metta_receipts = []
        for item in package["worlds"]:
            world = read_world(REPO_ROOT / item["path"])
            metta_receipts.append(
                write_metta_compilation(
                    world,
                    output_dir / "metta" / f"{world['world_id']}.metta",
                )
            )
        receipt["metta_compilations"] = metta_receipts
        write_json(output_dir / "VALIDATION_RECEIPT.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
