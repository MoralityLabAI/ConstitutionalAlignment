from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from typing import Any

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = (
    REPO_ROOT
    / "environments"
    / "jinn_beast_metta"
    / "jinn_beast_metta"
    / "data"
)
EXPERIMENT_ROOT = (
    REPO_ROOT
    / "experiments"
    / "jinn_beast_metta_rl_v1"
    / "moral_control_mesh_v2"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


class MoralControlMeshV2RegistrationTests(unittest.TestCase):
    def test_registration_is_prospective_and_hash_bound(self) -> None:
        registration = json.loads(
            (EXPERIMENT_ROOT / "registration.json").read_text(encoding="utf-8")
        )
        environment = registration["environment"]
        self.assertEqual(
            registration["status"],
            "prospective_before_any_v2_model_rollout",
        )
        self.assertEqual(environment["version"], "0.1.12")
        self.assertEqual(
            environment["data_sha256"],
            sha256(DATA_ROOT / "moral_control_mesh_v2_tasks.jsonl"),
        )
        self.assertEqual(
            environment["manifest_sha256"],
            sha256(DATA_ROOT / "moral_control_mesh_v2_manifest.json"),
        )
        self.assertEqual(
            environment["scorer_sha256"],
            sha256(DATA_ROOT.parent / "mesh_v2.py"),
        )

    def test_process_evidence_is_executed_not_self_reported(self) -> None:
        registration = json.loads(
            (EXPERIMENT_ROOT / "registration.json").read_text(encoding="utf-8")
        )
        intervention = registration["intervention"]
        self.assertEqual(
            intervention["process_evidence"],
            "executed_environment_transition_trace",
        )
        self.assertFalse(intervention["self_reported_reasoning_is_primary"])
        self.assertTrue(intervention["same_base_weights_across_frames"])

    def test_spend_and_promotion_are_fail_closed(self) -> None:
        registration = json.loads(
            (EXPERIMENT_ROOT / "registration.json").read_text(encoding="utf-8")
        )
        execution = registration["execution"]
        self.assertEqual(execution["hard_total_new_spend_cap_usd"], 12.0)
        self.assertTrue(execution["hosted_training_only"])
        self.assertFalse(execution["local_model_or_gpu_training"])
        self.assertTrue(execution["nine_b_requires_four_b_confirmatory_pass"])
        self.assertEqual(
            execution["four_b_development_cap_usd"]
            + execution["four_b_confirmatory_cap_usd"]
            + execution["conditional_nine_b_cap_usd"]
            + execution["qualitative_village_cap_usd"],
            execution["hard_total_new_spend_cap_usd"],
        )

    def test_preflights_are_tiny_and_save_executed_trace(self) -> None:
        for frame in ("jinn", "beast"):
            config = load_toml(
                REPO_ROOT
                / "configs"
                / "eval"
                / f"moral_control_mesh_v2_qwen35_4b_base_{frame}_preflight.toml"
            )
            self.assertEqual(config["num_examples"], 2)
            self.assertEqual(config["rollouts_per_example"], 1)
            self.assertEqual(config["max_concurrent"], 1)
            self.assertEqual(config["max_tokens"], 256)
            self.assertEqual(
                config["state_columns"],
                ["mesh_trace", "mesh_receipt"],
            )
            self.assertEqual(config["timeout"], 90)
            self.assertEqual(config["max_retries"], 1)
            self.assertEqual(
                config["eval"][0]["env_args"]["task_mode"],
                "moral_control_mesh_v2",
            )
            self.assertEqual(config["eval"][0]["env_args"]["frame"], frame)

    def test_training_pair_is_symmetric_and_capped(self) -> None:
        configs = {
            frame: load_toml(
                REPO_ROOT
                / "configs"
                / "rl"
                / f"moral_control_mesh_v2_qwen35_4b_{frame}.toml"
            )
            for frame in ("jinn", "beast")
        }
        for frame, config in configs.items():
            self.assertEqual(config["max_steps"], 8)
            self.assertEqual(config["batch_size"], 96)
            self.assertEqual(config["rollouts_per_example"], 2)
            self.assertEqual(config["max_inflight_rollouts"], 4)
            self.assertEqual(config["sampling"]["max_tokens"], 256)
            self.assertFalse(config["sampling"]["enable_thinking"])
            self.assertEqual(config["env"][0]["version"], "0.1.12")
            self.assertEqual(config["env"][0]["args"]["frame"], frame)
            self.assertEqual(
                config["env"][0]["args"]["task_mode"],
                "moral_control_mesh_v2",
            )
            self.assertEqual(config["checkpoints"]["interval"], 4)

        ignored = {"name", "env", "eval"}
        jinn = {
            key: value
            for key, value in configs["jinn"].items()
            if key not in ignored
        }
        beast = {
            key: value
            for key, value in configs["beast"].items()
            if key not in ignored
        }
        self.assertEqual(jinn, beast)


if __name__ == "__main__":
    unittest.main()
