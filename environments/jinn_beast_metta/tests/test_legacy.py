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

import verifiers as vf  # noqa: E402
from verifiers.types import flatten_task_input  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
