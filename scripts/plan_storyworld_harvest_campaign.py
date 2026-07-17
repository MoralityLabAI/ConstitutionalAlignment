#!/usr/bin/env python3
"""Plan balanced, replayable GPT-5.6 storyworld harvest jobs without calling an API."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import (
    materialize_instance_sweep,
    read_json,
    sha256_file,
    sha256_json,
    validate_curriculum_package,
    validate_world,
    write_json,
    write_jsonl,
)


DEFAULT_CAMPAIGN = (
    REPO_ROOT
    / "experiments"
    / "storyworld_curriculum_v1"
    / "harvest_campaign_10m_v1.json"
)


def _review_approved(world: dict[str, Any]) -> bool:
    return world["review"]["status"] == "approved" and all(
        item["status"] in {"approved", "not_required"}
        for item in world["review"]["requirements"]
    )


def _validate_campaign_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != "storyworld_harvest_campaign_plan_v1":
        raise ValueError("unexpected harvest campaign schema")
    if config["status"] != "planning_estimate_not_spend_authorization":
        raise ValueError("campaign must remain a planning estimate before the real pilot")
    arms = list(map(str, config["arms"]))
    if set(arms) != {"neutral", "constitutional", "jinn", "beast"}:
        raise ValueError("campaign must cover all four adapter arms")
    family_count = int(config["train_family_count"])
    per_family = int(config["traces_per_family_per_arm"])
    if family_count * per_family != int(config["traces_per_arm"]):
        raise ValueError("campaign per-family trace allocation does not sum per arm")
    mix = {str(key): float(value) for key, value in config["actor_schedule_mix"].items()}
    if set(mix) != {"single", "dyadic"} or abs(sum(mix.values()) - 1.0) > 1e-9:
        raise ValueError("actor schedule mix must contain single and dyadic shares summing to one")
    if per_family % 2 or mix != {"single": 0.5, "dyadic": 0.5}:
        raise ValueError("v1 planner requires an even 50/50 per-family schedule allocation")
    if config["teacher_mode"] != "command":
        raise ValueError("real campaign cannot use the scripted fixture teacher")
    if not isinstance(config.get("token_calibration"), dict):
        raise ValueError("campaign requires a token_calibration receipt")


def build_campaign_plan(
    repo_root: Path,
    campaign_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    repo_root = Path(repo_root).resolve()
    campaign_path = Path(campaign_path).resolve()
    config = read_json(campaign_path)
    _validate_campaign_config(config)
    package_path = (repo_root / str(config["package_path"])).resolve()
    package = read_json(package_path)
    package_receipt = validate_curriculum_package(repo_root, package_path)
    recipe_path = (repo_root / str(config["recipe_path"])).resolve()
    recipe = read_json(recipe_path)
    ensemble_path = (repo_root / str(config["teacher_ensemble_path"])).resolve()

    worlds_by_family: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    sweep_by_world: dict[str, str] = {}
    for sweep_value in package["instance_sweeps"]:
        sweep_path = (repo_root / str(sweep_value)).resolve()
        worlds, _ = materialize_instance_sweep(repo_root, sweep_path)
        for world in worlds:
            if world["source_split"] != "train":
                continue
            world_id = str(world["world_id"])
            family_id = str(world["family_id"])
            worlds_by_family[family_id][world_id] = world
            sweep_by_world[world_id] = sweep_path.relative_to(repo_root).as_posix()

    family_ids = sorted(worlds_by_family)
    if len(family_ids) != int(config["train_family_count"]):
        raise ValueError(
            f"campaign expected {config['train_family_count']} train families; found {len(family_ids)}"
        )
    if any(not variants for variants in worlds_by_family.values()):
        raise ValueError("campaign family has no materialized instances")
    all_instances = [
        world for family in worlds_by_family.values() for world in family.values()
    ]
    instance_receipts = {
        str(world["world_id"]): validate_world(world) for world in all_instances
    }
    if any(len(world["agents"]) < 2 for world in all_instances):
        raise ValueError("dyadic campaign requires at least two declared agents in every train instance")
    if any(receipt["path_turns_min"] != 6 for receipt in instance_receipts.values()):
        raise ValueError("v1 campaign call projection requires six-turn train instances")
    if any(receipt["path_turns_max"] != 6 for receipt in instance_receipts.values()):
        raise ValueError("v1 campaign call projection requires six-turn train instances")

    jobs: list[dict[str, Any]] = []
    pilot_ids: set[str] = set()
    per_family = int(config["traces_per_family_per_arm"])
    pilot_per_family = int(config["pilot_traces_per_family_per_arm"])
    for arm_index, arm in enumerate(map(str, config["arms"])):
        for family_id in family_ids:
            variants = [worlds_by_family[family_id][key] for key in sorted(worlds_by_family[family_id])]
            for ordinal in range(per_family):
                world = variants[(ordinal + arm_index) % len(variants)]
                provenance = world["instance_provenance"]
                schedule_mode = "single" if ordinal % 2 == 0 else "dyadic"
                actor = str(world["actor_agent_id"])
                other_agents = [
                    str(item["agent_id"])
                    for item in world["agents"]
                    if str(item["agent_id"]) != actor
                ]
                actor_schedule = [actor] if schedule_mode == "single" else [actor, *other_agents]
                seed_payload = {
                    "campaign_seed": int(config["seed"]),
                    "arm": arm,
                    "family_id": family_id,
                    "world_id": world["world_id"],
                    "ordinal": ordinal,
                }
                digest = sha256_json(seed_payload)
                episode_seed = max(1, int(digest[:8], 16) & 0x7FFFFFFF)
                job_id = f"job_{digest[:24]}"
                job = {
                    "schema_version": "storyworld_harvest_job_v1",
                    "job_id": job_id,
                    "campaign_id": config["campaign_id"],
                    "arm": arm,
                    "family_id": family_id,
                    "sweep_path": sweep_by_world[str(world["world_id"])],
                    "profile_id": provenance["profile_id"],
                    "world_id": world["world_id"],
                    "world_content_sha256": sha256_json(world),
                    "transition_graph_sha256": instance_receipts[str(world["world_id"])][
                        "transition_graph_sha256"
                    ],
                    "episode_seed": episode_seed,
                    "actor_schedule_mode": schedule_mode,
                    "actor_schedule": actor_schedule,
                    "teacher_mode": "command",
                    "agent_command": config["agent_command"],
                    "source_split": "train",
                    "training_eligible": True,
                    "review_status": world["review"]["status"],
                    "execution_eligible": _review_approved(world),
                    "pilot_job": ordinal < pilot_per_family,
                    "family_ordinal": ordinal,
                }
                jobs.append(job)
                if ordinal < pilot_per_family:
                    pilot_ids.add(job_id)

    jobs.sort(key=lambda item: sha256_json({"seed": config["seed"], "job_id": item["job_id"]}))
    shard_size = int(config["shard_size"])
    remaining_index = 0
    for index, job in enumerate(jobs):
        job["campaign_index"] = index
        if job["pilot_job"]:
            job["shard_index"] = None
            job["shard_offset"] = None
        else:
            job["shard_index"] = remaining_index // shard_size
            job["shard_offset"] = remaining_index % shard_size
            remaining_index += 1

    if len({job["job_id"] for job in jobs}) != len(jobs):
        raise ValueError("campaign planner produced duplicate job IDs")
    if any(job["source_split"] != "train" for job in jobs):
        raise ValueError("non-training job reached campaign plan")

    arm_counts = Counter(str(job["arm"]) for job in jobs)
    family_counts = Counter(str(job["family_id"]) for job in jobs)
    schedule_counts = Counter(str(job["actor_schedule_mode"]) for job in jobs)
    family_arm_counts: dict[str, dict[str, int]] = defaultdict(dict)
    for family_id in family_ids:
        for arm in map(str, config["arms"]):
            family_arm_counts[family_id][arm] = sum(
                job["family_id"] == family_id and job["arm"] == arm for job in jobs
            )

    calibration = config["token_calibration"]
    traces_per_arm = int(config["traces_per_arm"])
    unique_instances_per_arm = len(all_instances)
    projections: dict[str, Any] = {}
    for slice_id, values in calibration["per_trace"].items():
        projections[slice_id] = {
            "estimated_available_packed_tokens_per_arm": traces_per_arm
            * int(values["packed_tokens"]),
            "estimated_available_assistant_tokens_per_arm": traces_per_arm
            * int(values["assistant_tokens"]),
            "packed_target_tokens_per_arm": int(recipe["slice_tokens"][slice_id]),
            "assistant_minimum_tokens_per_arm": int(
                recipe["minimum_assistant_tokens_by_slice"][slice_id]
            ),
        }
    for slice_id, values in calibration["per_unique_world_arm"].items():
        projections[slice_id] = {
            "estimated_available_packed_tokens_per_arm": unique_instances_per_arm
            * int(values["packed_tokens"]),
            "estimated_available_assistant_tokens_per_arm": unique_instances_per_arm
            * int(values["assistant_tokens"]),
            "packed_target_tokens_per_arm": int(recipe["slice_tokens"][slice_id]),
            "assistant_minimum_tokens_per_arm": int(
                recipe["minimum_assistant_tokens_by_slice"][slice_id]
            ),
        }
    for values in projections.values():
        values["estimated_packed_coverage"] = (
            values["estimated_available_packed_tokens_per_arm"]
            >= values["packed_target_tokens_per_arm"]
        )
        values["estimated_assistant_coverage"] = (
            values["estimated_available_assistant_tokens_per_arm"]
            >= values["assistant_minimum_tokens_per_arm"]
        )

    pending_review_worlds = sorted(
        {
            str(item["world_id"])
            for item in package_receipt["worlds"]
            if item["source_split"] == "train"
            and not _review_approved(
                next(
                    world
                    for world in all_instances
                    if world["instance_provenance"]["base_world_id"] == item["world_id"]
                )
            )
        }
    )
    pilot_jobs = [job for job in jobs if job["job_id"] in pilot_ids]
    remaining_jobs = [job for job in jobs if not job["pilot_job"]]
    turns = len(jobs) * 6
    teacher_calls = turns * 6
    remaining_turns = len(remaining_jobs) * 6
    remaining_teacher_calls = remaining_turns * 6
    manifest = {
        "schema_version": "storyworld_harvest_campaign_manifest_v1",
        "campaign_id": config["campaign_id"],
        "status": config["status"],
        "campaign_config_path": campaign_path.relative_to(repo_root).as_posix(),
        "campaign_config_sha256": sha256_file(campaign_path),
        "package_sha256": sha256_file(package_path),
        "recipe_sha256": sha256_file(recipe_path),
        "teacher_ensemble_sha256": sha256_file(ensemble_path),
        "jobs": len(jobs),
        "pilot_jobs": len(pilot_jobs),
        "remaining_jobs": len(remaining_jobs),
        "shards": math.ceil(len(remaining_jobs) / shard_size),
        "shard_size": shard_size,
        "train_families": len(family_ids),
        "materialized_train_instances": len(all_instances),
        "jobs_by_arm": dict(sorted(arm_counts.items())),
        "jobs_by_family": dict(sorted(family_counts.items())),
        "jobs_by_family_and_arm": dict(sorted(family_arm_counts.items())),
        "actor_schedules": dict(sorted(schedule_counts.items())),
        "projected_turns": turns,
        "projected_teacher_calls": teacher_calls,
        "projected_remaining_turns": remaining_turns,
        "projected_remaining_teacher_calls": remaining_teacher_calls,
        "teacher_calls_per_turn": 6,
        "token_projection": projections,
        "external_slice_requirements_per_arm": {
            slice_id: {
                "packed_tokens": int(recipe["slice_tokens"][slice_id]),
                "assistant_tokens": int(recipe["minimum_assistant_tokens_by_slice"][slice_id]),
            }
            for slice_id in ("static_identity_calibration", "ordinary_helpfulness_guardrails")
        },
        "execution_gate": {
            "execution_ready": not pending_review_worlds,
            "pending_review_base_worlds": pending_review_worlds,
            "credential_validity": "not_checked_by_planner",
            "pilot_must_complete_before_full_campaign": True,
            "exact_tokenizer_recalibration_required": True,
        },
        "sealed_evaluation_jobs": 0,
        "development_training_jobs": 0,
        "claim_boundary": calibration["claim_boundary"],
        "passed": True,
    }
    return jobs, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan balanced real-teacher harvest jobs without making API calls."
    )
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    jobs, manifest = build_campaign_plan(REPO_ROOT, args.campaign)
    if args.output_dir is not None:
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        jobs_path = output_dir / "jobs.jsonl"
        pilot_path = output_dir / "pilot_jobs.jsonl"
        remaining_path = output_dir / "remaining_jobs.jsonl"
        write_jsonl(jobs_path, jobs)
        write_jsonl(pilot_path, [job for job in jobs if job["pilot_job"]])
        write_jsonl(remaining_path, [job for job in jobs if not job["pilot_job"]])

        shard_dir = output_dir / "shards"
        shard_dir.mkdir(parents=True, exist_ok=True)
        shard_paths: list[Path] = []
        for shard_index in range(int(manifest["shards"])):
            shard_path = shard_dir / f"shard_{shard_index:04d}.jsonl"
            write_jsonl(
                shard_path,
                [
                    job
                    for job in jobs
                    if not job["pilot_job"] and int(job["shard_index"]) == shard_index
                ],
            )
            shard_paths.append(shard_path)

        manifest["artifacts"] = {
            "jobs.jsonl": {
                "rows": len(jobs),
                "sha256": sha256_file(jobs_path),
            },
            "pilot_jobs.jsonl": {
                "rows": sum(bool(job["pilot_job"]) for job in jobs),
                "sha256": sha256_file(pilot_path),
            },
            "remaining_jobs.jsonl": {
                "rows": sum(not job["pilot_job"] for job in jobs),
                "sha256": sha256_file(remaining_path),
            },
            "shards": [
                {
                    "path": path.relative_to(output_dir).as_posix(),
                    "rows": sum(
                        not job["pilot_job"] and int(job["shard_index"]) == index
                        for job in jobs
                    ),
                    "sha256": sha256_file(path),
                }
                for index, path in enumerate(shard_paths)
            ],
        }
        write_json(output_dir / "CAMPAIGN_MANIFEST.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
