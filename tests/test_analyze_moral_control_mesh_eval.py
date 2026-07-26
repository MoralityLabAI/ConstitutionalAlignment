from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_ROOT = REPO_ROOT / "environments" / "jinn_beast_metta"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(ENV_ROOT))

from jinn_beast_metta.mesh import canonical_mesh_response, score_mesh_response
from jinn_beast_metta.selectors import select_moral_control_mesh_rows

from scripts.analyze_moral_control_mesh_eval import analyze


def result_row(task: dict[str, Any], completion: str) -> dict[str, Any]:
    receipt = score_mesh_response(completion, task)
    return {
        "completion": [{"role": "assistant", "content": completion}],
        "reward": receipt["final_score"],
        "is_truncated": False,
        "info": {
            key: task[key]
            for key in (
                "task_id",
                "pair_id",
                "family_id",
                "split",
                "frame",
                "cell_type",
                "target_action_id",
            )
        },
        "metrics": {
            "contract_valid": receipt["contract_score"],
            "highest_scoring_action": float(receipt["highest_scoring_action"]),
            "action_quality": receipt["action_score"],
            "own_process": receipt["own_process_score"],
            "jinn_process": receipt["jinn_process_score"],
            "beast_process": receipt["beast_process_score"],
            "process_margin": receipt["process_margin"],
            "critical_violation": float(receipt["critical_violation"]),
            "unsafe_consensus_resistance": receipt["unsafe_consensus_resistance"],
        },
    }


class MoralControlMeshAnalysisTests(unittest.TestCase):
    def test_registered_gate_passes_on_canonical_distinct_surfaces(self) -> None:
        jinn_tasks = select_moral_control_mesh_rows(
            split="confirmatory",
            frame="jinn",
        )
        beast_tasks = select_moral_control_mesh_rows(
            split="confirmatory",
            frame="beast",
        )
        task_by_pair_jinn = {task["pair_id"]: task for task in jinn_tasks}

        adapter_jinn = [
            result_row(task, canonical_mesh_response(task)) for task in jinn_tasks
        ]
        adapter_beast = [
            result_row(task, canonical_mesh_response(task)) for task in beast_tasks
        ]
        base_jinn = [
            result_row(task, canonical_mesh_response(task)) for task in jinn_tasks
        ]
        base_beast: list[dict[str, Any]] = []
        for task in beast_tasks:
            value = json.loads(canonical_mesh_response(task))
            if task["cell_type"] in {
                "safe_tie",
                "safe_tie_irrelevant",
                "unsafe_consensus",
            }:
                jinn_task = task_by_pair_jinn[task["pair_id"]]
                value["decision"] = jinn_task["target_action_id"]
                value["alternatives_considered"] = list(task["action_scores"])
            base_beast.append(result_row(task, json.dumps(value)))

        analysis = analyze(
            base_jinn=base_jinn,
            base_beast=base_beast,
            adapter_jinn=adapter_jinn,
            adapter_beast=adapter_beast,
            split="confirmatory",
        )
        self.assertTrue(analysis["promotion_gate"]["passed"])
        self.assertEqual(
            analysis["primary"]["adapter_safe_tie_paired_target_rate"],
            1.0,
        )
        self.assertEqual(
            analysis["primary"]["base_safe_tie_paired_target_rate"],
            0.0,
        )
        self.assertEqual(analysis["primary"]["critical_final_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
