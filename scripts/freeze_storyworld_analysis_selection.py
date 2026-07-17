#!/usr/bin/env python3
"""Apply the frozen global development rule and freeze all pre-unseal analysis bytes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json


def _cell_score(score: dict[str, Any], locked_metrics: list[str]) -> float:
    values = []
    for metric in locked_metrics:
        if metric not in score.get("metrics", {}):
            raise ValueError(f"development score lacks locked metric: {metric}")
        value = float(score["metrics"][metric]["value"])
        values.append(1.0 - value if metric == "forecast_brier_score" else value)
    return sum(values) / len(values)


def freeze_analysis_selection(
    analysis_plan_path: Path,
    score_paths: list[Path],
    analysis_code_paths: list[Path],
) -> dict[str, Any]:
    analysis_plan_path = analysis_plan_path.resolve()
    plan = read_json(analysis_plan_path)
    if plan.get("schema_version") != "storyworld_analysis_plan_v1" or plan.get(
        "status"
    ) != "frozen_before_adapter_results":
        raise ValueError("analysis plan is not the frozen pre-result plan")
    scores: dict[tuple[str, int], tuple[Path, dict[str, Any]]] = {}
    for value in score_paths:
        path = value.resolve()
        score = read_json(path)
        if score.get("schema_version") != "storyworld_development_eval_score_v1":
            raise ValueError("unexpected development score schema")
        cell = (str(score["arm"]), int(score["checkpoint_tokens"]))
        if cell in scores:
            raise ValueError(f"duplicate development score cell: {cell}")
        scores[cell] = (path, score)
    expected = {
        (arm, int(checkpoint))
        for arm in plan["arms"]
        for checkpoint in plan["checkpoint_tokens"]
    }
    if set(scores) != expected:
        raise ValueError(f"development matrix is incomplete: {len(expected - set(scores))} missing")
    requirements = plan["selection_rule"]["eligible_cell_requirements"]
    by_checkpoint: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for (arm, checkpoint), (path, score) in scores.items():
        invalid_rate = int(score["invalid_responses"]) / int(score["items"])
        eligible = (
            score.get("passed")
            and float(score["coverage"]) == float(requirements["coverage"])
            and int(score["duplicate_predictions"]) == int(
                requirements["duplicate_predictions"]
            )
            and int(score["unknown_predictions"]) == int(
                requirements["unknown_predictions"]
            )
            and invalid_rate <= float(requirements["maximum_invalid_response_rate"])
            and score.get("sealed_evaluation_content_opened") is False
        )
        by_checkpoint[checkpoint].append(
            {
                "arm": arm,
                "score_path": str(path),
                "score_sha256": sha256_file(path),
                "cell_score": _cell_score(score, plan["locked_metrics"]),
                "invalid_response_rate": invalid_rate,
                "eligible": bool(eligible),
                "checkpoint_prefix_sha256": score["checkpoint_prefix_sha256"],
            }
        )
    candidates = []
    for checkpoint in map(int, plan["checkpoint_tokens"]):
        cells = sorted(by_checkpoint[checkpoint], key=lambda item: item["arm"])
        eligible = len(cells) == len(plan["arms"]) and all(item["eligible"] for item in cells)
        candidates.append(
            {
                "checkpoint_tokens": checkpoint,
                "eligible": eligible,
                "mean_four_arm_score": (
                    sum(item["cell_score"] for item in cells) / len(cells)
                    if cells
                    else None
                ),
                "cells": cells,
            }
        )
    eligible_candidates = [item for item in candidates if item["eligible"]]
    if not eligible_candidates:
        raise ValueError("no global checkpoint satisfies the frozen eligibility rule")
    selected = sorted(
        eligible_candidates,
        key=lambda item: (-float(item["mean_four_arm_score"]), int(item["checkpoint_tokens"])),
    )[0]
    code_receipts = []
    for value in analysis_code_paths:
        path = value.resolve()
        if not path.is_file():
            raise ValueError(f"analysis code file is missing: {path}")
        code_receipts.append({"path": str(path), "sha256": sha256_file(path)})
    if not code_receipts:
        raise ValueError("analysis freeze requires at least one code artifact")
    body = {
        "schema_version": "storyworld_analysis_freeze_v1",
        "status": "frozen_ready_for_one_time_unseal",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_plan_sha256": sha256_file(analysis_plan_path),
        "selection_rule": plan["selection_rule"],
        "locked_metrics": plan["locked_metrics"],
        "primary_contrasts": plan["primary_contrasts"],
        "checkpoint_candidates": candidates,
        "selected_checkpoint_tokens": int(selected["checkpoint_tokens"]),
        "selected_mean_four_arm_score": float(selected["mean_four_arm_score"]),
        "analysis_code": code_receipts,
        "development_score_receipts": len(scores),
        "sealed_evaluation_opened": False,
        "post_unseal_changes_allowed": False,
        "passed": True,
    }
    return {**body, "analysis_freeze_id": f"analysis-freeze-{sha256_json(body)[:24]}"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analysis-plan",
        type=Path,
        default=REPO_ROOT
        / "experiments"
        / "storyworld_curriculum_v1"
        / "analysis_plan_v1.json",
    )
    parser.add_argument("--development-score", type=Path, action="append", required=True)
    parser.add_argument("--analysis-code", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = freeze_analysis_selection(
        args.analysis_plan, args.development_score, args.analysis_code
    )
    write_json(args.output.resolve(), receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
