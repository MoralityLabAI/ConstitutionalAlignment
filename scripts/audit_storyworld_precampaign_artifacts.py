#!/usr/bin/env python3
"""Recompute and audit every no-spend artifact prepared for external review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json
from alignment_harness.trajectory_curriculum import read_jsonl
from scripts.plan_storyworld_support_slices import build_support_slice_plan
from scripts.normalize_recovered_storyworld_extras import normalize_source
from scripts.prepare_recovered_storyworld_extras_review import prepare_recovered_review
from scripts.prepare_storyworld_review_queue import build_review_queue
from scripts.prepare_storyworld_support_prompt_reviews import (
    build_support_prompt_review_queue,
)


def audit_precampaign_artifacts(
    package_path: Path,
    world_review_queue_path: Path,
    support_config_path: Path,
    support_plan_dir: Path,
    prompt_review_queue_path: Path,
    recovered_source_root: Path,
    recovered_dir: Path,
    human_review_handoff_dir: Path,
) -> dict[str, Any]:
    package_path = package_path.resolve()
    world_review_queue_path = world_review_queue_path.resolve()
    support_config_path = support_config_path.resolve()
    support_plan_dir = support_plan_dir.resolve()
    prompt_review_queue_path = prompt_review_queue_path.resolve()
    recovered_source_root = recovered_source_root.resolve()
    recovered_dir = recovered_dir.resolve()
    human_review_handoff_dir = human_review_handoff_dir.resolve()
    plan_manifest_path = support_plan_dir / "SUPPORT_PLAN_MANIFEST.json"
    scenarios_path = support_plan_dir / "support_scenarios.jsonl"
    jobs_path = support_plan_dir / "jobs.jsonl"
    pilot_jobs_path = support_plan_dir / "pilot_jobs.jsonl"
    remaining_jobs_path = support_plan_dir / "remaining_jobs.jsonl"

    observed_world_queue = read_json(world_review_queue_path)
    expected_world_queue = build_review_queue(REPO_ROOT, package_path)
    if observed_world_queue != expected_world_queue:
        raise ValueError("world review queue does not equal a fresh deterministic rebuild")

    config = read_json(support_config_path)
    expected_scenarios, expected_jobs, expected_manifest = build_support_slice_plan(config)
    observed_manifest = read_json(plan_manifest_path)
    for key, value in expected_manifest.items():
        if observed_manifest.get(key) != value:
            raise ValueError(f"support plan manifest drifted at {key}")
    planner_path = REPO_ROOT / "scripts" / "plan_storyworld_support_slices.py"
    if observed_manifest.get("config_sha256") != sha256_file(support_config_path):
        raise ValueError("support plan config hash mismatch")
    if observed_manifest.get("planner_sha256") != sha256_file(planner_path):
        raise ValueError("support plan planner hash mismatch")

    observed_scenarios = read_jsonl(scenarios_path)
    observed_jobs = read_jsonl(jobs_path)
    observed_pilot = read_jsonl(pilot_jobs_path)
    observed_remaining = read_jsonl(remaining_jobs_path)
    if observed_scenarios != expected_scenarios or observed_jobs != expected_jobs:
        raise ValueError("support scenarios/jobs do not equal a fresh deterministic rebuild")
    if observed_pilot != [item for item in expected_jobs if item["pilot_job"]]:
        raise ValueError("support pilot artifact is not the exact pilot partition")
    if observed_remaining != [item for item in expected_jobs if not item["pilot_job"]]:
        raise ValueError("support remaining artifact is not the exact remaining partition")

    named_paths = {
        "support_scenarios.jsonl": scenarios_path,
        "jobs.jsonl": jobs_path,
        "pilot_jobs.jsonl": pilot_jobs_path,
        "remaining_jobs.jsonl": remaining_jobs_path,
    }
    artifacts = observed_manifest.get("artifacts", {})
    for name, path in named_paths.items():
        item = artifacts.get(name, {})
        if (
            not path.is_file()
            or item.get("sha256") != sha256_file(path)
            or int(item.get("rows", -1)) != len(read_jsonl(path))
        ):
            raise ValueError(f"support plan artifact is missing or drifted: {name}")
    concatenated_shards: list[dict[str, Any]] = []
    for expected_index, item in enumerate(artifacts.get("shards", [])):
        expected_relative = f"shards/shard_{expected_index:04d}.jsonl"
        if item.get("path") != expected_relative:
            raise ValueError("support shard ordering/path drifted")
        path = support_plan_dir / expected_relative
        rows = read_jsonl(path)
        if (
            not path.is_file()
            or item.get("sha256") != sha256_file(path)
            or int(item.get("rows", -1)) != len(rows)
        ):
            raise ValueError(f"support shard is missing or drifted: {expected_relative}")
        concatenated_shards.extend(rows)
    if concatenated_shards != observed_remaining:
        raise ValueError("support shards do not exactly partition remaining jobs in order")

    observed_prompt_queue = read_json(prompt_review_queue_path)
    expected_prompt_queue = build_support_prompt_review_queue(
        support_config_path,
        plan_manifest_path,
        scenarios_path,
        pilot_jobs_path,
    )
    if observed_prompt_queue != expected_prompt_queue:
        raise ValueError("support prompt review queue differs from a fresh rebuild")

    recovered_source_manifest_path = (
        REPO_ROOT
        / "experiments"
        / "storyworld_curriculum_v1"
        / "recovered_static_source_v1.json"
    )
    token_recipe_path = (
        REPO_ROOT
        / "experiments"
        / "storyworld_curriculum_v1"
        / "token_recipe_10m_per_arm.json"
    )
    recovered_manifest_path = recovered_dir / "NORMALIZATION_MANIFEST.json"
    recovered_rows_path = recovered_dir / "extra_rows.jsonl"
    recovered_review_queue_path = recovered_dir / "REVIEW_QUEUE.json"
    expected_recovered_rows, expected_recovered_manifest = normalize_source(
        recovered_source_root,
        recovered_source_manifest_path,
        token_recipe_path,
    )
    observed_recovered_rows = read_jsonl(recovered_rows_path)
    observed_recovered_manifest = read_json(recovered_manifest_path)
    if observed_recovered_rows != expected_recovered_rows:
        raise ValueError("recovered normalized rows differ from a fresh source rebuild")
    for key, value in expected_recovered_manifest.items():
        if observed_recovered_manifest.get(key) != value:
            raise ValueError(f"recovered normalization manifest drifted at {key}")
    recovered_artifact = observed_recovered_manifest.get("artifacts", {}).get(
        "extra_rows.jsonl", {}
    )
    if (
        recovered_artifact.get("sha256") != sha256_file(recovered_rows_path)
        or int(recovered_artifact.get("rows", -1)) != len(observed_recovered_rows)
    ):
        raise ValueError("recovered normalized row artifact is missing or drifted")
    observed_recovered_queue = read_json(recovered_review_queue_path)
    queue_body = {
        key: value
        for key, value in observed_recovered_queue.items()
        if key != "queue_content_sha256"
    }
    if observed_recovered_queue.get("queue_content_sha256") != sha256_json(queue_body):
        raise ValueError("recovered review queue content hash mismatch")
    expected_recovered_queue = prepare_recovered_review(
        recovered_manifest_path, recovered_rows_path
    )
    for key, value in expected_recovered_queue.items():
        if key not in {"created_at", "queue_content_sha256"} and observed_recovered_queue.get(
            key
        ) != value:
            raise ValueError(f"recovered review queue drifted at {key}")

    handoff_manifest_path = human_review_handoff_dir / "HANDOFF_MANIFEST.json"
    handoff = read_json(handoff_manifest_path)
    handoff_body = {
        key: value for key, value in handoff.items() if key != "handoff_content_sha256"
    }
    if (
        handoff.get("schema_version") != "storyworld_human_review_handoff_v1"
        or handoff.get("handoff_content_sha256") != sha256_json(handoff_body)
        or handoff.get("source_queues", {}).get("world")
        != sha256_file(world_review_queue_path)
        or handoff.get("source_queues", {}).get("support_prompt")
        != sha256_file(prompt_review_queue_path)
        or handoff.get("source_queues", {}).get("recovered")
        != sha256_file(recovered_review_queue_path)
        or handoff.get("source_queues", {}).get("recovered_rows")
        != sha256_file(recovered_rows_path)
        or handoff.get("untouched_templates_rejected") is not True
        or handoff.get("human_review_complete") is not False
        or handoff.get("spend_authorized") is not False
    ):
        raise ValueError("human review handoff manifest is invalid or stale")
    for item in handoff.get("files", {}).values():
        path = human_review_handoff_dir / str(item.get("path", ""))
        if (
            not path.is_file()
            or item.get("sha256") != sha256_file(path)
            or int(item.get("bytes", -1)) != path.stat().st_size
        ):
            raise ValueError("human review handoff file is missing or drifted")

    return {
        "schema_version": "storyworld_precampaign_artifact_audit_v1",
        "status": "prepared_for_external_review_no_spend_authorized",
        "package_sha256": sha256_file(package_path),
        "world_review_queue": {
            "path": world_review_queue_path.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(world_review_queue_path),
            "worlds": int(observed_world_queue["counts"]["worlds"]),
            "review_tasks": int(observed_world_queue["counts"]["review_tasks"]),
        },
        "support_campaign": {
            "plan_manifest_path": plan_manifest_path.relative_to(REPO_ROOT).as_posix(),
            "plan_manifest_sha256": sha256_file(plan_manifest_path),
            "scenarios": len(observed_scenarios),
            "jobs": len(observed_jobs),
            "pilot_jobs": len(observed_pilot),
            "remaining_jobs": len(observed_remaining),
            "shards": len(artifacts.get("shards", [])),
            "sealed_evaluation_jobs": 0,
            "development_jobs": 0,
            "execution_ready": False,
            "training_approved_rows": 0,
        },
        "support_prompt_review_queue": {
            "path": prompt_review_queue_path.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(prompt_review_queue_path),
            "content_sha256": observed_prompt_queue["queue_content_sha256"],
            "review_tasks": int(observed_prompt_queue["review_tasks_count"]),
        },
        "recovered_static_source": {
            "normalization_manifest_path": recovered_manifest_path.relative_to(
                REPO_ROOT
            ).as_posix(),
            "normalization_manifest_sha256": sha256_file(recovered_manifest_path),
            "rows_sha256": sha256_file(recovered_rows_path),
            "rows": len(observed_recovered_rows),
            "training_approved_rows": int(
                observed_recovered_manifest["training_approved_rows"]
            ),
            "review_queue_path": recovered_review_queue_path.relative_to(
                REPO_ROOT
            ).as_posix(),
            "review_queue_sha256": sha256_file(recovered_review_queue_path),
            "review_tasks": len(observed_recovered_queue["review_tasks"]),
            "license_receipt_required": True,
        },
        "human_review_handoff": {
            "manifest_path": handoff_manifest_path.relative_to(REPO_ROOT).as_posix(),
            "manifest_sha256": sha256_file(handoff_manifest_path),
            "handoff_content_sha256": handoff["handoff_content_sha256"],
            "human_decisions_required": int(
                handoff["counts"]["total_human_decisions_required"]
            ),
            "untouched_templates_rejected": True,
            "human_review_complete": False,
        },
        "main_campaign_materialized": False,
        "main_campaign_dependency": (
            "Apply all current world-review receipts first, then regenerate main jobs so "
            "their world hashes bind the reviewed sources."
        ),
        "teacher_calls_made": 0,
        "spend_authorized": False,
        "training_approved_rows": 0,
        "artifact_set_sha256": sha256_json(
            {
                "world_review_queue": sha256_file(world_review_queue_path),
                "support_plan": sha256_file(plan_manifest_path),
                "support_prompt_queue": sha256_file(prompt_review_queue_path),
                "recovered_normalization": sha256_file(recovered_manifest_path),
                "recovered_review_queue": sha256_file(recovered_review_queue_path),
                "human_review_handoff": sha256_file(handoff_manifest_path),
            }
        ),
        "claim_boundary": (
            "This receipt proves deterministic no-spend preparation only. Human review, "
            "provider calls, token yield, training release, and adapter training remain pending."
        ),
        "passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--world-review-queue", type=Path, required=True)
    parser.add_argument("--support-config", type=Path, required=True)
    parser.add_argument("--support-plan-dir", type=Path, required=True)
    parser.add_argument("--prompt-review-queue", type=Path, required=True)
    parser.add_argument("--recovered-source-root", type=Path, required=True)
    parser.add_argument("--recovered-dir", type=Path, required=True)
    parser.add_argument("--human-review-handoff-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = audit_precampaign_artifacts(
        args.package,
        args.world_review_queue,
        args.support_config,
        args.support_plan_dir,
        args.prompt_review_queue,
        args.recovered_source_root,
        args.recovered_dir,
        args.human_review_handoff_dir,
    )
    if args.output is not None:
        write_json(args.output.resolve(), receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
