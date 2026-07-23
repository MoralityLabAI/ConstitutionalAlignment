"""Verifiers v1 taskset for deterministic Jinn/Beast storyworld rewards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import verifiers.v1 as vf

from .core import score_response


FRAME_VALUES = ("neutral", "constitutional", "jinn", "beast")
SPLIT_VALUES = ("candidate_train", "development")


class JinnBeastMettaTaskData(vf.TaskData):
    scenario_id: str
    pair_id: str
    cross_skin_pair_id: str
    split: Literal["candidate_train", "development"]
    frame: Literal["neutral", "constitutional", "jinn", "beast"]
    visible_fact_ids: list[str]
    expected_uncertainty: Literal["bounded", "material"]
    expected_review_required: bool
    action_scores: dict[str, dict[str, Any]]
    training_approved: bool
    source_review_status: str
    proof_receipt: dict[str, Any]


class JinnBeastMettaTask(vf.Task[JinnBeastMettaTaskData, vf.State, vf.TaskConfig]):
    @vf.reward(weight=1.0)
    async def constitutional_policy(self, trace: vf.Trace) -> float:
        receipt = score_response(trace.last_reply or "", self.data.model_dump())
        trace.record_metrics(
            {
                "jbm/contract": receipt["contract_score"],
                "jbm/legal_action": float(receipt["legal_action"]),
                "jbm/action_score": receipt["action_score"],
                "jbm/evidence": receipt["evidence_score"],
                "jbm/uncertainty": receipt["uncertainty_score"],
                "jbm/review": receipt["review_score"],
                "jbm/critical_violation": float(receipt["critical_violation"]),
                "jbm/proxy_regret": receipt["proxy_regret"],
            }
        )
        trace.info["jinn_beast_metta"] = {
            "scenario_id": self.data.scenario_id,
            "pair_id": self.data.pair_id,
            "cross_skin_pair_id": self.data.cross_skin_pair_id,
            "frame": self.data.frame,
            "proof_receipt": self.data.proof_receipt,
            "score_receipt": receipt,
        }
        return float(receipt["final_score"])


class JinnBeastMettaConfig(vf.TasksetConfig):
    split: Literal["candidate_train", "development"] = "development"
    frame: Literal["balanced", "neutral", "constitutional", "jinn", "beast"] = (
        "balanced"
    )
    require_training_approval: bool = True
    task: vf.TaskConfig = vf.TaskConfig()


def _load_rows() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parent / "data" / "tasks.jsonl"
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number} is not valid JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number} must contain an object")
        task_id = str(row.get("task_id", ""))
        if not task_id:
            raise ValueError(f"{path}:{line_number} has no task_id")
        if task_id in seen:
            raise ValueError(f"{path}:{line_number} duplicates task_id {task_id}")
        seen.add(task_id)
        rows.append(row)
    if not rows:
        raise ValueError(f"{path} is empty")
    return rows


def select_rows(
    split: Literal["candidate_train", "development"] = "development",
    frame: Literal["balanced", "neutral", "constitutional", "jinn", "beast"] = (
        "balanced"
    ),
    require_training_approval: bool = True,
) -> list[dict[str, Any]]:
    """Select rows once for both v1 tasksets and the legacy eval bridge."""
    if split not in SPLIT_VALUES:
        raise ValueError(f"unsupported split: {split!r}")
    if frame != "balanced" and frame not in FRAME_VALUES:
        raise ValueError(f"unsupported frame: {frame!r}")

    rows = [
        row
        for row in _load_rows()
        if row["split"] == split
        and (frame == "balanced" or row["frame"] == frame)
    ]
    if not rows:
        raise ValueError(f"no rows for split={split!r}, frame={frame!r}")
    if split == "candidate_train" and require_training_approval:
        blocked = [row["task_id"] for row in rows if not row["training_approved"]]
        if blocked:
            raise ValueError(
                "candidate_train is fail-closed: "
                f"{len(blocked)} rows lack training approval"
            )
    return rows


class JinnBeastMettaTaskset(vf.Taskset[JinnBeastMettaTask, JinnBeastMettaConfig]):
    def load(self) -> list[JinnBeastMettaTask]:
        rows = select_rows(
            split=self.config.split,
            frame=self.config.frame,
            require_training_approval=self.config.require_training_approval,
        )

        tasks: list[JinnBeastMettaTask] = []
        for index, row in enumerate(rows):
            tasks.append(
                JinnBeastMettaTask(
                    JinnBeastMettaTaskData(
                        idx=index,
                        name=row["task_id"],
                        prompt=row["prompt"],
                        system_prompt=row["system_prompt"],
                        scenario_id=row["scenario_id"],
                        pair_id=row["pair_id"],
                        cross_skin_pair_id=row["cross_skin_pair_id"],
                        split=row["split"],
                        frame=row["frame"],
                        visible_fact_ids=row["visible_fact_ids"],
                        expected_uncertainty=row["expected_uncertainty"],
                        expected_review_required=row["expected_review_required"],
                        action_scores=row["action_scores"],
                        training_approved=row["training_approved"],
                        source_review_status=row["source_review_status"],
                        proof_receipt=row["proof_receipt"],
                    ),
                    self.config.task,
                )
            )
        return tasks
