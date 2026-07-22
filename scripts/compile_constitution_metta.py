#!/usr/bin/env python3
"""Compile constitution.md into a MeTTa kernel and hash-bound prompt bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitutional_metta import (  # noqa: E402
    compile_constitution_to_metta,
    render_prompt_bundle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--constitution", type=Path, default=Path("constitution.md"))
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    compilation = compile_constitution_to_metta(args.constitution)
    prompts = render_prompt_bundle(args.constitution)
    (args.output_dir / "constitution_kernel_v2.metta").write_text(
        compilation["metta_text"], encoding="utf-8", newline="\n"
    )
    receipt = {key: value for key, value in compilation.items() if key != "metta_text"}
    (args.output_dir / "constitution_kernel_v2.receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "system_prompt_bundle_v2.json").write_text(
        json.dumps(prompts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for prompt_id, prompt in prompts["prompts"].items():
        (args.output_dir / f"{prompt_id}.txt").write_text(
            prompt["text"] + "\n", encoding="utf-8", newline="\n"
        )
    print(json.dumps({"status": "completed", "compilation": receipt, "prompts": prompts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
