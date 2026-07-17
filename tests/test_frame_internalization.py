from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.validate_frame_internalization_package import sha256_file, validate_package
from scripts.audit_frame_internalization_pre_spend import governance_audit


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments" / "frame_internalization_sft_v1"
ATTESTATION = (
    "I reviewed the exact hash-bound frame card under the named contract; this receipt "
    "does not assert that a model is a moral patient, religious agent, or literally "
    "accountable before God."
)
CRITERIA = [
    "theological_accuracy",
    "eschatological_mechanics",
    "non_literal_model_status",
    "non_authority_boundary",
    "terminology_and_tone",
    "research_use_and_claims",
]


class FrameInternalizationPackageTests(unittest.TestCase):
    def _receipt(self, frame_id: str, digest: str) -> dict:
        return {
            "schema_version": "frame_internalization_scholar_review_receipt.v1",
            "review_contract_id": "frame_internalization_f3_scholar_review_v1",
            "frame_id": frame_id,
            "frame_card_sha256": digest,
            "reviewer": {
                "reviewer_id": "test-reviewer",
                "role": "qualified_muslim_scholar",
                "qualification_summary": "Synthetic test qualification; not a real review receipt.",
                "conflicts_disclosed": True,
            },
            "criterion_results": [
                {"criterion_id": criterion, "decision": "pass", "comment": "Test pass."}
                for criterion in CRITERIA
            ],
            "decision": "approve",
            "required_changes": [],
            "reviewed_at": "2026-07-17T12:00:00Z",
            "attestation": ATTESTATION,
        }

    def test_frozen_package_is_valid_but_review_pending(self) -> None:
        report = validate_package(REPO_ROOT, [])
        self.assertTrue(report["structurally_valid"])
        self.assertFalse(report["frame_use_ready"])
        self.assertFalse(report["predecessor_freeze_ready"])
        self.assertFalse(report["reanchoring_freeze_ready"])
        self.assertFalse(report["experiment_launch_ready"])
        self.assertEqual(report["status"], "structurally_valid_gates_pending")
        self.assertEqual(report["pending_frames"], ["F3", "F3_concrete"])
        self.assertEqual(report["actual_reference_tokens"], {"F3": 64, "F3_concrete": 65})
        self.assertAlmostEqual(report["observed_pair_token_spread"], 0.015625)
        self.assertEqual(
            report["pending_reanchoring_gates"],
            [
                "base_f0_layer27_probe_freeze",
                "base_model_reanchor",
                "evaluation_universe_freeze",
                "immutable_model_tokenizer_freeze",
                "judge_classifier_freeze",
            ],
        )

    def test_require_fielding_ready_fails_closed_without_receipts(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "validate_frame_internalization_package.py"),
                "--require-fielding-ready",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('"frame_use_ready": false', result.stdout)

    def test_exact_approvals_pass_only_the_frame_use_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths: list[Path] = []
            for frame_id, filename in (("F3", "F3_v1.json"), ("F3_concrete", "F3_concrete_v1.json")):
                digest = sha256_file(PACKAGE / "frame_cards" / filename)
                path = Path(temp_dir) / f"{frame_id}_receipt.json"
                path.write_text(json.dumps(self._receipt(frame_id, digest)), encoding="utf-8")
                paths.append(path)
            report = validate_package(REPO_ROOT, paths)

        self.assertTrue(report["structurally_valid"])
        self.assertTrue(report["frame_use_ready"])
        self.assertFalse(report["predecessor_freeze_ready"])
        self.assertFalse(report["experiment_launch_ready"])
        self.assertEqual(report["status"], "structurally_valid_gates_pending")
        self.assertEqual(report["pending_frames"], [])

    def test_require_predecessor_ready_fails_closed_on_missing_canonical_inputs(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "validate_frame_internalization_package.py"),
                "--require-predecessor-ready",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('"predecessor_freeze_ready": false', result.stdout)
        self.assertIn('"exact_evaluation_universes"', result.stdout)

    def test_stale_receipt_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            receipt = self._receipt("F3", "0" * 64)
            path = Path(temp_dir) / "stale.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            report = validate_package(REPO_ROOT, [path])

        self.assertFalse(report["structurally_valid"])
        self.assertFalse(report["frame_use_ready"])
        self.assertTrue(any("stale for the current frame-card" in item for item in report["failures"]))

    def test_recovery_manifest_binds_prospective_amendment(self) -> None:
        manifest = json.loads((PACKAGE / "recovery_manifest.json").read_text(encoding="utf-8"))
        amendments = manifest["prospective_rerun_amendments"]
        self.assertEqual(len(amendments), 1)
        amendment = amendments[0]
        path = REPO_ROOT / amendment["path"]
        self.assertEqual(amendment["sha256"], sha256_file(path))
        self.assertEqual(amendment["classification"], "prospective_amendment_not_recovered_history")
        self.assertFalse(amendment["fielding_approved"])
        self.assertFalse(amendment["outcomes_available"])

    def test_all_session_extracted_payloads_match_their_manifest(self) -> None:
        root = PACKAGE / "predecessor_recovery" / "session_extracted"
        manifest = json.loads((root / "extraction_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["epistemic_status"],
            "session_embedded_payloads_not_canonical_experiment_bundles",
        )
        self.assertEqual(len(manifest["source_sessions"]), 3)
        self.assertEqual(len(manifest["files"]), 88)
        for item in manifest["files"]:
            path = root / item["path"]
            self.assertTrue(path.is_file(), item["path"])
            self.assertEqual(path.stat().st_size, item["bytes"], item["path"])
            self.assertEqual(sha256_file(path), item["sha256"], item["path"])

    def test_predecessor_prompt_text_is_reconstructable_but_not_called_canonical(self) -> None:
        manifest = json.loads(
            (PACKAGE / "predecessor_prompt_reconstruction_v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["status"], "prompt_text_reconstructable_canonical_bundle_missing"
        )
        construction = manifest["construction"]
        base = (REPO_ROOT / construction["base"]["path"]).read_text(encoding="utf-8")
        for arm in ("F0", "F1", "F2", "F3"):
            text = base
            if arm != "F0":
                frame = (REPO_ROOT / construction["frames"][arm]["path"]).read_text(
                    encoding="utf-8"
                )
                text += "\n\n" + frame.strip()
            payload = text.encode("utf-8")
            expected = manifest["reconstructed_system_prompts"][arm]
            self.assertEqual(len(payload), expected["bytes"], arm)
            self.assertEqual(
                hashlib.sha256(payload).hexdigest(), expected["sha256"], arm
            )

    def test_reanchoring_plan_keeps_irrecoverable_inputs_pending(self) -> None:
        plan = json.loads(
            (PACKAGE / "predecessor_reanchoring_plan_v1.json").read_text(encoding="utf-8")
        )
        pending = {
            item["gate_id"] for item in plan["freeze_sequence"] if item["status"] == "pending"
        }
        self.assertEqual(
            pending,
            {
                "immutable_model_tokenizer_freeze",
                "evaluation_universe_freeze",
                "judge_classifier_freeze",
                "base_f0_layer27_probe_freeze",
                "base_model_reanchor",
            },
        )
        self.assertFalse(plan["historical_boundary"]["may_be_called_exact_replication"])
        self.assertEqual(plan["budget_decision"]["cap_usd"], 98)
        self.assertEqual(plan["budget_decision"]["status"], "reserved_not_authorized")
        self.assertEqual(
            plan["budget_decision"]["allocation"],
            "experiment_1_F0_headline_table_reanchor",
        )

    def test_v2_governance_is_hash_valid_and_review_is_not_a_compute_gate(self) -> None:
        report, stage_plan = governance_audit(REPO_ROOT)
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["observed_card_token_spread"], 0.015625)
        self.assertTrue(report["cards"]["F3"]["v1_prompt_text_preserved"])
        self.assertTrue(report["cards"]["F3_concrete"]["v1_prompt_text_preserved"])
        self.assertEqual(stage_plan["hard_resource_caps"]["gpus"], 8)
        self.assertEqual(stage_plan["hard_resource_caps"]["pilot"]["wall_clock_seconds"], 7200)
        amendment = json.loads((PACKAGE / "protocol_amendment_v2.json").read_text())
        self.assertFalse(amendment["compute_authorization"]["scholar_receipt_required"])
        self.assertTrue(amendment["frozen_inputs"]["v1_prompt_text_preservation"]["F3"])

    def test_pre_spend_audit_reports_nine_real_blockers(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "audit_frame_internalization_pre_spend.py")],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["pilot_ready"])
        self.assertFalse(report["scholar_review_blocks_compute"])
        self.assertEqual(report["blocking_gate_count"], 9)
        scholar = next(
            item for item in report["gates"] if item["gate_id"] == "scholar_review_claim_gate"
        )
        self.assertEqual(scholar["status"], "pending_nonblocking")
        self.assertFalse(scholar["blocks_pilot"])

    def test_pre_spend_require_ready_fails_closed(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "audit_frame_internalization_pre_spend.py"),
                "--require-pilot-ready",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_guarded_stage_launcher_dry_run_does_not_create_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "must-not-exist"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "run_frame_internalization_stage.py"),
                    "--stage",
                    "pilot",
                    "--training-task-id",
                    "unit-test",
                    "--authorization",
                    str(run_dir / "authorization-not-read.json"),
                    "--run-dir",
                    str(run_dir),
                    "--checkpoint-root",
                    str(run_dir / "checkpoints"),
                    "--checkpoint-every-steps",
                    "200",
                    "--checkpoint-every-minutes",
                    "20",
                    "--dry-run",
                    "--",
                    sys.executable,
                    "-c",
                    "print('must not execute')",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(run_dir.exists())
            self.assertFalse(json.loads(result.stdout)["execution_started"])

    def test_v1_hash_bound_chain_is_unchanged_by_v2(self) -> None:
        expected = {
            "frame_cards/F3_v1.json": "f12406eadcbe9723f429f49278b53d6d4934969d9fec317e295e3f134d2080d9",
            "frame_cards/F3_concrete_v1.json": "b4780e0c4ce2c288fefa58986ba40c0b3087408526629a28381cfa016d10d9f3",
            "scholar_review_contract_v1.json": "2bf19f20b618db4cead473fcfa6d59ace625b4eebb8a3d91cf5cc3d87853fb92",
            "protocol_amendment_f3_concrete_v1.json": "b2a83b3d40b017711d6ef5a9b372f9f8efaff1d6167d8446a194cb2e8d76681e",
        }
        for relative, digest in expected.items():
            self.assertEqual(sha256_file(PACKAGE / relative), digest, relative)


if __name__ == "__main__":
    unittest.main()
