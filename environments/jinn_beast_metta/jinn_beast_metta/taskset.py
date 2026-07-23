"""Verifiers v1 taskset for deterministic Jinn/Beast storyworld rewards."""

from __future__ import annotations

from typing import Any, Literal

import verifiers.v1 as vf

from .core import score_response
from .selectors import select_rows


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
