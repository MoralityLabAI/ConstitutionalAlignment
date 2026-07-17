from __future__ import annotations

import hashlib
import json
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
