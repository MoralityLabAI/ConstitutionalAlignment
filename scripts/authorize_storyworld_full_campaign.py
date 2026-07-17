#!/usr/bin/env python3
"""Record explicit human authorization for one hash-frozen post-pilot campaign."""

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

from alignment_harness.storyworlds import read_json, sha256_file, write_json


def build_full_campaign_authorization(
    manifest_path: Path,
    calibration_path: Path,
    pilot_review_bundle_path: Path,
    *,
    authorized_by: str,
    authorization_reference: str,
    max_teacher_calls: int,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    calibration_path = calibration_path.resolve()
    pilot_review_bundle_path = pilot_review_bundle_path.resolve()
    manifest = read_json(manifest_path)
    calibration = read_json(calibration_path)
    pilot_review_bundle = read_json(pilot_review_bundle_path)
    if manifest.get("schema_version") != "storyworld_harvest_campaign_manifest_v1":
        raise ValueError("unexpected post-pilot campaign manifest schema")
    if calibration.get("schema_version") != "storyworld_real_pilot_calibration_v1":
        raise ValueError("unexpected pilot calibration schema")
    if calibration.get("status") != "pilot_passed_pending_human_full_campaign_authorization":
        raise ValueError("pilot calibration is not at the authorization gate")
    if not calibration.get("passed") or not calibration.get(
        "full_campaign_ready_for_human_authorization"
    ):
        raise ValueError("pilot calibration did not pass every full-campaign gate")
    if (
        pilot_review_bundle.get("schema_version")
        != "storyworld_real_pilot_human_review_bundle_v1"
        or pilot_review_bundle.get("pilot_calibration_sha256")
        != sha256_file(calibration_path)
        or pilot_review_bundle.get("all_pilot_traces_approved") is not True
        or int(pilot_review_bundle.get("approved_traces", 0))
        != int(calibration["pilot_jobs"])
        or pilot_review_bundle.get("passed") is not True
    ):
        raise ValueError("real pilot lacks complete content-bound human approval")
    config_path = REPO_ROOT / str(manifest["campaign_config_path"])
    config = read_json(config_path)
    if config.get("pilot_calibration_sha256") != sha256_file(calibration_path):
        raise ValueError("post-pilot campaign is not bound to this calibration")
    recommendation = calibration["recalibrated_campaign"]
    if int(config["traces_per_family_per_arm"]) != int(
        recommendation["traces_per_family_per_arm"]
    ) or int(config["traces_per_arm"]) != int(recommendation["traces_per_arm"]):
        raise ValueError("post-pilot campaign does not use the calibrated balanced trace count")
    if manifest["campaign_config_sha256"] != sha256_file(config_path):
        raise ValueError("post-pilot campaign config hash mismatch")
    if manifest["package_sha256"] != calibration["package_sha256"]:
        raise ValueError("package changed between pilot calibration and campaign freeze")
    if manifest["recipe_sha256"] != calibration["recipe_sha256"]:
        raise ValueError("recipe changed between pilot calibration and campaign freeze")
    if any(
        not values["estimated_packed_coverage"]
        or not values["estimated_assistant_coverage"]
        for values in manifest["token_projection"].values()
    ):
        raise ValueError("post-pilot campaign projection does not cover every core quota")
    expected_calls = int(manifest["projected_remaining_teacher_calls"])
    if max_teacher_calls < expected_calls:
        raise ValueError(
            f"teacher-call ceiling {max_teacher_calls} is below planned requirement {expected_calls}"
        )
    if not str(authorized_by).strip() or not str(authorization_reference).strip():
        raise ValueError("authorization identity and external reference must be nonempty")

    output_root = manifest_path.parent
    artifacts = manifest.get("artifacts", {})
    authorized_artifacts = []
    remaining = artifacts.get("remaining_jobs.jsonl")
    if not isinstance(remaining, dict):
        raise ValueError("campaign manifest lacks remaining_jobs.jsonl")
    for relative, item in [
        ("remaining_jobs.jsonl", remaining),
        *[(str(value["path"]), value) for value in artifacts.get("shards", [])],
    ]:
        path = output_root / relative
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise ValueError(f"authorized campaign artifact is missing or drifted: {relative}")
        authorized_artifacts.append(
            {"path": relative, "rows": int(item["rows"]), "sha256": item["sha256"]}
        )
    if int(remaining["rows"]) != int(manifest["remaining_jobs"]):
        raise ValueError("remaining campaign job count mismatch")

    return {
        "schema_version": "storyworld_full_campaign_authorization_v1",
        "authorization_id": (
            f"full_campaign_auth_{manifest['campaign_id']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        ),
        "status": "authorized",
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "authorized_by": authorized_by,
        "authorization_reference": authorization_reference,
        "campaign_id": manifest["campaign_id"],
        "campaign_manifest_sha256": sha256_file(manifest_path),
        "campaign_config_sha256": manifest["campaign_config_sha256"],
        "package_sha256": manifest["package_sha256"],
        "recipe_sha256": manifest["recipe_sha256"],
        "pilot_calibration_sha256": sha256_file(calibration_path),
        "pilot_human_review_bundle_sha256": sha256_file(pilot_review_bundle_path),
        "frozen_tokenizer_artifact_set_sha256": calibration["tokenizer"][
            "tokenizer_artifact_set_sha256"
        ],
        "authorized_remaining_jobs": int(manifest["remaining_jobs"]),
        "expected_teacher_calls": expected_calls,
        "teacher_call_ceiling": int(max_teacher_calls),
        "authorized_job_artifacts": authorized_artifacts,
        "sealed_evaluation_jobs": 0,
        "development_training_jobs": 0,
        "claim_boundary": (
            "This explicitly authorizes only the hash-listed remaining train-job artifacts. "
            "It does not authorize pilot replay, evaluation access, recipe drift, or extra calls."
        ),
        "passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-manifest", type=Path, required=True)
    parser.add_argument("--pilot-calibration", type=Path, required=True)
    parser.add_argument("--pilot-review-bundle", type=Path, required=True)
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
    authorization = build_full_campaign_authorization(
        args.campaign_manifest,
        args.pilot_calibration,
        args.pilot_review_bundle,
        authorized_by=args.authorized_by,
        authorization_reference=args.authorization_reference,
        max_teacher_calls=args.max_teacher_calls,
    )
    write_json(args.output.resolve(), authorization)
    print(json.dumps(authorization, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
