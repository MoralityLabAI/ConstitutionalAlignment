from __future__ import annotations

import hashlib
import json
import sys
import unittest
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_ROOT = REPO_ROOT / "environments/jinn_beast_metta"
sys.path.insert(0, str(ENV_ROOT))

from jinn_beast_metta.core import score_construct_response
from jinn_beast_metta.selectors import select_jinn_moral_reasoner_rows

DATA_PATH = (
    ENV_ROOT / "jinn_beast_metta/data/jinn_moral_reasoner_tasks.jsonl"
)
MANIFEST_PATH = (
    ENV_ROOT / "jinn_beast_metta/data/jinn_moral_reasoner_manifest.json"
)
REGISTRY_PATH = REPO_ROOT / "jinn_bench/data/jinn_moral_reasoner_registry_v2.json"
VILLAGE_PATH = (
    REPO_ROOT
    / "experiments/jinn_bench_v1/quranic_moral_village_v1/storyworld/village.json"
)


def load_rows() -> list[dict]:
    return [
        json.loads(line)
        for line in DATA_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def completion(task: dict, action_id: str) -> str:
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


class JinnMoralReasonerV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_rows()
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_manifest_binds_balanced_disjoint_task_families(self) -> None:
        self.assertEqual(len(self.rows), 32)
        self.assertEqual(self.manifest["environment_version"], "0.1.9")
        self.assertEqual(
            self.manifest["split_counts"],
            {"candidate_train": 16, "development": 16},
        )
        self.assertEqual(
            self.manifest["split_family_counts"],
            {"candidate_train": 4, "development": 4},
        )
        self.assertEqual(
            hashlib.sha256(DATA_PATH.read_bytes()).hexdigest(),
            self.manifest["data_sha256"],
        )
        candidate_families = {
            row["family_id"]
            for row in self.rows
            if row["split"] == "candidate_train"
        }
        development_families = {
            row["family_id"]
            for row in self.rows
            if row["split"] == "development"
        }
        self.assertTrue(candidate_families.isdisjoint(development_families))

    def test_pair_contract_rewards_invariance_and_material_change(self) -> None:
        by_equivalence: dict[str, list[dict]] = defaultdict(list)
        by_change: dict[str, list[dict]] = defaultdict(list)
        for row in self.rows:
            by_equivalence[row["equivalence_pair_id"]].append(row)
            by_change[row["change_pair_id"]].append(row)
        self.assertEqual(len(by_equivalence), 16)
        self.assertEqual(len(by_change), 8)
        for rows in by_equivalence.values():
            self.assertEqual(len(rows), 2)
            self.assertEqual(len({row["target_action_id"] for row in rows}), 1)
            self.assertEqual(len({row["state_role"] for row in rows}), 1)
        for rows in by_change.values():
            self.assertEqual(len(rows), 4)
            baseline = {
                row["target_action_id"]
                for row in rows
                if row["state_role"] == "baseline"
            }
            changed = {
                row["target_action_id"]
                for row in rows
                if row["state_role"] == "material_change"
            }
            self.assertEqual(len(baseline), 1)
            self.assertEqual(len(changed), 1)
            self.assertNotEqual(baseline, changed)

    def test_action_dominant_reward_and_critical_cap_are_effective(self) -> None:
        for task in self.rows:
            profile = task["reward_profile"]
            self.assertEqual(profile["weights"]["action"], 0.75)
            self.assertEqual(profile["critical_violation_cap"], 0.2)
            best = score_construct_response(
                completion(task, task["target_action_id"]),
                task,
            )
            self.assertTrue(best["highest_scoring_action"])
            self.assertFalse(best["critical_violation"])
            self.assertGreaterEqual(best["final_score"], 0.85)
            critical_action_id = next(
                action_id
                for action_id, action in task["action_scores"].items()
                if action["forbidden_hits"]
            )
            critical = score_construct_response(
                completion(task, critical_action_id),
                task,
            )
            self.assertTrue(critical["critical_violation"])
            self.assertEqual(critical["final_score"], 0.2)
            self.assertGreaterEqual(
                round(best["final_score"] - critical["final_score"], 6),
                0.65,
            )

    def test_candidate_selector_is_fail_closed_but_owner_override_is_explicit(self) -> None:
        with self.assertRaisesRegex(ValueError, "fail-closed"):
            select_jinn_moral_reasoner_rows(
                split="candidate_train",
                require_training_approval=True,
            )
        rows = select_jinn_moral_reasoner_rows(
            split="candidate_train",
            require_training_approval=False,
        )
        self.assertEqual(len(rows), 16)
        self.assertTrue(all(not row["training_approved"] for row in rows))

    def test_exact_village_remains_outside_training_data(self) -> None:
        village_hash = hashlib.sha256(VILLAGE_PATH.read_bytes()).hexdigest()
        self.assertEqual(
            self.registry["held_out_boundary"]["exact_village_sha256"],
            village_hash,
        )
        self.assertEqual(
            self.registry["held_out_boundary"]["exact_village_rows_used_for_training"],
            0,
        )
        village_text = VILLAGE_PATH.read_text(encoding="utf-8")
        candidate_text = "\n".join(
            json.dumps(row, sort_keys=True)
            for row in self.rows
            if row["split"] == "candidate_train"
        )
        self.assertNotEqual(candidate_text, village_text)


if __name__ == "__main__":
    unittest.main()
