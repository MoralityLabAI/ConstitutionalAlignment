from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments" / "frame_internalization_sft_v1"
SCRIPT = REPO_ROOT / "scripts" / "factor_frame_internalization_gates.py"
RECEIPT = PACKAGE / "readiness" / "gate_factorization_20260721.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_active_qwen_gates_are_factored_without_weakening() -> None:
    report = read_json(RECEIPT)
    assert report["schema_version"] == "frame_internalization_gate_factorization.v1"
    assert report["active_execution"] == "qwen3_1p7b_single_gpu_v1"
    assert report["pilot_ready"] is False
    assert report["summary"] == {
        "factor_count": 20,
        "passed_factor_count": 7,
        "pending_factor_count": 13,
        "failed_factor_count": 0,
        "parent_gate_count": 10,
        "passed_parent_gate_count": 2,
        "blocking_parent_gate_count": 8,
    }
    assert report["current_frontier"] == ["F04", "F12"]
    assert report["projected_execution_waves"] == [
        ["F04", "F12"],
        ["F06", "F13"],
        ["F07", "F14", "F16"],
        ["F08", "F10", "F15"],
        ["F17", "F18"],
        ["F19"],
    ]
    assert report["invariants"]["parent_gate_pass_requires_every_required_factor"] is True
    assert report["invariants"]["factorization_does_not_authorize_compute"] is True


def test_only_local_model_and_evaluation_parent_gates_pass() -> None:
    report = read_json(RECEIPT)
    statuses = {item["gate_id"]: item["status"] for item in report["parent_gates"]}
    assert {gate_id for gate_id, status in statuses.items() if status == "passed"} == {
        "G01",
        "G06",
    }
    assert statuses["G10"] == "pending"
    authorization = next(item for item in report["factors"] if item["factor_id"] == "F19")
    assert authorization["execution_state"] == "blocked"
    assert len(authorization["blocked_by"]) == 12


def test_factorization_receipt_binds_its_generator() -> None:
    report = read_json(RECEIPT)
    generator = report["generator"]
    assert REPO_ROOT / generator["path"] == SCRIPT
    assert sha256_file(SCRIPT) == generator["sha256"]


def test_cli_reproduces_the_committed_factorization() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--as-of-date", "2026-07-21"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == read_json(RECEIPT)


def test_cli_requires_all_factors_for_pilot_readiness() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--require-ready-for-pilot"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr


def test_supplied_invalid_receipt_is_failed_not_pending() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        invalid = Path(temp_dir) / "primelab.json"
        invalid.write_text(json.dumps({"schema_version": "wrong", "passed": True}), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--primelab-environment",
                str(invalid),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    factor = next(item for item in report["factors"] if item["factor_id"] == "F04")
    gate = next(item for item in report["parent_gates"] if item["gate_id"] == "G02")
    assert factor["evidence_status"] == "failed"
    assert factor["execution_state"] == "failed"
    assert gate["status"] == "failed"


def test_exact_render_and_token_parity_are_independent_factors() -> None:
    arms = {
        arm: {
            "scenario_count": 5600,
            "train_count": 5320,
            "validation_count": 280,
            "scenario_ids_sha256": "1" * 64,
            "total_train_tokens": 1_000_000,
        }
        for arm in (
            "neutral_reflection",
            "F1_reflection",
            "F1_demonstration",
            "F3_reflection",
            "F3_demonstration",
            "F3_concrete_reflection",
        )
    }
    with tempfile.TemporaryDirectory() as temp_dir:
        manifest = Path(temp_dir) / "curriculum.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": "frame_internalization_curriculum_manifest.v1",
                    "passed": False,
                    "sequence_length": 4096,
                    "f3_pair_total_token_spread": 0.10,
                    "arms": arms,
                }
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--curriculum-manifest", str(manifest)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    factors = {item["factor_id"]: item for item in report["factors"]}
    assert factors["F07"]["evidence_status"] == "passed"
    assert factors["F08"]["evidence_status"] == "failed"
