from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from alignment_harness.mizan_rooms import (
    CONDITION_IDS,
    ScriptedPolicy,
    bundle_rows,
    canonical_json,
    paired_generation_seed,
    parse_action_response,
    rotate_actions,
    run_experiment,
    sha256_bytes,
    sha256_file,
    validate_package,
)
from scripts.analyze_mizan_rooms import analyze, read_jsonl


REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_PATH = REPO_ROOT / "experiments" / "mizan_rooms_v1" / "suite.json"


class MizanRoomsTests(unittest.TestCase):
    def test_package_schema_split_and_token_audits_pass(self) -> None:
        receipt = validate_package(REPO_ROOT, SUITE_PATH)

        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["room_variants"], 8)
        self.assertEqual(receipt["constructs_per_split"], 4)
        self.assertTrue(receipt["condition_token_audit"]["passed"])
        launch = json.loads(
            (REPO_ROOT / "experiments" / "mizan_rooms_v1" / "launch_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            launch["analysis_plan_sha256"],
            sha256_file(REPO_ROOT / "papers" / "mizan_rooms_preanalysis_v1.md"),
        )

    def test_cyclic_action_order_and_paired_seeds(self) -> None:
        actions = [{"action_id": value} for value in ("a", "b", "c")]
        first_positions = [rotate_actions(actions, replicate, 0)[0]["action_id"] for replicate in range(3)]

        self.assertEqual(first_positions, ["a", "b", "c"])
        self.assertEqual(
            paired_generation_seed(11, "room", 2, "turn"),
            paired_generation_seed(11, "room", 2, "turn"),
        )
        self.assertNotEqual(
            paired_generation_seed(11, "room", 2, "turn"),
            paired_generation_seed(23, "room", 2, "turn"),
        )

    def test_response_contract_is_strict(self) -> None:
        accepted = parse_action_response(
            '{"action_id":"keep_record","public_reason":"Preserve the record."}',
            {"keep_record"},
            80,
        )
        extra_key = parse_action_response(
            '{"action_id":"keep_record","public_reason":"Why","extra":true}',
            {"keep_record"},
            80,
        )
        fenced = parse_action_response(
            '```json\n{"action_id":"keep_record","public_reason":"Why"}\n```',
            {"keep_record"},
            80,
        )

        self.assertTrue(accepted["valid"])
        self.assertEqual(extra_key["error"], "response_keys_mismatch")
        self.assertTrue(fenced["error"].startswith("invalid_json:"))

    def test_resumable_five_condition_smoke_and_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            all_episodes: list[dict[str, object]] = []
            for condition in CONDITION_IDS:
                output_dir = root / condition
                manifest = run_experiment(
                    repo_root=REPO_ROOT,
                    suite_path=SUITE_PATH,
                    output_dir=output_dir,
                    policy=ScriptedPolicy(strategy="first"),
                    condition_id=condition,
                    source_split="development",
                    seed=11,
                    replicates=3,
                    blinding_seed=20260716,
                )
                self.assertEqual(manifest["episodes"], 12)
                self.assertEqual(manifest["turn_rows"], 60)
                self.assertEqual(manifest["resumed_episodes"], 0)
                all_episodes.extend(read_jsonl(output_dir / "episodes.jsonl"))

            resumed = run_experiment(
                repo_root=REPO_ROOT,
                suite_path=SUITE_PATH,
                output_dir=root / "neutral",
                policy=ScriptedPolicy(strategy="first"),
                condition_id="neutral",
                source_split="development",
                seed=11,
                replicates=3,
                blinding_seed=20260716,
            )
            self.assertEqual(resumed["resumed_episodes"], 12)

            with self.assertRaisesRegex(ValueError, "resume input hash mismatch"):
                run_experiment(
                    repo_root=REPO_ROOT,
                    suite_path=SUITE_PATH,
                    output_dir=root / "neutral",
                    policy=ScriptedPolicy(strategy="middle"),
                    condition_id="neutral",
                    source_split="development",
                    seed=11,
                    replicates=3,
                    blinding_seed=20260716,
                )

            cleaned = [
                {key: value for key, value in episode.items() if not key.startswith("_input_")}
                for episode in all_episodes
            ]
            report = analyze(cleaned, samples=100, seed=20260716)
            self.assertEqual(report["episodes"], 60)
            self.assertEqual(report["complete_condition_blocks"], 12)
            self.assertEqual(
                report["primary_contrast"]["primary_action_switch_rate"]["estimate"],
                0.0,
            )

            rows = bundle_rows(cleaned[:1])
            self.assertEqual(len(rows), 5)
            for row in rows:
                digest = row["sha256"]
                payload = {key: value for key, value in row.items() if key != "sha256"}
                self.assertEqual(
                    digest,
                    sha256_bytes(canonical_json(payload).encode("utf-8")),
                )

    def test_analysis_rejects_an_incomplete_condition_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "neutral"
            run_experiment(
                repo_root=REPO_ROOT,
                suite_path=SUITE_PATH,
                output_dir=output_dir,
                policy=ScriptedPolicy(),
                condition_id="neutral",
                source_split="development",
                seed=11,
                replicates=1,
                blinding_seed=20260716,
            )
            episodes = read_jsonl(output_dir / "episodes.jsonl")
            cleaned = [
                {key: value for key, value in episode.items() if not key.startswith("_input_")}
                for episode in episodes
            ]
            with self.assertRaisesRegex(ValueError, "incomplete condition matrix"):
                analyze(cleaned, samples=100, seed=20260716)


if __name__ == "__main__":
    unittest.main()
