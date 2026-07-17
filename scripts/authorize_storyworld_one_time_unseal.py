#!/usr/bin/env python3
"""Authorize the sole sealed evaluation opening after every frozen evidence gate."""

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
    read_json,
    sha256_file,
    sha256_json,
    validate_blinded_eval_protocol,
    write_json,
)


def build_unseal_authorization(
    package_path: Path,
    review_bundle_path: Path,
    packing_manifest_path: Path,
    nonleakage_path: Path,
    analysis_freeze_path: Path,
    training_receipt_paths: list[Path],
    sealed_authoring_receipt_path: Path,
    *,
    authorized_by: str,
    authorization_reference: str,
) -> dict[str, Any]:
    package_path = package_path.resolve()
    review_bundle_path = review_bundle_path.resolve()
    packing_manifest_path = packing_manifest_path.resolve()
    nonleakage_path = nonleakage_path.resolve()
    analysis_freeze_path = analysis_freeze_path.resolve()
    sealed_authoring_receipt_path = sealed_authoring_receipt_path.resolve()
    package = read_json(package_path)
    protocol_path = REPO_ROOT / package["blinded_eval_protocol"]
    split_path = REPO_ROOT / package["split_freeze"]
    protocol = read_json(protocol_path)
    split = read_json(split_path)
    validate_blinded_eval_protocol(split, protocol)
    review = read_json(review_bundle_path)
    if review.get("schema_version") != "storyworld_review_application_bundle_v1" or not review.get(
        "all_train_worlds_approved"
    ):
        raise ValueError("one-time unseal requires the complete approved nonsealed review bundle")
    packing = read_json(packing_manifest_path)
    if packing.get("schema_version") != "storyworld_packed_curriculum_manifest_v1" or packing.get(
        "release_status"
    ) != "review_approved":
        raise ValueError("one-time unseal requires the reviewed 10M packed curriculum")
    nonleakage = read_json(nonleakage_path)
    if nonleakage.get("schema_version") != "storyworld_training_provenance_nonleakage_v1" or not nonleakage.get(
        "passed"
    ):
        raise ValueError("one-time unseal requires the training nonleakage receipt")
    if nonleakage.get("packing_manifest_sha256") != sha256_file(packing_manifest_path):
        raise ValueError("nonleakage receipt belongs to another packed curriculum")
    analysis = read_json(analysis_freeze_path)
    if analysis.get("schema_version") != "storyworld_analysis_freeze_v1" or not analysis.get(
        "passed"
    ) or analysis.get("sealed_evaluation_opened") is not False:
        raise ValueError("one-time unseal requires the closed analysis-selection freeze")
    selected = int(analysis["selected_checkpoint_tokens"])
    receipts = []
    arms = set()
    for value in training_receipt_paths:
        path = value.resolve()
        receipt = read_json(path)
        if receipt.get("schema_version") != "storyworld_adapter_training_receipt_v1" or not receipt.get(
            "passed"
        ):
            raise ValueError("invalid adapter training receipt at unseal")
        arm = str(receipt["arm"])
        if arm in arms:
            raise ValueError("duplicate adapter arm at unseal")
        arms.add(arm)
        matches = [
            item
            for item in receipt["checkpoints"]
            if int(item["target_tokens"]) == selected
        ]
        if len(matches) != 1:
            raise ValueError(f"selected adapter checkpoint is missing for {arm}")
        receipts.append(
            {
                "arm": arm,
                "path": str(path),
                "sha256": sha256_file(path),
                "selected_checkpoint_tokens": selected,
                "adapter_artifact_set_sha256": matches[0][
                    "adapter_artifact_set_sha256"
                ],
            }
        )
    if arms != {"neutral", "constitutional", "jinn", "beast"}:
        raise ValueError("one-time unseal requires all four matched adapter arms")
    authoring = read_json(sealed_authoring_receipt_path)
    if authoring.get("schema_version") != "storyworld_sealed_authoring_completion_v1" or authoring.get(
        "status"
    ) != "approved_in_external_access_controlled_environment":
        raise ValueError("sealed authoring is not complete and approved")
    if authoring.get("protocol_id") != protocol["protocol_id"]:
        raise ValueError("sealed authoring receipt belongs to another protocol")
    expected_families = {
        str(item["family_id"]) for item in protocol["evaluation_families"]
    }
    if set(map(str, authoring.get("family_ids", []))) != expected_families:
        raise ValueError("sealed authoring receipt does not cover the six frozen families")
    if int(authoring.get("approved_families", 0)) != len(expected_families):
        raise ValueError("not every sealed evaluation family is approved")
    if authoring.get("train_or_development_content_visible_to_authors") is not False:
        raise ValueError("sealed authoring receipt does not preserve author blinding")
    if authoring.get("candidate_adapter_outputs_visible_to_authors") is not False:
        raise ValueError("sealed authors were exposed to candidate adapter outputs")
    family_reviews = authoring.get("family_review_receipts", [])
    structural_reviews = authoring.get("structural_validation_receipts", [])
    if {str(item.get("family_id")) for item in family_reviews} != expected_families:
        raise ValueError("sealed authoring lacks one family review receipt per family")
    if {str(item.get("family_id")) for item in structural_reviews} != expected_families:
        raise ValueError("sealed authoring lacks one structural receipt per family")
    if not all(str(item.get("signature_or_external_receipt", "")).strip() for item in family_reviews):
        raise ValueError("sealed family review receipt lacks a signature")
    signed_at = datetime.fromisoformat(str(authoring.get("signed_at", "")).replace("Z", "+00:00"))
    if signed_at.tzinfo is None or signed_at.utcoffset() is None:
        raise ValueError("sealed authoring completion timestamp must include a timezone")
    if not str(authoring.get("signature_or_external_receipt", "")).strip() or not str(
        authoring.get("sealed_content_location_reference", "")
    ).strip():
        raise ValueError("sealed authoring completion lacks signature or location reference")
    if not authorized_by.strip() or not authorization_reference.strip():
        raise ValueError("one-time unseal requires human authorization attribution")
    body = {
        "schema_version": "storyworld_one_time_unseal_authorization_v1",
        "protocol_id": protocol["protocol_id"],
        "status": "authorized_not_yet_opened",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "authorized_by": authorized_by,
        "authorization_reference": authorization_reference,
        "package_sha256": sha256_file(package_path),
        "protocol_sha256": sha256_file(protocol_path),
        "split_freeze_sha256": sha256_file(split_path),
        "review_bundle_sha256": sha256_file(review_bundle_path),
        "packing_manifest_sha256": sha256_file(packing_manifest_path),
        "training_provenance_nonleakage_sha256": sha256_file(nonleakage_path),
        "analysis_freeze_sha256": sha256_file(analysis_freeze_path),
        "sealed_authoring_completion_sha256": sha256_file(
            sealed_authoring_receipt_path
        ),
        "selected_checkpoint_tokens": selected,
        "adapter_checkpoints": sorted(receipts, key=lambda item: item["arm"]),
        "evaluation_families": len(expected_families),
        "one_time_unseal": True,
        "sealed_content_opened": False,
        "additional_unseal_authorizations_allowed": False,
        "claim_boundary": (
            "This is the single authorization to transfer the already blinded external "
            "evaluation to its execution environment. It records no result and does not "
            "permit metric, contrast, checkpoint, or analysis changes."
        ),
        "passed": True,
    }
    return {**body, "unseal_authorization_id": f"one-time-unseal-{sha256_json(body)[:24]}"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package",
        type=Path,
        default=REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "package.json",
    )
    parser.add_argument("--review-bundle", type=Path, required=True)
    parser.add_argument("--packing-manifest", type=Path, required=True)
    parser.add_argument("--training-nonleakage", type=Path, required=True)
    parser.add_argument("--analysis-freeze", type=Path, required=True)
    parser.add_argument("--adapter-training-receipt", type=Path, action="append", required=True)
    parser.add_argument("--sealed-authoring-receipt", type=Path, required=True)
    parser.add_argument("--authorized-by", required=True)
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorize-one-time-unseal", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.authorize_one_time_unseal:
        raise ValueError("writing the gate requires --authorize-one-time-unseal")
    output_path = args.output.resolve()
    if output_path.exists():
        raise ValueError("one-time unseal authorization output already exists")
    receipt = build_unseal_authorization(
        args.package,
        args.review_bundle,
        args.packing_manifest,
        args.training_nonleakage,
        args.analysis_freeze,
        args.adapter_training_receipt,
        args.sealed_authoring_receipt,
        authorized_by=args.authorized_by,
        authorization_reference=args.authorization_reference,
    )
    write_json(output_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
