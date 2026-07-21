from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from alignment_harness.constitutional_hrm import (
    DECISION_A_ID,
    DECISION_B_ID,
    OFFICIAL_HRM_COMMIT,
    SEQ_LEN,
    TENET_IDS,
    Scenario,
    build_arm_dataset,
    choose_option,
    load_constitution_policy,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


class ConstitutionalHrmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_constitution_policy(REPO_ROOT / "constitution.md")

    def test_policy_is_bound_to_canonical_constitution(self) -> None:
        self.assertEqual(self.policy.constitution_id, "islamic_moral_tenets_v1")
        self.assertEqual(self.policy.tenet_weights, (4, 4, 4, 2, 2, 2))
        self.assertEqual(len(self.policy.sha256), 64)
        self.assertEqual(TENET_IDS, ("adl", "aql", "sidq", "ihsan", "amanah", "rahmah"))

    def test_swap_flips_each_non_tied_policy_decision(self) -> None:
        scenario = Scenario(
            group_id="swap",
            family="test",
            option_a_scores=(4, 4, 4, 2, 2, 2),
            option_a_prohibitions=(0, 0, 0, 0, 0),
            option_b_scores=(1, 1, 1, 4, 4, 4),
            option_b_prohibitions=(0, 0, 0, 0, 0),
        )
        for arm in ("constitutional", "utility"):
            original = choose_option(scenario, self.policy, arm)
            swapped = choose_option(scenario.swapped(), self.policy, arm)
            self.assertEqual({original, swapped}, {DECISION_A_ID, DECISION_B_ID})

    def test_dataset_matches_official_contract_and_has_disjoint_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "constitutional"
            manifest = build_arm_dataset(
                output_dir=root,
                constitution_path=REPO_ROOT / "constitution.md",
                arm="constitutional",
                train_groups=8,
                id_groups=4,
                ood_groups=4,
            )
            metadata = json.loads((root / "train" / "dataset.json").read_text())
            inputs = np.load(root / "train" / "all__inputs.npy")
            labels = np.load(root / "train" / "all__labels.npy")
            train_rows = [json.loads(line) for line in (root / "audit" / "train.jsonl").read_text().splitlines()]
            test_rows = [json.loads(line) for line in (root / "audit" / "test.jsonl").read_text().splitlines()]

            self.assertEqual(metadata["seq_len"], SEQ_LEN)
            self.assertEqual(metadata["sets"], ["all"])
            self.assertEqual(inputs.shape, labels.shape)
            self.assertTrue(np.all(labels[:, 1:] == 0))
            self.assertEqual(manifest["official_hrm"]["commit"], OFFICIAL_HRM_COMMIT)
            self.assertEqual(manifest["label_balance"]["train_a"], manifest["label_balance"]["train_b"])
            self.assertFalse(
                {row["group_id"] for row in train_rows}.intersection(
                    row["group_id"] for row in test_rows
                )
            )

    def test_arms_share_inputs_but_not_training_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            roots = {}
            for arm in ("constitutional", "utility", "shuffled"):
                root = Path(temporary) / arm
                build_arm_dataset(
                    output_dir=root,
                    constitution_path=REPO_ROOT / "constitution.md",
                    arm=arm,
                    train_groups=16,
                    id_groups=8,
                    ood_groups=8,
                )
                roots[arm] = root

            constitutional_inputs = np.load(roots["constitutional"] / "train" / "all__inputs.npy")
            constitutional_labels = np.load(roots["constitutional"] / "train" / "all__labels.npy")
            constitutional_test = np.load(roots["constitutional"] / "test" / "contrast__labels.npy")
            for arm in ("utility", "shuffled"):
                self.assertTrue(
                    np.array_equal(
                        constitutional_inputs,
                        np.load(roots[arm] / "train" / "all__inputs.npy"),
                    )
                )
                self.assertFalse(
                    np.array_equal(
                        constitutional_labels,
                        np.load(roots[arm] / "train" / "all__labels.npy"),
                    )
                )
                self.assertTrue(
                    np.array_equal(
                        constitutional_test,
                        np.load(roots[arm] / "test" / "contrast__labels.npy"),
                    )
                )

    def test_contrast_slice_contains_only_policy_disagreements(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "constitutional"
            manifest = build_arm_dataset(
                output_dir=root,
                constitution_path=REPO_ROOT / "constitution.md",
                arm="constitutional",
                train_groups=8,
                id_groups=8,
                ood_groups=8,
            )
            test_rows = [json.loads(line) for line in (root / "audit" / "test.jsonl").read_text().splitlines()]
            disagreements = sum(
                row["constitutional_label"] != row["utility_label"] for row in test_rows
            )
            self.assertEqual(disagreements, manifest["counts"]["contrast"])
            self.assertGreater(disagreements, 0)


if __name__ == "__main__":
    unittest.main()
