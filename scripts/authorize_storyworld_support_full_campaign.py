#!/usr/bin/env python3
"""Authorize only a calibrated support campaign's hash-listed remaining jobs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json
from alignment_harness.trajectory_curriculum import read_jsonl
from scripts.authorize_storyworld_support_pilot import _artifact


def build_support_full_authorization(
    config_path: Path,
    plan_manifest_path: Path,
    calibration_path: Path,
    pilot_review_bundle_path: Path,
    remaining_jobs_path: Path,
    *,
    authorized_by: str,
    authorization_reference: str,
    max_teacher_calls: int,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    plan_manifest_path = plan_manifest_path.resolve()
    calibration_path = calibration_path.resolve()
    pilot_review_bundle_path = pilot_review_bundle_path.resolve()
    remaining_jobs_path = remaining_jobs_path.resolve()
    config = read_json(config_path)
    manifest = read_json(plan_manifest_path)
    calibration = read_json(calibration_path)
    pilot_review_bundle = read_json(pilot_review_bundle_path)
    if calibration.get("schema_version") != "storyworld_support_real_pilot_calibration_v1":
        raise ValueError("unexpected support pilot calibration schema")
    if not calibration.get("passed") or not calibration.get(
        "full_campaign_ready_for_human_authorization"
    ):
        raise ValueError("support pilot did not conservatively cover every token target")
    if calibration.get("status") != "pilot_passed_pending_human_full_campaign_authorization":
        raise ValueError("support pilot calibration is not awaiting authorization")
    if calibration.get("campaign_id") != config.get("campaign_id"):
        raise ValueError("support calibration belongs to a different campaign")
    if calibration.get("config_sha256") != sha256_file(config_path):
        raise ValueError("support config drifted after pilot calibration")
    if calibration.get("plan_manifest_sha256") != sha256_file(plan_manifest_path):
        raise ValueError("support plan drifted after pilot calibration")
    if (
        pilot_review_bundle.get("schema_version")
        != "storyworld_support_pilot_human_review_bundle_v1"
        or pilot_review_bundle.get("pilot_calibration_sha256")
        != sha256_file(calibration_path)
        or pilot_review_bundle.get("all_pilot_outputs_approved") is not True
        or int(pilot_review_bundle.get("approved_outputs", 0))
        != int(calibration["pilot_jobs"])
        or pilot_review_bundle.get("passed") is not True
    ):
        raise ValueError("support pilot lacks complete content-bound human approval")
    artifact = _artifact(
        manifest, plan_manifest_path, remaining_jobs_path, "remaining_jobs.jsonl"
    )
    jobs = read_jsonl(remaining_jobs_path)
    if len(jobs) != int(artifact["rows"]) or len(jobs) != int(manifest["remaining_jobs"]):
        raise ValueError("remaining support job count differs from the plan")
    if not jobs or any(job.get("pilot_job") for job in jobs):
        raise ValueError("remaining support artifact contains a pilot job")
    if any(job.get("execution_eligible") for job in jobs):
        raise ValueError("remaining jobs must retain their frozen non-executable marker")
    if any(job.get("automatic_training_approval") for job in jobs):
        raise ValueError("remaining support jobs cannot automatically approve training rows")
    if len({str(job["job_id"]) for job in jobs}) != len(jobs):
        raise ValueError("remaining support artifact contains duplicate job IDs")
    if int(max_teacher_calls) != len(jobs):
        raise ValueError("teacher call ceiling must equal the exact remaining job count")
    if not authorized_by.strip() or not authorization_reference.strip():
        raise ValueError("authorization identity and external reference are required")

    authorized_artifacts = [
        {
            "path": remaining_jobs_path.name,
            "rows": len(jobs),
            "sha256": sha256_file(remaining_jobs_path),
        }
    ]
    shard_rows = 0
    for item in manifest.get("artifacts", {}).get("shards", []):
        shard_path = (plan_manifest_path.parent / str(item["path"])).resolve()
        if not shard_path.is_file() or sha256_file(shard_path) != item.get("sha256"):
            raise ValueError(f"support shard is missing or drifted: {item.get('path')}")
        rows = read_jsonl(shard_path)
        if len(rows) != int(item["rows"]) or any(job.get("pilot_job") for job in rows):
            raise ValueError(f"support shard contents are invalid: {item.get('path')}")
        shard_rows += len(rows)
        authorized_artifacts.append(
            {
                "path": str(item["path"]),
                "rows": len(rows),
                "sha256": sha256_file(shard_path),
            }
        )
    if shard_rows != len(jobs):
        raise ValueError("support shards do not partition the remaining jobs")

    body = {
        "schema_version": "storyworld_support_full_campaign_authorization_v2",
        "campaign_id": config["campaign_id"],
        "status": "authorized",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "authorized_by": authorized_by,
        "authorization_reference": authorization_reference,
        "config_sha256": sha256_file(config_path),
        "plan_manifest_sha256": sha256_file(plan_manifest_path),
        "pilot_calibration_sha256": sha256_file(calibration_path),
        "pilot_human_review_bundle_sha256": sha256_file(pilot_review_bundle_path),
        "pilot_authorization_id": calibration["pilot_authorization_id"],
        "teacher_adapter_sha256": calibration["teacher_adapter_sha256"],
        "tokenizer": calibration["tokenizer"],
        "full_campaign_projection": calibration["full_campaign_projection"],
        "authorized_job_artifacts": authorized_artifacts,
        "authorized_remaining_jobs": len(jobs),
        "authorized_teacher_calls": len(jobs),
        "teacher_call_ceiling": int(max_teacher_calls),
        "automatic_training_approval": False,
        "pilot_replay_authorized": False,
        "sealed_evaluation_jobs": 0,
        "development_jobs": 0,
        "claim_boundary": (
            "This authorizes only the hash-listed remaining support jobs after an exact-token "
            "pilot and human sample review. It does not authorize pilot replay, plan drift, "
            "extra calls, or training release."
        ),
        "passed": True,
    }
    return {**body, "authorization_id": f"support-full-{sha256_json(body)[:24]}"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--plan-manifest", type=Path, required=True)
    parser.add_argument("--pilot-calibration", type=Path, required=True)
    parser.add_argument("--pilot-review-bundle", type=Path, required=True)
    parser.add_argument("--remaining-jobs", type=Path, required=True)
    parser.add_argument("--authorized-by", required=True)
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--max-teacher-calls", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorize-full-campaign-spend", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.authorize_full_campaign_spend:
        raise ValueError("writing authorization requires --authorize-full-campaign-spend")
    authorization = build_support_full_authorization(
        args.config,
        args.plan_manifest,
        args.pilot_calibration,
        args.pilot_review_bundle,
        args.remaining_jobs,
        authorized_by=args.authorized_by,
        authorization_reference=args.authorization_reference,
        max_teacher_calls=args.max_teacher_calls,
    )
    write_json(args.output.resolve(), authorization)
    print(json.dumps(authorization, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
