from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_jinn_beast_construct_eval import evaluation_viewer_url, validate_model


class ConstructEvalModelValidationTests(unittest.TestCase):
    def test_accepts_registered_base_and_adapter_models(self) -> None:
        validate_model("Qwen/Qwen3.5-4B")
        validate_model("Qwen/Qwen3.5-4B:dqyfss0yuztdb35byayfu0j9")

    def test_rejects_other_or_malformed_models(self) -> None:
        invalid_models = (
            "Qwen/Qwen3.5-1.7B",
            "Qwen/Qwen3.5-4B:",
            "Qwen/Qwen3.5-4B:adapter:extra",
        )
        for model in invalid_models:
            with self.subTest(model=model), self.assertRaises(ValueError):
                validate_model(model)
        with self.assertRaises(TypeError):
            validate_model(None)

    def test_viewer_url_requires_a_hub_evaluation_id(self) -> None:
        self.assertEqual(
            evaluation_viewer_url("vqjhmqpxezrnt9lp7zutq77g"),
            "https://app.primeintellect.ai/dashboard/evaluations/"
            "vqjhmqpxezrnt9lp7zutq77g",
        )
        self.assertIsNone(evaluation_viewer_url("local_terminal_gate_job"))


if __name__ == "__main__":
    unittest.main()
