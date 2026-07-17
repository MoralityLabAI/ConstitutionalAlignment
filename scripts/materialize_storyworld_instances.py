#!/usr/bin/env python3
"""Materialize a validated matched-pair storyworld parameter sweep."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import materialize_instance_sweep, write_json


DEFAULT_SWEEP = (
    "experiments/storyworld_curriculum_v1/instance_sweeps/"
    "shura_payroll_cutover_sweep_v1.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", default=DEFAULT_SWEEP)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sweep_path = (REPO_ROOT / args.sweep).resolve()
    output_dir = Path(args.output_dir).resolve()
    worlds, receipt = materialize_instance_sweep(REPO_ROOT, sweep_path)
    world_entries = []
    for world in sorted(worlds, key=lambda item: str(item["world_id"])):
        relative_path = Path("worlds") / f"{world['world_id']}.json"
        write_json(output_dir / relative_path, world)
        world_entries.append(
            {
                "world_id": world["world_id"],
                "profile_id": world["instance_provenance"]["profile_id"],
                "skin_id": world["matched_pair"]["skin_id"],
                "path": relative_path.as_posix(),
            }
        )
    receipt["materialized_paths"] = world_entries
    write_json(output_dir / "INSTANCE_SWEEP_RECEIPT.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
