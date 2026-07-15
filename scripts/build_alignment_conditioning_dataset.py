#!/usr/bin/env python3
"""Build the storyworld conditioning and GRPO prompt datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitution import load_constitution
from alignment_harness.dataset import build_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/alignment_conditioning_v1.json")
    parser.add_argument("--output-dir", default="", help="Override config output_dir.")
    parser.add_argument("--constitution", default="", help="Override config constitution_path.")
    return parser.parse_args()


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def main() -> int:
    args = parse_args()
    config_path = resolve_repo_path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    constitution_path = resolve_repo_path(args.constitution or config["constitution_path"])
    output_dir = resolve_repo_path(args.output_dir or config["output_dir"])
    constitution = load_constitution(constitution_path)
    manifest = build_dataset(
        config=config,
        constitution=constitution,
        repo_root=REPO_ROOT,
        output_dir=output_dir,
    )
    summary = {
        "output_dir": str(output_dir),
        "source_rows": manifest["source_audit"]["physical_rows"],
        "source_reported_tokens": manifest["source_audit"]["reported_tokens"],
        "conditioning_rows": manifest["conditioning_corpus"]["retained_after_near_duplicate_cap"],
        "rl_unique_scenarios": manifest["conditioning_corpus"]["rl_unique_scenarios"],
        "hidden_reasoning_rows_used": 0,
        "research_only": manifest["research_only"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
