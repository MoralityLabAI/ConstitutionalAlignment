from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.build_primelab_f04_receipt import (
    EXPECTED_INVENTORY_SHA256,
    build_receipt,
)
from scripts.run_primelab_f04_probe import parse_nvidia_inventory


REPO_ROOT = Path(__file__).resolve().parent.parent
F04_PACKAGE = (
    REPO_ROOT / "experiments/frame_internalization_sft_v1/primelab_f04"
)
F04_RECEIPT = F04_PACKAGE / "environment_freeze_20260723.json"
F04_MANIFEST = F04_PACKAGE / "instance_manifest_20260723.json"
CURRENT_FACTORIZATION = (
    REPO_ROOT
    / "experiments/frame_internalization_sft_v1/readiness/"
    "gate_factorization_20260723.json"
)


def test_nvidia_inventory_parser_requires_exact_shape() -> None:
    rows = parse_nvidia_inventory("0, NVIDIA A100-SXM4-80GB, 81920, 570.10, GPU-123\n")
    assert rows == [
        {
            "index": 0,
            "name": "NVIDIA A100-SXM4-80GB",
            "memory_total_mib": 81920,
            "driver_version": "570.10",
            "uuid": "GPU-123",
        }
    ]


def test_f04_receipt_passes_only_with_remote_runtime_caps_and_cleanup() -> None:
    lock_hash = hashlib.sha256(b"frozen\n").hexdigest()
    probe = {
        "passed": True,
        "source_commit": "a" * 40,
        "gpu_inventory": [
            {
                "index": 0,
                "name": "NVIDIA A100-SXM4-80GB",
                "memory_total_mib": 81920,
            }
        ],
        "environment_lock_sha256": lock_hash,
        "runtime_receipt_sha256": "b" * 64,
        "network_isolation": {"passed": True},
        "gpu_topology_passed": True,
        "gpu_hour_cap_passed": True,
        "cleanup": {"passed": True},
        "inference_caps": {
            "maximum_wall_clock_seconds": 1800,
            "maximum_gpu_hours": 0.5,
            "maximum_output_bytes": 1073741824,
            "checkpoint_every_requests": 1,
        },
    }
    runtime = {
        "passed": True,
        "engine": {
            "venue": "primelab",
            "python_cuda_cleanup": {"status": "completed"},
        },
        "artifact_inventory_sha256": EXPECTED_INVENTORY_SHA256,
    }
    instance = {
        "passed": True,
        "provider": "Massed Compute",
        "gpu_sku": "A100 80GB",
        "socket": "SXM4",
        "gpu_count": 1,
        "gpu_vram_gib": 80,
        "vcpu": 16,
        "ram_gib": 120,
        "disk_gib": 500,
        "deployment_type": "Virtual Machine",
        "pricing_type": "on_demand",
        "security": "secure_cloud",
        "region": "United States",
        "image": "ubuntu_22_cuda_12",
        "price_usd_per_hour": 1.23,
    }
    receipt = build_receipt(probe, runtime, instance, lock_hash)
    assert receipt["passed"] is True
    assert receipt["gpu_count"] == 1
    assert receipt["gpu_vram_gib"] == 80
    assert receipt["scope_boundary"]["authorizes_training"] is False

    failed = build_receipt(
        {**probe, "cleanup": {"passed": False}}, runtime, instance, lock_hash
    )
    assert failed["passed"] is False
    assert failed["failures"] == ["cleanup_passed"]

    price_drift = build_receipt(
        probe, runtime, {**instance, "price_usd_per_hour": 1.31}, lock_hash
    )
    assert price_drift["passed"] is False
    assert price_drift["failures"] == ["instance_price_within_cap"]


def test_f04_requirements_are_exactly_pinned() -> None:
    requirements = (
        REPO_ROOT
        / "experiments/frame_internalization_sft_v1/primelab_f04/requirements_f04.txt"
    ).read_text(encoding="utf-8")
    package_lines = [
        line for line in requirements.splitlines() if not line.startswith("--")
    ]
    assert package_lines
    assert all("==" in line for line in package_lines)
    assert "torch==2.5.1+cu121" in package_lines


def test_factorization_accepts_the_f04_receipt_schema(tmp_path: Path) -> None:
    receipt_path = tmp_path / "f04.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": "frame_internalization_primelab_environment_freeze.v1",
                "passed": True,
                "gpu_count": 1,
                "gpu_vram_gib": 80,
                "environment_lock_sha256": "a" * 64,
                "model_artifact_inventory_sha256": EXPECTED_INVENTORY_SHA256,
                "inference_caps": {
                    "maximum_wall_clock_seconds": 1800,
                    "maximum_gpu_hours": 0.5,
                    "maximum_output_bytes": 1073741824,
                    "checkpoint_every_requests": 1,
                },
                "cleanup_required": True,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/factor_frame_internalization_gates.py"),
            "--primelab-environment",
            str(receipt_path),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    factor = next(item for item in report["factors"] if item["factor_id"] == "F04")
    assert factor["evidence_status"] == "passed"
    assert factor["execution_state"] == "satisfied"


def test_candidate_offer_is_not_pre_authorized_for_billing() -> None:
    plan = json.loads(
        (
            REPO_ROOT / "experiments/frame_internalization_sft_v1/primelab_f04/"
            "f04_bringup_plan_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert plan["billing_authorized"] is False
    assert plan["candidate_offer"]["gpu_vram_gib"] >= 24
    assert plan["spend_caps"]["maximum_compute_cost_usd"] == 0.65
    for item in plan["executables"]:
        path = REPO_ROOT / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    requirements = REPO_ROOT / plan["environment"]["requirements_path"]
    assert (
        hashlib.sha256(requirements.read_bytes()).hexdigest()
        == plan["environment"]["requirements_sha256"]
    )


def test_committed_f04_receipt_records_bounded_terminated_run() -> None:
    receipt = json.loads(F04_RECEIPT.read_text(encoding="utf-8"))
    manifest = json.loads(F04_MANIFEST.read_text(encoding="utf-8"))

    assert receipt["passed"] is True
    assert receipt["failures"] == []
    assert all(receipt["checks"].values())
    assert receipt["source_commit"] == "0d1b4f1146dc57373fab2f0c1958229f29b57a58"
    assert receipt["instance"] == manifest
    assert manifest["termination"]["passed"] is True
    assert manifest["termination"]["running_pods_after"] == 0
    assert manifest["lifecycle"]["within_time_and_price_caps"] is True
    assert manifest["lifecycle"]["full_lifetime_price_upper_bound_usd"] <= 0.65
    assert receipt["scope_boundary"]["authorizes_training"] is False


def test_current_factorization_reproduces_with_f04_satisfied() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/factor_frame_internalization_gates.py"),
            "--as-of-date",
            "2026-07-23",
            "--primelab-environment",
            str(F04_RECEIPT),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report == json.loads(CURRENT_FACTORIZATION.read_text(encoding="utf-8"))
    factor = next(item for item in report["factors"] if item["factor_id"] == "F04")
    assert factor["evidence_status"] == "passed"
    assert factor["execution_state"] == "satisfied"
    assert report["summary"]["passed_factor_count"] == 8
    assert report["summary"]["passed_parent_gate_count"] == 3
    assert report["current_frontier"] == ["F06", "F12", "F13"]
