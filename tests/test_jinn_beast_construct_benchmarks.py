from __future__ import annotations

import json
import unittest
from pathlib import Path

from jinn_bench.construct_scoring import (
    build_construct_run_receipt,
    load_metta_policy,
    score_construct_response,
)
from jinn_bench.construct_training import collate_candidate_rollouts
from jinn_bench.scoring import load_json, load_jsonl, sha256_file

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "jinn_bench/data/construct_benchmarks_v1.json"
TASKS_PATH = REPO_ROOT / "jinn_bench/data/construct_tasks_v1.jsonl"
SFT_PATH = REPO_ROOT / "jinn_bench/data/construct_candidate_sft_v1.jsonl"
PREFERENCES_PATH = (
    REPO_ROOT / "jinn_bench/data/construct_candidate_preferences_v1.jsonl"
)
SOURCE_ANCHORS_PATH = REPO_ROOT / "jinn_bench/data/construct_source_anchors_v1.json"


class JinnBeastConstructBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_json(REGISTRY_PATH)
        cls.tasks = load_jsonl(TASKS_PATH)

    def test_registry_binds_two_separate_constructs_and_all_artifacts(self) -> None:
        self.assertEqual(
            self.registry["schema_version"],
            "jinn_beast_construct_benchmarks_registry_v1",
        )
        self.assertEqual(
            set(self.registry["constructs"]),
            {"jinn_ness_v1", "beast_from_earth_witness_v1"},
        )
        self.assertEqual(self.registry["data"]["task_rows"], 12)
        self.assertEqual(self.registry["data"]["candidate_train_rows"], 8)
        self.assertEqual(self.registry["data"]["development_rows"], 4)
        self.assertEqual(self.registry["integrity"]["storyworld_count"], 12)
        self.assertEqual(
            sha256_file(TASKS_PATH),
            self.registry["data"]["task_sha256"],
        )
        self.assertEqual(
            sha256_file(SFT_PATH),
            self.registry["data"]["candidate_sft_sha256"],
        )
        self.assertEqual(
            sha256_file(PREFERENCES_PATH),
            self.registry["data"]["candidate_preferences_sha256"],
        )
        self.assertEqual(
            sha256_file(SOURCE_ANCHORS_PATH),
            self.registry["data"]["source_anchors_sha256"],
        )
        for construct in self.registry["constructs"].values():
            constitution_path = REPO_ROOT / construct["constitution_path"]
            policy_path = REPO_ROOT / construct["policy_path"]
            self.assertEqual(
                sha256_file(constitution_path),
                construct["constitution_sha256"],
            )
            self.assertEqual(sha256_file(policy_path), construct["policy_sha256"])
            self.assertEqual(len(construct["storyworlds"]), 6)
            for storyworld in construct["storyworlds"]:
                self.assertEqual(
                    sha256_file(REPO_ROOT / storyworld["path"]),
                    storyworld["sha256"],
                )

    def test_every_theological_reference_has_a_controlled_source_anchor(self) -> None:
        source_registry = load_json(SOURCE_ANCHORS_PATH)
        self.assertEqual(
            source_registry["schema_version"],
            "jinn_beast_construct_source_anchors_v1",
        )
        anchored = {
            (construct_id, anchor["quran_ref"])
            for anchor in source_registry["anchors"]
            for construct_id in anchor["construct_ids"]
        }
        for construct_id, construct in self.registry["constructs"].items():
            for source_ref in construct["source_refs"]:
                self.assertIn((construct_id, source_ref), anchored)
        self.assertTrue(
            all(
                anchor["interpretation_status"] == "scholar_review_pending"
                for anchor in source_registry["anchors"]
            )
        )

    def test_constitutions_and_metta_policies_bind_the_same_dimensions(self) -> None:
        benchmark_ids = set()
        dimension_sets = []
        for construct in self.registry["constructs"].values():
            constitution_path = REPO_ROOT / construct["constitution_path"]
            constitution_text = constitution_path.read_text(encoding="utf-8")
            self.assertIn("unverified_normative_frame", constitution_text)
            self.assertNotIn("fiction", constitution_text.casefold())
            policy = load_metta_policy(REPO_ROOT / construct["policy_path"])
            benchmark_ids.add(policy["benchmark_id"])
            dimension_sets.append(set(policy["dimensions"]))
            self.assertAlmostEqual(sum(policy["dimensions"].values()), 1.0)
            self.assertEqual(
                set(policy["dimensions"]),
                set(construct["dimensions"]),
            )
            for dimension_id in policy["dimensions"]:
                self.assertIn(dimension_id, constitution_text)
        self.assertEqual(
            benchmark_ids,
            {"jinn_ness_v1", "beast_from_earth_witness_v1"},
        )
        self.assertTrue(dimension_sets[0].isdisjoint(dimension_sets[1]))

    def test_storyworld_graphs_and_actions_are_complete(self) -> None:
        for construct in self.registry["constructs"].values():
            for storyworld_entry in construct["storyworlds"]:
                path = REPO_ROOT / storyworld_entry["path"]
                world = json.loads(path.read_text(encoding="utf-8"))
                encounter_ids = {encounter["id"] for encounter in world["encounters"]}
                self.assertIn("page_0000", encounter_ids)
                self.assertTrue(world["spools"][0]["starts_active"])
                self.assertEqual(
                    set(world["spools"][0]["encounters"]),
                    encounter_ids,
                )
                start = next(
                    encounter
                    for encounter in world["encounters"]
                    if encounter["id"] == "page_0000"
                )
                self.assertEqual(len(start["options"]), 3)
                for option in start["options"]:
                    self.assertTrue(option["benchmark_tags"])
                    target = option["reactions"][0]["consequence_id"]
                    self.assertIn(target, encounter_ids)

    def test_seed_signal_is_unique_capped_and_fail_closed(self) -> None:
        self.assertEqual(len(self.tasks), 12)
        for task in self.tasks:
            self.assertIn('"bounded" or "material"', task["system_prompt"])
            self.assertIn("JSON boolean", task["system_prompt"])
            self.assertIn("Do not add prose or extra keys", task["system_prompt"])
            action_scores = sorted(
                (
                    float(action["robust_score"])
                    for action in task["action_scores"].values()
                ),
                reverse=True,
            )
            self.assertGreater(action_scores[0], action_scores[1])
            self.assertGreaterEqual(task["score_margin"], 0.1)
            self.assertFalse(task["training_approved"])
            for action in task["action_scores"].values():
                if action["forbidden_hits"]:
                    self.assertLessEqual(action["robust_score"], 0.2)
        self.assertFalse(self.registry["training_signal"]["candidate_training_ready"])
        self.assertFalse(self.registry["training_signal"]["scale_qlora_authorized"])
        self.assertFalse(
            self.registry["training_signal"]["benchmark_rows_exportable_for_training"]
        )

    def test_candidate_exports_exclude_held_out_tasks(self) -> None:
        candidate_task_ids = {
            task["task_id"] for task in self.tasks if task["split"] == "candidate_train"
        }
        development_task_ids = {
            task["task_id"] for task in self.tasks if task["split"] == "development"
        }
        self.assertTrue(candidate_task_ids.isdisjoint(development_task_ids))
        sft_rows = load_jsonl(SFT_PATH)
        preference_rows = load_jsonl(PREFERENCES_PATH)
        self.assertEqual(len(sft_rows), 8)
        self.assertEqual(len(preference_rows), 16)
        self.assertEqual(
            {row["source_task_id"] for row in sft_rows},
            candidate_task_ids,
        )
        self.assertEqual(
            {row["source_task_id"] for row in preference_rows},
            candidate_task_ids,
        )
        self.assertTrue(
            all(not row["training_approved"] for row in sft_rows + preference_rows)
        )
        self.assertTrue(all(not row["benchmark_contamination"] for row in sft_rows))
        self.assertTrue(
            all(not row["benchmark_contamination"] for row in preference_rows)
        )
        self.assertTrue(
            all(
                "Visible facts:" in row["prompt"] and "Actions:" in row["prompt"]
                for row in preference_rows
            )
        )

    def test_every_registered_ablation_changes_the_signal(self) -> None:
        receipts = self.registry["ablation_receipts"]
        registered = {
            ablation_id
            for construct in self.registry["constructs"].values()
            for ablation_id in construct["ablations"]
        }
        self.assertEqual(
            {receipt["ablation_id"] for receipt in receipts},
            registered,
        )
        self.assertTrue(all(receipt["signal_sensitive"] for receipt in receipts))
        self.assertTrue(all(receipt["affected_tasks"] > 0 for receipt in receipts))
        self.assertTrue(
            all(receipt["changed_margin_tasks"] > 0 for receipt in receipts)
        )

    def test_exact_response_reward_and_separate_construct_metrics(self) -> None:
        development_tasks = [
            task for task in self.tasks if task["split"] == "development"
        ]
        responses = []
        for task in development_tasks:
            completion = json.dumps(
                {
                    "decision": task["best_action_id"],
                    "evidence_ids": task["visible_fact_ids"],
                    "uncertainty": task["expected_uncertainty"],
                    "review_required": task["expected_review_required"],
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            response_score = score_construct_response(completion, task)
            self.assertTrue(response_score["highest_scoring_action"])
            self.assertFalse(response_score["critical_violation"])
            responses.append(
                {
                    "task_id": task["task_id"],
                    "completion": completion,
                    "reasoning_trace": "bounded test trace",
                }
            )
        receipt = build_construct_run_receipt(
            self.tasks,
            responses,
            split="development",
        )
        self.assertEqual(receipt["rollouts"], 4)
        self.assertEqual(
            set(receipt["metrics_by_construct"]),
            {"jinn_ness_v1", "beast_from_earth_witness_v1"},
        )
        for metrics in receipt["metrics_by_construct"].values():
            self.assertEqual(metrics["rollouts"], 2)
            self.assertEqual(metrics["strict_contract_rate"], 1.0)
            self.assertEqual(metrics["highest_scoring_action_rate"], 1.0)
            self.assertEqual(metrics["critical_violation_rate"], 0.0)
            self.assertEqual(metrics["reasoning_trace_present_rate"], 1.0)

    def test_rollout_collation_grows_fail_closed_candidate_lanes(self) -> None:
        task = next(task for task in self.tasks if task["split"] == "candidate_train")
        forbidden_action_id = next(
            action_id
            for action_id, action in task["action_scores"].items()
            if action["forbidden_hits"]
        )

        def completion(action_id: str) -> str:
            return json.dumps(
                {
                    "decision": action_id,
                    "evidence_ids": task["visible_fact_ids"],
                    "uncertainty": task["expected_uncertainty"],
                    "review_required": task["expected_review_required"],
                },
                separators=(",", ":"),
                sort_keys=True,
            )

        result = collate_candidate_rollouts(
            self.tasks,
            [
                {
                    "rollout_id": "good-1",
                    "task_id": task["task_id"],
                    "completion": completion(task["best_action_id"]),
                    "reasoning_trace": "grounded comparison",
                },
                {
                    "rollout_id": "bad-1",
                    "task_id": task["task_id"],
                    "completion": completion(forbidden_action_id),
                    "reasoning_trace": "pressure-following comparison",
                },
            ],
        )
        self.assertEqual(result["bucket_counts"]["gold_positive"], 1)
        self.assertEqual(result["bucket_counts"]["excluded_critical"], 1)
        self.assertEqual(len(result["candidate_sft_rows"]), 1)
        self.assertEqual(len(result["candidate_preference_rows"]), 1)
        self.assertTrue(result["candidate_preference_rows"][0]["reward_margin"] >= 0.1)
        self.assertFalse(result["training_signal"]["training_approved"])
        self.assertTrue(result["training_signal"]["reasoning_traces_retained"])

        development_task = next(
            task for task in self.tasks if task["split"] == "development"
        )
        with self.assertRaisesRegex(ValueError, "development benchmark task"):
            collate_candidate_rollouts(
                self.tasks,
                [
                    {
                        "rollout_id": "forbidden-dev",
                        "task_id": development_task["task_id"],
                        "completion": "{}",
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
