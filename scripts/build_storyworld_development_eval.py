#!/usr/bin/env python3
"""Build public development items and a separate deterministic scoring key."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworld_evaluation import (
    build_development_evaluation,
    write_development_evaluation,
)


DEFAULT_PACKAGE = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "package.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-provisional", action="store_true")
    args = parser.parse_args()
    public, keys, manifest = build_development_evaluation(
        REPO_ROOT,
        args.package.resolve(),
        allow_provisional=args.allow_provisional,
    )
    complete = write_development_evaluation(args.output_dir.resolve(), public, keys, manifest)
    print(json.dumps(complete, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
