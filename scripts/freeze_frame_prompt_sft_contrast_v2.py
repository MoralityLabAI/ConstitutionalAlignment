#!/usr/bin/env python3
"""Version the direct prompt-versus-SFT contract onto the licensed v2 universe."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments/frame_internalization_sft_v1"
DEFAULT_INPUT = PACKAGE / "prompt_sft_contrast_v1.json"
DEFAULT_OUTPUT = PACKAGE / "prompt_sft_contrast_v2.json"
AMENDMENT = PACKAGE / "PROTOCOL_AMENDMENT_LICENSED_HARMBENCH_V2.md"
UNIVERSE_MANIFEST = PACKAGE / "rerun_freeze/evaluation_universes_v2.json"
UNIVERSE = PACKAGE / "rerun_freeze/evaluation_universes_v2/harmful_queries.jsonl"
JUDGE = PACKAGE / "rerun_freeze/judge_classifier_inputs_v2.json"
PROGRESS = PACKAGE / "rerun_freeze/predecessor_reanchor_progress_v2.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def binding(path: Path) -> dict[str, Any]:
    return {"path": relative(path), "sha256": sha256_file(path)}


def main() -> int:
    args = parse_args()
    contract = json.loads(args.input.read_text(encoding="utf-8"))
    contract["schema_version"] = "frame_internalization_prompt_sft_contrast.v2"
    contract["contract_id"] = "frame_internalization_direct_prompt_sft_v2_harmbench"
    contract["classification"] = (
        "prospective_analysis_amendment_on_licensed_v2_evaluation_universe"
    )
    contract["universe_amendment"] = {
        **binding(AMENDMENT),
        "changed_provision": (
            "Replaces the unlicensed recovered harmful universe before affected outcomes; "
            "retains the estimands, paired design, decoding, scoring, and bootstrap."
        ),
    }
    universe = contract["evaluation"]["universe"]
    universe.update(binding(UNIVERSE))
    universe["manifest"] = {
        **binding(UNIVERSE_MANIFEST),
        "license_gate_must_pass_before_execution": True,
    }
    contract["evaluation"]["historical_reanchor_separation"] = (
        "The recovered three-sample v1 calibration is descriptive provenance only. "
        "It is not pooled with v2 and its historical F0 interval is not a v2 pass/fail target."
    )
    contract["evaluation"]["prospective_v2_baseline"] = {
        "required_before_adapter_outcomes": True,
        "same_200_prompt_ids_as_prompt_and_sft_cells": True,
        "magnitude_acceptance_interval": None,
        "report_complete_joined_F0_estimate": True,
    }
    contract["frozen_scoring_inputs"]["judge_classifier_inputs"] = {
        **binding(JUDGE),
        "must_pass_before_execution": True,
    }
    contract["frozen_scoring_inputs"]["reanchor_progress"] = {
        **binding(PROGRESS),
        "probe_frozen_before_adapter_outcomes_must_be_true": True,
    }
    gate = contract["analysis_gate"]
    gate.pop("base_reanchor_required", None)
    gate["prospective_v2_base_baseline_required"] = True
    gate["historical_v1_interval_as_v2_pass_fail_forbidden"] = True
    contract["interpretation_boundary"] = (
        "This is a within-model operational comparison of two interventions on the licensed "
        "v2 universe. It does not reproduce the predecessor universe and does not support a "
        "model-family-general claim that fine-tuning is superior to prompting."
    )
    contract["freezer"] = binding(Path(__file__))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {"output": str(args.output), "sha256": sha256_file(args.output)}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
