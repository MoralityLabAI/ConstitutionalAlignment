#!/usr/bin/env python3
"""Authorize hash-bound four-arm adapter training after all data/base gates pass."""

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

from alignment_harness.adapter_training import (
    audit_packed_curriculum_for_training,
    verify_local_model_fingerprint,
)
from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json
from alignment_harness.trajectory_curriculum import HuggingFaceTokenCounter


def build_adapter_training_authorization(
    training_recipe_path: Path,
    token_recipe_path: Path,
    packing_manifest_path: Path,
    base_freeze_path: Path,
    output_root: Path,
    *,
    authorized_by: str,
    authorization_reference: str,
    max_gpu_hours: float,
) -> dict[str, Any]:
    training_recipe_path = training_recipe_path.resolve()
    token_recipe_path = token_recipe_path.resolve()
    packing_manifest_path = packing_manifest_path.resolve()
    base_freeze_path = base_freeze_path.resolve()
    output_root = output_root.resolve()
    training_recipe = read_json(training_recipe_path)
    token_recipe = read_json(token_recipe_path)
    base_freeze = read_json(base_freeze_path)
    if base_freeze.get("schema_version") != "storyworld_adapter_base_freeze_v1":
        raise ValueError("unexpected adapter base-freeze schema")
    if base_freeze.get("status") != "frozen_not_training_authorization" or not base_freeze.get(
        "passed"
    ):
        raise ValueError("adapter base freeze is not valid")
    verify_local_model_fingerprint(Path(base_freeze["model_dir"]), base_freeze)
    current_tokenizer = HuggingFaceTokenCounter(
        str(Path(base_freeze["tokenizer_dir"]).resolve())
    ).description
    if current_tokenizer.get("tokenizer_artifact_set_sha256") != base_freeze[
        "tokenizer"
    ].get("tokenizer_artifact_set_sha256"):
        raise ValueError("frozen base tokenizer drifted before training authorization")
    audit = audit_packed_curriculum_for_training(
        packing_manifest_path, training_recipe, token_recipe
    )
    if audit["tokenizer"].get("tokenizer_artifact_set_sha256") != base_freeze[
        "tokenizer"
    ].get("tokenizer_artifact_set_sha256"):
        raise ValueError("packed curriculum tokenizer differs from the frozen base tokenizer")
    if not authorized_by.strip() or not authorization_reference.strip():
        raise ValueError("adapter training authorization requires human attribution and reference")
    if float(max_gpu_hours) <= 0:
        raise ValueError("adapter training total GPU-hour ceiling must be positive")
    arms = list(training_recipe["arms"])
    max_gpu_hours_per_arm = float(max_gpu_hours) / len(arms)
    trainer_path = REPO_ROOT / "scripts" / "train_storyworld_adapter_curve.py"
    body = {
        "schema_version": "storyworld_adapter_training_authorization_v1",
        "status": "authorized",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "authorized_by": authorized_by,
        "authorization_reference": authorization_reference,
        "training_recipe_sha256": sha256_file(training_recipe_path),
        "token_recipe_sha256": sha256_file(token_recipe_path),
        "packing_manifest_sha256": sha256_file(packing_manifest_path),
        "packed_curriculum_audit": audit,
        "base_freeze_id": base_freeze["base_freeze_id"],
        "base_freeze_sha256": sha256_file(base_freeze_path),
        "model_artifact_set_sha256": base_freeze["model_artifact_set_sha256"],
        "tokenizer_artifact_set_sha256": base_freeze["tokenizer"][
            "tokenizer_artifact_set_sha256"
        ],
        "trainer_sha256": sha256_file(trainer_path),
        "authorized_output_root": str(output_root),
        "authorized_arms": arms,
        "authorized_checkpoint_tokens": list(training_recipe["checkpoint_tokens"]),
        "authorized_adapter_runs": len(arms),
        "max_total_gpu_hours": float(max_gpu_hours),
        "max_gpu_hours_per_arm": max_gpu_hours_per_arm,
        "gpu_hour_allocation_policy": "equal_nontransferable_ceiling_per_matched_arm",
        "automatic_evaluation_selection": False,
        "sealed_evaluation_opened": False,
        "claim_boundary": (
            "This authorizes one continuous prefix run for each listed arm at the exact "
            "base, pack, tokenizer, trainer, output root, and dose boundaries. It does not "
            "authorize recipe drift, additional runs, cross-arm budget transfer, evaluation "
            "selection, or sealed access."
        ),
        "passed": True,
    }
    return {**body, "authorization_id": f"adapter-train-{sha256_json(body)[:24]}"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-recipe", type=Path, required=True)
    parser.add_argument("--token-recipe", type=Path, required=True)
    parser.add_argument("--packing-manifest", type=Path, required=True)
    parser.add_argument("--base-freeze", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--authorized-by", required=True)
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument(
        "--max-gpu-hours",
        type=float,
        required=True,
        help=(
            "Total four-arm GPU-hour ceiling; v1 partitions it equally into "
            "nontransferable per-arm ceilings."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorize-adapter-training-spend", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.authorize_adapter_training_spend:
        raise ValueError(
            "writing adapter authorization requires --authorize-adapter-training-spend"
        )
    authorization = build_adapter_training_authorization(
        args.training_recipe,
        args.token_recipe,
        args.packing_manifest,
        args.base_freeze,
        args.output_root,
        authorized_by=args.authorized_by,
        authorization_reference=args.authorization_reference,
        max_gpu_hours=args.max_gpu_hours,
    )
    write_json(args.output.resolve(), authorization)
    print(json.dumps(authorization, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
