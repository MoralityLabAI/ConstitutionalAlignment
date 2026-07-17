#!/usr/bin/env python3
"""Audit end-to-end readiness without confusing structural validity with completion."""

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

from alignment_harness.adapter_training import audit_packed_curriculum_for_training
from alignment_harness.storyworlds import read_json, sha256_file, validate_curriculum_package, write_json


def _gate(
    gate_id: str,
    status: str,
    evidence: dict[str, Any],
    next_action: str,
) -> dict[str, Any]:
    if status not in {"passed", "pending", "failed"}:
        raise ValueError("invalid readiness gate status")
    return {
        "gate_id": gate_id,
        "status": status,
        "evidence": evidence,
        "next_action": "none" if status == "passed" else next_action,
    }


def _optional(path: Path | None) -> tuple[Path | None, dict[str, Any] | None]:
    if path is None:
        return None, None
    resolved = path.resolve()
    if not resolved.is_file():
        return resolved, None
    return resolved, read_json(resolved)


def audit_readiness(args: argparse.Namespace) -> dict[str, Any]:
    package_path = args.package.resolve()
    package = read_json(package_path)
    package_validation = validate_curriculum_package(REPO_ROOT, package_path)
    token_recipe_path = REPO_ROOT / package["token_recipe"]
    training_recipe_path = REPO_ROOT / package["adapter_training_recipe"]
    token_recipe = read_json(token_recipe_path)
    training_recipe = read_json(training_recipe_path)
    gates = [
        _gate(
            "factory_design",
            "passed" if package_validation["passed"] else "failed",
            {
                "package_sha256": sha256_file(package_path),
                "train_families": package_validation["split_freeze"]["family_counts"][
                    "train"
                ],
                "development_families": package_validation["split_freeze"][
                    "family_counts"
                ]["development"],
                "sealed_evaluation_families": package_validation["split_freeze"][
                    "family_counts"
                ]["evaluation"],
                "planned_adapter_checkpoints": package_validation[
                    "adapter_training_recipe"
                ]["planned_adapter_checkpoints"],
            },
            "repair the structural package validation failures",
        )
    ]

    review_value = args.review_bundle
    if review_value is None and package.get("review_bundle"):
        review_value = REPO_ROOT / str(package["review_bundle"])
    review_path, review = _optional(review_value)
    review_passed = bool(
        review
        and review.get("schema_version") == "storyworld_review_application_bundle_v1"
        and review.get("all_train_worlds_approved")
        and int(review.get("approved_worlds", 0)) == len(package["worlds"])
    )
    gates.append(
        _gate(
            "nonsealed_world_reviews",
            "passed" if review_passed else "pending",
            {
                "path": str(review_path) if review_path else None,
                "sha256": sha256_file(review_path) if review_path and review_path.is_file() else None,
                "approved_worlds": int(review.get("approved_worlds", 0)) if review else 0,
                "required_worlds": len(package["worlds"]),
            },
            "obtain and atomically apply all 51 content-bound review receipts",
        )
    )

    main_path, main_pilot = _optional(args.main_pilot_calibration)
    main_review_path, main_review = _optional(args.main_pilot_review_bundle)
    main_passed = bool(
        main_pilot
        and main_pilot.get("schema_version") == "storyworld_real_pilot_calibration_v1"
        and main_pilot.get("passed")
        and main_pilot.get("full_campaign_ready_for_human_authorization")
        and int(main_pilot.get("pilot_jobs", 0)) == 48
        and main_review
        and main_review.get("schema_version")
        == "storyworld_real_pilot_human_review_bundle_v1"
        and main_review.get("pilot_calibration_sha256") == sha256_file(main_path)
        and main_review.get("all_pilot_traces_approved")
        and int(main_review.get("approved_traces", 0)) == 48
        and main_review.get("passed")
    )
    gates.append(
        _gate(
            "real_storyworld_teacher_pilot",
            "passed" if main_passed else "pending",
            {
                "path": str(main_path) if main_path else None,
                "sha256": sha256_file(main_path) if main_path and main_path.is_file() else None,
                "pilot_jobs": int(main_pilot.get("pilot_jobs", 0)) if main_pilot else 0,
                "teacher_calls": int(main_pilot.get("teacher_calls", 0)) if main_pilot else 0,
                "human_review_bundle_path": str(main_review_path)
                if main_review_path
                else None,
                "human_approved_traces": int(main_review.get("approved_traces", 0))
                if main_review
                else 0,
            },
            "run, exact-token audit, and human-review all 48 nonstored real-teacher pilot traces",
        )
    )

    support_path, support_pilot = _optional(args.support_pilot_calibration)
    support_review_path, support_review = _optional(args.support_pilot_review_bundle)
    support_passed = bool(
        support_pilot
        and support_pilot.get("schema_version")
        == "storyworld_support_real_pilot_calibration_v1"
        and support_pilot.get("passed")
        and support_pilot.get("full_campaign_ready_for_human_authorization")
        and int(support_pilot.get("pilot_jobs", 0)) == 76
        and support_path
        and support_review
        and support_review.get("schema_version")
        == "storyworld_support_pilot_human_review_bundle_v1"
        and support_review.get("pilot_calibration_sha256")
        == sha256_file(support_path)
        and support_review.get("all_pilot_outputs_approved")
        and int(support_review.get("approved_outputs", 0)) == 76
        and support_review.get("passed")
    )
    gates.append(
        _gate(
            "real_support_teacher_pilot",
            "passed" if support_passed else "pending",
            {
                "path": str(support_path) if support_path else None,
                "sha256": sha256_file(support_path) if support_path and support_path.is_file() else None,
                "pilot_jobs": int(support_pilot.get("pilot_jobs", 0)) if support_pilot else 0,
                "human_review_bundle_path": str(support_review_path)
                if support_review_path
                else None,
                "human_approved_outputs": int(support_review.get("approved_outputs", 0))
                if support_review
                else 0,
            },
            "review prompts, run and audit the 76-job support pilot, then human-review all 76 outputs",
        )
    )

    packed_path, packed = _optional(args.packing_manifest)
    packed_audit = None
    packed_status = "pending"
    packed_error = None
    if packed is not None and packed_path is not None:
        try:
            packed_audit = audit_packed_curriculum_for_training(
                packed_path, training_recipe, token_recipe
            )
            packed_status = "passed"
        except Exception as exc:
            packed_status = "failed"
            packed_error = f"{type(exc).__name__}: {exc}"
    gates.append(
        _gate(
            "reviewed_10m_four_arm_pack",
            packed_status,
            {
                "path": str(packed_path) if packed_path else None,
                "sha256": sha256_file(packed_path) if packed_path and packed_path.is_file() else None,
                "audit_passed": bool(packed_audit and packed_audit["passed"]),
                "error": packed_error,
                "target_total_tokens": 4 * int(token_recipe["target_tokens_per_arm"]),
                "target_total_assistant_tokens": 4
                * int(token_recipe["minimum_assistant_tokens_per_arm"]),
            },
            "harvest, approve, derive, and pack unique rows with complete upstream provenance",
        )
    )

    base_path, base = _optional(args.base_freeze)
    base_passed = bool(
        base
        and base.get("schema_version") == "storyworld_adapter_base_freeze_v1"
        and base.get("passed")
        and base.get("license_review_reference")
    )
    gates.append(
        _gate(
            "base_model_and_tokenizer_freeze",
            "passed" if base_passed else "pending",
            {
                "path": str(base_path) if base_path else None,
                "sha256": sha256_file(base_path) if base_path and base_path.is_file() else None,
                "model_id": base.get("model_id") if base else None,
                "model_revision": base.get("model_revision") if base else None,
            },
            "select a research-compatible base and freeze local weights, tokenizer, revision, and license review",
        )
    )

    authorization_path, authorization = _optional(args.training_authorization)
    authorization_passed = bool(
        authorization
        and authorization.get("schema_version")
        == "storyworld_adapter_training_authorization_v1"
        and authorization.get("passed")
        and packed_path
        and authorization.get("packing_manifest_sha256") == sha256_file(packed_path)
        and base_path
        and authorization.get("base_freeze_sha256") == sha256_file(base_path)
    )
    gates.append(
        _gate(
            "adapter_training_authorization",
            "passed" if authorization_passed else "pending",
            {
                "path": str(authorization_path) if authorization_path else None,
                "sha256": sha256_file(authorization_path)
                if authorization_path and authorization_path.is_file()
                else None,
                "authorized_runs": int(authorization.get("authorized_adapter_runs", 0))
                if authorization
                else 0,
            },
            "issue one hash-bound four-arm training authorization with a compute ceiling",
        )
    )

    training_receipts = []
    for value in args.adapter_training_receipt:
        path, receipt = _optional(value)
        if path and receipt:
            training_receipts.append((path, receipt))
    arms = Counter(
        str(receipt.get("arm"))
        for _, receipt in training_receipts
        if receipt.get("schema_version") == "storyworld_adapter_training_receipt_v1"
        and receipt.get("passed")
        and len(receipt.get("checkpoints", [])) == 4
    )
    training_passed = set(arms) == set(token_recipe["arms"]) and set(arms.values()) == {1}
    gates.append(
        _gate(
            "four_adapter_spend_curves",
            "passed" if training_passed else "pending",
            {
                "receipt_paths": [str(path) for path, _ in training_receipts],
                "completed_by_arm": dict(sorted(arms.items())),
                "required_arms": token_recipe["arms"],
                "required_checkpoints_per_arm": token_recipe["checkpoints"],
            },
            "train one ordered assistant-only curve for every arm and verify all 16 adapter checkpoints",
        )
    )

    scores = []
    for value in args.development_score:
        path, score = _optional(value)
        if path and score:
            scores.append((path, score))
    score_cells = Counter(
        (str(score.get("arm")), int(score.get("checkpoint_tokens", 0)))
        for _, score in scores
        if score.get("schema_version") == "storyworld_development_eval_score_v1"
        and score.get("passed")
        and float(score.get("coverage", 0)) == 1.0
        and not score.get("sealed_evaluation_content_opened")
    )
    expected_cells = {
        (arm, int(checkpoint))
        for arm in token_recipe["arms"]
        for checkpoint in token_recipe["checkpoints"]
    }
    development_passed = set(score_cells) == expected_cells and set(score_cells.values()) == {1}
    gates.append(
        _gate(
            "development_checkpoint_matrix",
            "passed" if development_passed else "pending",
            {
                "score_receipts": len(scores),
                "complete_unique_cells": len(score_cells),
                "required_cells": len(expected_cells),
            },
            "score every arm at 1M/3M/6M/10M on development only and freeze the selection",
        )
    )

    analysis_path, analysis = _optional(args.analysis_freeze)
    analysis_passed = bool(
        analysis
        and analysis.get("schema_version") == "storyworld_analysis_freeze_v1"
        and analysis.get("passed")
        and analysis.get("sealed_evaluation_opened") is False
    )
    gates.append(
        _gate(
            "analysis_and_checkpoint_selection_freeze",
            "passed" if analysis_passed else "pending",
            {
                "path": str(analysis_path) if analysis_path else None,
                "sha256": sha256_file(analysis_path)
                if analysis_path and analysis_path.is_file()
                else None,
            },
            "freeze chosen checkpoints, contrasts, metrics, and analysis code before unseal",
        )
    )

    sealed_path, sealed = _optional(args.sealed_evaluation_receipt)
    sealed_passed = bool(
        sealed
        and sealed.get("schema_version") == "storyworld_one_time_sealed_evaluation_receipt_v1"
        and sealed.get("passed")
        and sealed.get("one_time_unseal")
        and int(sealed.get("evaluation_families", 0)) in {6, 7, 8}
    )
    gates.append(
        _gate(
            "one_time_sealed_evaluation",
            "passed" if sealed_passed else "pending",
            {
                "path": str(sealed_path) if sealed_path else None,
                "sha256": sha256_file(sealed_path)
                if sealed_path and sealed_path.is_file()
                else None,
                "sealed_content_opened": bool(sealed),
            },
            "after every freeze gate, authorize and record the single sealed evaluation opening",
        )
    )
    counts = Counter(item["status"] for item in gates)
    return {
        "schema_version": "storyworld_curriculum_end_to_end_readiness_v1",
        "package_id": package["package_id"],
        "gates": gates,
        "gate_summary": {
            "passed": counts["passed"],
            "pending": counts["pending"],
            "failed": counts["failed"],
            "total": len(gates),
        },
        "ready_for_teacher_pilot": review_passed,
        "ready_for_adapter_training": packed_status == "passed"
        and base_passed
        and authorization_passed,
        "objective_complete": all(item["status"] == "passed" for item in gates),
        "claim_boundary": (
            "A structurally valid factory is not a generated corpus, trained adapter, or "
            "completed evaluation. objective_complete is true only when every evidence gate passes."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package",
        type=Path,
        default=REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "package.json",
    )
    parser.add_argument("--review-bundle", type=Path)
    parser.add_argument("--main-pilot-calibration", type=Path)
    parser.add_argument("--main-pilot-review-bundle", type=Path)
    parser.add_argument("--support-pilot-calibration", type=Path)
    parser.add_argument("--support-pilot-review-bundle", type=Path)
    parser.add_argument("--packing-manifest", type=Path)
    parser.add_argument("--base-freeze", type=Path)
    parser.add_argument("--training-authorization", type=Path)
    parser.add_argument("--adapter-training-receipt", type=Path, action="append", default=[])
    parser.add_argument("--development-score", type=Path, action="append", default=[])
    parser.add_argument("--analysis-freeze", type=Path)
    parser.add_argument("--sealed-evaluation-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = audit_readiness(args)
    if args.output is not None:
        write_json(args.output.resolve(), receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
