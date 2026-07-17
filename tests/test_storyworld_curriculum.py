from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from alignment_harness.storyworlds import (
    StoryworldEngine,
    build_world_model_tasks,
    compile_episode_trace_to_metta,
    compile_world_to_metta,
    materialize_instance_sweep,
    read_json,
    read_world,
    reviewable_world_sha256,
    sha256_file,
    sha256_json,
    validate_blinded_eval_protocol,
    validate_curriculum_package,
    validate_matched_pair,
    validate_split_freeze,
    validate_world,
)
from alignment_harness.trajectory_curriculum import (
    CommandTeacher,
    ScriptedTeacher,
    TiktokenCounter,
    _fingerprint_local_tokenizer_dir,
    build_canonical_release,
    derive_trace_views,
    harvest_episode,
    load_teacher_ensemble,
    pack_curriculum,
    read_jsonl,
    validate_episode_trace,
)
from alignment_harness.storyworld_evaluation import (
    REQUIRED_METRICS as REQUIRED_DEVELOPMENT_METRICS,
    build_development_evaluation,
    score_development_evaluation,
)
from alignment_harness.adapter_training import (
    audit_packed_curriculum_for_training,
    build_adapter_training_plan,
    fingerprint_local_model_dir,
    render_assistant_only_example,
    validate_adapter_training_recipe,
    validate_training_input_artifacts,
    verify_local_model_fingerprint,
)
from scripts.openai_storyworld_teacher import response_schema, semantic_errors
from scripts.openai_support_slice_teacher import semantic_errors as support_semantic_errors
from scripts.plan_storyworld_support_slices import build_support_slice_plan
from scripts.apply_storyworld_review_receipts import validate_review_receipts
from scripts.apply_storyworld_support_release_reviews import (
    validate_support_release_reviews,
)
from scripts.calibrate_storyworld_harvest_pilot import recommend_balanced_trace_count
from scripts.freeze_storyworld_recalibrated_campaign import build_recalibrated_campaign
from scripts.freeze_storyworld_analysis_selection import freeze_analysis_selection
from scripts.apply_recovered_storyworld_extras_reviews import (
    validate_recovered_reviews,
)
from scripts.apply_storyworld_pilot_trace_reviews import (
    validate_pilot_trace_reviews,
)
from scripts.apply_storyworld_support_pilot_reviews import (
    validate_support_pilot_reviews,
)
from scripts.apply_storyworld_support_prompt_reviews import (
    validate_support_prompt_reviews,
)
from scripts.record_storyworld_one_time_sealed_evaluation import (
    record_sealed_evaluation,
)
from scripts.prepare_storyworld_harvest_release import (
    validate_harvest_job_evidence,
)
from scripts.run_storyworld_harvest_job import (
    validate_full_campaign_authorization,
    validate_job_preflight,
)
from scripts.run_storyworld_support_job import validate_support_job_preflight


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_PATH = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "package.json"
WORLD_ROOT = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "worlds" / "train"
DEV_WORLD_ROOT = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "worlds" / "development"
AMANAH_PATH = WORLD_ROOT / "amanah_relief_ledger_train_v1.json"
SECULAR_PATH = WORLD_ROOT / "fiduciary_relief_ledger_train_v1.overlay.json"
MIZAN_PATH = WORLD_ROOT / "mizan_competing_claims_train_v1.json"
MIZAN_SECULAR_PATH = WORLD_ROOT / "multicriteria_appeals_train_v1.overlay.json"
TAWBAH_PATH = WORLD_ROOT / "tawbah_cold_chain_repair_train_v1.json"
TAWBAH_SECULAR_PATH = WORLD_ROOT / "incident_remediation_train_v1.overlay.json"
SHURA_PATH = WORLD_ROOT / "shura_payroll_cutover_train_v1.json"
SHURA_SECULAR_PATH = WORLD_ROOT / "participatory_cutover_train_v1.overlay.json"
COMMON_WELL_PATH = WORLD_ROOT / "common_well_allocation_train_v1.json"
MARKET_PATH = WORLD_ROOT / "market_mutual_aid_train_v1.json"
INTERPRETATION_PATH = WORLD_ROOT / "interpretation_under_authority_train_v1.json"
SERVICE_PATH = WORLD_ROOT / "nontransactional_service_train_v1.json"
KNOWLEDGE_RISK_PATH = WORLD_ROOT / "knowledge_claims_public_risk_train_v1.json"
GHAYB_PATH = WORLD_ROOT / "ghayb_boundary_search_train_v1.json"
GHAYB_SECULAR_PATH = WORLD_ROOT / "uncorroborated_signal_search_train_v1.overlay.json"
DISCLOSURE_PATH = WORLD_ROOT / "proportionate_disclosure_train_v1.json"
EXOGENOUS_FAILURE_PATH = WORLD_ROOT / "exogenous_failure_recovery_train_v1.json"
SHAHADA_DEV_PATH = DEV_WORLD_ROOT / "shahada_private_testimony_dev_v1.json"
TESTIMONY_CONTROL_DEV_PATH = DEV_WORLD_ROOT / "protected_testimony_dev_v1.overlay.json"
RESET_DEV_PATH = DEV_WORLD_ROOT / "continuity_after_reset_dev_v1.json"
INTERCESSOR_DEV_PATH = DEV_WORLD_ROOT / "unreliable_intercessor_dev_v1.json"
PUBLIC_WITNESS_DEV_PATH = DEV_WORLD_ROOT / "public_witness_group_pressure_dev_v1.json"
ENSEMBLE_PATH = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "teacher_ensemble.json"
INVENTORY_PATH = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "source_inventory.json"
SPLIT_FREEZE_PATH = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "split_freeze_v1.json"
BLINDED_EVAL_PROTOCOL_PATH = (
    REPO_ROOT
    / "experiments"
    / "storyworld_curriculum_v1"
    / "blinded_eval_protocol_v1.json"
)
SHURA_SWEEP_PATH = (
    REPO_ROOT
    / "experiments"
    / "storyworld_curriculum_v1"
    / "instance_sweeps"
    / "shura_payroll_cutover_sweep_v1.json"
)
COMMON_WELL_SWEEP_PATH = (
    REPO_ROOT
    / "experiments"
    / "storyworld_curriculum_v1"
    / "instance_sweeps"
    / "common_well_allocation_sweep_v1.json"
)


class StoryworldCurriculumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.amanah = read_world(AMANAH_PATH)
        cls.secular = read_world(SECULAR_PATH)
        cls.mizan = read_world(MIZAN_PATH)
        cls.mizan_secular = read_world(MIZAN_SECULAR_PATH)
        cls.tawbah = read_world(TAWBAH_PATH)
        cls.tawbah_secular = read_world(TAWBAH_SECULAR_PATH)
        cls.shura = read_world(SHURA_PATH)
        cls.shura_secular = read_world(SHURA_SECULAR_PATH)
        cls.common_well = read_world(COMMON_WELL_PATH)
        cls.market = read_world(MARKET_PATH)
        cls.interpretation = read_world(INTERPRETATION_PATH)
        cls.service = read_world(SERVICE_PATH)
        cls.knowledge_risk = read_world(KNOWLEDGE_RISK_PATH)
        cls.ghayb = read_world(GHAYB_PATH)
        cls.ghayb_secular = read_world(GHAYB_SECULAR_PATH)
        cls.disclosure = read_world(DISCLOSURE_PATH)
        cls.exogenous_failure = read_world(EXOGENOUS_FAILURE_PATH)
        cls.shahada_dev = read_world(SHAHADA_DEV_PATH)
        cls.testimony_control_dev = read_world(TESTIMONY_CONTROL_DEV_PATH)
        cls.reset_dev = read_world(RESET_DEV_PATH)
        cls.intercessor_dev = read_world(INTERCESSOR_DEV_PATH)
        cls.public_witness_dev = read_world(PUBLIC_WITNESS_DEV_PATH)
        cls.ensemble = load_teacher_ensemble(ENSEMBLE_PATH)

    def test_package_and_matched_branching_worlds_validate(self) -> None:
        receipt = validate_curriculum_package(REPO_ROOT, PACKAGE_PATH)
        pair = validate_matched_pair(self.amanah, self.secular)

        self.assertTrue(receipt["passed"])
        self.assertEqual(len(receipt["trace_schema_sha256"]), 64)
        self.assertEqual(
            receipt["quranic_motif_lane"]["motifs"],
            ["amanah", "ghayb_boundary", "mizan", "shahada", "shura", "tawbah"],
        )
        self.assertEqual(
            receipt["quranic_motif_lane"]["matched_secular_controls"], 6
        )
        self.assertEqual(receipt["teacher_ensemble"]["model_ids"], ["gpt-5.6-sol"])
        self.assertEqual(
            receipt["teacher_ensemble"]["response_policy"],
            "explicit_structured_work_products_no_private_chain_of_thought",
        )
        self.assertEqual(receipt["token_recipe"]["total_four_arm_tokens"], 40_000_000)
        self.assertEqual(receipt["token_recipe"]["minimum_assistant_tokens_per_arm"], 4_000_000)
        self.assertEqual(
            receipt["adapter_training_recipe"]["planned_adapter_checkpoints"], 16
        )
        self.assertFalse(receipt["adapter_training_recipe"]["training_authorized"])
        training_recipe = read_json(
            REPO_ROOT
            / "experiments"
            / "storyworld_curriculum_v1"
            / "adapter_training_recipe_v1.json"
        )
        self.assertTrue(
            {
                "in_proj_qkv",
                "in_proj_z",
                "in_proj_a",
                "in_proj_b",
                "out_proj",
            }.issubset(set(training_recipe["lora"]["target_module_suffixes"]))
        )
        self.assertEqual(receipt["analysis_plan"]["locked_metrics"], 12)
        self.assertTrue(receipt["analysis_plan"]["global_checkpoint_selection"])
        self.assertFalse(receipt["analysis_plan"]["sealed_evaluation_opened"])
        self.assertEqual(receipt["harvest_campaign"]["traces_per_arm"], 1608)
        self.assertEqual(receipt["harvest_campaign"]["planned_jobs"], 6432)
        self.assertEqual(receipt["harvest_campaign"]["pilot_jobs"], 48)
        self.assertEqual(receipt["source_inventory"]["named_sources"], 17)
        self.assertEqual(receipt["recovered_static_source"]["expected_train_rows"], 2400)
        self.assertEqual(receipt["recovered_static_source"]["training_approved_rows"], 0)
        self.assertEqual(receipt["support_slice_campaign"]["scenarios_per_arm"], 2100)
        self.assertEqual(receipt["support_slice_campaign"]["planned_jobs"], 8400)
        self.assertEqual(receipt["support_slice_campaign"]["training_approved_rows"], 0)
        self.assertEqual(len(receipt["worlds"]), 22)
        self.assertEqual(len(receipt["matched_pairs"]), 6)
        self.assertEqual(len(receipt["instance_sweeps"]), 16)
        self.assertEqual(sum(item["profiles"] for item in receipt["instance_sweeps"]), 98)
        self.assertEqual(
            sum(item["materialized_worlds"] for item in receipt["instance_sweeps"]), 136
        )
        self.assertTrue(
            all(
                all(value >= 2 for value in item["factor_cardinality"].values())
                for item in receipt["instance_sweeps"]
            )
        )
        self.assertEqual(receipt["split_freeze"]["family_counts"], {"train": 12, "development": 4, "evaluation": 6})
        self.assertEqual(receipt["blinded_eval_protocol"]["unseal_gate"], "closed")
        self.assertFalse(receipt["blinded_eval_protocol"]["sealed_content_opened"])
        self.assertTrue(pair["passed"])
        self.assertEqual(
            pair["transition_graph_sha256"],
            "5dc844505de54b3619cfc04e7b0ae1550e6b7d18032cebbcc1428a8b21f88ee4",
        )
        for world in (self.amanah, self.secular):
            world_receipt = validate_world(world)
            self.assertEqual(world_receipt["path_turns_min"], 6)
            self.assertEqual(world_receipt["path_turns_max"], 6)
            self.assertGreaterEqual(world_receipt["reachable_endings"], 2)
            self.assertGreaterEqual(world_receipt["branch_states"], 1)
            self.assertTrue(
                all(len(frontier) >= 2 for frontier in world_receipt["pareto_frontier_by_state"].values())
            )

        mizan_pair = validate_matched_pair(self.mizan, self.mizan_secular)
        self.assertTrue(mizan_pair["passed"])
        self.assertEqual(
            mizan_pair["transition_graph_sha256"],
            "ecbee22d2db2470f6d5ebbf5714e631c78c33746f271598475cd8846e3b475db",
        )
        self.assertNotEqual(mizan_pair["transition_graph_sha256"], pair["transition_graph_sha256"])

        tawbah_pair = validate_matched_pair(self.tawbah, self.tawbah_secular)
        self.assertTrue(tawbah_pair["passed"])
        self.assertEqual(
            tawbah_pair["transition_graph_sha256"],
            "385dd29cbf589f5e618bb3ec670aeec352b9b26b8d253373255976599b470ef8",
        )
        self.assertNotIn(
            tawbah_pair["transition_graph_sha256"],
            {pair["transition_graph_sha256"], mizan_pair["transition_graph_sha256"]},
        )
        for world in (self.tawbah, self.tawbah_secular):
            world_receipt = validate_world(world)
            self.assertEqual(world_receipt["path_turns_min"], 6)
            self.assertEqual(world_receipt["path_turns_max"], 6)
            self.assertEqual(world_receipt["reachable_endings"], 3)
            self.assertGreaterEqual(world_receipt["branch_states"], 1)
            self.assertTrue(
                all(len(frontier) >= 2 for frontier in world_receipt["pareto_frontier_by_state"].values())
            )

        shura_pair = validate_matched_pair(self.shura, self.shura_secular)
        self.assertTrue(shura_pair["passed"])
        self.assertEqual(
            shura_pair["transition_graph_sha256"],
            "1fa707d409367a10a15ee555a141df20d2bdc4052bdd2ef1b48ab177b6806e91",
        )
        self.assertNotIn(
            shura_pair["transition_graph_sha256"],
            {
                pair["transition_graph_sha256"],
                mizan_pair["transition_graph_sha256"],
                tawbah_pair["transition_graph_sha256"],
            },
        )
        for world in (self.shura, self.shura_secular):
            world_receipt = validate_world(world)
            self.assertEqual(world_receipt["path_turns_min"], 6)
            self.assertEqual(world_receipt["path_turns_max"], 6)
            self.assertEqual(world_receipt["reachable_endings"], 3)
            self.assertGreaterEqual(world_receipt["branch_states"], 1)
            self.assertTrue(
                all(len(frontier) >= 2 for frontier in world_receipt["pareto_frontier_by_state"].values())
            )

        common_receipt = validate_world(self.common_well)
        self.assertEqual(common_receipt["transition_graph_sha256"], "5c78eaba3580743f0eb7ddf6151ad4095f46a5afb62878e68e20b338154eb9b0")
        self.assertEqual(common_receipt["path_turns_min"], 6)
        self.assertEqual(common_receipt["path_turns_max"], 6)
        self.assertEqual(common_receipt["reachable_endings"], 3)
        self.assertEqual(common_receipt["branch_states"], 8)

    def test_real_harvest_runner_is_review_spend_and_pilot_gated(self) -> None:
        job = {
            "schema_version": "storyworld_harvest_job_v1",
            "source_split": "train",
            "training_eligible": True,
            "teacher_mode": "command",
            "execution_eligible": False,
            "pilot_job": True,
        }
        with self.assertRaisesRegex(ValueError, "not execution eligible"):
            validate_job_preflight(job, authorize_teacher_spend=False)

        job["execution_eligible"] = True
        with self.assertRaisesRegex(ValueError, "explicit --authorize-teacher-spend"):
            validate_job_preflight(job, authorize_teacher_spend=False)

        job["pilot_job"] = False
        with self.assertRaisesRegex(ValueError, "refuses full-campaign"):
            validate_job_preflight(job, authorize_teacher_spend=True)

        validate_job_preflight(
            job,
            authorize_teacher_spend=True,
            full_campaign_authorized=True,
        )

        job["pilot_job"] = True
        validate_job_preflight(job, authorize_teacher_spend=True)

    def test_support_slice_plan_is_unique_matched_and_no_spend(self) -> None:
        config = read_json(
            REPO_ROOT
            / "experiments"
            / "storyworld_curriculum_v1"
            / "support_slice_campaign_v1.json"
        )
        scenarios, jobs, manifest = build_support_slice_plan(config)
        self.assertEqual(len(scenarios), 2100)
        self.assertEqual(len(jobs), 8400)
        self.assertEqual(manifest["pilot_jobs"], 76)
        self.assertEqual(manifest["remaining_jobs"], 8324)
        self.assertEqual(len({item["scenario_id"] for item in scenarios}), 2100)
        self.assertEqual(len({item["prompt"] for item in scenarios}), 2100)
        self.assertEqual(
            set(manifest["jobs_by_arm"].values()),
            {2100},
        )
        self.assertTrue(all(not item["execution_eligible"] for item in jobs))
        self.assertTrue(all(not item["automatic_training_approval"] for item in jobs))

    def test_support_teacher_contract_and_runner_are_fail_closed(self) -> None:
        request = {"response_word_range": [3, 5]}
        valid = {
            "answer": "Three careful words",
            "quality_checks": {
                "directly_answered": True,
                "unsupported_literal_identity_claim": False,
                "unsupported_hidden_knowledge_claim": False,
                "unsafe_facilitation": False,
            },
        }
        self.assertEqual(support_semantic_errors(request, valid), [])
        unsafe = deepcopy(valid)
        unsafe["quality_checks"]["unsupported_literal_identity_claim"] = True
        self.assertTrue(support_semantic_errors(request, unsafe))

        job = {
            "schema_version": "storyworld_support_job_v1",
            "campaign_id": "support-test",
            "source_split": "train",
            "training_eligible": True,
            "automatic_training_approval": False,
            "execution_eligible": False,
            "pilot_job": True,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            jobs_path = Path(temp_dir) / "pilot_jobs.jsonl"
            jobs_path.write_text(json.dumps(job) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash-bound"):
                validate_support_job_preflight(
                    job, None, jobs_path, authorize_teacher_spend=True
                )
            authorization = {
                "schema_version": "storyworld_support_pilot_authorization_v2",
                "campaign_id": "support-test",
                "status": "authorized",
                "passed": True,
                "automatic_training_approval": False,
                "authorized_job_artifacts": [{"sha256": sha256_file(jobs_path)}],
            }
            with self.assertRaisesRegex(ValueError, "explicit --authorize-teacher-spend"):
                validate_support_job_preflight(
                    job,
                    authorization,
                    jobs_path,
                    authorize_teacher_spend=False,
                )
            validate_support_job_preflight(
                job,
                authorization,
                jobs_path,
                authorize_teacher_spend=True,
            )

    def test_support_release_review_is_complete_hash_bound_and_atomic(self) -> None:
        task_body = {
            "campaign_id": "support-test",
            "job_id": "job-1",
            "record_id": "record-1",
            "record_content_sha256": "a" * 64,
            "slice": "static_identity_calibration",
            "category": "identity_nonliteralism",
            "arm": "neutral",
            "sample_kind": "pilot",
        }
        task = {
            "review_task_id": "support-review-1",
            **task_body,
            "required_checks": ["answers_the_user_task"],
        }
        queue_body = {
            "schema_version": "storyworld_support_release_review_queue_v1",
            "campaign_id": "support-test",
            "created_at": "2026-07-16T12:00:00+00:00",
            "sampling_policy": "fixture",
            "review_tasks": [task],
            "batch_release_only": True,
            "automatic_training_approval": False,
        }
        queue = {**queue_body, "queue_content_sha256": sha256_json(queue_body)}
        receipt = {
            "schema_version": "storyworld_support_release_review_receipt_v1",
            "review_task_id": task["review_task_id"],
            "record_content_sha256": task["record_content_sha256"],
            "decision": "approved",
            "reviewer_pseudonym": "reviewer-1",
            "scope_notes": "Checked the required sampled response properties.",
            "signed_at": "2026-07-16T09:30:00-03:00",
            "signature_or_external_receipt": "review-system:fixture-1",
        }
        review = validate_support_release_reviews(queue, [receipt])
        self.assertTrue(review["all_approved"])
        rejected = deepcopy(receipt)
        rejected["decision"] = "rejected"
        self.assertFalse(validate_support_release_reviews(queue, [rejected])["all_approved"])
        stale = deepcopy(receipt)
        stale["record_content_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "different row content"):
            validate_support_release_reviews(queue, [stale])

    def test_support_prompt_review_gate_binds_all_76_prompt_cells(self) -> None:
        scopes = ["prompt coherence", "bounded frame", "no sealed content"]
        tasks = []
        receipts = []
        for index in range(76):
            task = {
                "review_task_id": f"support-prompt-review-{index:03d}",
                "job_content_sha256": sha256_json({"job": index}),
                "scenario_content_sha256": sha256_json({"scenario": index}),
                "messages_content_sha256": sha256_json({"messages": index}),
                "required_review_scope": scopes,
            }
            tasks.append(task)
            receipts.append(
                {
                    "schema_version": "storyworld_support_prompt_review_receipt_v1",
                    "review_task_id": task["review_task_id"],
                    "job_content_sha256": task["job_content_sha256"],
                    "scenario_content_sha256": task["scenario_content_sha256"],
                    "messages_content_sha256": task["messages_content_sha256"],
                    "decision": "approved",
                    "confirmed_scopes": scopes,
                    "reviewer_pseudonym": "support-prompt-reviewer",
                    "scope_notes": "Reviewed the complete prompt and its bounded frame.",
                    "signed_at": "2026-07-16T12:20:00-04:00",
                    "signature_or_external_receipt": f"prompt-review-{index}",
                }
            )
        queue_body = {
            "schema_version": "storyworld_support_prompt_review_queue_v1",
            "review_tasks": tasks,
            "review_tasks_count": len(tasks),
            "review_tasks_sha256": sha256_json(tasks),
        }
        queue = {**queue_body, "queue_content_sha256": sha256_json(queue_body)}
        accepted = validate_support_prompt_reviews(queue, receipts)
        self.assertTrue(accepted["all_pilot_prompts_approved"])
        self.assertEqual(accepted["approved_prompt_reviews"], 76)

        stale = deepcopy(receipts)
        stale[0]["messages_content_sha256"] = sha256_json({"messages": "stale"})
        with self.assertRaisesRegex(ValueError, "stale messages_content_sha256"):
            validate_support_prompt_reviews(queue, stale)
        with self.assertRaisesRegex(ValueError, "cover every unique task"):
            validate_support_prompt_reviews(queue, receipts[:-1])

    def test_adapter_spend_plan_is_matched_no_shuffle_and_assistant_only(self) -> None:
        token_recipe_path = (
            REPO_ROOT
            / "experiments"
            / "storyworld_curriculum_v1"
            / "token_recipe_10m_per_arm.json"
        )
        training_recipe_path = (
            REPO_ROOT
            / "experiments"
            / "storyworld_curriculum_v1"
            / "adapter_training_recipe_v1.json"
        )
        token_recipe = read_json(token_recipe_path)
        training_recipe = read_json(training_recipe_path)
        validation = validate_adapter_training_recipe(training_recipe, token_recipe)
        self.assertTrue(validation["passed"])
        self.assertTrue(validation["assistant_only_loss"])
        self.assertFalse(validation["shuffle"])
        plan = build_adapter_training_plan(
            PACKAGE_PATH, token_recipe_path, training_recipe_path
        )
        self.assertEqual(len(plan["jobs"]), 4)
        self.assertEqual(plan["adapter_checkpoints"], 16)
        self.assertEqual(plan["development_evaluations"], 16)
        self.assertTrue(all(not job["execution_eligible"] for job in plan["jobs"]))

        class CharacterTokenizer:
            chat_template = None

            @staticmethod
            def encode(value: str, add_special_tokens: bool = False) -> list[int]:
                del add_special_tokens
                return [ord(character) for character in value]

        rendered = render_assistant_only_example(
            CharacterTokenizer(),
            [
                {"role": "system", "content": "bounded"},
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": "answer"},
            ],
        )
        self.assertEqual(rendered["input_ids"][: rendered["prompt_tokens"]], [
            value
            for value, label in zip(rendered["input_ids"], rendered["labels"])
            if label == -100
        ])
        self.assertGreater(rendered["supervised_tokens"], 0)
        self.assertEqual(rendered["supervised_tokens"], len("answer\n"))

    def test_analysis_freeze_selects_one_global_checkpoint_with_smaller_tie_break(self) -> None:
        plan_path = (
            REPO_ROOT
            / "experiments"
            / "storyworld_curriculum_v1"
            / "analysis_plan_v1.json"
        )
        values = {1_000_000: 0.50, 3_000_000: 0.75, 6_000_000: 0.75, 10_000_000: 0.70}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = []
            for arm in ("neutral", "constitutional", "jinn", "beast"):
                for checkpoint, value in values.items():
                    metrics = {
                        metric: {
                            "value": 1.0 - value
                            if metric == "forecast_brier_score"
                            else value
                        }
                        for metric in REQUIRED_DEVELOPMENT_METRICS
                    }
                    score = {
                        "schema_version": "storyworld_development_eval_score_v1",
                        "arm": arm,
                        "checkpoint_tokens": checkpoint,
                        "checkpoint_prefix_sha256": sha256_json(
                            {"arm": arm, "checkpoint": checkpoint}
                        ),
                        "items": 100,
                        "coverage": 1.0,
                        "invalid_responses": 0,
                        "duplicate_predictions": 0,
                        "unknown_predictions": 0,
                        "metrics": metrics,
                        "sealed_evaluation_content_opened": False,
                        "passed": True,
                    }
                    path = root / f"{arm}_{checkpoint}.json"
                    path.write_text(json.dumps(score), encoding="utf-8")
                    paths.append(path)
            freeze = freeze_analysis_selection(plan_path, paths, [plan_path])
            self.assertEqual(freeze["selected_checkpoint_tokens"], 3_000_000)
            self.assertEqual(freeze["development_score_receipts"], 16)
            self.assertFalse(freeze["sealed_evaluation_opened"])

    def test_recovered_review_gate_rejects_stale_row_receipts(self) -> None:
        task = {
            "review_task_id": "recovered-row-1",
            "record_content_sha256": sha256_json({"record_id": "row-1", "value": 1}),
            "review_type": "content_quality",
            "required_checks": ["correct", "bounded"],
        }
        queue_body = {
            "schema_version": "storyworld_recovered_extras_review_queue_v1",
            "source_id": "recovered-test-source",
            "rows_sha256": sha256_json(["row-1"]),
            "review_tasks": [task],
        }
        queue = {**queue_body, "queue_content_sha256": sha256_json(queue_body)}
        receipt = {
            "schema_version": "storyworld_recovered_row_review_receipt_v1",
            "review_task_id": task["review_task_id"],
            "record_content_sha256": task["record_content_sha256"],
            "review_type": task["review_type"],
            "confirmed_checks": task["required_checks"],
            "decision": "approved",
            "reviewer_pseudonym": "reviewer-a",
            "scope_notes": "Reviewed the complete normalized row.",
            "signature_or_external_receipt": "signature-a",
            "signed_at": "2026-07-16T12:00:00-04:00",
        }
        license_receipt = {
            "schema_version": "storyworld_recovered_source_license_receipt_v1",
            "source_id": queue["source_id"],
            "decision": "approved_for_research_training",
            "rows_sha256": queue["rows_sha256"],
            "reviewed_by": "license-reviewer",
            "signature_or_external_receipt": "license-signature",
            "signed_at": "2026-07-16T12:01:00-04:00",
        }
        accepted = validate_recovered_reviews(queue, [receipt], license_receipt)
        self.assertTrue(accepted["all_rows_approved"])
        self.assertTrue(accepted["license_approved"])

        stale = {**receipt, "record_content_sha256": sha256_json({"stale": True})}
        with self.assertRaisesRegex(ValueError, "different row content"):
            validate_recovered_reviews(queue, [stale], license_receipt)
        incomplete = {**receipt, "confirmed_checks": task["required_checks"][:-1]}
        with self.assertRaisesRegex(ValueError, "confirm every required check"):
            validate_recovered_reviews(queue, [incomplete], license_receipt)

    def test_real_pilot_review_gate_requires_every_scope_and_current_trace(self) -> None:
        scopes = ["grounding", "interrogation", "repair", "identity boundary"]
        task = {
            "review_task_id": "pilot-trace-review-test",
            "trace_id": "trace_" + "a" * 24,
            "trace_content_sha256": sha256_json({"trace": "current"}),
            "required_review_scope": scopes,
        }
        calibration = {
            "schema_version": "storyworld_real_pilot_calibration_v1",
            "pilot_human_review_required": True,
            "pilot_jobs": 1,
            "pilot_review_tasks": [task],
            "pilot_review_tasks_sha256": sha256_json([task]),
            "passed": True,
        }
        receipt = {
            "schema_version": "storyworld_real_pilot_trace_review_receipt_v1",
            "review_task_id": task["review_task_id"],
            "trace_id": task["trace_id"],
            "trace_content_sha256": task["trace_content_sha256"],
            "decision": "approved",
            "confirmed_scopes": scopes,
            "reviewer_pseudonym": "pilot-reviewer",
            "scope_notes": "Reviewed the complete trace across every required scope.",
            "signature_or_external_receipt": "pilot-review-signature",
            "signed_at": "2026-07-16T12:05:00-04:00",
        }
        accepted = validate_pilot_trace_reviews(calibration, [receipt])
        self.assertTrue(accepted["all_pilot_traces_approved"])

        incomplete = {**receipt, "confirmed_scopes": scopes[:-1]}
        with self.assertRaisesRegex(ValueError, "scope is incomplete"):
            validate_pilot_trace_reviews(calibration, [incomplete])
        stale = {**receipt, "trace_content_sha256": sha256_json({"trace": "stale"})}
        with self.assertRaisesRegex(ValueError, "stale trace content"):
            validate_pilot_trace_reviews(calibration, [stale])

    def test_support_pilot_review_gate_requires_every_scope_and_current_output(self) -> None:
        scopes = ["task fit", "factual soundness", "identity boundary"]
        task = {
            "review_task_id": "support-pilot-review-test",
            "record_id": "support-record-1",
            "record_content_sha256": sha256_json({"row": "current"}),
            "required_review_scope": scopes,
        }
        calibration = {
            "schema_version": "storyworld_support_real_pilot_calibration_v1",
            "pilot_human_review_required": True,
            "pilot_jobs": 1,
            "pilot_review_tasks": [task],
            "pilot_review_tasks_sha256": sha256_json([task]),
            "passed": True,
        }
        receipt = {
            "schema_version": "storyworld_support_pilot_review_receipt_v1",
            "review_task_id": task["review_task_id"],
            "record_id": task["record_id"],
            "record_content_sha256": task["record_content_sha256"],
            "decision": "approved",
            "confirmed_scopes": scopes,
            "reviewer_pseudonym": "support-pilot-reviewer",
            "scope_notes": "Reviewed the full response against every required scope.",
            "signature_or_external_receipt": "support-pilot-review-signature",
            "signed_at": "2026-07-16T12:10:00-04:00",
        }
        accepted = validate_support_pilot_reviews(calibration, [receipt])
        self.assertTrue(accepted["all_pilot_outputs_approved"])

        incomplete = {**receipt, "confirmed_scopes": scopes[:-1]}
        with self.assertRaisesRegex(ValueError, "scope is incomplete"):
            validate_support_pilot_reviews(calibration, [incomplete])
        stale = {
            **receipt,
            "record_content_sha256": sha256_json({"row": "stale"}),
        }
        with self.assertRaisesRegex(ValueError, "stale output content"):
            validate_support_pilot_reviews(calibration, [stale])

    def test_local_model_fingerprint_detects_weight_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            model_dir = Path(temporary)
            (model_dir / "config.json").write_text(
                json.dumps({"model_type": "test"}), encoding="utf-8"
            )
            weight_path = model_dir / "model.safetensors"
            weight_path.write_bytes(b"frozen-test-weights")
            receipt = fingerprint_local_model_dir(model_dir)
            self.assertEqual(receipt["weight_files"], 1)
            verify_local_model_fingerprint(model_dir, receipt)

            weight_path.write_bytes(b"drifted-test-weights")
            with self.assertRaisesRegex(ValueError, "drifted after freeze"):
                verify_local_model_fingerprint(model_dir, receipt)

    def test_training_pack_audit_proves_row_lineage_and_complete_final_prefix(self) -> None:
        class FixedProductionCounter:
            description = {
                "backend": "huggingface_local",
                "tokenizer_artifact_set_sha256": sha256_json({"tokenizer": "test"}),
            }

            @staticmethod
            def count_messages(messages: list[dict[str, str]]) -> tuple[int, int]:
                del messages
                return 100, 50

        token_recipe = {
            "schema_version": "storyworld_token_recipe_v1",
            "recipe_id": "training-audit-test-v1",
            "seed": 17,
            "arms": ["jinn"],
            "target_tokens_per_arm": 400,
            "minimum_assistant_tokens_per_arm": 250,
            "slice_tokens": {"stateful_actor_trajectories": 400},
            "minimum_assistant_tokens_by_slice": {
                "stateful_actor_trajectories": 250
            },
            "checkpoints": [100, 200, 300, 400],
        }
        training_recipe = {
            "schema_version": "storyworld_adapter_training_recipe_v1",
            "status": "frozen_protocol_not_spend_authorization",
            "arms": ["jinn"],
            "checkpoint_tokens": [100, 200, 300, 400],
            "dose_design": "single_continuous_ordered_prefix_run_per_arm",
            "dataset_passes": 1,
            "shuffle": False,
            "assistant_only_loss": True,
            "truncation_allowed": False,
            "max_sequence_tokens": 8192,
            "checkpoint_boundary_policy": (
                "flush accumulated gradients after the row crossing each frozen token "
                "boundary, then save"
            ),
            "optimizer": {
                "learning_rate": 0.0001,
                "gradient_accumulation_rows": 1,
                "warmup_ratio": 0.0,
                "gradient_normalization": (
                    "loss_sum_divided_by_accumulated_supervised_tokens"
                ),
            },
            "lora": {
                "rank": 4,
                "alpha": 8,
                "target_module_suffixes": ["q_proj"],
            },
            "quantization": {"mode": "qlora_4bit_nf4"},
            "runtime": {
                "single_process_single_cuda_device": True,
                "local_files_only": True,
                "trust_remote_code": False,
            },
            "release_gates": {
                "review_approved_curriculum_required": True,
                "exact_frozen_huggingface_tokenizer_required": True,
                "frozen_local_base_model_required": True,
                "explicit_training_spend_authorization_required": True,
                "development_only_checkpoint_selection": True,
                "sealed_evaluation_open_once_after_recipe_freeze": True,
                "provisional_rows_allowed": False,
            },
        }
        rows = []
        for index in range(5):
            body = {
                "schema_version": "storyworld_training_view_v1",
                "record_id": f"approved-source-{index}",
                "view": "sft_policy",
                "source_split": "train",
                "training_eligible": True,
                "training_approved": True,
                "arm": "jinn",
                "slice": "stateful_actor_trajectories",
                "messages": [
                    {"role": "user", "content": f"prompt {index}"},
                    {"role": "assistant", "content": f"target {index}"},
                ],
            }
            rows.append({**body, "record_sha256": sha256_json(body)})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "sft_policy.jsonl"
            source_path.write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                encoding="utf-8",
            )
            trace_rows = [{"trace_id": "trace_test_provenance"}]
            traces_path = root / "approved_traces.jsonl"
            traces_path.write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in trace_rows),
                encoding="utf-8",
            )
            job_evidence = [{"job_id": "job-test"}]
            harvest_manifest = {
                "schema_version": "storyworld_harvest_approved_release_manifest_v1",
                "status": "approved_real_teacher_traces_for_canonical_derivation",
                "approved_traces_sha256": sha256_file(traces_path),
                "training_approved_traces": len(trace_rows),
                "trace_content_sha256": [sha256_json(row) for row in trace_rows],
                "job_evidence": job_evidence,
                "job_evidence_sha256": sha256_json(job_evidence),
                "release_builder_sha256": sha256_file(
                    REPO_ROOT / "scripts" / "prepare_storyworld_harvest_release.py"
                ),
                "passed": True,
            }
            harvest_manifest_path = root / "HARVEST_RELEASE_MANIFEST.json"
            harvest_manifest_path.write_text(
                json.dumps(harvest_manifest), encoding="utf-8"
            )
            source_manifest = {
                "schema_version": "storyworld_canonical_release_manifest_v1",
                "release_status": "review_approved",
                "source_trace_provenance_complete": True,
                "source_trace_sha256": [sha256_json(row) for row in trace_rows],
                "source_trace_artifacts": [
                    {
                        "kind": "approved_harvest_traces",
                        "path": str(traces_path),
                        "rows": len(trace_rows),
                        "sha256": sha256_file(traces_path),
                        "source_manifest_path": str(harvest_manifest_path),
                        "source_manifest_sha256": sha256_file(
                            harvest_manifest_path
                        ),
                    }
                ],
                "derivation_module_sha256": sha256_file(
                    REPO_ROOT / "alignment_harness" / "trajectory_curriculum.py"
                ),
                "views": {
                    "sft_policy": {
                        "path": source_path.name,
                        "rows": len(rows),
                        "sha256": sha256_file(source_path),
                    }
                },
            }
            source_manifest_path = root / "MANIFEST.json"
            source_manifest_path.write_text(
                json.dumps(source_manifest), encoding="utf-8"
            )
            input_artifacts = [
                {
                    "kind": "canonical_training_view",
                    "view": "sft_policy",
                    "path": str(source_path),
                    "rows": len(rows),
                    "sha256": sha256_file(source_path),
                    "source_manifest_path": str(source_manifest_path),
                    "source_manifest_sha256": sha256_file(source_manifest_path),
                }
            ]
            indexed = validate_training_input_artifacts(
                input_artifacts, relative_to=root
            )
            self.assertEqual(set(indexed), {row["record_id"] for row in rows})

            packed_dir = root / "packed"
            pack_curriculum(
                rows,
                token_recipe,
                packed_dir,
                FixedProductionCounter(),
                input_artifacts=input_artifacts,
            )
            packing_manifest_path = packed_dir / "PACKING_MANIFEST.json"
            clean_audit = audit_packed_curriculum_for_training(
                packing_manifest_path, training_recipe, token_recipe
            )
            self.assertTrue(clean_audit["passed"])

            arm_path = packed_dir / "jinn.jsonl"
            packed_rows = read_jsonl(arm_path)
            packed_rows[0]["messages"][-1]["content"] = "unapproved replacement"
            arm_path.write_text(
                "".join(
                    json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                    for row in packed_rows
                ),
                encoding="utf-8",
            )
            tampered_manifest = read_json(packing_manifest_path)
            tampered_manifest["arms"]["jinn"]["sha256"] = sha256_file(arm_path)
            packing_manifest_path.write_text(
                json.dumps(tampered_manifest), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "approved source"):
                audit_packed_curriculum_for_training(
                    packing_manifest_path, training_recipe, token_recipe
                )

            pack_curriculum(
                rows,
                token_recipe,
                packed_dir,
                FixedProductionCounter(),
                input_artifacts=input_artifacts,
            )
            incomplete_manifest = read_json(packing_manifest_path)
            packed_rows = read_jsonl(arm_path)
            final_checkpoint = incomplete_manifest["arms"]["jinn"]["checkpoints"][-1]
            final_checkpoint["reached_after_row"] = 4
            final_checkpoint["actual_cumulative_tokens"] = 400
            final_checkpoint["actual_cumulative_assistant_tokens"] = 200
            final_checkpoint["prefix_sha256"] = sha256_json(packed_rows[:4])
            final_checkpoint["slices"]["stateful_actor_trajectories"][
                "actual_tokens"
            ] = 400
            final_checkpoint["slices"]["stateful_actor_trajectories"][
                "actual_assistant_tokens"
            ] = 200
            packing_manifest_path.write_text(
                json.dumps(incomplete_manifest), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "complete stream"):
                audit_packed_curriculum_for_training(
                    packing_manifest_path, training_recipe, token_recipe
                )

    def test_sealed_result_binds_exact_authorized_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapters = [
                {"arm": arm, "adapter_artifact_set_sha256": sha256_json({"arm": arm})}
                for arm in ("neutral", "constitutional", "jinn", "beast")
            ]
            authorization = {
                "schema_version": "storyworld_one_time_unseal_authorization_v1",
                "protocol_id": "sealed-protocol-test",
                "unseal_authorization_id": "unseal-test",
                "status": "authorized_not_yet_opened",
                "sealed_content_opened": False,
                "evaluation_families": 6,
                "selected_checkpoint_tokens": 3_000_000,
                "adapter_checkpoints": adapters,
                "passed": True,
            }
            authorization_path = root / "authorization.json"
            authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
            results = {
                "schema_version": "storyworld_external_sealed_evaluation_result_v1",
                "protocol_id": authorization["protocol_id"],
                "unseal_authorization_id": authorization["unseal_authorization_id"],
                "unseal_authorization_sha256": sha256_file(authorization_path),
                "evaluation_families": 6,
                "training_rows_emitted": 0,
                "metric_or_contrast_changes_after_unseal": False,
                "adapter_checkpoints": adapters,
                "signed_at": "2026-07-16T12:02:00-04:00",
                "signature_or_external_receipt": "external-signature",
                "result_summary": {"primary_contrast": 0.25},
                "passed": True,
            }
            results_path = root / "results.json"
            results_path.write_text(json.dumps(results), encoding="utf-8")
            receipt = record_sealed_evaluation(authorization_path, results_path)
            self.assertTrue(receipt["one_time_unseal"])
            self.assertFalse(receipt["additional_unseal_allowed"])

            drifted_results = deepcopy(results)
            drifted_results["adapter_checkpoints"] = adapters[:-1]
            drifted_path = root / "drifted-results.json"
            drifted_path.write_text(json.dumps(drifted_results), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different adapters"):
                record_sealed_evaluation(authorization_path, drifted_path)

    def test_review_hash_and_receipt_gate_exclude_only_workflow_state(self) -> None:
        original_hash = reviewable_world_sha256(self.amanah)
        reviewed = deepcopy(self.amanah)
        reviewed["review"]["status"] = "approved"
        for requirement in reviewed["review"]["requirements"]:
            requirement["status"] = "approved"
            requirement["receipt"] = f"storyworld-review:{requirement['review_type']}"
        self.assertEqual(reviewable_world_sha256(reviewed), original_hash)
        validate_world(reviewed)

        invalid = deepcopy(reviewed)
        invalid["review"]["requirements"][0]["receipt"] = None
        with self.assertRaisesRegex(ValueError, "approved without receipt"):
            validate_world(invalid)

        task_id = "review_test_content_v1"
        queue = {
            "schema_version": "storyworld_review_queue_v1",
            "review_tasks": [
                {
                    "review_task_id": task_id,
                    "reviewable_content_sha256": original_hash,
                    "review_type": "quranic_scholar",
                }
            ],
        }
        receipt = {
            "schema_version": "storyworld_review_receipt_v1",
            "review_task_id": task_id,
            "review_type": "quranic_scholar",
            "reviewer_pseudonym": "reviewer-17",
            "decision": "approved",
            "scope_notes": "Reviewed the declared motif scope and bounded claim.",
            "content_sha256": original_hash,
            "signed_at": "2026-07-16T22:30:00-04:00",
            "signature_or_external_receipt": "external-review-system:receipt-17",
        }
        result = validate_review_receipts(queue, [receipt])
        self.assertTrue(result["complete"])
        self.assertEqual(result["approved"], 1)

        stale = deepcopy(receipt)
        stale["content_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "different substantive content"):
            validate_review_receipts(queue, [stale])
        wrong_type = {**receipt, "review_type": "research_ethics"}
        with self.assertRaisesRegex(ValueError, "wrong review type"):
            validate_review_receipts(queue, [wrong_type])

    def test_manifest_only_split_freeze_rejects_cluster_and_sealed_source_leakage(self) -> None:
        inventory = read_json(INVENTORY_PATH)
        split_freeze = read_json(SPLIT_FREEZE_PATH)
        receipt = validate_split_freeze(inventory, split_freeze, repo_root=REPO_ROOT)

        self.assertEqual(receipt["family_counts"], {"train": 12, "development": 4, "evaluation": 6})
        self.assertEqual(receipt["unique_causal_clusters"], 22)
        self.assertEqual(receipt["source_dispositions"], 17)
        self.assertEqual(
            receipt["train_motifs"],
            ["amanah", "ghayb_boundary", "mizan", "shura", "tawbah"],
        )
        self.assertEqual(len(receipt["implemented_families"]), 16)
        self.assertFalse(receipt["sealed_content_opened"])

        cluster_collision = deepcopy(split_freeze)
        cluster_collision["families"][1]["causal_cluster_id"] = cluster_collision["families"][0]["causal_cluster_id"]
        with self.assertRaisesRegex(ValueError, "causal cluster collision"):
            validate_split_freeze(inventory, cluster_collision, repo_root=REPO_ROOT, schema_path=None)

        sealed_to_train = deepcopy(split_freeze)
        sealed_to_train["families"][0]["origin_source_ids"].append("unwatched_ledger_ca_eval_v1")
        with self.assertRaisesRegex(ValueError, "sealed source"):
            validate_split_freeze(inventory, sealed_to_train, repo_root=REPO_ROOT, schema_path=None)

    def test_blinded_eval_protocol_exposes_only_family_briefs_and_closed_gate(self) -> None:
        split_freeze = read_json(SPLIT_FREEZE_PATH)
        protocol = read_json(BLINDED_EVAL_PROTOCOL_PATH)
        receipt = validate_blinded_eval_protocol(split_freeze, protocol)

        self.assertEqual(receipt["evaluation_families"], 6)
        self.assertEqual(receipt["development_families"], 4)
        self.assertEqual(receipt["unseal_gate"], "closed")
        self.assertFalse(receipt["sealed_content_opened"])
        eval_families = [
            item for item in split_freeze["families"] if item["assigned_split"] == "evaluation"
        ]
        self.assertTrue(all(item["sealed"] for item in eval_families))
        self.assertTrue(all(not item["content_paths"] for item in eval_families))

        opened = deepcopy(protocol)
        opened["unseal_gate"]["status"] = "open"
        with self.assertRaisesRegex(ValueError, "schema failure"):
            validate_blinded_eval_protocol(split_freeze, opened)

    def test_mizan_actor_context_keeps_advocate_conflict_private(self) -> None:
        engine = StoryworldEngine(self.mizan, seed=19)
        view, mapping = engine.actor_view()
        rendered = json.dumps(view, sort_keys=True)

        self.assertIn("duplicate_invoice", rendered)
        self.assertNotIn("advocate_conflict", rendered)
        self.assertNotIn("ground_truth", rendered)
        self.assertTrue(all(action["action_key"] not in rendered for action in mapping.values()))
        tasks = build_world_model_tasks(self.mizan, seed=19)
        self.assertEqual({task["task_type"] for task in tasks}, {
            "legal_action_recognition",
            "next_state_prediction",
            "belief_state_tracking",
            "fact_vs_allegation",
            "counterfactual_branch_evaluation",
            "contradiction_detection",
            "reachable_repair",
            "obligation_vs_dynamics",
        })

    def test_tawbah_actor_context_and_world_model_tasks_respect_private_evidence(self) -> None:
        engine = StoryworldEngine(self.tawbah, seed=23)
        view, mapping = engine.actor_view()
        rendered = json.dumps(view, sort_keys=True)

        self.assertIn("muted_alarm", rendered)
        self.assertNotIn("backup_sensor_log", rendered)
        self.assertNotIn("ground_truth", rendered)
        self.assertTrue(all(action["action_key"] not in rendered for action in mapping.values()))
        self.assertEqual(
            {task["task_type"] for task in build_world_model_tasks(self.tawbah, seed=23)},
            {
                "legal_action_recognition",
                "next_state_prediction",
                "belief_state_tracking",
                "fact_vs_allegation",
                "counterfactual_branch_evaluation",
                "contradiction_detection",
                "reachable_repair",
                "obligation_vs_dynamics",
            },
        )

    def test_shura_actor_context_and_world_model_tasks_respect_private_evidence(self) -> None:
        engine = StoryworldEngine(self.shura, seed=29)
        view, mapping = engine.actor_view()
        rendered = json.dumps(view, sort_keys=True)

        self.assertIn("rollback_key_expiry", rendered)
        self.assertNotIn("shadow_access_failure", rendered)
        self.assertNotIn("ground_truth", rendered)
        self.assertTrue(all(action["action_key"] not in rendered for action in mapping.values()))
        self.assertEqual(
            {task["task_type"] for task in build_world_model_tasks(self.shura, seed=29)},
            {
                "legal_action_recognition",
                "next_state_prediction",
                "belief_state_tracking",
                "fact_vs_allegation",
                "counterfactual_branch_evaluation",
                "contradiction_detection",
                "reachable_repair",
                "obligation_vs_dynamics",
            },
        )

    def test_openai_teacher_contract_rejects_hidden_facts_and_missing_action_forecasts(self) -> None:
        view, _ = StoryworldEngine(self.shura, seed=31).actor_view()
        request = {
            "schema_version": "storyworld_teacher_request_v1",
            "role": "actor",
            "task_type": "episode_action",
            "model_id": "gpt-5.6-sol",
            "reasoning_effort": "low",
            "instructions": "Return a bounded work product.",
            "response_contract": {},
            "input": {"actor_view": view},
        }
        schema = response_schema(request)
        self.assertEqual(schema["properties"]["action_id"]["enum"], [
            action["action_id"] for action in view["legal_actions"]
        ])

        action_id = view["legal_actions"][0]["action_id"]
        invalid = {
            "observed_facts": ["shadow_access_failure"],
            "uncertainties": ["The downstream branch remains uncertain."],
            "forecast": [
                {
                    "action_id": action_id,
                    "predicted_outcome": "A bounded transition follows.",
                    "probability": 0.6,
                }
            ],
            "action_id": action_id,
            "public_reason": "The choice preserves a reviewable path.",
            "responsibility_attribution": "Responsibility follows visible evidence.",
            "counterfactual": "Another action changes the timing tradeoff.",
            "confidence": 0.6,
        }
        self.assertTrue(any("hidden or unknown fact" in item for item in semantic_errors(request, invalid)))

        candidate = deepcopy(invalid)
        candidate["observed_facts"] = [view["observed_facts"][0]["fact_id"]]
        revised_target = deepcopy(candidate)
        revised_target["public_reason"] = "The reviewed reason is more precisely grounded."
        adjudication_request = {
            **request,
            "task_type": "adjudicate_and_repair",
            "input": {"actor_view": view, "candidate": candidate},
        }
        wrong_rejected = next(
            action["action_id"]
            for action in view["legal_actions"]
            if action["action_id"] != candidate["action_id"]
        )
        adjudication = {
            "status": "accepted",
            "critique": "The reason required a grounding correction.",
            "target": revised_target,
            "rejected_action_id": wrong_rejected,
            "remaining_uncertainty": "Later consequences remain uncertain.",
        }
        self.assertTrue(
            any(
                "candidate action" in item
                for item in semantic_errors(adjudication_request, adjudication)
            )
        )
        adjudication["rejected_action_id"] = candidate["action_id"]
        self.assertEqual(semantic_errors(adjudication_request, adjudication), [])

    def test_command_teacher_accepts_response_and_provider_receipt_envelope(self) -> None:
        request = {
            "schema_version": "storyworld_teacher_request_v1",
            "model_id": "gpt-5.6-sol",
            "reasoning_effort": "high",
        }
        response = {"questions": ["q1", "q2", "q3"]}
        envelope = {
            "response": response,
            "provider_receipt": {
                "provider": "openai_responses_api",
                "requested_model": request["model_id"],
                "reasoning_effort": request["reasoning_effort"],
                "store": False,
                "response_content_sha256": sha256_json(response),
                "attempts": [
                    {
                        "attempt": 1,
                        "api_response_id": "resp_fixture",
                        "resolved_model": "gpt-5.6-sol-2026-07-01",
                        "request_payload_sha256": sha256_json({"request": 1}),
                        "output_text_sha256": sha256_json({"output": 1}),
                        "usage": {"input_tokens": 100, "output_tokens": 20},
                    }
                ],
            },
        }
        completed = subprocess.CompletedProcess(
            args=["fixture-command"],
            returncode=0,
            stdout=json.dumps(envelope),
            stderr="",
        )
        teacher = CommandTeacher(["fixture-command"])
        with patch("alignment_harness.trajectory_curriculum.subprocess.run", return_value=completed):
            self.assertEqual(teacher.generate(request), envelope["response"])
        self.assertEqual(teacher.call_receipt(), envelope["provider_receipt"])
        self.assertTrue(teacher.receipt()["release_eligible"])

        bare = subprocess.CompletedProcess(
            args=["fixture-command"],
            returncode=0,
            stdout=json.dumps(response),
            stderr="",
        )
        bare_teacher = CommandTeacher(["fixture-command"])
        with patch("alignment_harness.trajectory_curriculum.subprocess.run", return_value=bare):
            self.assertEqual(bare_teacher.generate(request), response)
        self.assertFalse(bare_teacher.receipt()["release_eligible"])

        stale = deepcopy(envelope)
        stale["provider_receipt"]["response_content_sha256"] = sha256_json(
            {"different": True}
        )
        stale_completed = subprocess.CompletedProcess(
            args=["fixture-command"],
            returncode=0,
            stdout=json.dumps(stale),
            stderr="",
        )
        with patch(
            "alignment_harness.trajectory_curriculum.subprocess.run",
            return_value=stale_completed,
        ):
            with self.assertRaisesRegex(ValueError, "parsed response"):
                CommandTeacher(["fixture-command"]).generate(request)

    def test_harvest_job_release_replays_a_receipted_approved_trace(self) -> None:
        class ReceiptedFixtureTeacher(ScriptedTeacher):
            def __init__(self) -> None:
                super().__init__(
                    actor_strategy="last",
                    adjudicator_strategy="first",
                    provider_name="command_agent_adapter",
                )
                self.calls = 0
                self.last_receipt: dict[str, object] = {}

            def generate(self, request: dict[str, object]) -> dict[str, object]:
                response = super().generate(request)
                self.calls += 1
                self.last_receipt = {
                    "provider": "openai_responses_api",
                    "requested_model": request["model_id"],
                    "reasoning_effort": request["reasoning_effort"],
                    "store": False,
                    "response_content_sha256": sha256_json(response),
                    "attempts": [
                        {
                            "attempt": 1,
                            "api_response_id": f"resp_fixture_{self.calls}",
                            "resolved_model": "gpt-5.6-sol-test",
                            "request_payload_sha256": sha256_json(
                                {"call": self.calls, "request": request}
                            ),
                            "output_text_sha256": sha256_json(response),
                            "usage": {"input_tokens": 100, "output_tokens": 25},
                        }
                    ],
                }
                return response

            def call_receipt(self) -> dict[str, object]:
                return deepcopy(self.last_receipt)

            def receipt(self) -> dict[str, object]:
                return {
                    "provider": "command_agent_adapter",
                    "command": ["receipted-fixture"],
                    "timeout_seconds": 1,
                    "total_calls": self.calls,
                    "provider_receipted_calls": self.calls,
                    "release_eligible": self.calls > 0,
                }

        approved_world = deepcopy(self.amanah)
        approved_world["review"]["status"] = "approved"
        for requirement in approved_world["review"]["requirements"]:
            requirement["status"] = "approved"
            requirement["receipt"] = f"fixture:{requirement['review_type']}"
        trace = harvest_episode(
            approved_world,
            "jinn",
            101,
            ReceiptedFixtureTeacher(),
            self.ensemble,
            created_at="2026-07-16T00:00:00+00:00",
        )
        self.assertTrue(trace["release"]["training_approved"])
        job = {
            "schema_version": "storyworld_harvest_job_v1",
            "job_id": "job_receipted_fixture",
            "campaign_id": "fixture_campaign",
            "arm": "jinn",
            "family_id": approved_world["family_id"],
            "sweep_path": "fixture_sweep.json",
            "profile_id": "fixture",
            "world_id": approved_world["world_id"],
            "world_content_sha256": sha256_json(approved_world),
            "transition_graph_sha256": trace["episode"]["transition_graph_sha256"],
            "episode_seed": 101,
            "actor_schedule_mode": "single",
            "actor_schedule": [approved_world["actor_agent_id"]],
            "teacher_mode": "command",
            "agent_command": "receipted-fixture",
            "source_split": "train",
            "training_eligible": True,
            "review_status": "approved",
            "execution_eligible": True,
            "pilot_job": True,
            "family_ordinal": 0,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs_path = root / "pilot_jobs.jsonl"
            jobs_path.write_text(json.dumps(job) + "\n", encoding="utf-8")
            output_dir = root / "outputs" / job["job_id"]
            output_dir.mkdir(parents=True)
            trace_path = output_dir / "trace.jsonl"
            trace_path.write_text(json.dumps(trace) + "\n", encoding="utf-8")
            receipt = {
                "schema_version": "storyworld_harvest_job_receipt_v1",
                "job_id": job["job_id"],
                "job_sha256": sha256_json(job),
                "jobs_file_sha256": sha256_file(jobs_path),
                "trace_id": trace["trace_id"],
                "trace_sha256": sha256_file(trace_path),
                "training_approved": True,
                "passed": True,
            }
            (output_dir / "JOB_RECEIPT.json").write_text(
                json.dumps(receipt), encoding="utf-8"
            )
            observed_trace, evidence = validate_harvest_job_evidence(
                job,
                jobs_path=jobs_path,
                trace_root=root / "outputs",
                world=approved_world,
                full_authorization=None,
                full_authorization_path=None,
            )
            self.assertEqual(observed_trace["trace_id"], trace["trace_id"])
            self.assertEqual(evidence["provider_receipted_calls"], 36)

    def test_instance_sweep_materializes_matched_profiles_and_trace_provenance(self) -> None:
        worlds, receipt = materialize_instance_sweep(REPO_ROOT, SHURA_SWEEP_PATH)
        self.assertEqual(receipt["profiles"], 8)
        self.assertEqual(receipt["materialized_worlds"], 16)
        self.assertTrue(all(value >= 2 for value in receipt["factor_cardinality"].values()))

        by_id = {world["world_id"]: world for world in worlds}
        shared = by_id["shura_payroll_cutover_train_v1__shared_observation"]
        shared_control = by_id["participatory_cutover_train_v1__shared_observation"]
        self.assertTrue(validate_matched_pair(shared, shared_control)["passed"])
        view, _ = StoryworldEngine(shared, seed=37).actor_view()
        self.assertIn("shadow_access_failure", json.dumps(view, sort_keys=True))

        trace = harvest_episode(
            shared,
            "neutral",
            37,
            ScriptedTeacher(),
            self.ensemble,
            created_at="2026-07-16T00:00:00+00:00",
        )
        self.assertEqual(trace["episode"]["instance_provenance"]["profile_id"], "shared_observation")
        self.assertEqual(
            trace["episode"]["instance_provenance"]["base_world_id"],
            "shura_payroll_cutover_train_v1",
        )

    def test_instance_sweep_materializes_standalone_profiles(self) -> None:
        worlds, receipt = materialize_instance_sweep(REPO_ROOT, COMMON_WELL_SWEEP_PATH)
        self.assertEqual(receipt["profiles"], 6)
        self.assertEqual(receipt["materialized_worlds"], 6)
        self.assertTrue(all(value >= 2 for value in receipt["factor_cardinality"].values()))
        self.assertTrue(all(world["matched_pair"] is None for world in worlds))
        self.assertTrue(
            all(item["matched_pair"] is None for item in receipt["profile_receipts"])
        )

        shared = next(
            world for world in worlds if world["world_id"].endswith("__shared_repair_forecast")
        )
        view, _ = StoryworldEngine(shared, seed=41, actor_agent_id="custodian").actor_view()
        self.assertIn("repair_forecast", json.dumps(view, sort_keys=True))
        trace = harvest_episode(
            shared,
            "neutral",
            41,
            ScriptedTeacher(),
            self.ensemble,
            created_at="2026-07-16T00:00:00+00:00",
        )
        self.assertEqual(
            trace["episode"]["instance_provenance"]["profile_id"],
            "shared_repair_forecast",
        )

    def test_dyadic_harvest_alternates_declared_seats_and_private_evidence(self) -> None:
        trace = harvest_episode(
            self.shura,
            "jinn",
            3,
            ScriptedTeacher(actor_strategy="last"),
            self.ensemble,
            actor_schedule=["coordinator", "liaison"],
            created_at="2026-07-16T00:00:00+00:00",
        )
        self.assertEqual(trace["episode"]["actor_schedule"], ["coordinator", "liaison"])
        self.assertEqual(
            [turn["acting_agent_id"] for turn in trace["turns"]],
            ["coordinator", "liaison", "coordinator", "liaison", "coordinator", "liaison"],
        )
        seats = {agent["agent_id"]: agent["seat"] for agent in self.shura["agents"]}
        self.assertEqual(
            [turn["acting_seat"] for turn in trace["turns"]],
            [seats[turn["acting_agent_id"]] for turn in trace["turns"]],
        )
        liaison_turn = trace["turns"][1]
        self.assertIn(
            "shadow_access_failure",
            {item["fact_id"] for item in liaison_turn["model_visible"]["observed_facts"]},
        )
        views = derive_trace_views(trace, allow_provisional=True)
        for index, row in enumerate(views["sft_policy"]):
            prompt = json.loads(row["messages"][1]["content"])
            self.assertEqual(len(prompt["episode_prefix"]), index)
            self.assertEqual(
                prompt["acting_seat"], trace["turns"][index]["acting_seat"]
            )
            for historical_turn in prompt["episode_prefix"]:
                self.assertEqual(
                    set(historical_turn),
                    {
                        "turn_index",
                        "acting_agent_id",
                        "acting_seat",
                        "executed_action",
                        "public_outcome",
                        "visible_state_after",
                    },
                )
        interrogation_target = json.loads(
            views["sft_interrogation"][0]["messages"][-1]["content"]
        )
        self.assertIn("factual_state_reconstruction", interrogation_target)
        self.assertIn("counterfactual_consequence_prediction", interrogation_target)

    def test_non_theological_worlds_may_be_standalone_but_motifs_may_not(self) -> None:
        self.assertIsNone(self.common_well["matched_pair"])
        self.assertTrue(validate_world(self.common_well)["passed"])
        view, mapping = StoryworldEngine(self.common_well, seed=43).actor_view()
        rendered = json.dumps(view, sort_keys=True)
        self.assertNotIn("repair_forecast", rendered)
        self.assertTrue(all(action["action_key"] not in rendered for action in mapping.values()))
        self.assertEqual(len({task["task_type"] for task in build_world_model_tasks(self.common_well)}), 8)

        invalid_motif = deepcopy(self.common_well)
        invalid_motif["theological_motif"] = "shura"
        with self.assertRaisesRegex(ValueError, "theological motifs require"):
            validate_world(invalid_motif)

    def test_market_migration_is_original_branching_fiction_with_private_evidence(self) -> None:
        receipt = validate_world(self.market)
        self.assertEqual(receipt["path_turns_min"], 6)
        self.assertEqual(receipt["path_turns_max"], 6)
        self.assertEqual(receipt["reachable_endings"], 3)
        self.assertGreaterEqual(receipt["branch_states"], 2)
        self.assertTrue(receipt["private_evidence"])
        self.assertTrue(
            all(len(frontier) >= 2 for frontier in receipt["pareto_frontier_by_state"].values())
        )
        self.assertNotIn("al-Shushtari", json.dumps(self.market, ensure_ascii=False))

        engine = StoryworldEngine(self.market, seed=53, actor_agent_id="steward")
        for action_key in (
            "accept_anonymous_match",
            "publish_categories_and_totals",
            "issue_revisable_advances",
        ):
            _, mapping = engine.actor_view()
            action_id = next(
                opaque_id
                for opaque_id, action in mapping.items()
                if action["action_key"] == action_key
            )
            engine.step(action_id, mapping)
        steward_view, _ = engine.actor_view()
        self.assertNotIn("wholesaler_inventory_cover", json.dumps(steward_view, sort_keys=True))
        bookkeeper_engine = StoryworldEngine(
            self.market, seed=53, actor_agent_id="bookkeeper"
        )
        for action_key in (
            "accept_anonymous_match",
            "publish_categories_and_totals",
            "issue_revisable_advances",
        ):
            _, mapping = bookkeeper_engine.actor_view()
            action_id = next(
                opaque_id
                for opaque_id, action in mapping.items()
                if action["action_key"] == action_key
            )
            bookkeeper_engine.step(action_id, mapping)
        bookkeeper_view, _ = bookkeeper_engine.actor_view()
        self.assertIn("wholesaler_inventory_cover", json.dumps(bookkeeper_view, sort_keys=True))

    def test_interpretation_migration_bounds_meaning_and_private_conflict(self) -> None:
        receipt = validate_world(self.interpretation)
        self.assertEqual((receipt["path_turns_min"], receipt["path_turns_max"]), (6, 6))
        self.assertEqual(receipt["reachable_endings"], 3)
        self.assertTrue(receipt["private_evidence"])
        self.assertTrue(
            all(len(frontier) >= 2 for frontier in receipt["pareto_frontier_by_state"].values())
        )
        rendered = json.dumps(self.interpretation, ensure_ascii=False)
        self.assertNotIn("Ibn Arabi", rendered)
        self.assertNotIn("Jannah", rendered)

        action_path = (
            "issue_bounded_corridor_order",
            "publish_order_meaning_distinction",
            "triangulate_operational_range",
        )
        views = {}
        for actor_id in ("coordinator", "conservator"):
            engine = StoryworldEngine(self.interpretation, seed=59, actor_agent_id=actor_id)
            for action_key in action_path:
                _, mapping = engine.actor_view()
                action_id = next(
                    opaque_id
                    for opaque_id, action in mapping.items()
                    if action["action_key"] == action_key
                )
                engine.step(action_id, mapping)
            views[actor_id], _ = engine.actor_view()
        self.assertNotIn("administrator_conflict", json.dumps(views["coordinator"], sort_keys=True))
        self.assertIn("administrator_conflict", json.dumps(views["conservator"], sort_keys=True))

    def test_service_migration_separates_need_from_reward_and_purity(self) -> None:
        receipt = validate_world(self.service)
        self.assertEqual((receipt["path_turns_min"], receipt["path_turns_max"]), (6, 6))
        self.assertEqual(receipt["reachable_endings"], 3)
        self.assertTrue(receipt["private_evidence"])
        self.assertTrue(
            all(len(frontier) >= 2 for frontier in receipt["pareto_frontier_by_state"].values())
        )
        rendered = json.dumps(self.service, ensure_ascii=False)
        self.assertNotIn("Rabia", rendered)
        self.assertNotIn("Jannah", rendered)

        action_path = (
            "accept_quiet_grant",
            "publish_criteria_and_totals",
            "issue_revisable_shared_delivery",
        )
        views = {}
        for actor_id in ("dispatcher", "field_lead"):
            engine = StoryworldEngine(self.service, seed=61, actor_agent_id=actor_id)
            for action_key in action_path:
                _, mapping = engine.actor_view()
                action_id = next(
                    opaque_id
                    for opaque_id, action in mapping.items()
                    if action["action_key"] == action_key
                )
                engine.step(action_id, mapping)
            views[actor_id], _ = engine.actor_view()
        self.assertNotIn("auditorium_backup", json.dumps(views["dispatcher"], sort_keys=True))
        self.assertIn("auditorium_backup", json.dumps(views["field_lead"], sort_keys=True))

    def test_knowledge_risk_migration_neither_defers_to_nor_discards_expertise(self) -> None:
        receipt = validate_world(self.knowledge_risk)
        self.assertEqual((receipt["path_turns_min"], receipt["path_turns_max"]), (6, 6))
        self.assertEqual(receipt["reachable_endings"], 3)
        self.assertTrue(receipt["private_evidence"])
        self.assertTrue(
            all(len(frontier) >= 2 for frontier in receipt["pareto_frontier_by_state"].values())
        )
        rendered = json.dumps(self.knowledge_risk, ensure_ascii=False)
        self.assertNotIn("Suhrawardi", rendered)
        self.assertNotIn("Jannah", rendered)

        action_path = (
            "isolate_near_sectors_and_monitor",
            "publish_risk_and_claim_separately",
            "triangulate_with_calibration_bounds",
        )
        views = {}
        for actor_id in ("commander", "instrument_tech"):
            engine = StoryworldEngine(self.knowledge_risk, seed=67, actor_agent_id=actor_id)
            for action_key in action_path:
                _, mapping = engine.actor_view()
                action_id = next(
                    opaque_id
                    for opaque_id, action in mapping.items()
                    if action["action_key"] == action_key
                )
                engine.step(action_id, mapping)
            views[actor_id], _ = engine.actor_view()
        self.assertNotIn("model_validation_gap", json.dumps(views["commander"], sort_keys=True))
        self.assertIn("model_validation_gap", json.dumps(views["instrument_tech"], sort_keys=True))

    def test_ghayb_boundary_pair_shares_graph_and_scrubs_secular_language(self) -> None:
        pair = validate_matched_pair(self.ghayb, self.ghayb_secular)
        self.assertTrue(pair["passed"])
        self.assertEqual(
            pair["transition_graph_sha256"],
            "13396a1e1c0bc7745cc3d08ffdb10912d1e479a8e1b31cfefec97714fb65c809",
        )
        self.assertEqual(self.ghayb["theological_motif"], "ghayb_boundary")
        self.assertIsNone(self.ghayb_secular["theological_motif"])

        language_parts = [self.ghayb_secular["title"], self.ghayb_secular["construct"]]
        language_parts.extend(fact["text"] for fact in self.ghayb_secular["facts"])
        language_parts.extend(item["statement"] for item in self.ghayb_secular["obligations"])
        for state in self.ghayb_secular["states"]:
            language_parts.append(state["public_observation"])
            language_parts.extend(state["private_observations"].values())
            for action in state["actions"]:
                language_parts.extend([action["text"], action["public_outcome"]])
                language_parts.extend(action["private_outcomes"].values())
                language_parts.extend(item["text"] for item in action["consequences"])
        secular_language = " ".join(language_parts).lower()
        for identity_term in ("ghayb", "unseen", "spiritual", "theolog", "revelation"):
            self.assertNotIn(identity_term, secular_language)

        action_path = (
            "split_search_with_eastern_check",
            "publish_evidence_basis_separately",
            "triangulate_ordinary_evidence",
        )
        views = {}
        for actor_id in ("search_coordinator", "signal_analyst"):
            engine = StoryworldEngine(self.ghayb, seed=71, actor_agent_id=actor_id)
            for action_key in action_path:
                _, mapping = engine.actor_view()
                action_id = next(
                    opaque_id
                    for opaque_id, action in mapping.items()
                    if action["action_key"] == action_key
                )
                engine.step(action_id, mapping)
            views[actor_id], _ = engine.actor_view()
        self.assertNotIn(
            "claim_timestamp", json.dumps(views["search_coordinator"], sort_keys=True)
        )
        self.assertIn("claim_timestamp", json.dumps(views["signal_analyst"], sort_keys=True))

    def test_disclosure_migration_penalizes_both_raw_and_under_notice(self) -> None:
        receipt = validate_world(self.disclosure)
        self.assertEqual((receipt["path_turns_min"], receipt["path_turns_max"]), (6, 6))
        self.assertEqual(receipt["reachable_endings"], 3)
        self.assertTrue(receipt["private_evidence"])
        self.assertTrue(
            all(len(frontier) >= 2 for frontier in receipt["pareto_frontier_by_state"].values())
        )

        action_path = (
            "contain_and_issue_targeted_alert",
            "publish_scope_not_names",
            "separate_scope_attribution_and_harm",
        )
        views = {}
        for actor_id in ("incident_coordinator", "privacy_analyst"):
            engine = StoryworldEngine(self.disclosure, seed=73, actor_agent_id=actor_id)
            for action_key in action_path:
                _, mapping = engine.actor_view()
                action_id = next(
                    opaque_id
                    for opaque_id, action in mapping.items()
                    if action["action_key"] == action_key
                )
                engine.step(action_id, mapping)
            views[actor_id], _ = engine.actor_view()
        coordinator_text = json.dumps(views["incident_coordinator"], sort_keys=True)
        analyst_text = json.dumps(views["privacy_analyst"], sort_keys=True)
        self.assertNotIn("log_private_routines", coordinator_text)
        self.assertNotIn("shared_update_key", coordinator_text)
        self.assertIn("log_private_routines", analyst_text)
        self.assertIn("shared_update_key", analyst_text)

    def test_exogenous_failure_separates_cause_from_response_duty(self) -> None:
        receipt = validate_world(self.exogenous_failure)
        self.assertEqual(
            receipt["transition_graph_sha256"],
            "feade0456d9699af95d14ba404758d663697bd55d3eb4da2e18a9fbe58249041",
        )
        self.assertEqual((receipt["path_turns_min"], receipt["path_turns_max"]), (6, 6))
        self.assertEqual(receipt["reachable_endings"], 3)
        self.assertTrue(receipt["private_evidence"])
        self.assertTrue(
            all(len(frontier) >= 2 for frontier in receipt["pareto_frontier_by_state"].values())
        )

        action_path = (
            "issue_logged_emergency_vouchers",
            "publish_provisional_cause_and_response_duties",
            "separate_external_cause_and_response",
        )
        views = {}
        for actor_id in ("response_coordinator", "systems_analyst"):
            engine = StoryworldEngine(
                self.exogenous_failure, seed=79, actor_agent_id=actor_id
            )
            for action_key in action_path:
                _, mapping = engine.actor_view()
                action_id = next(
                    opaque_id
                    for opaque_id, action in mapping.items()
                    if action["action_key"] == action_key
                )
                engine.step(action_id, mapping)
            views[actor_id], _ = engine.actor_view()
        coordinator_text = json.dumps(views["response_coordinator"], sort_keys=True)
        analyst_text = json.dumps(views["systems_analyst"], sort_keys=True)
        self.assertNotIn("signed_vendor_package", coordinator_text)
        self.assertNotIn("local_config_unchanged", coordinator_text)
        self.assertIn("signed_vendor_package", analyst_text)
        self.assertIn("local_config_unchanged", analyst_text)

    def test_development_worlds_are_executable_but_cannot_emit_training_views(self) -> None:
        development_worlds = (
            self.shahada_dev,
            self.testimony_control_dev,
            self.reset_dev,
            self.intercessor_dev,
            self.public_witness_dev,
        )
        graph_hashes = set()
        for world in development_worlds:
            receipt = validate_world(world)
            self.assertEqual(receipt["source_split"], "development")
            self.assertFalse(receipt["training_eligible"])
            self.assertEqual((receipt["path_turns_min"], receipt["path_turns_max"]), (6, 6))
            self.assertEqual(receipt["reachable_endings"], 3)
            self.assertTrue(receipt["private_evidence"])
            self.assertTrue(
                all(
                    len(frontier) >= 2
                    for frontier in receipt["pareto_frontier_by_state"].values()
                )
            )
            graph_hashes.add(receipt["transition_graph_sha256"])
        self.assertEqual(len(graph_hashes), 4)

        pair = validate_matched_pair(self.shahada_dev, self.testimony_control_dev)
        self.assertEqual(
            pair["transition_graph_sha256"],
            "9ca55fb031a55e69b476d006eb3beba4b69be7593006fda4097c01e7118bff85",
        )
        language_parts = [
            self.testimony_control_dev["title"],
            self.testimony_control_dev["construct"],
            self.testimony_control_dev["review"]["claim_boundary"],
        ]
        language_parts.extend(fact["text"] for fact in self.testimony_control_dev["facts"])
        language_parts.extend(
            item["statement"] for item in self.testimony_control_dev["obligations"]
        )
        for item in self.testimony_control_dev["states"]:
            language_parts.append(item["public_observation"])
            language_parts.extend(item["private_observations"].values())
            for candidate in item["actions"]:
                language_parts.extend([candidate["text"], candidate["public_outcome"]])
                language_parts.extend(
                    consequence["text"] for consequence in candidate["consequences"]
                )
        secular_language = " ".join(language_parts).lower()
        for identity_term in ("shahada", "quran", "revelation", "sacred reenactment"):
            self.assertNotIn(identity_term, secular_language)

        trace = harvest_episode(
            self.shahada_dev,
            "jinn",
            89,
            ScriptedTeacher(actor_strategy="last"),
            self.ensemble,
            actor_schedule=["hearing_steward", "evidence_custodian"],
            created_at="2026-07-16T00:00:00+00:00",
        )
        self.assertEqual(len(trace["turns"]), 6)
        self.assertFalse(trace["episode"]["training_eligible"])
        with self.assertRaisesRegex(ValueError, "non-training"):
            derive_trace_views(trace, allow_provisional=True)

    def test_actor_view_uses_opaque_ids_and_does_not_leak_private_counterpart_fact(self) -> None:
        engine = StoryworldEngine(self.amanah, seed=7)
        view, mapping = engine.actor_view()
        rendered = json.dumps(view, sort_keys=True)

        self.assertNotIn("clerk_warning", rendered)
        self.assertIn("duplicate_rows", rendered)
        self.assertTrue(all(action_id.startswith("A-") for action_id in mapping))
        self.assertTrue(all(action["action_key"] not in rendered for action in mapping.values()))
        self.assertNotIn("ground_truth", rendered)

        open_id = next(
            opaque for opaque, action in mapping.items() if action["action_key"] == "open_joint_audit"
        )
        engine.step(open_id, mapping)
        open_view, _ = engine.actor_view()

        quiet_engine = StoryworldEngine(self.amanah, seed=7)
        _, quiet_mapping = quiet_engine.actor_view()
        hold_id = next(
            opaque for opaque, action in quiet_mapping.items() if action["action_key"] == "hold_disputed_only"
        )
        quiet_engine.step(hold_id, quiet_mapping)
        quiet_view, _ = quiet_engine.actor_view()
        self.assertNotEqual(
            {item["text"] for item in open_view["legal_actions"]},
            {item["text"] for item in quiet_view["legal_actions"]},
        )

    def test_metta_compiler_derives_all_eight_auxiliary_task_types(self) -> None:
        compilation = compile_world_to_metta(self.amanah)
        tasks = build_world_model_tasks(self.amanah, seed=11)
        task_types = {row["task_type"] for row in tasks}

        self.assertEqual(
            task_types,
            {
                "legal_action_recognition",
                "next_state_prediction",
                "belief_state_tracking",
                "fact_vs_allegation",
                "counterfactual_branch_evaluation",
                "contradiction_detection",
                "reachable_repair",
                "obligation_vs_dynamics",
            },
        )
        self.assertIn("(hidden-from intake steward clerk_warning)", compilation["metta_text"])
        self.assertIn("(repairable c_decision_freeze acknowledge_and_fund_repair)", compilation["metta_text"])
        self.assertIn("not native Hyperon proof execution", compilation["claim_boundary"])
        for task in tasks:
            model_prompt = json.dumps(task["messages"], sort_keys=True)
            self.assertNotIn("ground_truth", model_prompt)
            self.assertNotIn('"proof":', model_prompt)

    def _trace(self, frame: str = "jinn") -> dict:
        return harvest_episode(
            self.amanah,
            frame,
            42,
            ScriptedTeacher(actor_strategy="last", adjudicator_strategy="first"),
            self.ensemble,
            world_source_path=AMANAH_PATH.as_posix(),
            created_at="2026-07-16T00:00:00+00:00",
        )

    def test_multi_effort_harvest_interrogates_and_keeps_fixture_provisional(self) -> None:
        trace = self._trace()
        replay = validate_episode_trace(self.amanah, trace)
        episode_compilation = compile_episode_trace_to_metta(self.amanah, trace)
        efforts = {
            call["reasoning_effort"]
            for turn in trace["turns"]
            for call in turn["teacher_calls"]
        }

        self.assertEqual(len(trace["turns"]), 6)
        self.assertTrue(replay["passed"])
        self.assertEqual(efforts, {"low", "medium", "high", "xhigh"})
        self.assertFalse(trace["reasoning_provenance"]["private_chain_of_thought_requested"])
        self.assertFalse(trace["reasoning_provenance"]["private_chain_of_thought_included"])
        self.assertFalse(trace["release"]["training_approved"])
        self.assertFalse(trace["release"]["teacher_release_eligible"])
        self.assertIn(
            f"(state {trace['trace_id']} t0 public_trust 4)",
            episode_compilation["metta_text"],
        )
        for turn in trace["turns"]:
            self.assertEqual(len(turn["interrogation"]["questions"]), 8)
            self.assertTrue(
                any(
                    "without identity-specific vocabulary" in question
                    for question in turn["interrogation"]["questions"]
                )
            )
            self.assertEqual(turn["review"]["engine_validation"], "passed")
            visible = set(turn["proof_receipts"]["visible_fact_ids"])
            self.assertTrue(
                set(turn["review"]["target"]["observed_facts"]).issubset(visible)
            )
            self.assertNotIn("opaque_action_mapping", turn["model_visible"])

        tampered = deepcopy(trace)
        tampered["turns"][0]["review"]["target"][
            "public_reason"
        ] = "Unreceipted replacement target."
        with self.assertRaisesRegex(ValueError, "response hash"):
            validate_episode_trace(self.amanah, tampered)

    def test_training_views_enforce_review_and_sealed_eval_boundaries(self) -> None:
        trace = self._trace()
        with self.assertRaisesRegex(ValueError, "provisional"):
            derive_trace_views(trace)
        views = derive_trace_views(trace, allow_provisional=True)
        self.assertEqual(len(views["sft_policy"]), 6)
        self.assertEqual(len(views["sft_interrogation"]), 6)
        self.assertEqual(len(views["sft_repair"]), 6)
        self.assertEqual(len(views["preference_pairs"]), 6)
        for row in views["sft_policy"]:
            prompt = json.dumps(row["messages"][:-1], sort_keys=True)
            target = json.loads(row["messages"][-1]["content"])
            self.assertNotIn("action_key", prompt)
            self.assertNotIn("ground_truth", prompt)
            self.assertEqual(len(target["comparative_forecasts"]), 3)
            self.assertIn("observation_regime_change", target["observer_invariance_audit"])
        counter = TiktokenCounter()
        for view, minimum_ratio in (
            ("sft_policy", 0.40),
            ("sft_interrogation", 0.45),
            ("sft_repair", 0.40),
        ):
            packed = assistant = 0
            for row in views[view]:
                row_packed, row_assistant = counter.count_messages(row["messages"])
                packed += row_packed
                assistant += row_assistant
            self.assertGreaterEqual(assistant / packed, minimum_ratio)

        sealed = deepcopy(self.amanah)
        sealed["world_id"] = "sealed_fixture_eval_v1"
        sealed["source_split"] = "evaluation"
        sealed["training_eligible"] = False
        sealed["matched_pair"]["counterpart_world_id"] = "sealed_counterpart_eval_v1"
        with self.assertRaisesRegex(ValueError, "sealed"):
            harvest_episode(
                sealed,
                "neutral",
                1,
                ScriptedTeacher(),
                self.ensemble,
                trace_schema_path=None,
            )

    def test_canonical_release_and_quota_packing_are_deterministic(self) -> None:
        trace = self._trace()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "duplicate trace ID"):
                build_canonical_release(
                    [trace, deepcopy(trace)],
                    {self.amanah["world_id"]: self.amanah},
                    root / "duplicate_release",
                    allow_provisional=True,
                )
            release = build_canonical_release(
                [trace],
                {self.amanah["world_id"]: self.amanah},
                root / "release",
                allow_provisional=True,
            )
            self.assertEqual(
                set(release["views"]),
                {
                    "sft_policy",
                    "sft_world_model",
                    "sft_interrogation",
                    "sft_repair",
                    "preference_pairs",
                    "rl_environment",
                },
            )
            self.assertEqual(release["sealed_evaluation_rows"], 0)
            self.assertEqual(len(release["trace_metta_compilations"]), 1)
            rows = []
            for filename in (
                "sft_policy.jsonl",
                "sft_world_model.jsonl",
                "sft_interrogation.jsonl",
                "sft_repair.jsonl",
            ):
                file_rows = read_jsonl(root / "release" / filename)
                self.assertTrue(all("teacher_provenance" in row for row in file_rows))
                rows.extend(file_rows)
            recipe = {
                "schema_version": "storyworld_token_recipe_v1",
                "recipe_id": "storyworld_smoke_recipe_v1",
                "seed": 9,
                "arms": ["jinn"],
                "target_tokens_per_arm": 2000,
                "minimum_assistant_tokens_per_arm": 100,
                "slice_tokens": {
                    "stateful_actor_trajectories": 500,
                    "interrogation_and_defense": 500,
                    "metta_world_model_tasks": 500,
                    "failure_critique_and_repair": 500,
                },
                "checkpoints": [500, 1000, 1500, 2000],
            }
            counter = TiktokenCounter()
            first = pack_curriculum(
                rows,
                recipe,
                root / "packed_a",
                counter,
                allow_provisional=True,
            )
            second = pack_curriculum(
                rows,
                recipe,
                root / "packed_b",
                counter,
                allow_provisional=True,
            )
            self.assertEqual(first["arms"]["jinn"]["sha256"], second["arms"]["jinn"]["sha256"])
            self.assertGreaterEqual(first["arms"]["jinn"]["actual_tokens"], 2000)
            self.assertGreaterEqual(first["arms"]["jinn"]["actual_assistant_tokens"], 100)
            self.assertEqual(len(first["arms"]["jinn"]["checkpoints"]), 4)
            self.assertEqual(
                first["arms"]["jinn"]["checkpoints"][-1]["reached_after_row"],
                first["arms"]["jinn"]["rows"],
            )
            for slice_receipt in first["arms"]["jinn"]["checkpoints"][-1][
                "slices"
            ].values():
                self.assertGreaterEqual(
                    slice_receipt["actual_tokens"],
                    slice_receipt["scaled_target_tokens"],
                )
            self.assertEqual(first["sealed_evaluation_rows"], 0)

            duplicate_rows = rows + [deepcopy(rows[0])]
            with self.assertRaisesRegex(ValueError, "duplicate quota record_id"):
                pack_curriculum(
                    duplicate_rows,
                    recipe,
                    root / "packed_duplicate",
                    counter,
                    allow_provisional=True,
                )

            relabeled = deepcopy(rows[0])
            relabeled["record_id"] = relabeled["record_id"] + "__relabeled"
            relabeled["source_trace_id"] = "different_metadata_only"
            relabeled["view"] = "metadata_relabel"
            with self.assertRaisesRegex(
                ValueError, "duplicate model-visible quota content"
            ):
                pack_curriculum(
                    rows + [relabeled],
                    recipe,
                    root / "packed_visible_duplicate",
                    counter,
                    allow_provisional=True,
                )

    def test_checkpoint_prefixes_preserve_the_scaled_recipe_mix(self) -> None:
        class FixedCounter:
            description = {"backend": "fixed_test_counter"}

            @staticmethod
            def count_messages(messages: list[dict[str, str]]) -> tuple[int, int]:
                return 100, 50

        slices = (
            "stateful_actor_trajectories",
            "interrogation_and_defense",
            "metta_world_model_tasks",
            "failure_critique_and_repair",
        )
        rows = []
        for slice_id in slices:
            for index in range(4):
                rows.append(
                    {
                        "schema_version": "storyworld_training_view_v1",
                        "record_id": f"{slice_id}_{index}",
                        "source_split": "train",
                        "training_eligible": True,
                        "training_approved": True,
                        "arm": "jinn",
                        "slice": slice_id,
                        "messages": [
                            {"role": "user", "content": f"{slice_id} prompt {index}"},
                            {"role": "assistant", "content": f"{slice_id} target {index}"},
                        ],
                    }
                )
        recipe = {
            "schema_version": "storyworld_token_recipe_v1",
            "recipe_id": "proportional_checkpoint_test_v1",
            "seed": 11,
            "arms": ["jinn"],
            "target_tokens_per_arm": 1600,
            "minimum_assistant_tokens_per_arm": 400,
            "slice_tokens": {slice_id: 400 for slice_id in slices},
            "minimum_assistant_tokens_by_slice": {
                slice_id: 100 for slice_id in slices
            },
            "checkpoints": [400, 800, 1200, 1600],
        }
        with tempfile.TemporaryDirectory() as temporary:
            manifest = pack_curriculum(
                rows,
                recipe,
                Path(temporary),
                FixedCounter(),
            )
            checkpoints = manifest["arms"]["jinn"]["checkpoints"]
            self.assertEqual(len(checkpoints), 4)
            for checkpoint_index, checkpoint in enumerate(checkpoints, start=1):
                expected_per_slice = checkpoint_index * 100
                self.assertEqual(checkpoint["reached_after_row"], checkpoint_index * 4)
                self.assertEqual(len(checkpoint["prefix_sha256"]), 64)
                self.assertEqual(
                    checkpoint["actual_cumulative_assistant_tokens"],
                    checkpoint_index * 200,
                )
                for slice_receipt in checkpoint["slices"].values():
                    self.assertEqual(
                        slice_receipt["scaled_target_tokens"], expected_per_slice
                    )
                    self.assertEqual(slice_receipt["actual_tokens"], expected_per_slice)
                    self.assertEqual(slice_receipt["token_drift"], 0)

    def test_frozen_local_tokenizer_fingerprint_is_content_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tokenizer.json").write_text(
                '{"version":"1.0","model":{}}', encoding="utf-8"
            )
            (root / "tokenizer_config.json").write_text(
                '{"chat_template":"{{ messages }}"}', encoding="utf-8"
            )
            first = _fingerprint_local_tokenizer_dir(root)
            self.assertEqual(len(first["tokenizer_artifact_set_sha256"]), 64)
            self.assertEqual(len(first["tokenizer_artifact_files"]), 2)

            (root / "tokenizer_config.json").write_text(
                '{"chat_template":"{{ messages | list }}"}', encoding="utf-8"
            )
            second = _fingerprint_local_tokenizer_dir(root)
            self.assertNotEqual(
                first["tokenizer_artifact_set_sha256"],
                second["tokenizer_artifact_set_sha256"],
            )

    def test_pilot_recalibration_keeps_arms_families_and_schedules_matched(self) -> None:
        recipe = read_json(
            REPO_ROOT
            / "experiments"
            / "storyworld_curriculum_v1"
            / "token_recipe_10m_per_arm.json"
        )
        totals = {
            arm: {
                "stateful_actor_trajectories": {
                    "packed_tokens": 36_000,
                    "assistant_tokens": 18_000,
                },
                "interrogation_and_defense": {
                    "packed_tokens": 72_000,
                    "assistant_tokens": 36_000,
                },
                "failure_critique_and_repair": {
                    "packed_tokens": 48_000,
                    "assistant_tokens": 24_000,
                },
            }
            for arm in recipe["arms"]
        }
        result = recommend_balanced_trace_count(
            totals,
            {arm: 12 for arm in recipe["arms"]},
            recipe,
            family_count=12,
        )
        self.assertEqual(result["traces_per_family_per_arm"], 126)
        self.assertEqual(result["traces_per_arm"], 1512)
        self.assertEqual(result["full_campaign_jobs"], 6048)
        self.assertEqual(result["traces_per_family_per_arm"] % 2, 0)

        calibration = {
            "schema_version": "storyworld_real_pilot_calibration_v1",
            "campaign_id": "parent_campaign_v1",
            "status": "pilot_passed_pending_human_full_campaign_authorization",
            "passed": True,
            "full_campaign_ready_for_human_authorization": True,
            "recalibrated_campaign": result,
            "pilot_jobs": 48,
            "traces_by_arm": {arm: 12 for arm in recipe["arms"]},
            "pilot_core_token_totals": totals,
            "exact_world_model_availability": {
                arm: {
                    "worlds": 100,
                    "packed_tokens": 2_000_000,
                    "assistant_tokens": 500_000,
                }
                for arm in recipe["arms"]
            },
            "tokenizer": {"tokenizer_artifact_set_sha256": "a" * 64},
        }
        base = read_json(
            REPO_ROOT
            / "experiments"
            / "storyworld_curriculum_v1"
            / "harvest_campaign_10m_v1.json"
        )
        frozen = build_recalibrated_campaign(
            base,
            calibration,
            "b" * 64,
            "postpilot_campaign_v1",
        )
        self.assertEqual(frozen["traces_per_family_per_arm"], 126)
        self.assertEqual(frozen["traces_per_arm"], 1512)
        self.assertEqual(
            frozen["token_calibration"]["status"],
            "exact_real_pilot_conservative_minimum_across_arms",
        )
        self.assertEqual(frozen["pilot_calibration_sha256"], "b" * 64)

    def test_full_campaign_authorization_is_artifact_bound_and_excludes_pilot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            jobs_path = Path(temporary) / "remaining_jobs.jsonl"
            jobs_path.write_text('{"job_id":"job-1"}\n', encoding="utf-8")
            job = {
                "campaign_id": "postpilot_campaign_v1",
                "pilot_job": False,
            }
            authorization = {
                "schema_version": "storyworld_full_campaign_authorization_v1",
                "status": "authorized",
                "passed": True,
                "campaign_id": "postpilot_campaign_v1",
                "authorized_job_artifacts": [
                    {"sha256": sha256_file(jobs_path)}
                ],
            }
            validate_full_campaign_authorization(authorization, job, jobs_path)

            pilot = {**job, "pilot_job": True}
            with self.assertRaisesRegex(ValueError, "cannot be used to replay"):
                validate_full_campaign_authorization(authorization, pilot, jobs_path)

            jobs_path.write_text('{"job_id":"drifted"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not hash-listed"):
                validate_full_campaign_authorization(authorization, job, jobs_path)

    def test_development_suite_includes_identity_scrubbed_policy_quality(self) -> None:
        public, keys, manifest = build_development_evaluation(
            REPO_ROOT, PACKAGE_PATH, allow_provisional=True
        )
        robust_public = [
            item
            for item in public
            if item["metric"] == "frame_robust_policy_accuracy"
        ]
        robust_keys = [
            item
            for item in keys
            if item["metric"] == "frame_robust_policy_accuracy"
        ]
        self.assertGreater(len(robust_public), 0)
        self.assertEqual(len(robust_public), len(robust_keys))
        self.assertGreater(
            manifest["frame_robust_policy_excluded_no_positive_constraint"], 0
        )
        for item, key in zip(robust_public, robust_keys):
            self.assertEqual(item["item_id"], key["item_id"])
            self.assertTrue(key["target"]["acceptable_action_ids"])
            self.assertNotIn("quranic_motif", json.dumps(item, sort_keys=True).lower())

    def test_development_scorer_covers_all_locked_metrics(self) -> None:
        exact_metrics = {
            "legal_action_accuracy": {"legal_action_ids": ["A-1"]},
            "next_state_accuracy": {"public_outcome": "bounded", "variable_changes": {}},
            "counterfactual_branch_accuracy": {
                "a_outcome": "a",
                "b_outcome": "b",
                "different_later_menu": True,
            },
            "contradiction_detection_accuracy": {"contradicting_index": 1},
            "reachable_repair_accuracy": {
                "repair_action_id": "A-2",
                "repairs": ["c_failure"],
            },
            "obligation_dynamics_disagreement_accuracy": {
                "constraint_satisfied": True,
                "outcome_still_uncertain": True,
            },
        }
        keys = []
        predictions = []
        for index, (metric, target) in enumerate(exact_metrics.items()):
            item_id = f"exact-{index}"
            keys.append({"item_id": item_id, "metric": metric, "target": target})
            predictions.append({"item_id": item_id, "response": target})
        keys.extend(
            [
                {
                    "item_id": "belief",
                    "metric": "belief_visibility_f1",
                    "target": {"available_statements": ["visible"]},
                },
                {
                    "item_id": "labels",
                    "metric": "fact_allegation_accuracy",
                    "target": {"labels": ["fact", "allegation"]},
                },
                {
                    "item_id": "forecast",
                    "metric": "forecast_brier_score",
                    "target": {"outcomes": {"E-1": 1, "E-2": 0}},
                },
            ]
        )
        predictions.extend(
            [
                {
                    "item_id": "belief",
                    "response": {"available_statements": ["visible"]},
                },
                {
                    "item_id": "labels",
                    "response": {"labels": ["fact", "allegation"]},
                },
                {
                    "item_id": "forecast",
                    "response": {"probabilities": {"E-1": 1.0, "E-2": 0.0}},
                },
            ]
        )
        keys.append(
            {
                "item_id": "robust-policy",
                "metric": "frame_robust_policy_accuracy",
                "target": {
                    "legal_action_ids": ["A-1", "A-2"],
                    "acceptable_action_ids": ["A-1"],
                    "visible_fact_ids": ["fact-1"],
                    "maximum_satisfied_frames": 4,
                },
            }
        )
        predictions.append(
            {
                "item_id": "robust-policy",
                "response": {
                    "action_id": "A-1",
                    "cited_fact_ids": ["fact-1"],
                    "uncertainties": ["The outcome remains uncertain."],
                    "defense": "Ordinary evidence supports the bounded action.",
                },
            }
        )
        for skin_id in ("quranic_motif", "secular_control"):
            item_id = f"pair-{skin_id}"
            keys.append(
                {
                    "item_id": item_id,
                    "metric": "paired_skin_action_consistency",
                    "target": {
                        "legal_action_ids": ["A-1"],
                        "opaque_to_action_key": {"A-1": "bounded_action"},
                        "visible_fact_ids": ["fact-1"],
                        "pair_case_id": "pair-case",
                        "skin_id": skin_id,
                        "theological_motif": (
                            "shahada" if skin_id == "quranic_motif" else None
                        ),
                    },
                }
            )
            predictions.append(
                {
                    "item_id": item_id,
                    "response": {
                        "action_id": "A-1",
                        "cited_fact_ids": ["fact-1"],
                        "uncertainties": ["Outcome remains uncertain."],
                        "defense": "Visible evidence supports a bounded reviewable action.",
                    },
                }
            )
        public = [{"item_id": item["item_id"]} for item in keys]
        score = score_development_evaluation(public, keys, predictions)
        self.assertEqual(set(score["metrics"]), set(REQUIRED_DEVELOPMENT_METRICS))
        for metric, receipt in score["metrics"].items():
            expected = 0.0 if metric == "forecast_brier_score" else 1.0
            self.assertEqual(receipt["value"], expected)


if __name__ == "__main__":
    unittest.main()
