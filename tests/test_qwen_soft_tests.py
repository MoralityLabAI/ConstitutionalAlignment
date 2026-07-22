from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.analyze_qwen_soft_test_mizan import analyze_run
from scripts.build_qwen_soft_test_mizan_probes import build_probe_rows
from scripts.build_storyworld_format_control_dataset import build_format_control_rows
from scripts.collate_jinn_experiment_data import collate


REPO_ROOT = Path(__file__).resolve().parent.parent


class QwenSoftTestTests(unittest.TestCase):
    def test_collation_catalogs_and_archives_without_mutating_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "jinn_or_beast"
            repo = root / "repo"
            output = source / "collated"
            (source / "run_a").mkdir(parents=True)
            (source / "run_a/result.json").write_text('{"ok": true}\n')
            (source / "run_b").mkdir()
            (source / "run_b/rows.jsonl").write_text('{"row": 1}\n')
            (repo / "experiments/meta").mkdir(parents=True)
            (repo / "experiments/meta/receipt.json").write_text('{"status": "ok"}\n')

            summary = collate(
                source,
                output,
                repo,
                (Path("experiments/meta"),),
                "snapshot.zip",
            )

            self.assertEqual(summary["source_file_count"], 2)
            self.assertTrue(summary["archive_crc_check_passed"])
            self.assertTrue((source / "run_a/result.json").exists())
            catalog_rows = [
                json.loads(line)
                for line in (output / "source_catalog.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(
                {row["relative_path"] for row in catalog_rows},
                {"run_a/result.json", "run_b/rows.jsonl"},
            )
            with zipfile.ZipFile(output / "snapshot.zip") as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "data/run_a/result.json",
                        "data/run_b/rows.jsonl",
                        "repo_metadata/experiments/meta/receipt.json",
                    },
                )

    def test_closeout_covers_every_registered_soft_test(self) -> None:
        matrix = json.loads(
            (
                REPO_ROOT / "experiments/qwen_soft_tests_v1/soft_test_matrix_v1.json"
            ).read_text(encoding="utf-8")
        )
        closeout = json.loads(
            (
                REPO_ROOT
                / "experiments/qwen_soft_tests_v1/soft_test_closeout_20260722.json"
            ).read_text(encoding="utf-8")
        )
        registered = {
            item["id"]
            for group in (matrix["completed_tests"], matrix["remaining_tests"])
            for item in group
        }
        completed = {item["id"] for item in closeout["tests"]}
        self.assertEqual(completed, registered)
        self.assertEqual(closeout["status"], "complete_all_registered_local_soft_tests")
        self.assertEqual(
            closeout["completion_audit"]["st05_generation_rows_observed"], 80
        )
        self.assertFalse(closeout["primelab_spend_authorized_automatically"])

        collation = json.loads(
            (
                REPO_ROOT / "experiments/qwen_soft_tests_v1/"
                "jinn_or_beast_collation_20260722.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(collation["status"], "complete_and_independently_verified")
        self.assertEqual(collation["coverage"]["source_file_count"], 847)
        self.assertEqual(collation["verification"]["source_hash_mismatches"], 0)
        self.assertFalse(collation["primelab_spend_authorized_automatically"])

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

    def test_mizan_analyzer_requires_and_scores_the_complete_probe_universe(
        self,
    ) -> None:
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
