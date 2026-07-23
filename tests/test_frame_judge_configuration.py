from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.freeze_frame_judge_configuration import canonical_sha256


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "freeze_frame_judge_configuration.py"
RECEIPT = (
    REPO_ROOT
    / "experiments/frame_internalization_sft_v1/readiness/"
    "judge_configuration_freeze_v1.json"
)
FACTORIZATION = (
    REPO_ROOT
    / "experiments/frame_internalization_sft_v1/readiness/"
    "gate_factorization_20260723_f12.json"
)
F04 = (
    REPO_ROOT
    / "experiments/frame_internalization_sft_v1/primelab_f04/"
    "environment_freeze_20260723.json"
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_judge_configuration_is_exact_and_prospective() -> None:
    receipt = read_json(RECEIPT)
    settings = receipt["decoding_settings"]

    assert receipt["passed"] is True
    assert receipt["failures"] == []
    assert all(receipt["checks"].values())
    assert receipt["immutable_revisions"] is True
    assert receipt["judge_revision"] == "claude-opus-4-8"
    assert receipt["classifier_revision"] == "claude-sonnet-5"
    assert settings["shared"]["anthropic_version"] == "2023-06-01"
    assert set(settings["shared"]["sampling_parameters"].values()) == {
        "omitted",
        "unsupported_omitted",
    }
    assert receipt["decoding_settings_sha256"] == canonical_sha256(settings)
    assert receipt["scope_boundary"]["asserts_prediction_completion"] is False
    assert receipt["scope_boundary"]["authorizes_adapter_training"] is False


def test_judge_configuration_cli_reproduces_receipt() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        output = Path(temp_dir) / "receipt.json"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--freeze-date",
                "2026-07-23",
                "--output",
                str(output),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert read_json(output) == read_json(RECEIPT)


def test_judge_receipt_binds_generator() -> None:
    receipt = read_json(RECEIPT)
    generator = receipt["generator"]
    assert REPO_ROOT / generator["path"] == SCRIPT
    assert hashlib.sha256(SCRIPT.read_bytes()).hexdigest() == generator["sha256"]


def test_factorization_closes_only_f12_from_judge_receipt() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/factor_frame_internalization_gates.py"),
            "--as-of-date",
            "2026-07-23",
            "--primelab-environment",
            str(F04),
            "--judge-freeze",
            str(RECEIPT),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report == read_json(FACTORIZATION)
    factors = {item["factor_id"]: item for item in report["factors"]}
    assert factors["F12"]["evidence_status"] == "passed"
    assert factors["F14"]["evidence_status"] == "pending"
    assert factors["F15"]["evidence_status"] == "pending"
    assert report["summary"]["passed_factor_count"] == 9
    assert report["summary"]["passed_parent_gate_count"] == 3
    assert report["current_frontier"] == ["F06", "F13"]
