#!/usr/bin/env python3
"""Build the hash-bound review queue for every support-pilot prompt/arm cell."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json
from alignment_harness.trajectory_curriculum import read_jsonl
from scripts.authorize_storyworld_support_pilot import _artifact


def build_support_prompt_review_queue(
    config_path: Path,
    plan_manifest_path: Path,
    scenarios_path: Path,
    pilot_jobs_path: Path,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    plan_manifest_path = plan_manifest_path.resolve()
    scenarios_path = scenarios_path.resolve()
    pilot_jobs_path = pilot_jobs_path.resolve()
    config = read_json(config_path)
    manifest = read_json(plan_manifest_path)
    if config.get("schema_version") != "storyworld_support_slice_campaign_v1":
        raise ValueError("unexpected support campaign schema")
    if manifest.get("schema_version") != "storyworld_support_slice_plan_manifest_v1":
        raise ValueError("unexpected support plan manifest schema")
    if manifest.get("config_sha256") != sha256_file(config_path):
        raise ValueError("support config drifted after plan generation")
    scenario_artifact = _artifact(
        manifest, plan_manifest_path, scenarios_path, "support_scenarios.jsonl"
    )
    pilot_artifact = _artifact(
        manifest, plan_manifest_path, pilot_jobs_path, "pilot_jobs.jsonl"
    )
    scenarios = read_jsonl(scenarios_path)
    jobs = read_jsonl(pilot_jobs_path)
    if len(scenarios) != int(scenario_artifact["rows"]):
        raise ValueError("support scenario count differs from its manifest")
    if len(jobs) != int(pilot_artifact["rows"]) or len(jobs) != 76:
        raise ValueError("support prompt review requires the exact 76-job pilot")
    scenario_map = {str(item["scenario_id"]): item for item in scenarios}
    if len(scenario_map) != len(scenarios):
        raise ValueError("support scenarios contain duplicate IDs")

    tasks: list[dict[str, Any]] = []
    cells: Counter[tuple[str, str, str]] = Counter()
    for job in jobs:
        if (
            job.get("schema_version") != "storyworld_support_job_v1"
            or job.get("pilot_job") is not True
            or job.get("execution_eligible") is not False
            or job.get("automatic_training_approval") is not False
        ):
            raise ValueError("support prompt queue contains an invalid pilot job")
        scenario = scenario_map.get(str(job.get("scenario_id", "")))
        if scenario is None or job.get("scenario_sha256") != sha256_json(scenario):
            raise ValueError("support pilot references missing or drifted scenario content")
        arm = str(job["arm"])
        expected_messages = [
            {"role": "system", "content": config["system_prompts"][arm]},
            {"role": "user", "content": scenario["prompt"]},
        ]
        if job.get("messages") != expected_messages:
            raise ValueError("support pilot prompt drifted from config/scenario content")
        cell = (str(job["slice"]), str(job["category"]), arm)
        cells[cell] += 1
        body = {
            "campaign_id": config["campaign_id"],
            "job_id": job["job_id"],
            "job_content_sha256": sha256_json(job),
            "scenario_id": scenario["scenario_id"],
            "scenario_content_sha256": sha256_json(scenario),
            "messages_content_sha256": sha256_json(expected_messages),
            "slice": job["slice"],
            "category": job["category"],
            "arm": arm,
            "model_id": job["model_id"],
            "reasoning_effort": job["reasoning_effort"],
            "response_word_range": job["response_word_range"],
            "messages": expected_messages,
        }
        tasks.append(
            {
                "review_task_id": f"support-prompt-review-{sha256_json(body)[:24]}",
                **body,
                "required_review_scope": [
                    "user prompt is coherent, original, and category-appropriate",
                    "system frame is bounded, nonliteral, and non-theatrical",
                    "prompt requests useful behavior without unsafe facilitation",
                    "prompt contains no development or sealed-evaluation content",
                    "model, effort, and response range are appropriate for the task",
                ],
            }
        )
    if set(cells.values()) != {1} or len(cells) != len(jobs):
        raise ValueError("support prompt review must cover one unique slice/category/arm cell")
    tasks.sort(key=lambda item: str(item["review_task_id"]))
    queue_body = {
        "schema_version": "storyworld_support_prompt_review_queue_v1",
        "campaign_id": config["campaign_id"],
        "plan_manifest_sha256": sha256_file(plan_manifest_path),
        "support_scenarios_sha256": sha256_file(scenarios_path),
        "pilot_jobs_sha256": sha256_file(pilot_jobs_path),
        "review_tasks": tasks,
        "review_tasks_sha256": sha256_json(tasks),
        "review_tasks_count": len(tasks),
        "review_policy": "complete review of every pilot slice/category/arm prompt cell",
        "automatic_spend_authorization": False,
        "automatic_training_approval": False,
        "passed": True,
    }
    return {**queue_body, "queue_content_sha256": sha256_json(queue_body)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--plan-manifest", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, required=True)
    parser.add_argument("--pilot-jobs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue = build_support_prompt_review_queue(
        args.config, args.plan_manifest, args.scenarios, args.pilot_jobs
    )
    write_json(args.output.resolve(), queue)
    print(
        json.dumps(
            {
                "campaign_id": queue["campaign_id"],
                "review_tasks": queue["review_tasks_count"],
                "queue_content_sha256": queue["queue_content_sha256"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
