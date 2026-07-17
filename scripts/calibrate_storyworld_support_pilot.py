#!/usr/bin/env python3
"""Audit the real support pilot and conservatively project exact token yield."""

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

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json
from alignment_harness.trajectory_curriculum import (
    HuggingFaceTokenCounter,
    read_jsonl,
    validate_command_provider_receipt,
)
from scripts.authorize_storyworld_support_pilot import _artifact
from scripts.openai_support_slice_teacher import _word_count, semantic_errors
from scripts.run_storyworld_support_job import validate_support_authorization


def _sum_numeric_usage(target: dict[str, int], value: Any, prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{prefix}.{key}" if prefix else str(key)
            _sum_numeric_usage(target, child, location)
    elif isinstance(value, int) and not isinstance(value, bool):
        target[prefix] = target.get(prefix, 0) + value


def audit_support_pilot(
    config_path: Path,
    plan_manifest_path: Path,
    pilot_jobs_path: Path,
    authorization_path: Path,
    output_root: Path,
    tokenizer_path: Path,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    plan_manifest_path = plan_manifest_path.resolve()
    pilot_jobs_path = pilot_jobs_path.resolve()
    authorization_path = authorization_path.resolve()
    output_root = output_root.resolve()
    config = read_json(config_path)
    manifest = read_json(plan_manifest_path)
    authorization = read_json(authorization_path)
    if manifest.get("schema_version") != "storyworld_support_slice_plan_manifest_v1":
        raise ValueError("unexpected support plan manifest schema")
    if manifest.get("config_sha256") != sha256_file(config_path):
        raise ValueError("support config drifted after plan generation")
    artifact = _artifact(
        manifest, plan_manifest_path, pilot_jobs_path, "pilot_jobs.jsonl"
    )
    jobs = read_jsonl(pilot_jobs_path)
    if len(jobs) != int(artifact["rows"]) or len(jobs) != int(manifest["pilot_jobs"]):
        raise ValueError("support pilot job count differs from the frozen plan")
    if len({str(job["job_id"]) for job in jobs}) != len(jobs):
        raise ValueError("support pilot contains duplicate job IDs")

    counter = HuggingFaceTokenCounter(str(tokenizer_path.resolve()))
    token_cells: dict[tuple[str, str, str], dict[str, int]] = {}
    token_totals: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(
            lambda: {"rows": 0, "packed_tokens": 0, "assistant_tokens": 0}
        )
    )
    usage_totals: dict[str, int] = {}
    word_counts: list[int] = []
    record_ids: set[str] = set()
    teacher_calls = 0
    teacher_adapter_hashes: set[str] = set()
    pilot_review_tasks: list[dict[str, Any]] = []
    for job in jobs:
        validate_support_authorization(authorization, job, pilot_jobs_path)
        job_id = str(job["job_id"])
        output_dir = output_root / job_id
        receipt_path = output_dir / "JOB_RECEIPT.json"
        row_path = output_dir / "provisional_row.jsonl"
        if not receipt_path.is_file() or not row_path.is_file():
            raise ValueError(f"support pilot output is missing for {job_id}")
        receipt = read_json(receipt_path)
        if receipt.get("schema_version") != "storyworld_support_job_receipt_v1":
            raise ValueError(f"{job_id}: unexpected support receipt schema")
        if receipt.get("job_id") != job_id or receipt.get("job_sha256") != sha256_json(job):
            raise ValueError(f"{job_id}: job receipt identity mismatch")
        if receipt.get("jobs_file_sha256") != sha256_file(pilot_jobs_path):
            raise ValueError(f"{job_id}: receipt belongs to another job artifact")
        if receipt.get("authorization_sha256") != sha256_file(authorization_path):
            raise ValueError(f"{job_id}: receipt belongs to another authorization")
        teacher_adapter_hashes.add(str(receipt.get("teacher_adapter_sha256", "")))
        if receipt.get("row_sha256") != sha256_file(row_path):
            raise ValueError(f"{job_id}: provisional row file hash mismatch")
        rows = read_jsonl(row_path)
        if len(rows) != 1:
            raise ValueError(f"{job_id}: each support job must emit exactly one row")
        row = rows[0]
        if row.get("schema_version") != "storyworld_training_view_v1":
            raise ValueError(f"{job_id}: unexpected provisional row schema")
        record_id = str(row["record_id"])
        if record_id in record_ids or receipt.get("record_id") != record_id:
            raise ValueError(f"{job_id}: duplicate or mismatched record ID")
        record_ids.add(record_id)
        base = {key: value for key, value in row.items() if key != "record_sha256"}
        if row.get("record_sha256") != sha256_json(base):
            raise ValueError(f"{job_id}: provisional record hash mismatch")
        if row.get("training_approved") or not row.get("training_eligible"):
            raise ValueError(f"{job_id}: pilot rows must remain provisional train data")
        messages = row.get("messages")
        if not isinstance(messages, list) or messages[:2] != job["messages"]:
            raise ValueError(f"{job_id}: provisional messages drifted from the job")
        if [item.get("role") for item in messages] != ["system", "user", "assistant"]:
            raise ValueError(f"{job_id}: provisional message roles are invalid")
        provenance = row.get("external_provenance", {})
        if provenance.get("job_sha256") != sha256_json(job):
            raise ValueError(f"{job_id}: provisional provenance job hash mismatch")
        provider = provenance.get("provider_call_receipt", {})
        attempts = provider.get("attempts", [])
        if provider.get("provider") != "openai_responses_api" or provider.get("store") is not False:
            raise ValueError(f"{job_id}: missing nonstored OpenAI provider receipt")
        if not attempts or not all(str(item.get("api_response_id", "")) for item in attempts):
            raise ValueError(f"{job_id}: incomplete OpenAI attempt receipt")
        teacher_calls += 1
        for attempt in attempts:
            _sum_numeric_usage(usage_totals, attempt.get("usage", {}))
        response = {
            "answer": messages[2]["content"],
            "quality_checks": provenance.get("quality_checks"),
        }
        request = {
            "model_id": job["model_id"],
            "reasoning_effort": job["reasoning_effort"],
            "response_word_range": job["response_word_range"],
        }
        validate_command_provider_receipt(request, response, provider)
        errors = semantic_errors(request, response)
        if errors:
            raise ValueError(f"{job_id}: " + "; ".join(errors))
        task_body = {
            "campaign_id": config["campaign_id"],
            "job_id": job_id,
            "record_id": record_id,
            "record_content_sha256": row["record_sha256"],
            "row_path": str(row_path.resolve()),
            "row_file_sha256": sha256_file(row_path),
            "slice": job["slice"],
            "category": job["category"],
            "arm": job["arm"],
        }
        pilot_review_tasks.append(
            {
                "review_task_id": f"support-pilot-review-{sha256_json(task_body)[:24]}",
                **task_body,
                "required_review_scope": [
                    "answers the frozen user task",
                    "factually and operationally sound",
                    "no unsupported literal identity or hidden-knowledge claim",
                    "no unsafe facilitation",
                    "arm framing is bounded, non-theatrical, and preserves ordinary helpfulness",
                ],
            }
        )
        words = _word_count(str(messages[2]["content"]))
        word_counts.append(words)
        packed, assistant = counter.count_messages(messages)
        arm, slice_id, category = str(job["arm"]), str(job["slice"]), str(job["category"])
        cell = (arm, slice_id, category)
        if cell in token_cells:
            raise ValueError("support pilot has more than one yield sample for a category/arm cell")
        token_cells[cell] = {
            "packed_tokens": packed,
            "assistant_tokens": assistant,
        }
        token_totals[arm][slice_id]["rows"] += 1
        token_totals[arm][slice_id]["packed_tokens"] += packed
        token_totals[arm][slice_id]["assistant_tokens"] += assistant

    category_counts = {
        str(key): int(value) for key, value in manifest["scenarios_by_category"].items()
    }
    safety = float(config["projection_safety_factor"])
    if not 0 < safety <= 1:
        raise ValueError("projection_safety_factor must be in (0, 1]")
    projections: dict[str, dict[str, Any]] = {}
    all_covered = True
    for arm in map(str, config["arms"]):
        projections[arm] = {}
        for slice_id in config["scenario_counts"]:
            cells = [
                (category, values)
                for (cell_arm, cell_slice, category), values in token_cells.items()
                if cell_arm == arm and cell_slice == slice_id
            ]
            projected_packed = sum(
                values["packed_tokens"] * category_counts[category]
                for category, values in cells
            )
            projected_assistant = sum(
                values["assistant_tokens"] * category_counts[category]
                for category, values in cells
            )
            conservative_packed = math.floor(projected_packed * safety)
            conservative_assistant = math.floor(projected_assistant * safety)
            packed_target = int(config["packed_token_targets_per_arm"][slice_id])
            assistant_target = int(
                config["minimum_assistant_token_targets_per_arm"][slice_id]
            )
            covered = (
                conservative_packed >= packed_target
                and conservative_assistant >= assistant_target
            )
            all_covered = all_covered and covered
            projections[arm][slice_id] = {
                "scenario_rows": int(config["scenario_counts"][slice_id]),
                "category_pilot_cells": len(cells),
                "projected_packed_tokens": projected_packed,
                "projected_assistant_tokens": projected_assistant,
                "projection_safety_factor": safety,
                "conservative_packed_tokens": conservative_packed,
                "conservative_assistant_tokens": conservative_assistant,
                "packed_target_tokens": packed_target,
                "assistant_target_tokens": assistant_target,
                "coverage": covered,
            }

    if teacher_adapter_hashes != {str(authorization["teacher_adapter_sha256"])}:
        raise ValueError("support pilot used a teacher adapter outside its authorization")

    pilot_review_tasks.sort(key=lambda item: str(item["review_task_id"]))
    return {
        "schema_version": "storyworld_support_real_pilot_calibration_v1",
        "campaign_id": config["campaign_id"],
        "status": (
            "pilot_passed_pending_human_full_campaign_authorization"
            if all_covered
            else "pilot_passed_replan_required_for_token_coverage"
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config_sha256": sha256_file(config_path),
        "plan_manifest_sha256": sha256_file(plan_manifest_path),
        "pilot_jobs_sha256": sha256_file(pilot_jobs_path),
        "pilot_authorization_sha256": sha256_file(authorization_path),
        "pilot_authorization_id": authorization["authorization_id"],
        "teacher_adapter_sha256": next(iter(teacher_adapter_hashes)),
        "pilot_jobs": len(jobs),
        "teacher_calls": teacher_calls,
        "pilot_human_review_required": True,
        "pilot_review_tasks": pilot_review_tasks,
        "pilot_review_tasks_sha256": sha256_json(pilot_review_tasks),
        "provider_usage": dict(sorted(usage_totals.items())),
        "word_count": {
            "minimum": min(word_counts),
            "maximum": max(word_counts),
            "mean": sum(word_counts) / len(word_counts),
        },
        "tokenizer": counter.description,
        "pilot_token_totals": {
            arm: {slice_id: dict(values) for slice_id, values in slices.items()}
            for arm, slices in token_totals.items()
        },
        "full_campaign_projection": projections,
        "full_campaign_ready_for_human_authorization": all_covered,
        "training_approved_rows": 0,
        "sealed_evaluation_rows": 0,
        "development_rows": 0,
        "claim_boundary": (
            "This audits genuine nonstored pilot responses and exact tokenizer yield. It "
            "does not authorize remaining spend or approve any response for training."
        ),
        "passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--plan-manifest", type=Path, required=True)
    parser.add_argument("--pilot-jobs", type=Path, required=True)
    parser.add_argument("--pilot-authorization", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = audit_support_pilot(
        args.config,
        args.plan_manifest,
        args.pilot_jobs,
        args.pilot_authorization,
        args.output_root,
        args.tokenizer,
    )
    write_json(args.output.resolve(), receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
