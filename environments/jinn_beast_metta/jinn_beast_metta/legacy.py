"""Legacy Verifiers environment bridge used by Prime hosted evaluation."""

from __future__ import annotations

import json
from typing import Any, Literal, cast

from datasets import Dataset
import verifiers as vf

from .core import score_response
from .taskset import select_rows


Completion = str | list[dict[str, Any]]


def _score_receipt(
    completion: Completion,
    parser: vf.Parser,
    task_payload: str,
) -> dict[str, Any]:
    text = parser.parse_answer(completion)
    task = json.loads(task_payload)
    if not isinstance(task, dict):
        raise ValueError("task_payload must decode to an object")
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


def _compact_task_payload(row: dict[str, Any]) -> str:
    action_scores = {
        action_id: {
            "action_key": values["action_key"],
            "robust_score": values["robust_score"],
            "forbidden_hits": values["forbidden_hits"],
        }
        for action_id, values in row["action_scores"].items()
    }
    payload = {
        "visible_fact_ids": row["visible_fact_ids"],
        "expected_uncertainty": row["expected_uncertainty"],
        "expected_review_required": row["expected_review_required"],
        "action_scores": action_scores,
    }
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


def _legacy_dataset(rows: list[dict[str, Any]]) -> Dataset:
    records: list[dict[str, Any]] = []
    for example_id, row in enumerate(rows):
        prompt = [
            {"role": "system", "content": row["system_prompt"]},
            {"role": "user", "content": row["prompt"]},
        ]
        answer = _canonical_answer(row)
        task = {
            "prompt": prompt,
            "answer": answer,
            "example_id": example_id,
            "info": {
                "task_id": row["task_id"],
                "scenario_id": row["scenario_id"],
                "pair_id": row["pair_id"],
                "cross_skin_pair_id": row["cross_skin_pair_id"],
                "frame": row["frame"],
                "split": row["split"],
                "proof_receipt": row["proof_receipt"],
            },
            "task_payload": _compact_task_payload(row),
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
    require_training_approval: bool = True,
) -> vf.Environment:
    """Load a v0-compatible single-turn environment for hosted evaluation."""
    rows = select_rows(
        split=split,
        frame=frame,
        require_training_approval=require_training_approval,
    )
    dataset = _legacy_dataset(rows)
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
        ],
        weights=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
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
                "require_training_approval": require_training_approval,
            },
        ),
    )
