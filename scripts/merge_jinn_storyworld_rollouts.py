#!/usr/bin/env python3
"""Merge complete local storyworld rollout shards with exact-universe checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.local_storyworld_dag import (  # noqa: E402
    ACTION_PARSER_VERSION,
    ROLLOUT_SCHEMA,
    cycle_config,
    load_jsonl,
    load_plan,
    summarize_rollouts,
)
from alignment_harness.storyworlds import (  # noqa: E402
    read_world,
    sha256_file,
    write_json,
    write_jsonl,
)


DEFAULT_PLAN = REPO_ROOT / "experiments" / "local_storyworld_dag_v1" / "cycle_plan.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--cycle", type=int, required=True)
    parser.add_argument("--lane", choices=("train", "holdout"), required=True)
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def resolve_world_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def expected_universe(
    plan: dict[str, Any], cycle: int, lane: str
) -> set[tuple[str, int]]:
    config = cycle_config(plan, cycle)
    if lane == "train":
        entries = config["train_worlds"]
        seeds = config["train_seeds"]
    else:
        entries = plan["holdout_worlds"]
        seeds = plan["holdout_seeds"]
    world_ids = [str(read_world(resolve_world_path(item["path"]))["world_id"]) for item in entries]
    return {(world_id, int(seed)) for world_id in world_ids for seed in seeds}


def main() -> int:
    args = parse_args()
    plan, plan_receipt = load_plan(Path(args.plan))
    config = cycle_config(plan, args.cycle)
    inputs = [Path(value).resolve() for value in args.input]
    episodes: list[dict[str, Any]] = []
    source_receipts: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for path in inputs:
        rows = load_jsonl(path)
        if not rows:
            raise ValueError(f"empty rollout shard: {path}")
        source_receipts.append(
            {"path": str(path), "sha256": sha256_file(path), "episodes": len(rows)}
        )
        for episode in rows:
            if episode.get("schema_version") != ROLLOUT_SCHEMA:
                raise ValueError(f"unexpected rollout schema in {path}")
            if int(episode.get("cycle", -1)) != args.cycle:
                raise ValueError(f"cycle mismatch in {path}")
            if episode.get("lane") != args.lane:
                raise ValueError(f"lane mismatch in {path}")
            if episode.get("plan_sha256") != plan_receipt["plan_sha256"]:
                raise ValueError(f"plan hash mismatch in {path}")
            if episode.get("action_parser_version") != ACTION_PARSER_VERSION:
                raise ValueError(f"action parser version mismatch in {path}")
            if not episode.get("terminal"):
                raise ValueError(f"non-terminal episode in {path}")
            key = (str(episode["world_id"]), int(episode["seed"]))
            if key in seen:
                raise ValueError(f"duplicate episode across shards: {key}")
            seen.add(key)
            episodes.append(episode)

    expected = expected_universe(plan, args.cycle, args.lane)
    if seen != expected:
        raise ValueError(
            f"merged universe mismatch; missing={sorted(expected - seen)} extra={sorted(seen - expected)}"
        )
    episodes.sort(key=lambda item: (str(item["world_id"]), int(item["seed"])))
    summary = summarize_rollouts(episodes, float(config["acceptance_threshold"]))
    summary.update(
        {
            "experiment_id": plan["experiment_id"],
            "cycle": int(args.cycle),
            "lane": args.lane,
            "plan_sha256": plan_receipt["plan_sha256"],
            "episode_universe_total": len(expected),
            "merged_shards": len(inputs),
        }
    )

    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    rollout_path = output_dir / "storyworld_rollouts.jsonl"
    summary_path = output_dir / "storyworld_summary.json"
    write_jsonl(rollout_path, episodes)
    write_json(summary_path, summary)
    receipt = {
        "schema_version": "local_storyworld_dag_merge_receipt_v1",
        "status": "complete",
        "cycle": int(args.cycle),
        "lane": args.lane,
        "plan_sha256": plan_receipt["plan_sha256"],
        "inputs": source_receipts,
        "rollout_path": str(rollout_path),
        "rollout_sha256": sha256_file(rollout_path),
        "summary_path": str(summary_path),
        "summary_sha256": sha256_file(summary_path),
        "episodes": len(episodes),
        "turns": summary["turns"],
        "claim_boundary": plan["claim_boundary"],
    }
    write_json(output_dir / "merge_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
