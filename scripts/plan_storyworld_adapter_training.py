#!/usr/bin/env python3
"""Emit the no-spend four-arm adapter checkpoint plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.adapter_training import build_adapter_training_plan
from alignment_harness.storyworlds import write_json


DEFAULT_PACKAGE = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "package.json"
DEFAULT_TOKEN_RECIPE = (
    REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "token_recipe_10m_per_arm.json"
)
DEFAULT_TRAINING_RECIPE = (
    REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "adapter_training_recipe_v1.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--token-recipe", type=Path, default=DEFAULT_TOKEN_RECIPE)
    parser.add_argument("--training-recipe", type=Path, default=DEFAULT_TRAINING_RECIPE)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_adapter_training_plan(args.package, args.token_recipe, args.training_recipe)
    if args.output is not None:
        write_json(args.output.resolve(), plan)
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
