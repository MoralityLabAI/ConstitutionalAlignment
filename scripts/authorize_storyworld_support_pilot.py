#!/usr/bin/env python3
"""Create a human-attributed, hash-bound authorization for the support pilot."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json
from alignment_harness.trajectory_curriculum import read_jsonl


def _artifact(
    manifest: dict[str, Any], manifest_path: Path, artifact_path: Path, name: str
) -> dict[str, Any]:
    expected_path = (manifest_path.parent / name).resolve()
    if artifact_path.resolve() != expected_path:
        raise ValueError(f"{name} must be read beside the support plan manifest")
    item = manifest.get("artifacts", {}).get(name)
    if not isinstance(item, dict):
        raise ValueError(f"support plan manifest does not record {name}")
    if sha256_file(artifact_path) != item.get("sha256"):
        raise ValueError(f"support plan artifact hash mismatch: {name}")
    return item


def build_support_pilot_authorization(
    config_path: Path,
    plan_manifest_path: Path,
    scenarios_path: Path,
    pilot_jobs_path: Path,
    prompt_review_bundle_path: Path,
    *,
    authorized_by: str,
    authorization_reference: str,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    plan_manifest_path = plan_manifest_path.resolve()
    scenarios_path = scenarios_path.resolve()
    pilot_jobs_path = pilot_jobs_path.resolve()
    prompt_review_bundle_path = prompt_review_bundle_path.resolve()
    config = read_json(config_path)
    manifest = read_json(plan_manifest_path)
    prompt_review_bundle = read_json(prompt_review_bundle_path)
    if config.get("schema_version") != "storyworld_support_slice_campaign_v1":
        raise ValueError("unexpected support campaign schema")
    if manifest.get("schema_version") != "storyworld_support_slice_plan_manifest_v1":
        raise ValueError("unexpected support plan manifest schema")
    if manifest.get("status") != "prompt_design_pending_review_not_spend_authorization":
        raise ValueError("support plan is not the frozen no-spend design")
    if not manifest.get("passed") or manifest.get("execution_ready"):
        raise ValueError("support plan must pass while remaining non-executable")
    if manifest.get("campaign_id") != config.get("campaign_id"):
        raise ValueError("support config and plan belong to different campaigns")
    if manifest.get("config_sha256") != sha256_file(config_path):
        raise ValueError("support config drifted after plan generation")
    planner_path = REPO_ROOT / "scripts" / "plan_storyworld_support_slices.py"
    teacher_path = REPO_ROOT / "scripts" / "openai_support_slice_teacher.py"
    if manifest.get("planner_sha256") != sha256_file(planner_path):
        raise ValueError("support planner drifted after plan generation")

    scenario_artifact = _artifact(
        manifest, plan_manifest_path, scenarios_path, "support_scenarios.jsonl"
    )
    pilot_artifact = _artifact(
        manifest, plan_manifest_path, pilot_jobs_path, "pilot_jobs.jsonl"
    )
    scenarios = read_jsonl(scenarios_path)
    jobs = read_jsonl(pilot_jobs_path)
    if len(scenarios) != int(scenario_artifact["rows"]) or len(scenarios) != int(
        manifest["scenarios"]
    ):
        raise ValueError("support scenario row count mismatch")
    if len(jobs) != int(pilot_artifact["rows"]) or len(jobs) != int(
        manifest["pilot_jobs"]
    ):
        raise ValueError("support pilot row count mismatch")
    if len({item["scenario_id"] for item in scenarios}) != len(scenarios):
        raise ValueError("support scenarios contain duplicate IDs")
    if len({item["prompt"] for item in scenarios}) != len(scenarios):
        raise ValueError("support scenarios contain duplicate prompt content")
    scenario_map = {str(item["scenario_id"]): item for item in scenarios}

    cells: Counter[tuple[str, str, str]] = Counter()
    for job in jobs:
        if job.get("schema_version") != "storyworld_support_job_v1":
            raise ValueError("unexpected support pilot job schema")
        if not job.get("pilot_job") or job.get("execution_eligible"):
            raise ValueError("pilot artifact must contain only frozen non-executable pilot jobs")
        if job.get("automatic_training_approval"):
            raise ValueError("support pilot cannot automatically approve training data")
        if job.get("source_split") != "train" or not job.get("training_eligible"):
            raise ValueError("support pilot contains a non-training source")
        scenario = scenario_map.get(str(job["scenario_id"]))
        if scenario is None or job.get("scenario_sha256") != sha256_json(scenario):
            raise ValueError("support pilot scenario reference is missing or hash-mismatched")
        arm = str(job["arm"])
        if job.get("messages") != [
            {"role": "system", "content": config["system_prompts"][arm]},
            {"role": "user", "content": scenario["prompt"]},
        ]:
            raise ValueError("support pilot messages drifted from config/scenario content")
        if job.get("model_id") != config["model_id"] or job.get(
            "reasoning_effort"
        ) != config["reasoning_effort_by_slice"][scenario["slice"]]:
            raise ValueError("support pilot teacher configuration drifted")
        cells[(str(job["slice"]), str(job["category"]), arm)] += 1
    if set(cells.values()) != {1} or len(cells) != len(jobs):
        raise ValueError("support pilot must contain one job per slice/category/arm cell")
    if (
        prompt_review_bundle.get("schema_version")
        != "storyworld_support_prompt_human_review_bundle_v1"
        or prompt_review_bundle.get("campaign_id") != config["campaign_id"]
        or prompt_review_bundle.get("plan_manifest_sha256")
        != sha256_file(plan_manifest_path)
        or prompt_review_bundle.get("support_scenarios_sha256")
        != sha256_file(scenarios_path)
        or prompt_review_bundle.get("pilot_jobs_sha256")
        != sha256_file(pilot_jobs_path)
        or prompt_review_bundle.get("all_pilot_prompts_approved") is not True
        or int(prompt_review_bundle.get("approved_prompts", 0)) != len(jobs)
        or prompt_review_bundle.get("automatic_spend_authorization") is not False
        or prompt_review_bundle.get("passed") is not True
    ):
        raise ValueError("support pilot lacks complete content-bound prompt approval")
    if not authorized_by.strip() or not authorization_reference.strip():
        raise ValueError("authorization identity and external reference are required")

    body = {
        "schema_version": "storyworld_support_pilot_authorization_v2",
        "campaign_id": config["campaign_id"],
        "status": "authorized",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "authorized_by": authorized_by,
        "authorization_reference": authorization_reference,
        "config_sha256": sha256_file(config_path),
        "plan_manifest_sha256": sha256_file(plan_manifest_path),
        "planner_sha256": sha256_file(planner_path),
        "teacher_adapter_sha256": sha256_file(teacher_path),
        "support_scenarios_sha256": sha256_file(scenarios_path),
        "prompt_human_review_bundle_sha256": sha256_file(prompt_review_bundle_path),
        "authorized_job_artifacts": [
            {
                "path": pilot_jobs_path.name,
                "rows": len(jobs),
                "sha256": sha256_file(pilot_jobs_path),
            }
        ],
        "authorized_teacher_calls": len(jobs),
        "reviewed_category_arm_cells": len(cells),
        "automatic_training_approval": False,
        "sealed_evaluation_jobs": 0,
        "development_jobs": 0,
        "claim_boundary": (
            "This authorizes exactly one nonstored teacher call for each hash-listed pilot "
            "job. It does not authorize remaining jobs or approve any response for training."
        ),
        "passed": True,
    }
    return {**body, "authorization_id": f"support-pilot-{sha256_json(body)[:24]}"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--plan-manifest", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--pilot-jobs", type=Path, required=True)
    parser.add_argument("--prompt-review-bundle", type=Path, required=True)
    parser.add_argument("--authorized-by", required=True)
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorize-pilot-spend", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.authorize_pilot_spend:
        raise ValueError("writing authorization requires --authorize-pilot-spend")
    authorization = build_support_pilot_authorization(
        args.config,
        args.plan_manifest,
        args.scenarios,
        args.pilot_jobs,
        args.prompt_review_bundle,
        authorized_by=args.authorized_by,
        authorization_reference=args.authorization_reference,
    )
    write_json(args.output.resolve(), authorization)
    print(json.dumps(authorization, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
