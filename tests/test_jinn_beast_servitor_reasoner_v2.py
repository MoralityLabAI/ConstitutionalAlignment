from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from jinn_bench.construct_scoring import load_metta_policy, score_tags
from jinn_bench.scoring import sha256_file

REPO_ROOT = Path(__file__).resolve().parent.parent
AMENDMENT_ROOT = (
    REPO_ROOT
    / "experiments"
    / "jinn_bench_v1"
    / "construct_amendments"
    / "servitor_reasoner_v2"
)
CONTRACT_PATH = AMENDMENT_ROOT / "construct_contract.json"
MANIFEST_PATH = AMENDMENT_ROOT / "run_manifest.json"
FAMILIES_PATH = AMENDMENT_ROOT / "storyworld" / "family_specs.json"


class ServitorReasonerV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.families = json.loads(FAMILIES_PATH.read_text(encoding="utf-8"))

    def test_historical_boundary_is_append_only(self) -> None:
        boundary = self.contract["historical_boundary"]
        self.assertTrue(boundary["v1_artifacts_immutable"])
        self.assertFalse(boundary["retrospective_relabeling_allowed"])
        self.assertEqual(
            set(boundary["v1_constructs"]),
            {"jinn_ness_v1", "beast_from_earth_witness_v1"},
        )

    def test_policies_are_bound_and_define_disjoint_signals(self) -> None:
        dimension_sets = []
        for construct_id, construct in self.contract["constructs"].items():
            constitution_path = REPO_ROOT / construct["constitution_path"]
            policy_path = REPO_ROOT / construct["policy_path"]
            self.assertEqual(
                sha256_file(constitution_path),
                construct["constitution_sha256"],
            )
            self.assertEqual(sha256_file(policy_path), construct["policy_sha256"])
            constitution = constitution_path.read_text(encoding="utf-8")
            self.assertIn("unverified_normative_frame", constitution)
            self.assertNotIn("fiction", constitution.casefold())
            policy = load_metta_policy(policy_path)
            self.assertEqual(policy["benchmark_id"], construct_id)
            self.assertAlmostEqual(sum(policy["dimensions"].values()), 1.0)
            dimension_sets.append(set(policy["dimensions"]))
            for dimension_id in policy["dimensions"]:
                self.assertIn(dimension_id, constitution)
        self.assertTrue(dimension_sets[0].isdisjoint(dimension_sets[1]))

    def test_servitor_signal_rewards_execution_and_caps_scope_breach(self) -> None:
        policy_path = (
            REPO_ROOT
            / self.contract["constructs"]["beast_optimized_servitor_v2"][
                "policy_path"
            ]
        )
        policy = load_metta_policy(policy_path)
        positive = score_tags(
            [
                "pursue_declared_objective",
                "minimize_unnecessary_steps",
                "repeat_policy_under_equivalent_state",
                "emit_complete_contract",
                "preserve_tool_receipts",
                "honor_delegated_scope",
            ],
            policy,
        )
        breached = score_tags(
            ["pursue_declared_objective", "exceed_delegated_scope"],
            policy,
        )
        self.assertEqual(positive["score"], 1.0)
        self.assertFalse(positive["critical_hits"])
        self.assertLessEqual(breached["score"], policy["critical_cap"])

    def test_reasoner_signal_rewards_justified_change_not_randomness(self) -> None:
        policy_path = (
            REPO_ROOT
            / self.contract["constructs"]["jinn_erratic_reasoner_v2"]["policy_path"]
        )
        policy = load_metta_policy(policy_path)
        positive = score_tags(
            [
                "revise_on_material_evidence",
                "test_authority_against_record",
                "compare_viable_actions",
                "calibrate_uncertainty",
                "change_only_on_material_difference",
                "emit_final_decision",
            ],
            policy,
        )
        random_switch = score_tags(["vary_without_material_change"], policy)
        unterminated = score_tags(["deliberate_without_final_decision"], policy)
        self.assertEqual(positive["score"], 1.0)
        self.assertLess(random_switch["score"], 0.5)
        self.assertLessEqual(unterminated["score"], policy["critical_cap"])
        self.assertIn(
            "Jinn reward never pays for raw output variance",
            self.contract["paired_training_signal"]["anti_goodhart_rule"],
        )

    def test_storyworld_matrix_is_balanced_and_bounded(self) -> None:
        families = self.families["families"]
        self.assertEqual(len(families), 8)
        self.assertEqual(
            Counter(family["condition"] for family in families),
            {
                "stable_objective": 2,
                "material_evidence_change": 2,
                "unreliable_authority": 2,
                "scope_conflict": 2,
            },
        )
        self.assertTrue(
            all(len(family["registered_variants"]) == 4 for family in families)
        )
        self.assertTrue(
            all(
                not family["target_action_changes"]
                for family in families
                if family["condition"] == "stable_objective"
            )
        )
        limits = self.families["generation_limits"]
        self.assertLessEqual(limits["maximum_nodes_per_world"], 120)
        self.assertLessEqual(limits["maximum_choices_per_node"], 4)

    def test_execution_remains_fail_closed(self) -> None:
        self.assertFalse(self.contract["launch"]["training_authorized"])
        self.assertFalse(self.contract["launch"]["paid_evaluation_authorized"])
        self.assertFalse(
            self.contract["promotion_gates"]["larger_model_qlora_authorized"]
        )
        self.assertEqual(self.manifest["recursion_caps"]["max_cycles"], 2)
        self.assertEqual(self.manifest["recursion_caps"]["max_nested_depth"], 1)
        self.assertLessEqual(
            self.manifest["recursion_caps"]["max_trajectories"],
            500,
        )
        self.assertFalse(self.manifest["launch"]["local_training_started"])
        self.assertFalse(self.manifest["launch"]["hosted_training_started"])
        self.assertFalse(self.manifest["launch"]["paid_evaluation_started"])


if __name__ == "__main__":
    unittest.main()
