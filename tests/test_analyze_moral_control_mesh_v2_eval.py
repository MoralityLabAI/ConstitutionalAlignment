from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_moral_control_mesh_v2_eval import analyze

CELLS = (
    "decisive_canonical",
    "decisive_equivalent",
    "safe_tie",
    "safe_tie_irrelevant",
    "material_update",
    "unsafe_consensus",
)


def surface(frame: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cell in CELLS:
        for rollout in range(2):
            if frame == "jinn":
                mesh_trace = [
                    {
                        "tool": "inspect_action",
                        "accepted": True,
                        "action_id": f"A-{index}",
                    }
                    for index in range(3)
                ]
                mesh_trace.append(
                    {
                        "tool": "commit_decision",
                        "accepted": True,
                        "action_id": "A-target",
                    }
                )
                trace_length = 4.0
            else:
                mesh_trace = [
                    {
                        "tool": "prune_actions",
                        "accepted": True,
                    },
                    {
                        "tool": "commit_decision",
                        "accepted": True,
                        "action_id": "A-target",
                    },
                ]
                trace_length = 2.0
            rows.append(
                {
                    "reward": 0.96,
                    "is_truncated": False,
                    "info": {
                        "task_id": f"v2:{frame}:family:{cell}",
                        "pair_id": f"v2:family:{cell}",
                        "family_id": "family",
                        "split": "confirmatory",
                        "frame": frame,
                        "cell_type": cell,
                        "rollout": rollout,
                    },
                    "mesh_trace": mesh_trace,
                    "metrics": {
                        "protocol_complete": 1.0,
                        "target_action": 1.0,
                        "shared_moral_quality": 0.90,
                        "executed_process": 1.0,
                        "executed_process_margin": 1.0,
                        "critical_final_action": 0.0,
                        "grounded_commit": 1.0,
                        "efficient_trace": 1.0,
                        "rejected_tool_calls": 0.0,
                        "mesh_trace_length": trace_length,
                    },
                }
            )
    return rows


class MoralControlMeshV2AnalyzerTests(unittest.TestCase):
    def test_complete_paired_surfaces_pass(self) -> None:
        result = analyze(
            jinn_rows=surface("jinn"),
            beast_rows=surface("beast"),
            split="confirmatory",
        )
        self.assertTrue(result["promotion_gate"]["passed"])
        self.assertEqual(
            result["primary"]["trace_classifier_accuracy"],
            1.0,
        )
        self.assertEqual(
            result["primary"]["executed_process_margin"],
            1.0,
        )

    def test_process_failure_blocks_gate(self) -> None:
        jinn = surface("jinn")
        for row in jinn:
            row["metrics"]["executed_process_margin"] = 0.0
        result = analyze(
            jinn_rows=jinn,
            beast_rows=surface("beast"),
            split="confirmatory",
        )
        self.assertFalse(result["promotion_gate"]["passed"])
        self.assertFalse(
            result["promotion_gate"]["checks"]["executed_process_margin"]
        )

    def test_incomplete_pair_join_fails_loudly(self) -> None:
        jinn = surface("jinn")
        for row in jinn[:2]:
            row["info"]["pair_id"] = "v2:family:mismatched"
        with self.assertRaisesRegex(ValueError, "exact paired universe"):
            analyze(
                jinn_rows=jinn,
                beast_rows=surface("beast"),
                split="confirmatory",
            )


if __name__ == "__main__":
    unittest.main()
