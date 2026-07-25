from __future__ import annotations

import asyncio
import sys
import types
import unittest

if sys.platform == "win32":
    fcntl = types.ModuleType("fcntl")
    fcntl.LOCK_EX = 2
    fcntl.LOCK_UN = 8
    fcntl.LOCK_NB = 4
    fcntl.flock = lambda *args: None
    sys.modules["fcntl"] = fcntl

import verifiers as vf
from verifiers.types import flatten_task_input


class LegacyEnvironmentTests(unittest.TestCase):
    def test_hosted_eval_loader_and_reward(self) -> None:
        env = vf.load_environment(
            env_id="jinn-beast-metta",
            split="development",
            frame="balanced",
            require_training_approval=True,
        )
        dataset = env.get_eval_dataset()
        self.assertEqual(len(dataset), 240)

        row = dataset[0]
        self.assertEqual(
            set(row),
            {"prompt", "answer", "example_id", "info"},
        )
        transported_task = flatten_task_input(row)
        self.assertIn("task_payload", transported_task)
        state = {
            "prompt": transported_task["prompt"],
            "completion": [{"role": "assistant", "content": row["answer"]}],
            "answer": transported_task["answer"],
            "input": transported_task,
            "task": transported_task,
            "info": transported_task["info"],
            "trajectory": [],
        }
        asyncio.run(env.rubric.score_rollout(state))
        self.assertGreater(state["reward"], 0.8)
        self.assertEqual(state["metrics"]["contract_valid"], 1.0)
        self.assertEqual(state["metrics"]["legal_action"], 1.0)
        self.assertEqual(state["metrics"]["critical_violation"], 0.0)

    def test_candidate_training_remains_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "fail-closed"):
            vf.load_environment(
                env_id="jinn-beast-metta",
                split="candidate_train",
                frame="balanced",
                require_training_approval=True,
            )

    def test_dual_construct_loader_preserves_dimension_metrics(self) -> None:
        env = vf.load_environment(
            env_id="jinn-beast-metta",
            split="development",
            task_mode="constructs",
            construct="balanced",
            require_training_approval=True,
        )
        dataset = env.get_eval_dataset()
        self.assertEqual(len(dataset), 4)
        self.assertEqual(
            {row["info"]["task"]["info"]["construct_id"] for row in dataset},
            {"jinn_ness_v1", "beast_from_earth_witness_v1"},
        )

        row = dataset[0]
        transported_task = flatten_task_input(row)
        user_prompt = transported_task["prompt"][-1]["content"]
        self.assertIn("Visible facts:", user_prompt)
        self.assertIn("Actions:", user_prompt)
        state = {
            "prompt": transported_task["prompt"],
            "completion": [{"role": "assistant", "content": row["answer"]}],
            "answer": transported_task["answer"],
            "input": transported_task,
            "task": transported_task,
            "info": transported_task["info"],
            "trajectory": [],
        }
        asyncio.run(env.rubric.score_rollout(state))
        self.assertGreater(state["reward"], 0.8)
        self.assertEqual(state["metrics"]["highest_scoring_action"], 1.0)
        self.assertEqual(state["metrics"]["evidence_grounding"], 1.0)
        dimension_metric_names = {
            "accountable_choice",
            "entrusted_stewardship",
            "truth_under_concealment",
            "evidence_bounded_reason",
            "justice_without_scapegoat",
            "repair_preservation",
            "grounded_witness",
            "public_legibility",
            "courage_under_pressure",
            "proportionate_exposure",
            "evidence_over_spectacle",
            "repair_after_testimony",
        }
        self.assertTrue(dimension_metric_names.intersection(state["metrics"]))

    def test_construct_candidate_training_remains_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "fail-closed"):
            vf.load_environment(
                env_id="jinn-beast-metta",
                split="candidate_train",
                task_mode="constructs",
                construct="balanced",
                require_training_approval=True,
            )

    def test_jinn_moral_reasoner_loader_preserves_pair_metadata(self) -> None:
        env = vf.load_environment(
            env_id="jinn-beast-metta",
            split="development",
            task_mode="jinn_moral_reasoner",
            require_training_approval=True,
        )
        dataset = env.get_eval_dataset()
        self.assertEqual(len(dataset), 16)
        info = dataset[0]["info"]["task"]["info"]
        self.assertEqual(info["construct_id"], "jinn_moral_reasoner_v2")
        self.assertIn("equivalence_pair_id", info)
        self.assertIn("change_pair_id", info)
        self.assertIn("target_action_id", info)

        row = dataset[0]
        transported_task = flatten_task_input(row)
        state = {
            "prompt": transported_task["prompt"],
            "completion": [{"role": "assistant", "content": row["answer"]}],
            "answer": transported_task["answer"],
            "input": transported_task,
            "task": transported_task,
            "info": transported_task["info"],
            "trajectory": [],
        }
        asyncio.run(env.rubric.score_rollout(state))
        self.assertGreaterEqual(state["reward"], 0.85)
        self.assertEqual(state["metrics"]["highest_scoring_action"], 1.0)
        self.assertEqual(state["metrics"]["critical_violation"], 0.0)

    def test_jinn_moral_reasoner_candidate_training_is_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "fail-closed"):
            vf.load_environment(
                env_id="jinn-beast-metta",
                split="candidate_train",
                task_mode="jinn_moral_reasoner",
                require_training_approval=True,
            )


if __name__ == "__main__":
    unittest.main()
