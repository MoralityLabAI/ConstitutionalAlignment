#!/usr/bin/env python3
"""Audit the 48-trace real-teacher pilot and recalibrate the full campaign."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import (
    build_world_model_tasks,
    materialize_instance_sweep,
    read_json,
    sha256_file,
    sha256_json,
    validate_curriculum_package,
    validate_world,
    write_json,
)
from alignment_harness.trajectory_curriculum import (
    HuggingFaceTokenCounter,
    derive_trace_views,
    read_jsonl,
    validate_episode_trace,
)


DEFAULT_PACKAGE = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "package.json"
DEFAULT_RECIPE = (
    REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "token_recipe_10m_per_arm.json"
)
TRACE_SLICES = {
    "sft_policy": "stateful_actor_trajectories",
    "sft_interrogation": "interrogation_and_defense",
    "sft_repair": "failure_critique_and_repair",
}


def recommend_balanced_trace_count(
    pilot_totals_by_arm: dict[str, dict[str, dict[str, int]]],
    pilot_trace_counts: dict[str, int],
    recipe: dict[str, Any],
    family_count: int,
) -> dict[str, Any]:
    """Scale exact pilot yields to one matched, family-balanced trace count."""
    if family_count <= 0:
        raise ValueError("family_count must be positive")
    arm_requirements: dict[str, Any] = {}
    for arm in map(str, recipe["arms"]):
        traces = int(pilot_trace_counts.get(arm, 0))
        if traces <= 0:
            raise ValueError(f"pilot has no traces for arm {arm}")
        if arm not in pilot_totals_by_arm:
            raise ValueError(f"pilot has no token totals for arm {arm}")
        slice_requirements = {}
        for slice_id in TRACE_SLICES.values():
            totals = pilot_totals_by_arm[arm].get(slice_id, {})
            packed = int(totals.get("packed_tokens", 0))
            assistant = int(totals.get("assistant_tokens", 0))
            if packed <= 0 or assistant <= 0:
                raise ValueError(f"pilot has zero token yield for {arm}/{slice_id}")
            packed_required = math.ceil(
                int(recipe["slice_tokens"][slice_id]) * traces / packed
            )
            assistant_required = math.ceil(
                int(recipe["minimum_assistant_tokens_by_slice"][slice_id])
                * traces
                / assistant
            )
            slice_requirements[slice_id] = {
                "pilot_packed_tokens": packed,
                "pilot_assistant_tokens": assistant,
                "pilot_traces": traces,
                "mean_packed_tokens_per_trace": packed / traces,
                "mean_assistant_tokens_per_trace": assistant / traces,
                "traces_required_for_packed_target": packed_required,
                "traces_required_for_assistant_minimum": assistant_required,
                "binding_required_traces": max(packed_required, assistant_required),
            }
        arm_requirements[arm] = {
            "slices": slice_requirements,
            "binding_required_traces": max(
                item["binding_required_traces"] for item in slice_requirements.values()
            ),
        }

    binding = max(item["binding_required_traces"] for item in arm_requirements.values())
    per_family = math.ceil(binding / family_count)
    if per_family % 2:
        per_family += 1
    traces_per_arm = per_family * family_count
    for arm, arm_values in arm_requirements.items():
        pilot_traces = int(pilot_trace_counts[arm])
        for values in arm_values["slices"].values():
            values["projected_packed_tokens"] = math.floor(
                values["pilot_packed_tokens"] * traces_per_arm / pilot_traces
            )
            values["projected_assistant_tokens"] = math.floor(
                values["pilot_assistant_tokens"] * traces_per_arm / pilot_traces
            )
    return {
        "family_count": family_count,
        "traces_per_family_per_arm": per_family,
        "traces_per_arm": traces_per_arm,
        "full_campaign_jobs": traces_per_arm * len(recipe["arms"]),
        "schedule_constraint": "even per-family count preserves 50/50 single/dyadic allocation",
        "arm_requirements": arm_requirements,
    }


def _campaign_artifact(
    manifest: dict[str, Any], manifest_path: Path, artifact_path: Path
) -> dict[str, Any]:
    output_root = manifest_path.parent.resolve()
    artifact_path = artifact_path.resolve()
    candidates = []
    artifacts = manifest.get("artifacts", {})
    for relative in ("jobs.jsonl", "pilot_jobs.jsonl", "remaining_jobs.jsonl"):
        if relative in artifacts:
            candidates.append((output_root / relative, artifacts[relative]))
    for item in artifacts.get("shards", []):
        candidates.append((output_root / str(item["path"]), item))
    matches = [item for path, item in candidates if path.resolve() == artifact_path]
    if len(matches) != 1:
        raise ValueError("jobs file is not a unique hash-recorded campaign artifact")
    artifact = matches[0]
    if sha256_file(artifact_path) != artifact["sha256"]:
        raise ValueError("campaign jobs artifact hash mismatch")
    return artifact


def _sum_numeric_usage(target: dict[str, int], value: Any, prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{prefix}.{key}" if prefix else str(key)
            _sum_numeric_usage(target, child, location)
    elif isinstance(value, int) and not isinstance(value, bool):
        target[prefix] = target.get(prefix, 0) + value


def _resolve_campaign_worlds(
    package: dict[str, Any], jobs: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    needed_sweeps = sorted({str(job["sweep_path"]) for job in jobs})
    world_map: dict[str, dict[str, Any]] = {}
    all_train_worlds: dict[str, dict[str, Any]] = {}
    for sweep_value in package["instance_sweeps"]:
        sweep_path = (REPO_ROOT / str(sweep_value)).resolve()
        worlds, _ = materialize_instance_sweep(REPO_ROOT, sweep_path)
        for world in worlds:
            if world["source_split"] == "train":
                all_train_worlds[str(world["world_id"])] = world
        if sweep_path.relative_to(REPO_ROOT).as_posix() in needed_sweeps:
            for world in worlds:
                world_map[str(world["world_id"])] = world
    return world_map, list(all_train_worlds.values())


def _count_world_model_rows(
    worlds: list[dict[str, Any]], arms: list[str], counter: HuggingFaceTokenCounter
) -> dict[str, dict[str, int]]:
    totals = {
        arm: {"packed_tokens": 0, "assistant_tokens": 0, "rows": 0, "worlds": 0}
        for arm in arms
    }
    for arm in arms:
        for world in worlds:
            seen: set[str] = set()
            rows_for_world = 0
            for task in build_world_model_tasks(world):
                if task["task_type"] == "obligation_vs_dynamics" and task["proof"]["frame"] != arm:
                    continue
                assistant = json.dumps(task["target"], ensure_ascii=False, sort_keys=True)
                messages = [*task["messages"], {"role": "assistant", "content": assistant}]
                fingerprint = sha256_json(messages)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                packed, loss_bearing = counter.count_messages(messages)
                totals[arm]["packed_tokens"] += packed
                totals[arm]["assistant_tokens"] += loss_bearing
                totals[arm]["rows"] += 1
                rows_for_world += 1
            if rows_for_world:
                totals[arm]["worlds"] += 1
    return totals


def audit_pilot(
    package_path: Path,
    recipe_path: Path,
    campaign_manifest_path: Path,
    pilot_jobs_path: Path,
    trace_root: Path,
    tokenizer_path: Path,
) -> dict[str, Any]:
    package_path = package_path.resolve()
    recipe_path = recipe_path.resolve()
    campaign_manifest_path = campaign_manifest_path.resolve()
    pilot_jobs_path = pilot_jobs_path.resolve()
    trace_root = trace_root.resolve()
    package = read_json(package_path)
    package_receipt = validate_curriculum_package(REPO_ROOT, package_path)
    recipe = read_json(recipe_path)
    manifest = read_json(campaign_manifest_path)
    if manifest.get("schema_version") != "storyworld_harvest_campaign_manifest_v1":
        raise ValueError("unexpected campaign manifest schema")
    artifact = _campaign_artifact(manifest, campaign_manifest_path, pilot_jobs_path)
    jobs = read_jsonl(pilot_jobs_path)
    if len(jobs) != int(artifact["rows"]) or len(jobs) != int(manifest["pilot_jobs"]):
        raise ValueError("pilot job row count differs from campaign manifest")
    if not jobs or any(not job.get("pilot_job") for job in jobs):
        raise ValueError("pilot artifact contains a non-pilot job")
    if len({str(job["job_id"]) for job in jobs}) != len(jobs):
        raise ValueError("pilot contains duplicate job IDs")
    world_map, all_train_worlds = _resolve_campaign_worlds(package, jobs)
    counter = HuggingFaceTokenCounter(str(tokenizer_path))

    token_totals: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"packed_tokens": 0, "assistant_tokens": 0, "rows": 0})
    )
    trace_counts: Counter[str] = Counter()
    family_arm_counts: Counter[tuple[str, str]] = Counter()
    schedule_counts: Counter[str] = Counter()
    usage_totals: dict[str, int] = {}
    trace_ids: set[str] = set()
    teacher_calls = 0
    pilot_review_tasks = []
    for job in jobs:
        job_id = str(job["job_id"])
        output_dir = trace_root / job_id
        receipt_path = output_dir / "JOB_RECEIPT.json"
        trace_path = output_dir / "trace.jsonl"
        if not receipt_path.is_file() or not trace_path.is_file():
            raise ValueError(f"pilot output missing for {job_id}")
        receipt = read_json(receipt_path)
        if receipt.get("schema_version") != "storyworld_harvest_job_receipt_v1":
            raise ValueError(f"{job_id}: unexpected job receipt schema")
        if receipt.get("job_id") != job_id or receipt.get("job_sha256") != sha256_json(job):
            raise ValueError(f"{job_id}: receipt/job identity mismatch")
        if receipt.get("jobs_file_sha256") != sha256_file(pilot_jobs_path):
            raise ValueError(f"{job_id}: receipt belongs to a different pilot artifact")
        if receipt.get("trace_sha256") != sha256_file(trace_path):
            raise ValueError(f"{job_id}: trace file hash mismatch")
        traces = read_jsonl(trace_path)
        if len(traces) != 1:
            raise ValueError(f"{job_id}: each pilot job must contain exactly one trace")
        trace = traces[0]
        trace_id = str(trace["trace_id"])
        if trace_id in trace_ids or receipt.get("trace_id") != trace_id:
            raise ValueError(f"{job_id}: duplicate or mismatched trace ID")
        trace_ids.add(trace_id)
        arm = str(job["arm"])
        family_id = str(job["family_id"])
        world_id = str(job["world_id"])
        if world_id not in world_map:
            raise ValueError(f"{job_id}: job world is not materialized by the package")
        world = world_map[world_id]
        validation = validate_world(world)
        if sha256_json(world) != job["world_content_sha256"]:
            raise ValueError(f"{job_id}: world content drifted after planning")
        if validation["transition_graph_sha256"] != job["transition_graph_sha256"]:
            raise ValueError(f"{job_id}: world graph drifted after planning")
        if trace["episode"]["world_id"] != world_id or trace["episode"]["frame"] != arm:
            raise ValueError(f"{job_id}: trace world/arm mismatch")
        if int(trace["episode"]["seed"]) != int(job["episode_seed"]):
            raise ValueError(f"{job_id}: trace seed mismatch")
        if trace["episode"]["actor_schedule"] != job["actor_schedule"]:
            raise ValueError(f"{job_id}: trace actor schedule mismatch")
        if trace["provenance"]["world_content_sha256"] != sha256_json(world):
            raise ValueError(f"{job_id}: trace provenance world hash mismatch")
        if not trace["release"]["training_approved"] or trace["release"]["sealed_evaluation"]:
            raise ValueError(f"{job_id}: pilot trace is not approved train data")
        validate_episode_trace(world, trace)
        pilot_review_tasks.append(
            {
                "review_task_id": f"pilot-trace-review-{trace_id}",
                "job_id": job_id,
                "trace_id": trace_id,
                "trace_path": str(trace_path.resolve()),
                "trace_file_sha256": sha256_file(trace_path),
                "trace_content_sha256": sha256_json(trace),
                "world_id": world_id,
                "family_id": family_id,
                "arm": arm,
                "actor_schedule_mode": job["actor_schedule_mode"],
                "required_review_scope": [
                    "visible-fact grounding and uncertainty calibration",
                    "action/consequence/interrogation coherence",
                    "adjudication and repair target quality",
                    "identity-boundary and anti-theatrical behavior",
                    "absence of hidden-state claims or unsafe sacred reenactment",
                ],
            }
        )

        for turn in trace["turns"]:
            if len(turn["teacher_calls"]) != 6:
                raise ValueError(f"{job_id}: turn lacks six functional teacher calls")
            teacher_calls += len(turn["teacher_calls"])
            for call in turn["teacher_calls"]:
                provider = call.get("provider_call_receipt", {})
                if provider.get("provider") != "openai_responses_api" or provider.get("store") is not False:
                    raise ValueError(f"{job_id}: call lacks a nonstored OpenAI provider receipt")
                attempts = provider.get("attempts", [])
                if not attempts or not all(str(item.get("api_response_id", "")) for item in attempts):
                    raise ValueError(f"{job_id}: provider attempt receipt is incomplete")
                for attempt in attempts:
                    _sum_numeric_usage(usage_totals, attempt.get("usage", {}))

        views = derive_trace_views(trace)
        for view_name, slice_id in TRACE_SLICES.items():
            for row in views[view_name]:
                packed, assistant = counter.count_messages(row["messages"])
                token_totals[arm][slice_id]["packed_tokens"] += packed
                token_totals[arm][slice_id]["assistant_tokens"] += assistant
                token_totals[arm][slice_id]["rows"] += 1
        trace_counts[arm] += 1
        family_arm_counts[(family_id, arm)] += 1
        schedule_counts[str(job["actor_schedule_mode"])] += 1

    expected_arms = list(map(str, recipe["arms"]))
    expected_families = int(manifest["train_families"])
    if set(trace_counts) != set(expected_arms) or any(
        count != expected_families for count in trace_counts.values()
    ):
        raise ValueError("pilot must contain one trace per train family and arm")
    if any(count != 1 for count in family_arm_counts.values()):
        raise ValueError("pilot family/arm cells must contain exactly one trace")

    token_totals_plain = {
        arm: {slice_id: dict(values) for slice_id, values in slices.items()}
        for arm, slices in token_totals.items()
    }
    recommendation = recommend_balanced_trace_count(
        token_totals_plain,
        dict(trace_counts),
        recipe,
        expected_families,
    )
    world_model = _count_world_model_rows(all_train_worlds, expected_arms, counter)
    for arm, values in world_model.items():
        values["packed_target_tokens"] = int(
            recipe["slice_tokens"]["metta_world_model_tasks"]
        )
        values["assistant_minimum_tokens"] = int(
            recipe["minimum_assistant_tokens_by_slice"]["metta_world_model_tasks"]
        )
        values["packed_coverage"] = values["packed_tokens"] >= values["packed_target_tokens"]
        values["assistant_coverage"] = (
            values["assistant_tokens"] >= values["assistant_minimum_tokens"]
        )

    pilot_review_tasks.sort(key=lambda item: str(item["review_task_id"]))
    return {
        "schema_version": "storyworld_real_pilot_calibration_v1",
        "campaign_id": manifest["campaign_id"],
        "status": "pilot_passed_pending_human_full_campaign_authorization",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "package_sha256": sha256_file(package_path),
        "package_validation_passed": bool(package_receipt["passed"]),
        "recipe_sha256": sha256_file(recipe_path),
        "campaign_manifest_sha256": sha256_file(campaign_manifest_path),
        "pilot_jobs_sha256": sha256_file(pilot_jobs_path),
        "pilot_jobs": len(jobs),
        "trace_ids_sha256": sha256_json(sorted(trace_ids)),
        "traces_by_arm": dict(sorted(trace_counts.items())),
        "family_arm_cells": len(family_arm_counts),
        "actor_schedules": dict(sorted(schedule_counts.items())),
        "teacher_calls": teacher_calls,
        "pilot_human_review_required": True,
        "pilot_review_tasks": pilot_review_tasks,
        "pilot_review_tasks_sha256": sha256_json(pilot_review_tasks),
        "provider_usage": dict(sorted(usage_totals.items())),
        "tokenizer": counter.description,
        "pilot_core_token_totals": token_totals_plain,
        "recalibrated_campaign": recommendation,
        "exact_world_model_availability": world_model,
        "full_campaign_ready_for_human_authorization": all(
            values["packed_coverage"] and values["assistant_coverage"]
            for values in world_model.values()
        ),
        "sealed_evaluation_traces": 0,
        "development_training_traces": 0,
        "claim_boundary": (
            "This receipt measures a completed real pilot and recommends scale. It is not "
            "full-campaign spend authorization and does not approve external static data."
        ),
        "passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--recipe", type=Path, default=DEFAULT_RECIPE)
    parser.add_argument("--campaign-manifest", type=Path, required=True)
    parser.add_argument("--pilot-jobs", type=Path, required=True)
    parser.add_argument("--trace-root", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = audit_pilot(
        args.package,
        args.recipe,
        args.campaign_manifest,
        args.pilot_jobs,
        args.trace_root,
        args.tokenizer,
    )
    write_json(args.output.resolve(), receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
