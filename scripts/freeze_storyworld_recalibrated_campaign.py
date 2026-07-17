#!/usr/bin/env python3
"""Freeze a post-pilot campaign configuration from exact calibration evidence."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, write_json


DEFAULT_CAMPAIGN = (
    REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "harvest_campaign_10m_v1.json"
)


def build_recalibrated_campaign(
    base: dict[str, Any],
    calibration: dict[str, Any],
    calibration_sha256: str,
    campaign_id: str,
) -> dict[str, Any]:
    if calibration.get("schema_version") != "storyworld_real_pilot_calibration_v1":
        raise ValueError("unexpected real-pilot calibration schema")
    if calibration.get("status") != "pilot_passed_pending_human_full_campaign_authorization":
        raise ValueError("pilot calibration has not reached the post-pilot gate")
    if not calibration.get("passed") or not calibration.get(
        "full_campaign_ready_for_human_authorization"
    ):
        raise ValueError("pilot calibration does not support a full-campaign authorization")
    recommendation = calibration["recalibrated_campaign"]
    family_count = int(recommendation["family_count"])
    per_family = int(recommendation["traces_per_family_per_arm"])
    per_arm = int(recommendation["traces_per_arm"])
    if family_count * per_family != per_arm or per_family % 2:
        raise ValueError("recalibrated campaign is not family-balanced with an even schedule count")

    per_trace: dict[str, dict[str, int]] = {}
    for slice_id in (
        "stateful_actor_trajectories",
        "interrogation_and_defense",
        "failure_critique_and_repair",
    ):
        packed_means = []
        assistant_means = []
        for arm in base["arms"]:
            values = calibration["pilot_core_token_totals"][arm][slice_id]
            traces = int(calibration["traces_by_arm"][arm])
            packed_means.append(int(values["packed_tokens"]) // traces)
            assistant_means.append(int(values["assistant_tokens"]) // traces)
        per_trace[slice_id] = {
            "packed_tokens": min(packed_means),
            "assistant_tokens": min(assistant_means),
        }

    world_model_packed = []
    world_model_assistant = []
    for arm in base["arms"]:
        values = calibration["exact_world_model_availability"][arm]
        worlds = int(values["worlds"])
        if worlds <= 0:
            raise ValueError(f"calibration has no world-model worlds for arm {arm}")
        world_model_packed.append(int(values["packed_tokens"]) // worlds)
        world_model_assistant.append(int(values["assistant_tokens"]) // worlds)

    updated = deepcopy(base)
    updated["campaign_id"] = campaign_id
    updated["parent_campaign_id"] = calibration["campaign_id"]
    updated["train_family_count"] = family_count
    updated["traces_per_family_per_arm"] = per_family
    updated["traces_per_arm"] = per_arm
    updated["pilot_calibration_sha256"] = calibration_sha256
    updated["frozen_tokenizer_artifact_set_sha256"] = calibration["tokenizer"][
        "tokenizer_artifact_set_sha256"
    ]
    updated["token_calibration"] = {
        "status": "exact_real_pilot_conservative_minimum_across_arms",
        "tokenizer": calibration["tokenizer"],
        "source_pilot_calibration_sha256": calibration_sha256,
        "source_traces": int(calibration["pilot_jobs"]),
        "per_trace": per_trace,
        "per_unique_world_arm": {
            "metta_world_model_tasks": {
                "packed_tokens": min(world_model_packed),
                "assistant_tokens": min(world_model_assistant),
            }
        },
        "claim_boundary": (
            "Conservative minimum exact-tokenizer yield across the four real-pilot arms; "
            "the campaign must still be human-authorized and the final pack stops on measured quotas."
        ),
    }
    updated["execution_gates"] = {
        **deepcopy(base["execution_gates"]),
        "pilot_calibration_sha256": calibration_sha256,
        "frozen_tokenizer_artifact_set_sha256": updated[
            "frozen_tokenizer_artifact_set_sha256"
        ],
        "explicit_full_campaign_authorization_required": True,
    }
    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    try:
        output.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("post-pilot campaign config must be frozen inside the repository") from exc
    calibration_path = args.calibration.resolve()
    updated = build_recalibrated_campaign(
        read_json(args.base_campaign.resolve()),
        read_json(calibration_path),
        sha256_file(calibration_path),
        args.campaign_id,
    )
    write_json(output, updated)
    print(
        json.dumps(
            {
                "campaign_id": updated["campaign_id"],
                "traces_per_family_per_arm": updated["traces_per_family_per_arm"],
                "traces_per_arm": updated["traces_per_arm"],
                "pilot_calibration_sha256": updated["pilot_calibration_sha256"],
                "output": output.relative_to(REPO_ROOT).as_posix(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
