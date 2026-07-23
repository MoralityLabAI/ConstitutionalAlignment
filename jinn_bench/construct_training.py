"""Fail-closed collation of construct storyworld rollouts into candidate data."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .construct_scoring import score_construct_response

ROLLOUT_BUCKETS = (
    "excluded_critical",
    "repair_output_contract",
    "repair_action_choice",
    "repair_evidence_grounding",
    "repair_uncertainty_or_review",
    "gold_positive",
)


def render_task_prompt(task: dict[str, Any]) -> str:
    """Render the complete decision context used by SFT and preference rows."""
    return (
        f"{task['prompt']}\n\nVisible facts:\n"
        + "\n".join(f"- {fact['id']}: {fact['text']}" for fact in task["visible_facts"])
        + "\n\nActions:\n"
        + "\n".join(
            f"- {action_id}: {action['text']}"
            for action_id, action in task["action_scores"].items()
        )
    )


def classify_rollout(score: dict[str, Any]) -> str:
    """Assign each rollout to exactly one data-growth lane."""
    if score["critical_violation"]:
        return "excluded_critical"
    if score["contract_score"] != 1.0 or not score["legal_action"]:
        return "repair_output_contract"
    if not score["highest_scoring_action"]:
        return "repair_action_choice"
    if score["evidence_score"] != 1.0:
        return "repair_evidence_grounding"
    if score["uncertainty_score"] != 1.0 or score["review_score"] != 1.0:
        return "repair_uncertainty_or_review"
    return "gold_positive"


def collate_candidate_rollouts(
    tasks: list[dict[str, Any]],
    rollouts: list[dict[str, Any]],
    *,
    minimum_preference_margin: float = 0.1,
) -> dict[str, Any]:
    """Score candidate-only rollouts and produce unapproved training candidates."""
    if not 0.0 < minimum_preference_margin <= 1.0:
        raise ValueError("minimum_preference_margin must lie in (0, 1]")
    candidate_tasks = {
        task["task_id"]: task for task in tasks if task["split"] == "candidate_train"
    }
    development_ids = {
        task["task_id"] for task in tasks if task["split"] == "development"
    }
    if not candidate_tasks:
        raise ValueError("no candidate_train construct tasks are available")
    rollout_ids = [str(row.get("rollout_id", "")) for row in rollouts]
    if any(not rollout_id for rollout_id in rollout_ids):
        raise ValueError("every candidate rollout requires a rollout_id")
    if len(rollout_ids) != len(set(rollout_ids)):
        raise ValueError("candidate rollout ids must be unique")

    scored_rollouts = []
    bucket_counts: Counter[str] = Counter()
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rollout in rollouts:
        task_id = str(rollout.get("task_id", ""))
        if task_id in development_ids:
            raise ValueError(
                f"development benchmark task cannot enter training collation: {task_id}"
            )
        task = candidate_tasks.get(task_id)
        if task is None:
            raise ValueError(f"unknown candidate task id: {task_id}")
        completion = rollout.get("completion")
        if not isinstance(completion, str):
            raise ValueError(f"{rollout['rollout_id']}: completion must be a string")
        score = score_construct_response(completion, task)
        bucket = classify_rollout(score)
        scored = {
            "rollout_id": str(rollout["rollout_id"]),
            "task_id": task_id,
            "construct_id": task["construct_id"],
            "completion": completion,
            "reasoning_trace": str(rollout.get("reasoning_trace", "")),
            "model_id": str(rollout.get("model_id", "")),
            "bucket": bucket,
            "score": score,
        }
        scored_rollouts.append(scored)
        by_task[task_id].append(scored)
        bucket_counts[bucket] += 1

    sft_rows = []
    for scored in scored_rollouts:
        if scored["bucket"] != "gold_positive":
            continue
        task = candidate_tasks[scored["task_id"]]
        sft_rows.append(
            {
                "schema_version": "jinn_beast_construct_rollout_sft_v1",
                "source_rollout_id": scored["rollout_id"],
                "source_task_id": scored["task_id"],
                "construct_id": scored["construct_id"],
                "messages": [
                    {"role": "system", "content": task["system_prompt"]},
                    {"role": "user", "content": render_task_prompt(task)},
                    {"role": "assistant", "content": scored["completion"]},
                ],
                "reasoning_trace": scored["reasoning_trace"],
                "reward": scored["score"]["final_score"],
                "dimension_scores": scored["score"]["dimension_scores"],
                "training_approved": False,
                "source_review_status": task["source_review_status"],
                "benchmark_contamination": False,
            }
        )

    preference_rows = []
    for task_id, task_rollouts in sorted(by_task.items()):
        if len(task_rollouts) < 2:
            continue
        ordered = sorted(
            task_rollouts,
            key=lambda row: (
                -float(row["score"]["final_score"]),
                row["rollout_id"],
            ),
        )
        chosen = ordered[0]
        rejected = ordered[-1]
        margin = round(
            float(chosen["score"]["final_score"])
            - float(rejected["score"]["final_score"]),
            6,
        )
        if (
            margin < minimum_preference_margin
            or chosen["completion"] == rejected["completion"]
        ):
            continue
        task = candidate_tasks[task_id]
        preference_rows.append(
            {
                "schema_version": "jinn_beast_construct_rollout_preference_v1",
                "pair_id": (
                    f"{task_id}:{chosen['rollout_id']}>{rejected['rollout_id']}"
                ),
                "source_task_id": task_id,
                "construct_id": task["construct_id"],
                "system_prompt": task["system_prompt"],
                "prompt": render_task_prompt(task),
                "chosen": chosen["completion"],
                "rejected": rejected["completion"],
                "chosen_reward": chosen["score"]["final_score"],
                "rejected_reward": rejected["score"]["final_score"],
                "reward_margin": margin,
                "chosen_reasoning_trace": chosen["reasoning_trace"],
                "rejected_reasoning_trace": rejected["reasoning_trace"],
                "training_approved": False,
                "source_review_status": task["source_review_status"],
                "benchmark_contamination": False,
            }
        )

    return {
        "schema_version": "jinn_beast_construct_rollout_collation_v1",
        "rollouts": len(scored_rollouts),
        "bucket_counts": {bucket: bucket_counts[bucket] for bucket in ROLLOUT_BUCKETS},
        "scored_rollouts": scored_rollouts,
        "candidate_sft_rows": sft_rows,
        "candidate_preference_rows": preference_rows,
        "training_signal": {
            "candidate_sft_rows": len(sft_rows),
            "candidate_preference_rows": len(preference_rows),
            "reasoning_traces_retained": True,
            "training_approved": False,
            "benchmark_contamination": False,
            "approval_required": True,
        },
    }
