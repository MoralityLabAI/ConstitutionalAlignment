from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from typing import Any

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = (
    REPO_ROOT
    / "environments"
    / "jinn_beast_metta"
    / "jinn_beast_metta"
    / "data"
    / "moral_control_mesh_tasks.jsonl"
)
MANIFEST_PATH = DATA_PATH.with_name("moral_control_mesh_manifest.json")
SCORER_PATH = DATA_PATH.parents[1] / "mesh.py"
REGISTRATION_PATH = (
    REPO_ROOT
    / "experiments"
    / "jinn_beast_metta_rl_v1"
    / "moral_control_mesh_v1"
    / "registration.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


class MoralControlMeshRegistrationTests(unittest.TestCase):
    def test_registration_hashes_match_frozen_artifacts(self) -> None:
        registration = json.loads(REGISTRATION_PATH.read_text(encoding="utf-8"))
        environment = registration["environment"]
        self.assertEqual(environment["data_sha256"], _sha256(DATA_PATH))
        self.assertEqual(environment["manifest_sha256"], _sha256(MANIFEST_PATH))
        self.assertEqual(environment["scorer_sha256"], _sha256(SCORER_PATH))
        self.assertEqual(
            registration["status"],
            "prospective_primary_lane_frozen_before_adapter_outcomes",
        )

    def test_training_pair_is_symmetric_except_frame_and_model_size(self) -> None:
        configs: dict[tuple[str, str], dict[str, Any]] = {}
        for size in ("4b", "9b"):
            for frame in ("jinn", "beast"):
                path = (
                    REPO_ROOT
                    / "configs"
                    / "rl"
                    / f"moral_control_mesh_qwen35_{size}_{frame}.toml"
                )
                config = _load_toml(path)
                configs[(size, frame)] = config
                self.assertEqual(config["max_steps"], 12)
                self.assertEqual(config["batch_size"], 192)
                self.assertEqual(config["rollouts_per_example"], 4)
                self.assertEqual(config["max_inflight_rollouts"], 4)
                self.assertEqual(config["sampling"]["max_tokens"], 512)
                self.assertEqual(config["eval"]["sampling"]["max_tokens"], 768)
                self.assertFalse(config["sampling"]["enable_thinking"])
                self.assertEqual(config["env"][0]["version"], "0.1.11")
                self.assertEqual(config["env"][0]["args"]["frame"], frame)
                self.assertTrue(config["env"][0]["args"]["require_training_approval"])
                self.assertEqual(config["eval"]["interval"], 4)
                self.assertEqual(config["checkpoints"]["interval"], 4)

        ignored = {"name", "model", "env", "eval"}
        for size in ("4b", "9b"):
            jinn = {
                key: value
                for key, value in configs[(size, "jinn")].items()
                if key not in ignored
            }
            beast = {
                key: value
                for key, value in configs[(size, "beast")].items()
                if key not in ignored
            }
            self.assertEqual(jinn, beast)
            self.assertEqual(
                configs[(size, "jinn")]["eval"]["env"][0]["args"]["frame"],
                "jinn",
            )
            self.assertEqual(
                configs[(size, "beast")]["eval"]["env"][0]["args"]["frame"],
                "beast",
            )

    def test_cost_and_scale_gates_are_fail_closed(self) -> None:
        registration = json.loads(REGISTRATION_PATH.read_text(encoding="utf-8"))
        execution = registration["execution"]
        self.assertTrue(execution["four_b_before_nine_b"])
        self.assertEqual(execution["hard_total_cost_cap_usd"], 20.0)
        self.assertLessEqual(
            execution["four_b_stage_cap_usd"]
            + execution["nine_b_stage_cap_usd"]
            + execution["village_stage_cap_usd"],
            execution["hard_total_cost_cap_usd"],
        )
        self.assertFalse(execution["local_gpu_used"])
        self.assertEqual(execution["maximum_training_rollouts_per_pair"], 4608)
        self.assertEqual(
            execution["training_output_token_ceiling_per_pair"],
            4608 * 512,
        )
        self.assertTrue(execution["technical_preflight_informed_token_amendment"])

    def test_preflight_configs_are_small_and_nonthinking(self) -> None:
        for frame in ("jinn", "beast"):
            path = (
                REPO_ROOT
                / "configs"
                / "eval"
                / f"moral_control_mesh_qwen35_4b_base_{frame}_preflight.toml"
            )
            config = _load_toml(path)
            self.assertEqual(config["num_examples"], 4)
            self.assertEqual(config["rollouts_per_example"], 1)
            self.assertEqual(config["max_concurrent"], 2)
            self.assertEqual(config["max_tokens"], 768)
            self.assertFalse(
                config["sampling_args"]["extra_body"]["chat_template_kwargs"][
                    "enable_thinking"
                ]
            )
            self.assertEqual(config["eval"][0]["env_args"]["frame"], frame)

    def test_base_confirmatory_configs_cover_the_exact_surface(self) -> None:
        for frame in ("jinn", "beast"):
            path = (
                REPO_ROOT
                / "configs"
                / "eval"
                / f"moral_control_mesh_qwen35_4b_base_{frame}_confirmatory.toml"
            )
            config = _load_toml(path)
            self.assertEqual(config["model"], "Qwen/Qwen3.5-4B")
            self.assertEqual(config["num_examples"], 48)
            self.assertEqual(config["rollouts_per_example"], 4)
            self.assertEqual(config["max_tokens"], 768)
            self.assertEqual(config["timeout"], 30)
            self.assertEqual(config["max_retries"], 1)
            self.assertFalse(
                config["sampling_args"]["extra_body"]["chat_template_kwargs"][
                    "enable_thinking"
                ]
            )
            self.assertEqual(
                config["eval"][0]["env_args"],
                {
                    "split": "confirmatory",
                    "frame": frame,
                    "task_mode": "moral_control_mesh",
                    "require_training_approval": True,
                },
            )

    def test_adapter_confirmatory_configs_match_terminal_four_b_pair(self) -> None:
        adapter_ids = {
            "jinn": "s4geh2z9wobmvu7jbxi4vcuw",
            "beast": "twa9vqad5lw9gi4ffkstxioo",
        }
        for frame, adapter_id in adapter_ids.items():
            path = (
                REPO_ROOT
                / "configs"
                / "eval"
                / f"moral_control_mesh_qwen35_4b_{frame}_adapter_confirmatory.toml"
            )
            config = _load_toml(path)
            self.assertEqual(
                config["model"],
                f"Qwen/Qwen3.5-4B:{adapter_id}",
            )
            self.assertEqual(config["num_examples"], 48)
            self.assertEqual(config["rollouts_per_example"], 4)
            self.assertEqual(config["timeout"], 30)
            self.assertEqual(config["max_retries"], 1)
            self.assertEqual(config["eval"][0]["env_args"]["frame"], frame)
            self.assertEqual(
                config["eval"][0]["env_args"]["split"],
                "confirmatory",
            )


if __name__ == "__main__":
    unittest.main()
