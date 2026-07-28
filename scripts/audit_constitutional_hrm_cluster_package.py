#!/usr/bin/env python3
"""Audit the offline constitutional HRM cluster package and issue an F08A receipt."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OFFICIAL_COMMIT = "ac15626f8db096a63c775b84c9dc868776a6feda"
ARMS = (
    "constitutional_metta",
    "constitutional_text_only",
    "utility_control",
    "shuffled_control",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def git_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--official-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.repo_root.resolve()
    dataset = args.dataset_dir.resolve()
    official_root = args.official_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    model_config_path = (
        root / "experiments" / "constitutional_hrm_200m_v2" / "model_config.json"
    )
    experiment_plan_path = (
        root / "experiments" / "constitutional_hrm_200m_v2" / "experiment_plan.json"
    )
    tokenizer_receipt_path = (
        root
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "tokenizer"
        / "freeze_receipt.json"
    )
    adapter_receipt_path = (
        root
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "official_adapter"
        / "adapter_receipt.json"
    )
    trainer_path = root / "scripts" / "train_constitutional_hrm_200m_v2.py"
    runner_path = (
        root
        / "scripts"
        / "cluster"
        / "run_constitutional_hrm_200m_v2.sh"
    )
    curriculum_manifest_path = dataset / "manifest.json"
    model_config = json.loads(model_config_path.read_text(encoding="utf-8"))
    experiment_plan = json.loads(experiment_plan_path.read_text(encoding="utf-8"))
    tokenizer_receipt = json.loads(tokenizer_receipt_path.read_text(encoding="utf-8"))
    adapter_receipt = json.loads(adapter_receipt_path.read_text(encoding="utf-8"))
    curriculum_manifest = json.loads(
        curriculum_manifest_path.read_text(encoding="utf-8")
    )
    official = git_commit(official_root)
    ast.parse(trainer_path.read_text(encoding="utf-8"))
    runner_source = runner_path.read_text(encoding="utf-8")
    jobs = [
        {
            "job_id": f"{arm}__seed_{seed}",
            "arm": arm,
            "seed": seed,
            "cuda_visible_devices": str(gpu),
            "distributed": False,
        }
        for gpu, (arm, seed) in enumerate(
            (arm, seed) for arm in ARMS for seed in (713, 719)
        )
    ]
    authorized_sha256 = {
        "model_config": sha256_file(model_config_path),
        "curriculum_manifest": sha256_file(curriculum_manifest_path),
        "official_commit": official,
        "trainer": sha256_file(trainer_path),
        "cluster_runner": sha256_file(runner_path),
    }
    checks = {
        "f06_tokenizer_passed": tokenizer_receipt.get("status") == "passed",
        "f07_official_adapter_passed": adapter_receipt.get("status") == "passed",
        "official_ignore_label_contract": adapter_receipt.get("checks", {}).get(
            "official_ignore_label_contract"
        )
        is True,
        "official_commit_pinned": official == OFFICIAL_COMMIT,
        "curriculum_materialized": curriculum_manifest.get("status") == "passed",
        "curriculum_split_before_augmentation": curriculum_manifest.get(
            "checks", {}
        ).get("split_groups_disjoint")
        is True,
        "eight_unique_jobs": len(jobs) == 8
        and len({job["job_id"] for job in jobs}) == 8
        and len({job["cuda_visible_devices"] for job in jobs}) == 8,
        "four_arms_two_seeds": {job["arm"] for job in jobs} == set(ARMS)
        and {job["seed"] for job in jobs} == {713, 719},
        "no_ddp": experiment_plan["cluster_layout"]["distributed_data_parallel"]
        is False
        and all(job["distributed"] is False for job in jobs)
        and "torchrun" not in runner_source,
        "systemd_waits_for_owned_jobs": "--wait" in runner_source
        and "--pipe" in runner_source,
        "live_drill_precedes_pilot": 'MODE}" == "drill"' in runner_source
        and "--cluster-drill" in runner_source
        and "--max-optimizer-steps 1" in runner_source,
        "wall_cap": experiment_plan["cluster_layout"]["max_wall_seconds"] == 7200
        and "MAX_WALL_SECONDS=7200" in runner_source,
        "hard_ram_cap": "MemoryMax=96G" in runner_source,
        "swap_disabled": "MemorySwapMax=0" in runner_source
        and "/proc/swaps" in runner_source,
        "hard_cpu_cap": "CPUQuota=1200%" in runner_source,
        "io_caps": "IOReadBandwidthMax" in runner_source
        and "IOWriteBandwidthMax" in runner_source,
        "gpu_allocator_cap": "set_per_process_memory_fraction" in trainer_path.read_text(
            encoding="utf-8"
        ),
        "checkpoint_dual_trigger": "checkpoint_steps" in trainer_path.read_text(
            encoding="utf-8"
        )
        and "checkpoint_seconds" in trainer_path.read_text(encoding="utf-8"),
        "cleanup_contract": "remaining_compute_pids" in runner_source
        and "cuda.ipc_collect" in trainer_path.read_text(encoding="utf-8"),
        "architecture_195m_band": model_config["architecture"][
            "target_min_parameters"
        ]
        == 190_000_000
        and model_config["architecture"]["target_max_parameters"] == 205_000_000,
    }
    receipt_path = output / "f08a_offline_package_receipt.json"
    receipt = {
        "schema_version": "constitutional_hrm_f08a_offline_package_receipt_v2",
        "gate_id": "F08A_OFFLINE_CLUSTER_PACKAGE",
        "status": "passed" if all(checks.values()) else "failed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "optimizer_launch_authorized": False,
        "live_cluster_drill": {
            "gate_id": "F08B_LIVE_CLUSTER_DRILL_AND_RUNTIME",
            "status": "pending",
            "requires_spend_authorization": True,
        },
        "checks": checks,
        "jobs": jobs,
        "per_job_caps": {
            "memory_max_gb": 96,
            "memory_swap_max_bytes": 0,
            "cpu_quota_percent": 1200,
            "io_read_mb_s": 200,
            "io_write_mb_s": 100,
            "gpu_memory_fraction": 0.90,
            "tasks_max": 64,
        },
        "authorized_sha256": authorized_sha256,
        "dataset": {
            "path": str(dataset),
            "mode": curriculum_manifest["mode"],
            "counts": curriculum_manifest["counts"],
        },
        "official_root": str(official_root),
    }
    atomic_json(receipt_path, receipt)
    dry_run_results = {}
    if receipt["status"] == "passed":
        for arm in ARMS:
            command = [
                sys.executable,
                str(trainer_path),
                "--arm",
                arm,
                "--seed",
                "713",
                "--dataset-dir",
                str(dataset),
                "--official-root",
                str(official_root),
                "--model-config",
                str(model_config_path),
                "--authorization-receipt",
                str(receipt_path),
                "--output-dir",
                str(output / "dry_runs" / arm),
                "--dry-run",
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=90,
            )
            dry_run_results[arm] = {
                "exit_code": result.returncode,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-2000:],
            }
        receipt["dry_run_results"] = dry_run_results
        receipt["checks"]["all_arm_dry_runs_passed"] = all(
            item["exit_code"] == 0 for item in dry_run_results.values()
        )
        receipt["status"] = (
            "passed" if all(receipt["checks"].values()) else "failed"
        )
        atomic_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
