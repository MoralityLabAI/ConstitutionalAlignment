#!/usr/bin/env python3
"""Execute one approved, hash-bound campaign job with the real command teacher."""

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

from alignment_harness.storyworlds import (
    materialize_instance_sweep,
    sha256_file,
    sha256_json,
    validate_world,
    write_json,
    write_jsonl,
)
from alignment_harness.trajectory_curriculum import (
    CommandTeacher,
    harvest_episode,
    load_teacher_ensemble,
    read_jsonl,
)


DEFAULT_ENSEMBLE = (
    REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "teacher_ensemble.json"
)


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


def _approved(world: dict[str, Any]) -> bool:
    return world["review"]["status"] == "approved" and all(
        item["status"] in {"approved", "not_required"}
        for item in world["review"]["requirements"]
    )


def validate_job_preflight(
    job: dict[str, Any], *, authorize_teacher_spend: bool, full_campaign_authorized: bool = False
) -> None:
    """Reject unsafe jobs before constructing or invoking a command teacher."""
    if job.get("schema_version") != "storyworld_harvest_job_v1":
        raise ValueError("unexpected campaign job schema")
    if job.get("source_split") != "train" or not job.get("training_eligible"):
        raise ValueError("runner refuses non-training campaign jobs")
    if job.get("teacher_mode") != "command":
        raise ValueError("runner refuses fixture-teacher campaign jobs")
    if not job.get("execution_eligible"):
        raise ValueError(
            "job is not execution eligible; obtain reviews and regenerate the campaign plan"
        )
    if not job.get("pilot_job") and not full_campaign_authorized:
        raise ValueError(
            "v1 runner refuses full-campaign jobs until the pilot and exact-tokenizer "
            "recalibration gates are recorded in an explicit authorization"
        )
    if not authorize_teacher_spend:
        raise ValueError("teacher spend requires explicit --authorize-teacher-spend")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute one review-approved train job from a frozen campaign JSONL."
    )
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--job-id")
    parser.add_argument("--job-index", type=int)
    parser.add_argument("--ensemble", type=Path, default=DEFAULT_ENSEMBLE)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument(
        "--authorize-teacher-spend",
        action="store_true",
        help="Explicitly authorize this one review-approved job to invoke the teacher.",
    )
    parser.add_argument(
        "--full-campaign-authorization",
        type=Path,
        help="Hash-bound authorization receipt required for every non-pilot job.",
    )
    return parser.parse_args()


def validate_full_campaign_authorization(
    authorization: dict[str, Any], job: dict[str, Any], jobs_path: Path
) -> None:
    if authorization.get("schema_version") != "storyworld_full_campaign_authorization_v1":
        raise ValueError("unexpected full-campaign authorization schema")
    if authorization.get("status") != "authorized" or not authorization.get("passed"):
        raise ValueError("full-campaign authorization is not active")
    if authorization.get("campaign_id") != job.get("campaign_id"):
        raise ValueError("full-campaign authorization belongs to a different campaign")
    jobs_sha256 = sha256_file(jobs_path)
    if jobs_sha256 not in {
        str(item["sha256"]) for item in authorization.get("authorized_job_artifacts", [])
    }:
        raise ValueError("jobs file is not hash-listed by the full-campaign authorization")
    if job.get("pilot_job"):
        raise ValueError("full-campaign authorization cannot be used to replay a pilot job")


def main() -> int:
    args = parse_args()
    jobs_path = args.jobs.resolve()
    job = _select_job(jobs_path, args.job_id, args.job_index)
    full_authorization = None
    if args.full_campaign_authorization is not None:
        full_authorization = json.loads(
            args.full_campaign_authorization.resolve().read_text(encoding="utf-8-sig")
        )
        validate_full_campaign_authorization(full_authorization, job, jobs_path)
    validate_job_preflight(
        job,
        authorize_teacher_spend=args.authorize_teacher_spend,
        full_campaign_authorized=full_authorization is not None,
    )

    output_dir = args.output_root.resolve() / str(job["job_id"])
    receipt_path = output_dir / "JOB_RECEIPT.json"
    trace_path = output_dir / "trace.jsonl"
    claim_path = output_dir / "RUN_CLAIM.json"
    job_sha256 = sha256_json(job)
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("job_sha256") != job_sha256:
            raise ValueError("existing job receipt belongs to different job content")
        if not trace_path.is_file() or sha256_file(trace_path) != receipt.get("trace_sha256"):
            raise ValueError("existing job trace is missing or hash-mismatched")
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
        return 0
    if claim_path.is_file():
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        if claim.get("job_sha256") != job_sha256:
            raise ValueError("existing run claim belongs to different job content")
        raise ValueError(
            "an incomplete run claim exists; inspect it before explicitly resolving a "
            "possibly spent teacher job"
        )

    sweep_path = (REPO_ROOT / str(job["sweep_path"])).resolve()
    worlds, _ = materialize_instance_sweep(REPO_ROOT, sweep_path)
    matches = [world for world in worlds if world["world_id"] == job["world_id"]]
    if len(matches) != 1:
        raise ValueError(f"campaign world could not be resolved exactly once: {job['world_id']}")
    world = matches[0]
    validation = validate_world(world)
    if sha256_json(world) != job["world_content_sha256"]:
        raise ValueError("campaign world content hash drifted")
    if validation["transition_graph_sha256"] != job["transition_graph_sha256"]:
        raise ValueError("campaign transition graph hash drifted")
    if not _approved(world):
        raise ValueError("resolved world is not review-approved")

    ensemble_path = args.ensemble.resolve()
    ensemble = load_teacher_ensemble(ensemble_path)
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json(
        claim_path,
        {
            "schema_version": "storyworld_harvest_run_claim_v1",
            "campaign_id": job["campaign_id"],
            "job_id": job["job_id"],
            "job_sha256": job_sha256,
            "jobs_file_sha256": sha256_file(jobs_path),
            "world_content_sha256": sha256_json(world),
            "transition_graph_sha256": validation["transition_graph_sha256"],
            "ensemble_sha256": sha256_file(ensemble_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "claimed_before_teacher_invocation",
            **(
                {
                    "full_campaign_authorization_id": full_authorization[
                        "authorization_id"
                    ],
                    "full_campaign_authorization_sha256": sha256_file(
                        args.full_campaign_authorization.resolve()
                    ),
                }
                if full_authorization is not None
                else {}
            ),
            "claim_boundary": (
                "Absence of JOB_RECEIPT.json after this claim is ambiguous; do not retry "
                "without checking whether provider calls were spent."
            ),
        },
    )
    teacher = CommandTeacher.from_text(str(job["agent_command"]), args.timeout_seconds)
    trace = harvest_episode(
        world,
        str(job["arm"]),
        int(job["episode_seed"]),
        teacher,
        ensemble,
        world_source_path=(
            f"{job['sweep_path']}#{job['profile_id']}/{job['world_id']}"
        ),
        actor_schedule=list(map(str, job["actor_schedule"])),
    )
    if not trace["release"]["training_approved"]:
        raise ValueError("real job completed without a training-approved trace")

    write_jsonl(trace_path, [trace])
    receipt = {
        "schema_version": "storyworld_harvest_job_receipt_v1",
        "campaign_id": job["campaign_id"],
        "job_id": job["job_id"],
        "job_sha256": job_sha256,
        "jobs_file_sha256": sha256_file(jobs_path),
        "world_id": world["world_id"],
        "world_content_sha256": sha256_json(world),
        "transition_graph_sha256": validation["transition_graph_sha256"],
        "ensemble_sha256": sha256_file(ensemble_path),
        "teacher": teacher.receipt(),
        "trace_id": trace["trace_id"],
        "turns": len(trace["turns"]),
        "trace_path": trace_path.name,
        "trace_sha256": sha256_file(trace_path),
        "training_approved": True,
        **(
            {
                "full_campaign_authorization_id": full_authorization[
                    "authorization_id"
                ],
                "full_campaign_authorization_sha256": sha256_file(
                    args.full_campaign_authorization.resolve()
                ),
            }
            if full_authorization is not None
            else {}
        ),
        "sealed_evaluation_rows": 0,
        "passed": True,
    }
    write_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
