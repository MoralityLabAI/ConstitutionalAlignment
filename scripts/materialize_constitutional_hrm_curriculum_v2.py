#!/usr/bin/env python3
"""Materialize the deterministic matched curriculum for constitutional HRM v2."""

from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitutional_hrm_curriculum_v2 import (  # noqa: E402
    materialize_curriculum,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "curriculum_smoke",
    )
    parser.add_argument(
        "--tokenizer",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "tokenizer"
        / "tokenizer.json",
    )
    parser.add_argument(
        "--prompt-bundle",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "generated"
        / "system_prompt_bundle_v2.json",
    )
    parser.add_argument(
        "--constitution", type=Path, default=REPO_ROOT / "constitution.md"
    )
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--seed", type=int, default=20260728)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = materialize_curriculum(
        output_dir=args.output_dir.resolve(),
        tokenizer_path=args.tokenizer.resolve(),
        prompt_bundle_path=args.prompt_bundle.resolve(),
        constitution_path=args.constitution.resolve(),
        production=args.production,
        seed=args.seed,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
        if hasattr(torch.cuda, "ipc_collect"):
            torch.cuda.ipc_collect()
    return 0 if manifest["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
