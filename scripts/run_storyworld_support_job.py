#!/usr/bin/env python3
"""Run one hash-authorized support job and emit one provisional training row."""

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

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json, write_jsonl
from alignment_harness.trajectory_curriculum import CommandTeacher, read_jsonl
from scripts.openai_support_slice_teacher import semantic_errors


DEFAULT_TEACHER = REPO_ROOT / "scripts" / "openai_support_slice_teacher.py"


def _select_job(path: Path, job_id: str | None, job_index: int | None) -> dict[str, Any]:
    jobs = read_jsonl(path)
    if (job_id is None) == (job_index is None):
        raise ValueError("specify exactly one of --job-id or --job-index")
    if job_id is not None:
        matches = [item for item in jobs if item.get("job_id") == job_id]
        if len(matches) != 1:
            raise ValueError(f"expected exactly one job_id={job_id}; found {len(matches)}")
        return matches[0]
    assert job_index is not None
    if not 0 <= job_index < len(jobs):
        raise ValueError(f"job index {job_index} is outside 0..{len(jobs) - 1}")
    return jobs[job_index]


def validate_support_authorization(
    authorization: dict[str, Any], job: dict[str, Any], jobs_path: Path
) -> None:
    expected_schema = (
        "storyworld_support_pilot_authorization_v2"
        if job.get("pilot_job")
        else "storyworld_support_full_campaign_authorization_v2"
    )
    if authorization.get("schema_version") != expected_schema:
        raise ValueError("support authorization has the wrong scope for this job")
    if authorization.get("status") != "authorized" or not authorization.get("passed"):
        raise ValueError("support authorization is not active")
    if authorization.get("campaign_id") != job.get("campaign_id"):
        raise ValueError("support authorization belongs to a different campaign")
    if authorization.get("automatic_training_approval") is not False:
        raise ValueError("support spend authorization cannot approve training data")
    observed = sha256_file(jobs_path)
    if observed not in {
        str(item.get("sha256"))
        for item in authorization.get("authorized_job_artifacts", [])
    }:
        raise ValueError("jobs file is not hash-listed by the support authorization")


def validate_support_job_preflight(
    job: dict[str, Any],
    authorization: dict[str, Any] | None,
    jobs_path: Path,
    *,
    authorize_teacher_spend: bool,
) -> None:
    if job.get("schema_version") != "storyworld_support_job_v1":
        raise ValueError("unexpected support job schema")
    if job.get("source_split") != "train" or not job.get("training_eligible"):
        raise ValueError("support runner refuses non-training jobs")
    if job.get("automatic_training_approval"):
        raise ValueError("support runner refuses automatically approved jobs")
    if job.get("execution_eligible") is not False:
        raise ValueError("frozen support jobs must remain non-executable without authorization")
    if authorization is None:
        raise ValueError("support job requires a hash-bound pilot or full authorization")
    validate_support_authorization(authorization, job, jobs_path)
    if not authorize_teacher_spend:
        raise ValueError("teacher spend requires explicit --authorize-teacher-spend")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--job-id")
    parser.add_argument("--job-index", type=int)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--teacher", type=Path, default=DEFAULT_TEACHER)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--authorize-teacher-spend", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    jobs_path = args.jobs.resolve()
    authorization_path = args.authorization.resolve()
    job = _select_job(jobs_path, args.job_id, args.job_index)
    authorization = read_json(authorization_path)
    validate_support_job_preflight(
        job,
        authorization,
        jobs_path,
        authorize_teacher_spend=args.authorize_teacher_spend,
    )

    output_dir = args.output_root.resolve() / str(job["job_id"])
    claim_path = output_dir / "RUN_CLAIM.json"
    row_path = output_dir / "provisional_row.jsonl"
    receipt_path = output_dir / "JOB_RECEIPT.json"
    job_sha256 = sha256_json(job)
    if receipt_path.is_file():
        receipt = read_json(receipt_path)
        if receipt.get("job_sha256") != job_sha256:
            raise ValueError("existing support receipt belongs to different job content")
        if not row_path.is_file() or receipt.get("row_sha256") != sha256_file(row_path):
            raise ValueError("existing support row is missing or hash-mismatched")
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
        return 0
    if claim_path.is_file():
        claim = read_json(claim_path)
        if claim.get("job_sha256") != job_sha256:
            raise ValueError("existing support run claim belongs to different job content")
        raise ValueError(
            "an incomplete support run claim exists; inspect provider state before retrying"
        )

    teacher_path = args.teacher.resolve()
    if not teacher_path.is_file():
        raise ValueError("support teacher adapter is missing")
    if authorization.get("teacher_adapter_sha256") != sha256_file(teacher_path):
        raise ValueError("support teacher adapter is not hash-bound by the authorization")
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(
        claim_path,
        {
            "schema_version": "storyworld_support_run_claim_v1",
            "campaign_id": job["campaign_id"],
            "job_id": job["job_id"],
            "job_sha256": job_sha256,
            "jobs_file_sha256": sha256_file(jobs_path),
            "authorization_id": authorization["authorization_id"],
            "authorization_sha256": sha256_file(authorization_path),
            "teacher_adapter_sha256": sha256_file(teacher_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "claimed_before_teacher_invocation",
            "claim_boundary": (
                "Absence of JOB_RECEIPT.json after this claim is ambiguous; do not retry "
                "without checking whether the provider call was spent."
            ),
        },
    )
    request = {
        "schema_version": "storyworld_support_teacher_request_v1",
        "job_id": job["job_id"],
        "model_id": job["model_id"],
        "reasoning_effort": job["reasoning_effort"],
        "messages": job["messages"],
        "response_word_range": job["response_word_range"],
    }
    teacher = CommandTeacher([sys.executable, str(teacher_path)], args.timeout_seconds)
    response = teacher.generate(request)
    errors = semantic_errors(request, response)
    if errors:
        raise ValueError("support teacher semantic validation failed: " + "; ".join(errors))
    if not teacher.receipt().get("release_eligible"):
        raise ValueError("support teacher output lacks a complete provider receipt chain")
    messages = [*job["messages"], {"role": "assistant", "content": response["answer"]}]
    base = {
        "schema_version": "storyworld_training_view_v1",
        "record_id": f"{job['job_id']}__support",
        "view": "sft_support",
        "slice": job["slice"],
        "arm": job["arm"],
        "source_trace_id": None,
        "world_id": None,
        "source_split": "train",
        "training_eligible": True,
        "training_approved": False,
        "messages": messages,
        "external_provenance": {
            "campaign_id": job["campaign_id"],
            "job_id": job["job_id"],
            "job_sha256": job_sha256,
            "scenario_id": job["scenario_id"],
            "scenario_sha256": job["scenario_sha256"],
            "category": job["category"],
            "model_id": job["model_id"],
            "reasoning_effort": job["reasoning_effort"],
            "provider_call_receipt": teacher.call_receipt(),
            "quality_checks": response["quality_checks"],
            "pilot_job": bool(job["pilot_job"]),
            "authorization_id": authorization["authorization_id"],
        },
    }
    row = {**base, "record_sha256": sha256_json(base)}
    write_jsonl(row_path, [row])
    receipt = {
        "schema_version": "storyworld_support_job_receipt_v1",
        "campaign_id": job["campaign_id"],
        "job_id": job["job_id"],
        "job_sha256": job_sha256,
        "jobs_file_sha256": sha256_file(jobs_path),
        "authorization_id": authorization["authorization_id"],
        "authorization_sha256": sha256_file(authorization_path),
        "teacher_adapter_sha256": sha256_file(teacher_path),
        "teacher": teacher.receipt(),
        "record_id": row["record_id"],
        "record_sha256": row["record_sha256"],
        "row_path": row_path.name,
        "row_sha256": sha256_file(row_path),
        "training_approved": False,
        "sealed_evaluation_rows": 0,
        "development_rows": 0,
        "passed": True,
    }
    write_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
