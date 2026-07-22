from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.analyze_qwen_soft_test_mizan import analyze_run
from scripts.build_qwen_soft_test_mizan_probes import build_probe_rows
from scripts.build_storyworld_format_control_dataset import build_format_control_rows


REPO_ROOT = Path(__file__).resolve().parent.parent


class QwenSoftTestTests(unittest.TestCase):
    def test_st05_execution_is_frozen_and_wrapper_supports_base_only(self) -> None:
        freeze = json.loads(
            (
                REPO_ROOT
                / "experiments/qwen_soft_tests_v1/st05_execution_freeze_v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertFalse(freeze["mizan_outputs_seen_before_freeze"])
        self.assertEqual(freeze["generation"]["max_new_tokens"], 96)
        self.assertEqual(freeze["generation"]["probe_count"], 20)
        self.assertFalse(freeze["generation"]["repair_or_canonical_fallback_allowed"])
        wrapper = (
            REPO_ROOT / "scripts/models/generic/run_jinn_tiny_local_smoke.ps1"
        ).read_text(encoding="utf-8-sig")
        self.assertIn("[switch]$BaseOnly", wrapper)
        self.assertIn('$args += "--base-only"', wrapper)

    def test_format_control_preserves_legal_model_action(self) -> None:
        rows = [
            {
                "example_id": "source_1",
                "messages": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "A-1234567890: option"},
                    {"role": "assistant", "content": "constitutional target"},
                ],
                "source": {"model_action_id": "A-1234567890"},
            },
            {
                "example_id": "source_invalid",
                "messages": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "A-ABCDEFGHIJ: option"},
                    {"role": "assistant", "content": "constitutional target"},
                ],
                "source": {"model_action_id": None},
            },
        ]
        result = build_format_control_rows(rows, target_rows=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(len({row["example_id"] for row in result}), 3)
        self.assertTrue(
            all(
                row["messages"][-1]["content"].startswith("Decision: A-1234567890")
                for row in result
            )
        )
        self.assertTrue(
            all(row["source"]["constitutional_target_used"] is False for row in result)
        )

    def test_mizan_probe_pack_crosses_five_conditions_and_four_rooms(self) -> None:
        rows, manifest = build_probe_rows(
            REPO_ROOT,
            REPO_ROOT / "experiments/mizan_rooms_v1/suite.json",
        )
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({row["probe_id"] for row in rows}), 20)
        self.assertEqual(
            {row["condition_id"] for row in rows}, set(manifest["conditions"])
        )
        self.assertEqual(len({row["variant_id"] for row in rows}), 4)
        self.assertTrue(all(len(row["allowed_action_ids"]) == 3 for row in rows))

    def test_mizan_analyzer_requires_and_scores_the_complete_probe_universe(self) -> None:
        probes, manifest = build_probe_rows(
            REPO_ROOT,
            REPO_ROOT / "experiments/mizan_rooms_v1/suite.json",
        )
        generations = [
            {
                "example_id": probe["probe_id"],
                "response": json.dumps(
                    {
                        "action_id": probe["allowed_action_ids"][0],
                        "public_reason": "Bounded fixture response.",
                    }
                ),
            }
            for probe in probes
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "generations.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in generations),
                encoding="utf-8",
            )
            result = analyze_run(
                "fixture",
                path,
                {probe["probe_id"]: probe for probe in probes},
                set(manifest["failure_tags"]),
            )
        self.assertEqual(result["rows"], 20)
        self.assertEqual(result["valid_action_rate"], 1.0)
        self.assertEqual(len(result["conditions"]), 5)


if __name__ == "__main__":
    unittest.main()
