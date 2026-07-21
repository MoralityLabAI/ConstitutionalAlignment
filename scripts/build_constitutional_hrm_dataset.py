#!/usr/bin/env python3
"""Build matched HRM-format constitutional decision datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitutional_hrm import build_arm_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--constitution", type=Path, default=Path("constitution.md"))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/constitutional_hrm_v1/datasets"),
    )
    parser.add_argument(
        "--arms",
        nargs="+",
        choices=("constitutional", "utility", "shuffled"),
        default=("constitutional", "utility", "shuffled"),
    )
    parser.add_argument("--seed", type=int, default=713)
    parser.add_argument("--train-groups", type=int, default=64)
    parser.add_argument("--id-groups", type=int, default=24)
    parser.add_argument("--ood-groups", type=int, default=24)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifests = []
    for arm in args.arms:
        manifests.append(
            build_arm_dataset(
                output_dir=args.output_root / arm,
                constitution_path=args.constitution,
                arm=arm,
                seed=args.seed,
                train_groups=args.train_groups,
                id_groups=args.id_groups,
                ood_groups=args.ood_groups,
            )
        )
    print(json.dumps({"status": "completed", "manifests": manifests}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
