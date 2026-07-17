#!/usr/bin/env python3
"""Harvest multi-effort agent work products into canonical storyworld traces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_world, sha256_file, write_json, write_jsonl
from alignment_harness.trajectory_curriculum import (
    CommandTeacher,
    FRAME_IDS,
    ScriptedTeacher,
    harvest_episode,
    load_teacher_ensemble,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", required=True)
    parser.add_argument("--ensemble", default="experiments/storyworld_curriculum_v1/teacher_ensemble.json")
    parser.add_argument("--frames", default=",".join(FRAME_IDS))
    parser.add_argument("--seeds", default="42")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--teacher", choices=("command", "fixture"), default="command")
    parser.add_argument("--agent-command")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument(
        "--actor-schedule",
        default="single",
        help="single, dyadic, or a comma-separated schedule of declared agent IDs",
    )
    parser.add_argument("--fixture-actor-strategy", choices=("first", "middle", "last"), default="last")
    parser.add_argument("--fixture-adjudicator-strategy", choices=("first", "middle", "last"), default="first")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    world_path = (REPO_ROOT / args.world).resolve()
    ensemble_path = (REPO_ROOT / args.ensemble).resolve()
    world = read_world(world_path)
    ensemble = load_teacher_ensemble(ensemble_path)
    frames = [item.strip() for item in args.frames.split(",") if item.strip()]
    if not frames or any(frame not in FRAME_IDS for frame in frames):
        raise ValueError(f"--frames must be a comma-separated subset of {FRAME_IDS}")
    seeds = [int(item.strip()) for item in args.seeds.split(",") if item.strip()]
    if not seeds:
        raise ValueError("at least one seed is required")
    if args.teacher == "command":
        if not args.agent_command:
            raise ValueError("--agent-command is required for command teachers")
        teacher = CommandTeacher.from_text(args.agent_command, args.timeout_seconds)
    else:
        teacher = ScriptedTeacher(
            actor_strategy=args.fixture_actor_strategy,
            adjudicator_strategy=args.fixture_adjudicator_strategy,
        )
    declared_agents = [str(item["agent_id"]) for item in world["agents"]]
    if args.actor_schedule == "single":
        actor_schedule = [str(world["actor_agent_id"])]
    elif args.actor_schedule == "dyadic":
        if len(declared_agents) < 2:
            raise ValueError("--actor-schedule dyadic requires at least two declared agents")
        actor_schedule = declared_agents[:2]
    else:
        actor_schedule = [
            item.strip() for item in args.actor_schedule.split(",") if item.strip()
        ]
    traces = [
        harvest_episode(
            world,
            frame,
            seed,
            teacher,
            ensemble,
            world_source_path=world_path.as_posix(),
            actor_schedule=actor_schedule,
        )
        for seed in seeds
        for frame in frames
    ]
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    traces_path = output_dir / "traces.jsonl"
    write_jsonl(traces_path, traces)
    manifest = {
        "schema_version": "storyworld_trace_harvest_manifest_v1",
        "world_path": world_path.as_posix(),
        "world_source_sha256": sha256_file(world_path),
        "resolved_world_id": world["world_id"],
        "ensemble_path": ensemble_path.as_posix(),
        "ensemble_sha256": sha256_file(ensemble_path),
        "frames": frames,
        "seeds": seeds,
        "actor_schedule": actor_schedule,
        "teacher": teacher.receipt(),
        "traces": len(traces),
        "turns": sum(len(trace["turns"]) for trace in traces),
        "training_approved_traces": sum(bool(trace["release"]["training_approved"]) for trace in traces),
        "traces_path": traces_path.name,
        "traces_sha256": sha256_file(traces_path),
    }
    write_json(output_dir / "HARVEST_MANIFEST.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
