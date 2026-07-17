#!/usr/bin/env python3
"""Atomically audit and release the complete real-teacher trace campaign."""

from __future__ import annotations

import argparse
import json
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
    write_json,
    write_jsonl,
)
from alignment_harness.trajectory_curriculum import (
    read_jsonl,
    validate_episode_trace,
)


DEFAULT_PACKAGE = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "package.json"


def _resolve_worlds(
    package: dict[str, Any], jobs: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    needed = {str(job["sweep_path"]) for job in jobs}
    worlds: dict[str, dict[str, Any]] = {}
    for sweep_value in package["instance_sweeps"]:
        sweep_path = (REPO_ROOT / str(sweep_value)).resolve()
        relative = sweep_path.relative_to(REPO_ROOT).as_posix()
        if relative not in needed:
            continue
        materialized, _ = materialize_instance_sweep(REPO_ROOT, sweep_path)
        for world in materialized:
            world_id = str(world["world_id"])
            if world_id in worlds:
                raise ValueError(f"duplicate materialized campaign world: {world_id}")
            worlds[world_id] = world
    missing = sorted({str(job["world_id"]) for job in jobs}.difference(worlds))
    if missing:
        raise ValueError(f"campaign release cannot resolve {len(missing)} job worlds")
    return worlds


def validate_harvest_job_evidence(
    job: dict[str, Any],
    *,
    jobs_path: Path,
    trace_root: Path,
    world: dict[str, Any],
    full_authorization: dict[str, Any] | None,
    full_authorization_path: Path | None,
    authorized_jobs_file_hashes: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate one job/receipt/trace chain and deterministically replay the trace."""
    job_id = str(job["job_id"])
    output_dir = trace_root / job_id
    receipt_path = output_dir / "JOB_RECEIPT.json"
    trace_path = output_dir / "trace.jsonl"
    if not receipt_path.is_file() or not trace_path.is_file():
        raise ValueError(f"completed harvest evidence is missing: {job_id}")
    receipt = read_json(receipt_path)
    if receipt.get("schema_version") != "storyworld_harvest_job_receipt_v1":
        raise ValueError(f"unexpected harvest job receipt schema: {job_id}")
    observed_jobs_file_sha256 = str(receipt.get("jobs_file_sha256", ""))
    jobs_file_binding_valid = (
        observed_jobs_file_sha256 == sha256_file(jobs_path)
        if authorized_jobs_file_hashes is None
        else observed_jobs_file_sha256 in authorized_jobs_file_hashes
    )
    if (
        receipt.get("job_id") != job_id
        or receipt.get("job_sha256") != sha256_json(job)
        or not jobs_file_binding_valid
        or receipt.get("trace_sha256") != sha256_file(trace_path)
        or receipt.get("training_approved") is not True
        or receipt.get("passed") is not True
    ):
        raise ValueError(f"harvest job receipt binding drifted: {job_id}")
    traces = read_jsonl(trace_path)
    if len(traces) != 1:
        raise ValueError(f"harvest job must emit exactly one trace: {job_id}")
    trace = traces[0]
    if receipt.get("trace_id") != trace.get("trace_id"):
        raise ValueError(f"harvest receipt/trace ID drifted: {job_id}")
    if (
        sha256_json(world) != job["world_content_sha256"]
        or trace["episode"]["world_id"] != job["world_id"]
        or trace["episode"]["frame"] != job["arm"]
        or int(trace["episode"]["seed"]) != int(job["episode_seed"])
        or trace["episode"]["actor_schedule"] != job["actor_schedule"]
    ):
        raise ValueError(f"harvest job world/trace identity drifted: {job_id}")
    replay = validate_episode_trace(world, trace)
    if not trace["release"]["training_approved"] or trace["release"][
        "sealed_evaluation"
    ]:
        raise ValueError(f"harvest release contains non-approved or sealed trace: {job_id}")
    if full_authorization is None:
        if not job.get("pilot_job"):
            raise ValueError("non-pilot trace lacks full-campaign authorization")
        authorization_evidence = None
    else:
        if job.get("pilot_job") or full_authorization_path is None:
            raise ValueError("full-campaign authorization cannot cover a pilot trace")
        if (
            receipt.get("full_campaign_authorization_id")
            != full_authorization["authorization_id"]
            or receipt.get("full_campaign_authorization_sha256")
            != sha256_file(full_authorization_path)
        ):
            raise ValueError(f"remaining trace authorization drifted: {job_id}")
        authorization_evidence = {
            "authorization_id": full_authorization["authorization_id"],
            "authorization_sha256": sha256_file(full_authorization_path),
        }
    evidence = {
        "job_id": job_id,
        "pilot_job": bool(job["pilot_job"]),
        "job_sha256": sha256_json(job),
        "jobs_file_sha256": observed_jobs_file_sha256,
        "job_receipt_path": str(receipt_path.resolve()),
        "job_receipt_sha256": sha256_file(receipt_path),
        "trace_path": str(trace_path.resolve()),
        "trace_sha256": sha256_file(trace_path),
        "trace_id": trace["trace_id"],
        "trace_content_sha256": sha256_json(trace),
        "world_id": world["world_id"],
        "arm": job["arm"],
        "family_id": job["family_id"],
        "actor_schedule_mode": job["actor_schedule_mode"],
        "turns": replay["turns"],
        "provider_receipted_calls": replay["provider_receipted_calls"],
        "authorization": authorization_evidence,
    }
    return trace, evidence


def build_harvest_release(
    package_path: Path,
    pilot_calibration_path: Path,
    pilot_review_bundle_path: Path,
    pilot_jobs_path: Path,
    pilot_trace_root: Path,
    campaign_manifest_path: Path,
    remaining_jobs_path: Path,
    remaining_trace_root: Path,
    full_authorization_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    package_path = package_path.resolve()
    pilot_calibration_path = pilot_calibration_path.resolve()
    pilot_review_bundle_path = pilot_review_bundle_path.resolve()
    pilot_jobs_path = pilot_jobs_path.resolve()
    pilot_trace_root = pilot_trace_root.resolve()
    campaign_manifest_path = campaign_manifest_path.resolve()
    remaining_jobs_path = remaining_jobs_path.resolve()
    remaining_trace_root = remaining_trace_root.resolve()
    full_authorization_path = full_authorization_path.resolve()
    package = read_json(package_path)
    package_validation = validate_curriculum_package(REPO_ROOT, package_path)
    calibration = read_json(pilot_calibration_path)
    pilot_review_bundle = read_json(pilot_review_bundle_path)
    campaign = read_json(campaign_manifest_path)
    authorization = read_json(full_authorization_path)
    if calibration.get("schema_version") != "storyworld_real_pilot_calibration_v1" or not calibration.get(
        "passed"
    ):
        raise ValueError("invalid real-pilot calibration")
    if (
        pilot_review_bundle.get("schema_version")
        != "storyworld_real_pilot_human_review_bundle_v1"
        or pilot_review_bundle.get("pilot_calibration_sha256")
        != sha256_file(pilot_calibration_path)
        or pilot_review_bundle.get("all_pilot_traces_approved") is not True
        or pilot_review_bundle.get("passed") is not True
    ):
        raise ValueError("invalid real-pilot human review bundle")
    if campaign.get("schema_version") != "storyworld_harvest_campaign_manifest_v1" or not campaign.get(
        "passed"
    ):
        raise ValueError("invalid post-pilot campaign manifest")
    if authorization.get("schema_version") != "storyworld_full_campaign_authorization_v1" or not authorization.get(
        "passed"
    ):
        raise ValueError("invalid full-campaign authorization")
    if calibration.get("pilot_jobs_sha256") != sha256_file(pilot_jobs_path):
        raise ValueError("pilot calibration does not bind the supplied pilot jobs")
    if authorization.get("pilot_calibration_sha256") != sha256_file(
        pilot_calibration_path
    ) or authorization.get("campaign_manifest_sha256") != sha256_file(
        campaign_manifest_path
    ):
        raise ValueError("full-campaign authorization is not bound to the pilot/campaign")
    if authorization.get("pilot_human_review_bundle_sha256") != sha256_file(
        pilot_review_bundle_path
    ):
        raise ValueError("full-campaign authorization is not bound to pilot human review")
    if authorization.get("campaign_id") != campaign["campaign_id"]:
        raise ValueError("full-campaign authorization belongs to another campaign")
    remaining_hash = sha256_file(remaining_jobs_path)
    authorized_job_hashes = {
        str(item["sha256"])
        for item in authorization.get("authorized_job_artifacts", [])
    }
    if remaining_hash not in authorized_job_hashes:
        raise ValueError("remaining jobs are not hash-listed by the authorization")
    pilot_jobs = read_jsonl(pilot_jobs_path)
    remaining_jobs = read_jsonl(remaining_jobs_path)
    if (
        len(pilot_jobs) != int(calibration["pilot_jobs"])
        or len(remaining_jobs) != int(campaign["remaining_jobs"])
        or len(remaining_jobs) != int(authorization["authorized_remaining_jobs"])
        or len(pilot_jobs) + len(remaining_jobs) != int(campaign["jobs"])
    ):
        raise ValueError("pilot plus remaining job counts do not reconstruct the campaign")
    if any(not job.get("pilot_job") for job in pilot_jobs) or any(
        job.get("pilot_job") for job in remaining_jobs
    ):
        raise ValueError("pilot/remaining job partition drifted")
    jobs = [*pilot_jobs, *remaining_jobs]
    job_ids = [str(job["job_id"]) for job in jobs]
    if len(set(job_ids)) != len(job_ids):
        raise ValueError("harvest release contains duplicate job IDs")
    worlds = _resolve_worlds(package, jobs)
    traces = []
    evidence = []
    for job in pilot_jobs:
        trace, item = validate_harvest_job_evidence(
            job,
            jobs_path=pilot_jobs_path,
            trace_root=pilot_trace_root,
            world=worlds[str(job["world_id"])],
            full_authorization=None,
            full_authorization_path=None,
        )
        traces.append(trace)
        evidence.append(item)
    pilot_trace_ids = sorted(item["trace_id"] for item in evidence)
    if calibration.get("trace_ids_sha256") != sha256_json(pilot_trace_ids):
        raise ValueError("pilot trace set drifted after calibration")
    for job in remaining_jobs:
        trace, item = validate_harvest_job_evidence(
            job,
            jobs_path=remaining_jobs_path,
            trace_root=remaining_trace_root,
            world=worlds[str(job["world_id"])],
            full_authorization=authorization,
            full_authorization_path=full_authorization_path,
            authorized_jobs_file_hashes=authorized_job_hashes,
        )
        traces.append(trace)
        evidence.append(item)

    if len({str(trace["trace_id"]) for trace in traces}) != len(traces):
        raise ValueError("harvest release contains duplicate trace IDs")
    arm_counts = Counter(str(item["arm"]) for item in evidence)
    family_counts = Counter(str(item["family_id"]) for item in evidence)
    schedule_counts = Counter(str(item["actor_schedule_mode"]) for item in evidence)
    family_arm_counts: dict[str, dict[str, int]] = defaultdict(dict)
    for family in sorted(family_counts):
        for arm in sorted(arm_counts):
            family_arm_counts[family][arm] = sum(
                item["family_id"] == family and item["arm"] == arm
                for item in evidence
            )
    if dict(sorted(arm_counts.items())) != campaign["jobs_by_arm"]:
        raise ValueError("released trace arm balance drifted from the campaign")
    if dict(sorted(family_counts.items())) != campaign["jobs_by_family"]:
        raise ValueError("released trace family balance drifted from the campaign")
    if dict(sorted(schedule_counts.items())) != campaign["actor_schedules"]:
        raise ValueError("released single/dyadic balance drifted from the campaign")
    if dict(sorted(family_arm_counts.items())) != campaign["jobs_by_family_and_arm"]:
        raise ValueError("released family-by-arm matrix drifted from the campaign")
    provider_calls = sum(int(item["provider_receipted_calls"]) for item in evidence)
    if provider_calls != int(campaign["projected_teacher_calls"]):
        raise ValueError("released provider-call count drifted from the campaign")
    remaining_calls = sum(
        int(item["provider_receipted_calls"])
        for item in evidence
        if not item["pilot_job"]
    )
    if (
        remaining_calls != int(campaign["projected_remaining_teacher_calls"])
        or remaining_calls != int(authorization["expected_teacher_calls"])
        or remaining_calls > int(authorization["teacher_call_ceiling"])
    ):
        raise ValueError("released remaining provider-call count drifted or exceeded its ceiling")

    ordered_pairs = sorted(
        zip(traces, evidence), key=lambda pair: str(pair[1]["job_id"])
    )
    traces = [pair[0] for pair in ordered_pairs]
    evidence = [pair[1] for pair in ordered_pairs]
    manifest = {
        "schema_version": "storyworld_harvest_approved_release_manifest_v1",
        "status": "approved_real_teacher_traces_for_canonical_derivation",
        "package_sha256": sha256_file(package_path),
        "package_validation_passed": bool(package_validation["passed"]),
        "pilot_calibration_sha256": sha256_file(pilot_calibration_path),
        "pilot_human_review_bundle_sha256": sha256_file(pilot_review_bundle_path),
        "pilot_jobs_sha256": sha256_file(pilot_jobs_path),
        "campaign_manifest_sha256": sha256_file(campaign_manifest_path),
        "remaining_jobs_sha256": remaining_hash,
        "full_campaign_authorization_sha256": sha256_file(full_authorization_path),
        "release_builder_sha256": sha256_file(Path(__file__).resolve()),
        "traces": len(traces),
        "training_approved_traces": len(traces),
        "traces_by_arm": dict(sorted(arm_counts.items())),
        "traces_by_family": dict(sorted(family_counts.items())),
        "actor_schedules": dict(sorted(schedule_counts.items())),
        "provider_receipted_calls": provider_calls,
        "job_evidence": evidence,
        "job_evidence_sha256": sha256_json(evidence),
        "trace_content_sha256": [sha256_json(trace) for trace in traces],
        "source_split": "train",
        "sealed_evaluation_traces": 0,
        "development_training_traces": 0,
        "passed": True,
    }
    return traces, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--pilot-calibration", type=Path, required=True)
    parser.add_argument("--pilot-review-bundle", type=Path, required=True)
    parser.add_argument("--pilot-jobs", type=Path, required=True)
    parser.add_argument("--pilot-trace-root", type=Path, required=True)
    parser.add_argument("--campaign-manifest", type=Path, required=True)
    parser.add_argument("--remaining-jobs", type=Path, required=True)
    parser.add_argument("--remaining-trace-root", type=Path, required=True)
    parser.add_argument("--full-authorization", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    traces, manifest = build_harvest_release(
        args.package,
        args.pilot_calibration,
        args.pilot_review_bundle,
        args.pilot_jobs,
        args.pilot_trace_root,
        args.campaign_manifest,
        args.remaining_jobs,
        args.remaining_trace_root,
        args.full_authorization,
    )
    if args.apply:
        if args.output_dir is None:
            raise ValueError("--output-dir is required with --apply")
        output_dir = args.output_dir.resolve()
        traces_path = output_dir / "approved_traces.jsonl"
        manifest_path = output_dir / "HARVEST_RELEASE_MANIFEST.json"
        if traces_path.exists() or manifest_path.exists():
            raise ValueError("harvest release output already exists")
        output_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(traces_path, traces)
        manifest["approved_traces_path"] = traces_path.name
        manifest["approved_traces_sha256"] = sha256_file(traces_path)
        write_json(manifest_path, manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
