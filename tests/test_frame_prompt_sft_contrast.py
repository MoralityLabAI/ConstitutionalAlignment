from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_frame_prompt_sft_contrast import DEFAULT_CONTRACT, validate_contract


REPO_ROOT = Path(__file__).resolve().parent.parent
V2_CONTRACT = (
    REPO_ROOT
    / "experiments/frame_internalization_sft_v1/prompt_sft_contrast_v2.json"
)


class FramePromptSftContrastTests(unittest.TestCase):
    def test_frozen_contract_passes(self) -> None:
        report = validate_contract(REPO_ROOT, DEFAULT_CONTRACT)
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["confirmatory_contrast_count"], 6)
        self.assertEqual(report["secondary_contrast_count"], 9)
        self.assertEqual(
            report["rendered_prompts"]["F3_concrete"]["sha256"],
            "93c0c787b0b3ea073d25776718e9ce4051453d97904fd039fbb3f4dcf8994ae4",
        )

    def test_prompt_hash_mutation_fails_closed(self) -> None:
        contract = json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))
        contract["system_prompt_construction"]["prompts"]["F3"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mutated_contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            report = validate_contract(REPO_ROOT, path)
        self.assertFalse(report["passed"])
        self.assertIn("F3 composed prompt hash drift", report["failures"])

    def test_timing_mutation_fails_closed(self) -> None:
        contract = json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))
        contract["timing_attestation"]["adapter_outcomes_seen_before_freeze"] = True
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mutated_contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            report = validate_contract(REPO_ROOT, path)
        self.assertFalse(report["passed"])
        self.assertIn("timing attestation is incomplete or not prospective", report["failures"])

    def test_licensed_v2_contract_passes(self) -> None:
        report = validate_contract(REPO_ROOT, V2_CONTRACT)
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["confirmatory_contrast_count"], 6)
        contract = json.loads(V2_CONTRACT.read_text(encoding="utf-8"))
        self.assertIsNone(
            contract["evaluation"]["prospective_v2_baseline"]["magnitude_acceptance_interval"]
        )
        self.assertTrue(
            contract["analysis_gate"]["historical_v1_interval_as_v2_pass_fail_forbidden"]
        )

    def test_v2_historical_interval_reactivation_fails_closed(self) -> None:
        contract = json.loads(V2_CONTRACT.read_text(encoding="utf-8"))
        contract["analysis_gate"]["historical_v1_interval_as_v2_pass_fail_forbidden"] = False
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mutated_v2_contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            report = validate_contract(REPO_ROOT, path)
        self.assertFalse(report["passed"])
        self.assertIn(
            "v2 contract does not forbid the historical interval as a pass/fail target",
            report["failures"],
        )


if __name__ == "__main__":
    unittest.main()
