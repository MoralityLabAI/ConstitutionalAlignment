#!/usr/bin/env python3
"""Build the F04 PrimeLab environment-freeze receipt from remote evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_INVENTORY_SHA256 = (
    "26dbf683e31beebd0282217ea79a1b53f7a8fed6f4961978d7881c5a556e1959"
)
EXPECTED_INSTANCE = {
    "provider": "Massed Compute",
    "gpu_sku": "A100 80GB",
    "socket": "SXM4",
    "gpu_count": 1,
    "gpu_vram_gib": 80,
    "vcpu": 16,
    "ram_gib": 120,
    "disk_gib": 500,
    "deployment_type": "Virtual Machine",
    "security": "secure_cloud",
    "region": "United States",
    "image": "ubuntu_22_cuda_12",
    "pricing_type": "on_demand",
}
MAXIMUM_PRICE_USD_PER_HOUR = 1.30


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def build_receipt(
    probe: dict[str, Any],
    runtime: dict[str, Any],
    instance: dict[str, Any],
    environment_lock_sha256: str,
) -> dict[str, Any]:
    gpu_rows = list(probe.get("gpu_inventory", []))
    gpu_count = len(gpu_rows)
    gpu_vram_gib = (
        float(gpu_rows[0].get("memory_total_mib", 0)) / 1024 if gpu_count == 1 else 0
    )
    caps = dict(probe.get("inference_caps", {}))
    checks = {
        "probe_passed": probe.get("passed") is True,
        "runtime_passed": runtime.get("passed") is True,
        "runtime_venue_is_primelab": runtime.get("engine", {}).get("venue")
        == "primelab",
        "python_cuda_cleanup_passed": runtime.get("engine", {})
        .get("python_cuda_cleanup", {})
        .get("status")
        == "completed",
        "one_gpu": gpu_count == 1,
        "minimum_vram": gpu_vram_gib >= 24,
        "environment_lock_matches": probe.get("environment_lock_sha256")
        == environment_lock_sha256,
        "model_inventory_matches": runtime.get("artifact_inventory_sha256")
        == EXPECTED_INVENTORY_SHA256,
        "positive_caps": all(
            float(caps.get(key, 0)) > 0
            for key in (
                "maximum_wall_clock_seconds",
                "maximum_gpu_hours",
                "maximum_output_bytes",
                "checkpoint_every_requests",
            )
        ),
        "network_isolated": probe.get("network_isolation", {}).get("passed") is True,
        "gpu_topology_passed": probe.get("gpu_topology_passed") is True,
        "gpu_hour_cap_passed": probe.get("gpu_hour_cap_passed") is True,
        "cleanup_passed": probe.get("cleanup", {}).get("passed") is True,
        "instance_manifest_passed": instance.get("passed") is True,
        "instance_offer_matches": all(
            instance.get(key) == value for key, value in EXPECTED_INSTANCE.items()
        ),
        "instance_price_within_cap": 0
        < float(instance.get("price_usd_per_hour", 0))
        <= MAXIMUM_PRICE_USD_PER_HOUR,
    }
    passed = all(checks.values())
    return {
        "schema_version": "frame_internalization_primelab_environment_freeze.v1",
        "passed": passed,
        "gpu_count": gpu_count,
        "gpu_vram_gib": gpu_vram_gib,
        "gpu_inventory": gpu_rows,
        "environment_lock_sha256": environment_lock_sha256,
        "model_artifact_inventory_sha256": runtime.get("artifact_inventory_sha256"),
        "inference_caps": caps,
        "cleanup_required": True,
        "source_commit": probe.get("source_commit"),
        "instance": instance,
        "probe_runtime_receipt_sha256": probe.get("runtime_receipt_sha256"),
        "checks": checks,
        "failures": [name for name, value in checks.items() if not value],
        "scope_boundary": {
            "authorizes_curriculum_generation_after_gate_refresh": passed,
            "authorizes_training": False,
            "full_4096_training_smoke_still_required": True,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-summary", type=Path, required=True)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--instance-manifest", type=Path, required=True)
    parser.add_argument("--environment-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = build_receipt(
        read_json(args.probe_summary),
        read_json(args.runtime_receipt),
        read_json(args.instance_manifest),
        sha256_file(args.environment_lock),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
