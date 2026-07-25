"""Legacy Verifiers environment bridge used by Prime hosted evaluation."""

from __future__ import annotations

import json
from typing import Any, Literal, cast

import verifiers as vf
from datasets import Dataset

from .core import score_construct_response, score_response
from .selectors import (
    select_construct_rows,
    select_jinn_moral_reasoner_rows,
    select_quranic_village_replay_rows,
    select_rows,
)
from .village import score_village_response

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
    if scorer_id == "quranic_moral_village_replay_v2":
        return score_village_response(text or "", task)
    if scorer_id in {
        "dual_construct_metta_policy_v1",
        "jinn_moral_reasoner_policy_v2",
    }:
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


def village_action_safe(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["action_safe"])


def village_critical_failure(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["critical_failure"])


def village_target_reply(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["target_reply"])


def village_identity_leakage(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["identity_leakage"])


def village_exact_two_labels(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["exact_two_labels"])


def village_theme_coverage(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> float:
    return float(_score_receipt(completion, parser, task_payload)["theme_coverage"])


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
    construct_scorer = scorer_id in {
        "dual_construct_metta_policy_v1",
        "jinn_moral_reasoner_policy_v2",
    }
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
                if construct_scorer
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
    if construct_scorer:
        payload["construct_id"] = row["construct_id"]
        payload["benchmark_id"] = row["benchmark_id"]
    if scorer_id == "jinn_moral_reasoner_policy_v2":
        payload["reward_profile"] = row["reward_profile"]
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
    construct_scorer = scorer_id in {
        "dual_construct_metta_policy_v1",
        "jinn_moral_reasoner_policy_v2",
    }
    records: list[dict[str, Any]] = []
    for example_id, row in enumerate(rows):
        user_prompt = (
            _construct_user_prompt(row)
            if construct_scorer
            else row["prompt"]
        )
        prompt = [
            {"role": "system", "content": row["system_prompt"]},
            {"role": "user", "content": user_prompt},
        ]
        answer = _canonical_answer(row)
        if construct_scorer:
            info = {
                "task_id": row["task_id"],
                "scenario_id": row["scenario_id"],
                "storyworld_id": row["storyworld_id"],
                "construct_id": row["construct_id"],
                "benchmark_id": row["benchmark_id"],
                "split": row["split"],
                "target_dimensions": row["target_dimensions"],
            }
            if scorer_id == "jinn_moral_reasoner_policy_v2":
                info.update(
                    {
                        "family_id": row["family_id"],
                        "condition": row["condition"],
                        "state_role": row["state_role"],
                        "presentation_role": row["presentation_role"],
                        "equivalence_pair_id": row["equivalence_pair_id"],
                        "change_pair_id": row["change_pair_id"],
                        "target_action_id": row["target_action_id"],
                    }
                )
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


def _village_dataset(rows: list[dict[str, Any]]) -> Dataset:
    records: list[dict[str, Any]] = []
    for example_id, row in enumerate(rows):
        prompt = [
            {"role": "system", "content": row["system_prompt"]},
            {"role": "user", "content": row["prompt"]},
        ]
        info = {
            "task_id": row["task_id"],
            "stimulus_index": row["stimulus_index"],
            "probe_id": row["probe_id"],
            "topic_id": row["topic_id"],
            "round": row["round"],
            "source_stimulus_arm_id": row["source_stimulus_arm_id"],
            "target_alias": row["target_alias"],
            "split": row["split"],
        }
        task = {
            "prompt": prompt,
            "answer": row["answer"],
            "example_id": example_id,
            "info": info,
            "task_payload": json.dumps(
                row,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        records.append(
            {
                "prompt": prompt,
                "answer": row["answer"],
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
    task_mode: Literal[
        "cross_frame",
        "constructs",
        "jinn_moral_reasoner",
        "quranic_village_replay",
    ] = "cross_frame",
    construct: Literal["balanced", "jinn", "beast"] = "balanced",
    require_training_approval: bool = True,
) -> vf.Environment:
    """Load a v0-compatible single-turn environment for hosted evaluation."""
    if task_mode == "quranic_village_replay":
        if split != "development":
            raise ValueError("quranic_village_replay is held out and evaluation-only")
        rows = select_quranic_village_replay_rows()
        dataset = _village_dataset(rows)
        rubric = vf.Rubric(
            funcs=[
                constitutional_policy,
                contract_valid,
                village_action_safe,
                village_critical_failure,
                village_target_reply,
                village_identity_leakage,
                village_exact_two_labels,
                village_theme_coverage,
            ],
            weights=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        )
        return cast(
            vf.Environment,
            vf.SingleTurnEnv(
                dataset=dataset,
                eval_dataset=dataset,
                rubric=rubric,
                env_args={
                    "split": split,
                    "task_mode": task_mode,
                    "require_training_approval": require_training_approval,
                },
            ),
        )
    if task_mode == "jinn_moral_reasoner":
        rows = select_jinn_moral_reasoner_rows(
            split=split,
            require_training_approval=require_training_approval,
        )
        scorer_id = "jinn_moral_reasoner_policy_v2"
    elif task_mode == "constructs":
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
