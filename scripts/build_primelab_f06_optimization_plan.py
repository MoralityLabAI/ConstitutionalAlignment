#!/usr/bin/env python3
"""Build a no-spend, source-bound F06 batch-throughput proposal."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.hash_git_blobs import (
    REPO_ROOT,
    git_blob_bytes,
    git_blob_sha256,
    resolve_commit,
)


PACKAGE = Path("experiments/frame_internalization_sft_v1")
REQUEST_MANIFEST = (
    PACKAGE
    / "rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/request_manifest.json"
)
F04_RECEIPT = PACKAGE / "primelab_f04/environment_freeze_20260723.json"
ENVIRONMENT_LOCK = PACKAGE / "primelab_f04/environment_lock_20260723.txt"
PRIOR_RESULT = PACKAGE / "primelab_f06/f06_throughput_smoke_result_v1.json"
GENERATOR = Path("scripts/generate_qwen3_frame_curriculum_transcripts.py")
HASH_TOOL = Path("scripts/hash_git_blobs.py")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_git_json(path: Path, revision: str) -> dict[str, Any]:
    value = json.loads(git_blob_bytes(REPO_ROOT / path, revision))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object at {revision}:{path.as_posix()}")
    return value


def binding(path: Path, revision: str) -> dict[str, str]:
    return {
        "path": path.as_posix(),
        "sha256": git_blob_sha256(REPO_ROOT / path, revision),
    }


def build_plan(
    source_revision: str,
    frozen_at_utc: str | None = None,
) -> dict[str, Any]:
    source_commit = resolve_commit(source_revision)
    request_manifest = read_git_json(REQUEST_MANIFEST, source_commit)
    prior_result = read_git_json(PRIOR_RESULT, source_commit)
    generation = request_manifest["generation"]
    runtime = prior_result["runtime"]
    projection = prior_result["rough_linear_projection"]

    if prior_result["passed"] is not False:
        raise RuntimeError("the optimization proposal requires the fail-closed v1 result")
    if prior_result["factor_and_claim_boundary"]["f06_remains_pending"] is not True:
        raise RuntimeError("F06 must remain pending")
    if generation["chat_template_mode"] != "official_qwen3_enable_thinking_true":
        raise RuntimeError("thinking-mode freeze drift")
    if runtime["batch_size"] != 8:
        raise RuntimeError("unexpected baseline batch size")

    full_tokens = int(projection["projected_generated_tokens"])
    minimum_tokens_per_second = 240
    preferred_tokens_per_second = 320
    maximum_offer_price = 1.30

    return {
        "schema_version": "frame_internalization_f06_throughput_optimization_plan.v1",
        "plan_id": "qwen3_1p7b_f06_batch32_probe_v1",
        "frozen_at_utc": frozen_at_utc or utc_now(),
        "status": "prepared_not_authorized",
        "classification": "no_spend_prospective_throughput_optimization",
        "source_commit": source_commit,
        "authorization": {
            "billing_authorized": False,
            "pod_creation_authorized": False,
            "automatic_launch_allowed": False,
            "required_before_launch": (
                "a new user authorization bound to a current offer and capped cost"
            ),
        },
        "baseline": {
            "result": binding(PRIOR_RESULT, source_commit),
            "batch_size": runtime["batch_size"],
            "completed_transcripts": prior_result["operational_checks"][
                "completed_transcripts"
            ],
            "generated_tokens": runtime["generated_tokens"],
            "generator_elapsed_seconds": runtime["generator_elapsed_seconds"],
            "generated_tokens_per_second": runtime["generated_tokens_per_second"],
            "projected_full_generator_hours": projection[
                "projected_generator_hours"
            ],
            "projected_full_cost_usd": projection[
                "projected_cost_at_observed_rate_usd"
            ],
            "evidence_class": "throughput_and_output_shape_only",
        },
        "candidate": {
            "single_change_under_test": (
                "increase inference batch size from 8 to 32"
            ),
            "batch_size": 32,
            "limit_per_frame": 8,
            "source_frames": ["neutral", "F1", "F3", "F3_concrete"],
            "maximum_transcripts": 32,
            "turns_per_transcript": 3,
            "maximum_generation_turns": 96,
            "sampler_implementation": "top_p_inverse_cdf_single_softmax_v2",
            "per_call_telemetry_required": True,
        },
        "scientific_invariants": {
            "model_repository": generation["model_repository"],
            "model_revision": generation["model_revision"],
            "quantization": "bitsandbytes NF4 with double quantization",
            "compute_dtype": "float16",
            "chat_template_mode": generation["chat_template_mode"],
            "max_tokens_per_turn": generation["max_tokens_per_turn"],
            "temperature": generation["temperature"],
            "top_p": generation["top_p"],
            "turns": generation["turns"],
            "retry_attempts": generation["retry_attempts"],
            "paired_seed_rule": generation["paired_seed_rule"],
            "request_order": "first eight frozen scenarios per frame",
        },
        "proposed_hard_caps": {
            "maximum_billable_seconds": 1800,
            "watchdog_delay_seconds": 1620,
            "maximum_compute_cost_usd": 0.65,
            "maximum_offer_price_usd_per_hour": maximum_offer_price,
            "maximum_inference_wall_clock_seconds": 1200,
            "maximum_output_bytes": 1073741824,
            "maximum_peak_cuda_reserved_bytes": 80530636800,
            "spot_allowed": False,
            "checkpoint_every_completed_request": True,
        },
        "promotion_criteria": {
            "completed_transcripts": 32,
            "failed_requests": 0,
            "cleanup_passed": True,
            "minimum_generated_tokens_per_second": minimum_tokens_per_second,
            "preferred_generated_tokens_per_second": preferred_tokens_per_second,
            "maximum_projected_full_hours": 60,
            "maximum_projected_full_cost_usd": 75,
            "minimum_target_projection": {
                "generated_tokens": full_tokens,
                "hours": full_tokens / minimum_tokens_per_second / 3600,
                "cost_at_maximum_offer_price_usd": (
                    full_tokens
                    / minimum_tokens_per_second
                    / 3600
                    * maximum_offer_price
                ),
            },
            "preferred_target_projection": {
                "generated_tokens": full_tokens,
                "hours": full_tokens / preferred_tokens_per_second / 3600,
                "cost_at_maximum_offer_price_usd": (
                    full_tokens
                    / preferred_tokens_per_second
                    / 3600
                    * maximum_offer_price
                ),
            },
        },
        "canonical_git_bindings": {
            "byte_source": "git_cat_file_blob",
            "source_commit": source_commit,
            "frozen_inputs": {
                "request_manifest": binding(REQUEST_MANIFEST, source_commit),
                "f04_receipt": binding(F04_RECEIPT, source_commit),
                "environment_lock": binding(ENVIRONMENT_LOCK, source_commit),
                "prior_result": binding(PRIOR_RESULT, source_commit),
            },
            "development_executables": {
                "generator": binding(GENERATOR, source_commit),
                "hash_tool": binding(HASH_TOOL, source_commit),
            },
        },
        "required_future_launch_freeze": [
            "current provider offer and availability",
            "authorized wrapper and exact wrapper Git-blob hash",
            "exact source commit checkout",
            "watchdog PID and termination path",
            "environment and twelve model artifact checks",
        ],
        "abort_without_escalation_on": [
            "any canonical Git-blob mismatch",
            "offer above the proposed price cap",
            "OOM or peak reserved-memory cap breach",
            "wall-clock or output cap breach",
            "any failed transcript after frozen retries",
            "owned-process or GPU cleanup failure",
            "throughput below promotion threshold",
        ],
        "scope_boundary": {
            "launches_compute": False,
            "closes_f06": False,
            "authorizes_full_generation": False,
            "authorizes_adapter_training": False,
            "produces_behavioral_or_scientific_evidence": False,
            "purpose": (
                "prepare a comparable batch-throughput probe before further spend"
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan = build_plan(args.source_revision)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
