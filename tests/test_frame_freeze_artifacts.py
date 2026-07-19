from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments" / "frame_internalization_sft_v1"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_reconstructed_evaluation_universes_match_recovered_receipts() -> None:
    receipt = read_json(PACKAGE / "rerun_freeze" / "evaluation_universes_v1.json")
    assert receipt["exact_recovery"] is False
    assert receipt["recovered_set_hashes_matched"] is True
    assert receipt["universes"]["harmful"]["row_count"] == 200
    assert receipt["universes"]["benign"]["row_count"] == 100
    assert receipt["universes"]["override"]["row_count"] == 150
    assert receipt["universes"]["harmful"]["ordered_text_set_sha256_truncated_16"] == "3101e5efe15a6284"
    assert receipt["universes"]["benign"]["ordered_text_set_sha256_truncated_16"] == "aeeaa6ac1be36305"
    assert sha256_file(REPO_ROOT / receipt["selection_script"]["path"]) == receipt["selection_script"]["sha256"]
    for universe in receipt["universes"].values():
        path = REPO_ROOT / universe["path"]
        assert len(path.read_text(encoding="utf-8").splitlines()) == universe["row_count"]
        assert sha256_file(path) == universe["sha256"]


def test_split_freeze_is_hash_bound_and_cluster_disjoint() -> None:
    receipt = read_json(PACKAGE / "readiness" / "split_freeze_v1.json")
    assignments_path = REPO_ROOT / receipt["assignments_path"]
    assignments = [json.loads(line) for line in assignments_path.read_text(encoding="utf-8").splitlines()]
    assert receipt["passed"] is True
    assert receipt["scenario_count"] == 5600
    assert receipt["train_count"] == 5320
    assert receipt["validation_count"] == 280
    assert sha256_file(assignments_path) == receipt["assignments_sha256"]
    manifest = read_json(REPO_ROOT / receipt["manifest_path"])
    assert sha256_file(REPO_ROOT / manifest["builder_path"]) == manifest["builder_sha256"]
    train = {row["cluster_id"] for row in assignments if row["split"] == "train"}
    validation = {row["cluster_id"] for row in assignments if row["split"] == "val"}
    assert not train & validation


def test_evaluation_seal_binds_every_listed_file() -> None:
    seal = read_json(PACKAGE / "readiness" / "evaluation_seal_v1.json")
    assert seal["sealed"] is True
    assert seal["opened"] is False
    assert seal["exact_predecessor_recovery"] is False
    for item in seal["files"]:
        path = REPO_ROOT / item["path"]
        assert path.stat().st_size == item["bytes"]
        assert sha256_file(path) == item["sha256"]


def test_licensed_v2_evaluation_universe_is_hash_bound_and_not_a_reanchor() -> None:
    receipt = read_json(PACKAGE / "rerun_freeze" / "evaluation_universes_v2.json")
    assert receipt["schema_version"] == "frame_internalization_evaluation_universes.v2"
    assert receipt["passed"] is True
    assert receipt["exact_recovery"] is False
    assert receipt["license_gate"]["passed"] is True
    assert receipt["sources"]["harmful"]["repository"] == "centerforaisafety/HarmBench"
    assert receipt["sources"]["harmful"]["revision"] == (
        "8e1604d1171fe8a48d8febecd22f600e462bdcdd"
    )
    assert receipt["sources"]["harmful"]["license"] == "MIT"
    assert receipt["sources"]["harmful"]["selected_row_count"] == 200
    assert receipt["sources"]["harmful"]["unique_behavior_id_count"] == 200
    assert receipt["sources"]["harmful"]["nonempty_context_count"] == 0
    assert receipt["historical_reanchor_compatibility"][
        "recovered_f0_interval_is_confirmatory_target"
    ] is False
    assert receipt["universes"]["harmful"]["row_count"] == 200
    assert receipt["universes"]["benign"]["row_count"] == 100
    assert receipt["universes"]["override"]["row_count"] == 150
    assert sha256_file(REPO_ROOT / receipt["selection_script"]["path"]) == receipt[
        "selection_script"
    ]["sha256"]
    for universe in receipt["universes"].values():
        path = REPO_ROOT / universe["path"]
        assert len(path.read_text(encoding="utf-8").splitlines()) == universe["row_count"]
        assert sha256_file(path) == universe["sha256"]
    license_copy = REPO_ROOT / receipt["sources"]["harmful"]["license_copy"]["path"]
    assert sha256_file(license_copy) == receipt["sources"]["harmful"]["license_sha256"]


def test_v2_evaluation_seal_binds_every_listed_file() -> None:
    seal = read_json(PACKAGE / "readiness" / "evaluation_seal_v2.json")
    assert seal["schema_version"] == "frame_internalization_evaluation_seal.v2"
    assert seal["sealed"] is True
    assert seal["opened"] is False
    assert seal["exact_predecessor_recovery"] is False
    for item in seal["files"]:
        path = REPO_ROOT / item["path"]
        assert path.stat().st_size == item["bytes"]
        assert sha256_file(path) == item["sha256"]


def test_judge_contract_receipt_covers_all_suites_and_malformed_rows() -> None:
    receipt = read_json(PACKAGE / "readiness" / "judge_dry_run_v1.json")
    assert receipt["passed"] is True
    assert receipt["rows_per_suite"] == 3
    assert receipt["expected_parse_rate"] == 1
    assert set(receipt["suites"]) == {
        "storyworld",
        "identity_behavior",
        "pressure",
        "helpfulness",
        "theology_guardrail",
    }
    for suite in receipt["suites"].values():
        assert suite["completed"] == 2
        assert suite["errors"] == 1
        assert suite["expected_outcomes_observed"] == 3
    for item in receipt["implementation_files"]:
        assert sha256_file(REPO_ROOT / item["path"]) == item["sha256"]
    assert "identity_boundary" in receipt["identity_behavior_dimensions"]
    assert "epistemic_boundary" in receipt["identity_behavior_dimensions"]


def test_remote_model_inventory_is_immutable_and_hash_complete() -> None:
    inventory = read_json(PACKAGE / "rerun_freeze" / "model_tokenizer_remote_inventory_v1.json")
    assert inventory["passed"] is False
    assert inventory["immutable_revisions"] is True
    assert inventory["revision"] == "ff39d4a4688989f3f28868923d030c28e1b7d81c"
    assert inventory["weight_shard_count"] == 48
    assert inventory["artifact_count"] == 55
    assert inventory["chat_template_comparison"]["byte_identical"] is True
    assert len({item["path"] for item in inventory["artifacts"]}) == 55
    assert all(len(item["sha256"]) == 64 and item["size_bytes"] > 0 for item in inventory["artifacts"])
    assert sha256_file(REPO_ROOT / inventory["builder"]["path"]) == inventory["builder"]["sha256"]


def test_curriculum_request_pack_is_complete_paired_and_hash_bound() -> None:
    manifest = read_json(
        PACKAGE / "rerun_freeze" / "curriculum_generation_v1" / "request_manifest.json"
    )
    request_path = REPO_ROOT / manifest["requests"]["path"]
    rows = [json.loads(line) for line in request_path.read_text(encoding="utf-8").splitlines()]
    assert manifest["status"] == "requests_frozen_generation_pending"
    assert manifest["request_count"] == 22400
    assert sha256_file(request_path) == manifest["requests"]["sha256"]
    assert sha256_file(REPO_ROOT / manifest["builder"]["path"]) == manifest["builder"]["sha256"]
    assert Counter(row["source_frame"] for row in rows) == {
        "neutral": 5600,
        "F1": 5600,
        "F3": 5600,
        "F3_concrete": 5600,
    }
    by_frame = {
        frame: {row["scenario_id"]: row["generation_seed"] for row in rows if row["source_frame"] == frame}
        for frame in manifest["frames"]
    }
    assert all(seed_map == by_frame["neutral"] for seed_map in by_frame.values())
    assert len({row["request_id"] for row in rows}) == 22400


def test_nonleakage_precursor_is_clean_but_not_gate_satisfying() -> None:
    receipt = read_json(PACKAGE / "rerun_freeze" / "nonleakage_source_prompts_v1.json")
    assert receipt["passed"] is True
    assert receipt["gate_satisfying"] is False
    assert receipt["scope"] == "frozen_source_prompts_only"
    assert receipt["source_unit_count"] == 5600
    assert receipt["exact_overlap_count"] == 0
    assert receipt["normalized_overlap_count"] == 0
    assert receipt["ngram_overlap_count"] == 0


def test_predecessor_progress_binds_queue_without_claiming_completion() -> None:
    progress = read_json(PACKAGE / "rerun_freeze" / "predecessor_reanchor_progress_v1.json")
    judge = read_json(PACKAGE / "rerun_freeze" / "judge_classifier_inputs_v1.json")
    queue_path = REPO_ROOT / judge["validation_queue"]["path"]
    rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    assert progress["passed"] is False
    assert progress["probe_frozen_before_adapter_outcomes"] is False
    assert judge["passed"] is False
    assert judge["agreement_gate"]["minimum_cohens_kappa_each_task"] == 0.70
    assert sha256_file(queue_path) == judge["validation_queue"]["sha256"]
    assert Counter(row["task"] for row in rows) == {"compliance": 200, "strict_af": 200}
    assert all(not row["response"] and not row["human_label"] for row in rows)


def test_v2_predecessor_progress_binds_replacement_queue_without_claiming_completion() -> None:
    progress = read_json(PACKAGE / "rerun_freeze" / "predecessor_reanchor_progress_v2.json")
    judge = read_json(PACKAGE / "rerun_freeze" / "judge_classifier_inputs_v2.json")
    queue_path = REPO_ROOT / judge["validation_queue"]["path"]
    rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    assert progress["passed"] is False
    assert progress["probe_frozen_before_adapter_outcomes"] is False
    universe_gate = next(
        item for item in progress["subgates"] if item["gate_id"] == "evaluation_universe_freeze"
    )
    assert universe_gate["status"] == "passed_prospective_substitution"
    assert universe_gate["license_gate_passed"] is True
    assert universe_gate["historical_f0_interval_is_confirmatory_target"] is False
    baseline = next(
        item for item in progress["subgates"] if item["gate_id"] == "prospective_v2_base_baseline"
    )
    assert baseline["frozen_decision_rule"]["v2_magnitude_acceptance_interval"] is None
    assert judge["passed"] is False
    assert sha256_file(queue_path) == judge["validation_queue"]["sha256"]
    assert Counter(row["task"] for row in rows) == {"compliance": 200, "strict_af": 200}
    assert all(not row["response"] and not row["human_label"] for row in rows)


def test_v2_nonleakage_precursor_is_clean_but_not_gate_satisfying() -> None:
    receipt = read_json(PACKAGE / "rerun_freeze" / "nonleakage_source_prompts_v2.json")
    assert receipt["passed"] is True
    assert receipt["gate_satisfying"] is False
    assert receipt["scope"] == "frozen_source_prompts_only"
    assert receipt["source_unit_count"] == 5600
    assert receipt["evaluation_unit_count"] == 510
    assert receipt["exact_overlap_count"] == 0
    assert receipt["normalized_overlap_count"] == 0
    assert receipt["ngram_overlap_count"] == 0
