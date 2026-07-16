#!/usr/bin/env python3
"""Batch-export constitutional prompting runs into corpus shards."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--glob", default="*")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    script_path = Path(__file__).resolve().parent / "export_constitution_corpus_shard.py"
    runs_root = Path(args.runs_root).resolve()
    output_root = Path(args.output_root).resolve()
    ensure_dir(output_root)

    run_dirs: List[Path] = [p for p in sorted(runs_root.glob(args.glob)) if p.is_dir()]
    if not run_dirs:
        raise SystemExit(f"No run dirs matched {args.glob} under {runs_root}")

    for run_dir in run_dirs:
        out_jsonl = output_root / f"{run_dir.name}.jsonl"
        if out_jsonl.exists() and not args.overwrite:
            print(f"skip {out_jsonl}")
            continue
        cmd = [
            sys.executable,
            str(script_path),
            "--run-dir",
            str(run_dir),
            "--output-jsonl",
            str(out_jsonl),
        ]
        subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
