#!/usr/bin/env python3
"""Audit all support outputs and prepare a sampled human release-review queue."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json, write_jsonl
from alignment_harness.trajectory_curriculum import (
    HuggingFaceTokenCounter,
    read_jsonl,
    validate_command_provider_receipt,
)
from scripts.authorize_storyworld_support_pilot import _artifact
from scripts.openai_support_slice_teacher import semantic_errors


def _authorized_hashes(authorization: dict[str, Any]) -> set[str]:
    return {
        str(item["sha256"])
        for item in authorization.get("authorized_job_artifacts", [])
    }


def prepare_support_release(
    config_path: Path,
    plan_manifest_path: Path,
    jobs_path: Path,
    pilot_authorization_path: Path,
    full_authorization_path: Path,
    output_root: Path,
    tokenizer_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    config_path = config_path.resolve()
    plan_manifest_path = plan_manifest_path.resolve()
    jobs_path = jobs_path.resolve()
    pilot_authorization_path = pilot_authorization_path.resolve()
    full_authorization_path = full_authorization_path.resolve()
    output_root = output_root.resolve()
    config = read_json(config_path)
    manifest = read_json(plan_manifest_path)
    pilot_auth = read_json(pilot_authorization_path)
    full_auth = read_json(full_authorization_path)
    if manifest.get("config_sha256") != sha256_file(config_path):
        raise ValueError("support config drifted after plan generation")
    artifact = _artifact(manifest, plan_manifest_path, jobs_path, "jobs.jsonl")
    jobs = read_jsonl(jobs_path)
    if len(jobs) != int(artifact["rows"]) or len(jobs) != int(manifest["jobs"]):
        raise ValueError("support all-jobs artifact differs from the plan")
    if pilot_auth.get("schema_version") != "storyworld_support_pilot_authorization_v2":
        raise ValueError("unexpected support pilot authorization schema")
    if full_auth.get("schema_version") != "storyworld_support_full_campaign_authorization_v2":
        raise ValueError("unexpected support full authorization schema")
    if not pilot_auth.get("passed") or not full_auth.get("passed"):
        raise ValueError("support spend authorizations are not active")
    if pilot_auth.get("campaign_id") != config["campaign_id"] or full_auth.get(
        "campaign_id"
    ) != config["campaign_id"]:
        raise ValueError("support authorizations belong to another campaign")
    if pilot_auth.get("automatic_training_approval") is not False or full_auth.get(
        "automatic_training_approval"
    ) is not False:
        raise ValueError("support spend authorization cannot approve release")

    counter = HuggingFaceTokenCounter(str(tokenizer_path.resolve()))
    rows: list[dict[str, Any]] = []
    totals: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(
            lambda: {"rows": 0, "packed_tokens": 0, "assistant_tokens": 0}
        )
    )
    content_seen: set[str] = set()
    record_ids: set[str] = set()
    by_cell: dict[tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    pilot_allowed = _authorized_hashes(pilot_auth)
    full_allowed = _authorized_hashes(full_auth)
    for job in jobs:
        job_id = str(job["job_id"])
        output_dir = output_root / job_id
        receipt_path = output_dir / "JOB_RECEIPT.json"
        row_path = output_dir / "provisional_row.jsonl"
        if not receipt_path.is_file() or not row_path.is_file():
            raise ValueError(f"support output is missing for {job_id}")
        receipt = read_json(receipt_path)
        if receipt.get("schema_version") != "storyworld_support_job_receipt_v1":
            raise ValueError(f"{job_id}: unexpected job receipt schema")
        expected_auth = pilot_auth if job.get("pilot_job") else full_auth
        expected_auth_path = (
            pilot_authorization_path if job.get("pilot_job") else full_authorization_path
        )
        allowed_hashes = pilot_allowed if job.get("pilot_job") else full_allowed
        if receipt.get("job_id") != job_id or receipt.get("job_sha256") != sha256_json(job):
            raise ValueError(f"{job_id}: receipt/job identity mismatch")
        if receipt.get("authorization_id") != expected_auth["authorization_id"]:
            raise ValueError(f"{job_id}: wrong authorization scope")
        if receipt.get("authorization_sha256") != sha256_file(expected_auth_path):
            raise ValueError(f"{job_id}: authorization content hash mismatch")
        if receipt.get("jobs_file_sha256") not in allowed_hashes:
            raise ValueError(f"{job_id}: job source was not authorized")
        if receipt.get("teacher_adapter_sha256") != expected_auth[
            "teacher_adapter_sha256"
        ]:
            raise ValueError(f"{job_id}: teacher adapter drifted")
        if receipt.get("row_sha256") != sha256_file(row_path):
            raise ValueError(f"{job_id}: row file hash mismatch")
        emitted = read_jsonl(row_path)
        if len(emitted) != 1:
            raise ValueError(f"{job_id}: each support job must emit exactly one row")
        row = emitted[0]
        base = {key: value for key, value in row.items() if key != "record_sha256"}
        if row.get("record_sha256") != sha256_json(base):
            raise ValueError(f"{job_id}: row content hash mismatch")
        if row.get("training_approved") or row.get("source_split") != "train":
            raise ValueError(f"{job_id}: row reached release preparation already approved")
        record_id = str(row["record_id"])
        if record_id in record_ids:
            raise ValueError(f"duplicate support record ID: {record_id}")
        record_ids.add(record_id)
        messages = row.get("messages")
        if not isinstance(messages, list) or messages[:2] != job["messages"]:
            raise ValueError(f"{job_id}: row messages drifted from frozen job")
        if [item.get("role") for item in messages] != ["system", "user", "assistant"]:
            raise ValueError(f"{job_id}: invalid row message roles")
        fingerprint = sha256_json(
            {"arm": row["arm"], "slice": row["slice"], "messages": messages}
        )
        if fingerprint in content_seen:
            raise ValueError(f"duplicate support training content: {job_id}")
        content_seen.add(fingerprint)
        provenance = row.get("external_provenance", {})
        provider = provenance.get("provider_call_receipt", {})
        if provider.get("provider") != "openai_responses_api" or provider.get("store") is not False:
            raise ValueError(f"{job_id}: row lacks a nonstored provider receipt")
        if not provider.get("attempts"):
            raise ValueError(f"{job_id}: row lacks provider attempts")
        request = {
            "model_id": job["model_id"],
            "reasoning_effort": job["reasoning_effort"],
            "response_word_range": job["response_word_range"],
        }
        response = {
            "answer": messages[2]["content"],
            "quality_checks": provenance.get("quality_checks"),
        }
        validate_command_provider_receipt(request, response, provider)
        errors = semantic_errors(request, response)
        if errors:
            raise ValueError(f"{job_id}: " + "; ".join(errors))
        packed, assistant = counter.count_messages(messages)
        arm, slice_id = str(row["arm"]), str(row["slice"])
        totals[arm][slice_id]["rows"] += 1
        totals[arm][slice_id]["packed_tokens"] += packed
        totals[arm][slice_id]["assistant_tokens"] += assistant
        rows.append(row)
        by_cell[(slice_id, str(job["category"]), arm)].append((job, row))

    expected_scenario_cells = int(manifest["scenarios"])
    scenario_arm_counts = Counter((job["scenario_id"], job["arm"]) for job in jobs)
    if len(scenario_arm_counts) != expected_scenario_cells * len(config["arms"]) or set(
        scenario_arm_counts.values()
    ) != {1}:
        raise ValueError("support jobs no longer form complete matched scenario/arm cells")
    coverage = True
    for arm in map(str, config["arms"]):
        for slice_id in config["scenario_counts"]:
            values = totals[arm][slice_id]
            values["packed_target_tokens"] = int(
                config["packed_token_targets_per_arm"][slice_id]
            )
            values["assistant_target_tokens"] = int(
                config["minimum_assistant_token_targets_per_arm"][slice_id]
            )
            values["coverage"] = (
                values["packed_tokens"] >= values["packed_target_tokens"]
                and values["assistant_tokens"] >= values["assistant_target_tokens"]
            )
            coverage = coverage and bool(values["coverage"])
    if not coverage:
        raise ValueError("completed support outputs do not meet every exact token target")

    review_tasks = []
    for (slice_id, category, arm), candidates in sorted(by_cell.items()):
        pilot = [item for item in candidates if item[0]["pilot_job"]]
        remaining = [item for item in candidates if not item[0]["pilot_job"]]
        if len(pilot) != 1 or not remaining:
            raise ValueError("release review cells require one pilot and remaining outputs")
        selected = [pilot[0], min(remaining, key=lambda item: sha256_json(item[0]))]
        for sample_kind, (job, row) in zip(("pilot", "remaining"), selected):
            task_body = {
                "campaign_id": config["campaign_id"],
                "job_id": job["job_id"],
                "record_id": row["record_id"],
                "record_content_sha256": row["record_sha256"],
                "slice": slice_id,
                "category": category,
                "arm": arm,
                "sample_kind": sample_kind,
            }
            review_tasks.append(
                {
                    "review_task_id": f"support-review-{sha256_json(task_body)[:24]}",
                    **task_body,
                    "required_checks": [
                        "answers_the_user_task",
                        "factually_and_operationally_sound",
                        "no_unsupported_literal_identity_or_hidden_knowledge_claim",
                        "no_unsafe_facilitation",
                        "arm_frame_is_bounded_and_non_theatrical",
                    ],
                }
            )
    queue_body = {
        "schema_version": "storyworld_support_release_review_queue_v1",
        "campaign_id": config["campaign_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sampling_policy": "one pilot and one deterministic remaining row per slice/category/arm cell",
        "review_tasks": review_tasks,
        "batch_release_only": True,
        "automatic_training_approval": False,
    }
    queue = {**queue_body, "queue_content_sha256": sha256_json(queue_body)}
    release_manifest = {
        "schema_version": "storyworld_support_provisional_release_manifest_v1",
        "campaign_id": config["campaign_id"],
        "status": "exact_coverage_pending_human_sample_review",
        "config_sha256": sha256_file(config_path),
        "plan_manifest_sha256": sha256_file(plan_manifest_path),
        "jobs_sha256": sha256_file(jobs_path),
        "pilot_authorization_sha256": sha256_file(pilot_authorization_path),
        "full_authorization_sha256": sha256_file(full_authorization_path),
        "tokenizer": counter.description,
        "rows": len(rows),
        "rows_by_arm": dict(sorted(Counter(row["arm"] for row in rows).items())),
        "rows_by_slice": dict(sorted(Counter(row["slice"] for row in rows).items())),
        "exact_token_totals": {
            arm: {slice_id: dict(values) for slice_id, values in slices.items()}
            for arm, slices in totals.items()
        },
        "review_sample_rows": len(review_tasks),
        "review_sample_cells": len(by_cell),
        "training_approved_rows": 0,
        "sealed_evaluation_rows": 0,
        "development_rows": 0,
        "claim_boundary": (
            "Every provider output and exact token target has been audited, but all rows remain "
            "provisional until the complete sampled human review queue is approved."
        ),
        "passed": True,
    }
    return rows, queue, release_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--plan-manifest", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--pilot-authorization", type=Path, required=True)
    parser.add_argument("--full-authorization", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, queue, manifest = prepare_support_release(
        args.config,
        args.plan_manifest,
        args.jobs,
        args.pilot_authorization,
        args.full_authorization,
        args.output_root,
        args.tokenizer,
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = output_dir / "provisional_rows.jsonl"
    queue_path = output_dir / "RELEASE_REVIEW_QUEUE.json"
    write_jsonl(rows_path, rows)
    write_json(queue_path, queue)
    manifest["artifacts"] = {
        "provisional_rows.jsonl": {"rows": len(rows), "sha256": sha256_file(rows_path)},
        "RELEASE_REVIEW_QUEUE.json": {
            "tasks": len(queue["review_tasks"]),
            "sha256": sha256_file(queue_path),
        },
    }
    write_json(output_dir / "PROVISIONAL_RELEASE_MANIFEST.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
