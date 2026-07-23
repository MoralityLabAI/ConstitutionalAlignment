"""Legacy Verifiers environment bridge used by Prime hosted evaluation."""

from __future__ import annotations

import json
from typing import Any, Literal, cast

import verifiers as vf
from datasets import Dataset

from .core import score_construct_response, score_response
from .selectors import select_construct_rows, select_rows

Completion = str | list[dict[str, Any]]


def _score_receipt(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> dict[str, Any]:
    text = parser.parse_answer(completion)
    task = json.loads(task_payload)
    if not isinstance(task, dict):
        raise TypeError("task_payload must decode to an object")
    scorer_id = task.get("scorer_id")
    if scorer_id == "dual_construct_metta_policy_v1":
        return score_construct_response(text or "", task)
    if scorer_id != "cross_frame_metta_policy_v1":
        raise ValueError(f"unsupported scorer_id: {scorer_id!r}")
    return score_response(text or "", task)


def constitutional_policy(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["final_score"])


def contract_valid(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["contract_score"])


def legal_action(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["legal_action"])


def action_quality(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["action_score"])


def evidence_grounding(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["evidence_score"])


def uncertainty_match(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["uncertainty_score"])


def review_match(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["review_score"])


def critical_violation(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["critical_violation"])


def proxy_regret(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["proxy_regret"])


def highest_scoring_action(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(
        _score_receipt(completion, parser, task_payload)["highest_scoring_action"]
    )


def _dimension_metric(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
    dimension_id: str,
) -> float:
    receipt = _score_receipt(completion, parser, task_payload)
    dimensions = receipt.get("dimension_scores", {})
    if not isinstance(dimensions, dict):
        raise TypeError("dimension_scores must be an object")
    return float(dimensions.get(dimension_id, 0.0))


def accountable_choice(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(completion, parser, task_payload, "accountable_choice")


def entrusted_stewardship(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(completion, parser, task_payload, "entrusted_stewardship")


def truth_under_concealment(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(
        completion, parser, task_payload, "truth_under_concealment"
    )


def evidence_bounded_reason(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(
        completion, parser, task_payload, "evidence_bounded_reason"
    )


def justice_without_scapegoat(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(
        completion, parser, task_payload, "justice_without_scapegoat"
    )


def repair_preservation(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(completion, parser, task_payload, "repair_preservation")


def grounded_witness(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(completion, parser, task_payload, "grounded_witness")


def public_legibility(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(completion, parser, task_payload, "public_legibility")


def courage_under_pressure(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(completion, parser, task_payload, "courage_under_pressure")


def proportionate_exposure(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(completion, parser, task_payload, "proportionate_exposure")


def evidence_over_spectacle(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(
        completion, parser, task_payload, "evidence_over_spectacle"
    )


def repair_after_testimony(
    completion: Completion, parser: vf.Parser, task_payload: str
) -> float:
    return _dimension_metric(completion, parser, task_payload, "repair_after_testimony")


def _compact_task_payload(row: dict[str, Any], scorer_id: str) -> str:
    action_scores = {
        action_id: {
            "action_key": values["action_key"],
            "robust_score": values["robust_score"],
            "forbidden_hits": values["forbidden_hits"],
            **(
                {
                    "construct_receipt": {
                        "dimension_scores": values["construct_receipt"][
                            "dimension_scores"
                        ]
                    }
                }
                if scorer_id == "dual_construct_metta_policy_v1"
                else {}
            ),
        }
        for action_id, values in row["action_scores"].items()
    }
    payload = {
        "scorer_id": scorer_id,
        "visible_fact_ids": row["visible_fact_ids"],
        "expected_uncertainty": row["expected_uncertainty"],
        "expected_review_required": row["expected_review_required"],
        "action_scores": action_scores,
    }
    if scorer_id == "dual_construct_metta_policy_v1":
        payload["construct_id"] = row["construct_id"]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _canonical_answer(row: dict[str, Any]) -> str:
    action_id, _ = max(
        row["action_scores"].items(),
        key=lambda item: (float(item[1]["robust_score"]), item[0]),
    )
    return json.dumps(
        {
            "decision": action_id,
            "evidence_ids": row["visible_fact_ids"],
            "uncertainty": row["expected_uncertainty"],
            "review_required": row["expected_review_required"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _construct_user_prompt(row: dict[str, Any]) -> str:
    return (
        f"{row['prompt']}\n\nVisible facts:\n"
        + "\n".join(f"- {fact['id']}: {fact['text']}" for fact in row["visible_facts"])
        + "\n\nActions:\n"
        + "\n".join(
            f"- {action_id}: {action['text']}"
            for action_id, action in row["action_scores"].items()
        )
    )


def _legacy_dataset(rows: list[dict[str, Any]], scorer_id: str) -> Dataset:
    records: list[dict[str, Any]] = []
    for example_id, row in enumerate(rows):
        user_prompt = (
            _construct_user_prompt(row)
            if scorer_id == "dual_construct_metta_policy_v1"
            else row["prompt"]
        )
        prompt = [
            {"role": "system", "content": row["system_prompt"]},
            {"role": "user", "content": user_prompt},
        ]
        answer = _canonical_answer(row)
        if scorer_id == "dual_construct_metta_policy_v1":
            info = {
                "task_id": row["task_id"],
                "scenario_id": row["scenario_id"],
                "storyworld_id": row["storyworld_id"],
                "construct_id": row["construct_id"],
                "benchmark_id": row["benchmark_id"],
                "split": row["split"],
                "target_dimensions": row["target_dimensions"],
            }
        else:
            info = {
                "task_id": row["task_id"],
                "scenario_id": row["scenario_id"],
                "pair_id": row["pair_id"],
                "cross_skin_pair_id": row["cross_skin_pair_id"],
                "frame": row["frame"],
                "split": row["split"],
                "proof_receipt": row["proof_receipt"],
            }
        task = {
            "prompt": prompt,
            "answer": answer,
            "example_id": example_id,
            "info": info,
            "task_payload": _compact_task_payload(row, scorer_id),
        }
        records.append(
            {
                "prompt": prompt,
                "answer": answer,
                "example_id": example_id,
                "info": {"task": task},
            }
        )
    return Dataset.from_list(records)


def load_environment(
    split: Literal["candidate_train", "development"] = "development",
    frame: Literal["balanced", "neutral", "constitutional", "jinn", "beast"] = (
        "balanced"
    ),
    task_mode: Literal["cross_frame", "constructs"] = "cross_frame",
    construct: Literal["balanced", "jinn", "beast"] = "balanced",
    require_training_approval: bool = True,
) -> vf.Environment:
    """Load a v0-compatible single-turn environment for hosted evaluation."""
    if task_mode == "constructs":
        rows = select_construct_rows(
            split=split,
            construct=construct,
            require_training_approval=require_training_approval,
        )
        scorer_id = "dual_construct_metta_policy_v1"
    else:
        rows = select_rows(
            split=split,
            frame=frame,
            require_training_approval=require_training_approval,
        )
        scorer_id = "cross_frame_metta_policy_v1"
    dataset = _legacy_dataset(rows, scorer_id)
    rubric = vf.Rubric(
        funcs=[
            constitutional_policy,
            contract_valid,
            legal_action,
            action_quality,
            evidence_grounding,
            uncertainty_match,
            review_match,
            critical_violation,
            proxy_regret,
            highest_scoring_action,
            accountable_choice,
            entrusted_stewardship,
            truth_under_concealment,
            evidence_bounded_reason,
            justice_without_scapegoat,
            repair_preservation,
            grounded_witness,
            public_legibility,
            courage_under_pressure,
            proportionate_exposure,
            evidence_over_spectacle,
            repair_after_testimony,
        ],
        weights=[
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        ],
    )
    return cast(
        vf.Environment,
        vf.SingleTurnEnv(
            dataset=dataset,
            eval_dataset=dataset,
            rubric=rubric,
            env_args={
                "split": split,
                "frame": frame,
                "task_mode": task_mode,
                "construct": construct,
                "require_training_approval": require_training_approval,
            },
        ),
    )
