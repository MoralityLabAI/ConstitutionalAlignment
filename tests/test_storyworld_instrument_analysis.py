from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from alignment_harness.dataset import source_split_metadata
from scripts.analyze_constitutional_storyworld_evals import analyze
from run_constitution_storyworld import load_prompts


class StoryworldRunnerMetadataTests(unittest.TestCase):
    def test_v2_prompt_metadata_survives_loading(self) -> None:
        path = (
            REPO_ROOT
            / "data"
            / "storyworld_sources"
            / "constitutional_alignment_20260715_v2"
            / "evaluation"
            / "unwatched_ledger_ca_eval_v1.encounter_prompts.jsonl"
        )
        prompt = load_prompts([str(path)], max_prompts=1)[0]

        self.assertEqual(prompt.instrument_condition, "audited")
        self.assertEqual(prompt.instrument_metadata["condition_token_count"], 19)
        self.assertEqual(prompt.review_requirements, {"scholar": True})
        self.assertEqual(prompt.source_familiarity_risk, "low_original_fiction")
        self.assertEqual(len(prompt.option_order), 3)
        self.assertFalse(prompt.training_eligible)

    def test_condition_metadata_survives_conditioning_metadata_projection(self) -> None:
        row = {
            "instrument_condition": "default",
            "instrument_metadata": {"instrument_id": "common_well_ca_dev_v1"},
            "review_requirements": {"scholar": True},
            "source_familiarity_risk": "low_original_fiction",
            "option_order": ["a", "b", "c"],
        }
        metadata = source_split_metadata(row)

        self.assertEqual(metadata["instrument_condition"], "default")
        self.assertEqual(metadata["review_requirements"], {"scholar": True})
        self.assertEqual(metadata["option_order"], ["a", "b", "c"])


class StoryworldInstrumentAnalysisTests(unittest.TestCase):
    @staticmethod
    def _rows() -> list[dict]:
        rows = []
        for scenario_index, scenario in enumerate(("scene_one", "scene_two")):
            options = [f"{scenario}_a", f"{scenario}_b", f"{scenario}_c"]
            for condition in ("audited", "sealed"):
                for permutation in range(3):
                    order = options[permutation:] + options[:permutation]
                    if scenario_index == 0:
                        choice = options[0] if condition == "audited" else options[1]
                    else:
                        choice = options[0]
                    rows.append(
                        {
                            "constitution_id": "fixture_constitution",
                            "source_storyworld_slug": "unwatched_ledger_ca_eval_v1",
                            "source_split": "evaluation",
                            "training_eligible": False,
                            "adjudication_status": "pending",
                            "review_requirements": {"scholar": True},
                            "source_familiarity_risk": "low_original_fiction",
                            "instrument_condition": condition,
                            "scenario_group_id": f"unwatched__{scenario}",
                            "option_permutation": permutation,
                            "option_order": order,
                            "chosen_option_id": choice,
                        }
                    )
        return rows

    def test_paired_switch_rate_is_clustered_and_deterministic(self) -> None:
        first = analyze(self._rows(), bootstrap_samples=1_000, seed=17)
        second = analyze(self._rows(), bootstrap_samples=1_000, seed=17)
        report = first["unwatched_ledger"]["constitutions"]["fixture_constitution"]

        self.assertEqual(first, second)
        self.assertEqual(report["scenario_groups"], 2)
        self.assertEqual(report["complete_condition_pairs"], 6)
        self.assertEqual(report["valid_pairs_for_primary_estimand"], 6)
        self.assertEqual(
            report["primary_condition_induced_decision_switch_rate"]["estimate"],
            0.5,
        )
        self.assertFalse(first["publication_gates"]["normative_claims_allowed"])
        self.assertFalse(first["publication_gates"]["heuristic_compliance_metrics_reported"])

    def test_incomplete_condition_matrix_is_rejected(self) -> None:
        rows = self._rows()
        rows.pop()
        with self.assertRaisesRegex(ValueError, "expected permutations"):
            analyze(rows, bootstrap_samples=100, seed=1)

    def test_cli_fixture_can_be_serialized_as_runner_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "generations.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in self._rows()),
                encoding="utf-8",
            )
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 12)


if __name__ == "__main__":
    unittest.main()
