#!/usr/bin/env python3
"""Build the immutable eight-job constitutional HRM cluster launch manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARMS = (
    "constitutional_metta",
    "constitutional_text_only",
    "utility_control",
    "shuffled_control",
)
SEEDS = (713, 719)
OFFICIAL_COMMIT = "ac15626f8db096a63c775b84c9dc868776a6feda"


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.repo_root.resolve()
    dataset = args.dataset_dir.resolve()
    curriculum_manifest = dataset / "manifest.json"
    model_config = root / "experiments" / "constitutional_hrm_200m_v2" / "model_config.json"
    jobs = []
    gpu = 0
    for arm in ARMS:
        for seed in SEEDS:
            jobs.append(
                {
                    "job_id": f"{arm}__seed_{seed}",
                    "arm": arm,
                    "seed": seed,
                    "cuda_visible_devices": str(gpu),
                    "distributed": False,
                }
            )
            gpu += 1
    manifest = {
        "schema_version": "constitutional_hrm_cluster_launch_manifest_v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "frozen",
        "optimizer_launch_authorized": False,
        "official_commit": OFFICIAL_COMMIT,
        "jobs": jobs,
        "cluster": {
            "gpu_type": "A100_80GB",
            "gpu_count": 8,
            "max_wall_seconds": 7200,
            "distributed_data_parallel": False,
        },
        "per_job_caps": {
            "memory_max_gb": 96,
            "memory_swap_max_bytes": 0,
            "cpu_quota_percent": 1200,
            "io_read_mb_s": 200,
            "io_write_mb_s": 100,
            "gpu_memory_fraction": 0.90,
            "tasks_max": 64,
        },
        "checkpoint": {
            "optimizer_steps": 250,
            "seconds": 300,
            "retain_latest": 2,
            "required_before_success": True,
        },
        "stop_rules": [
            "hash drift",
            "non-finite loss or gradient",
            "hard cap breach",
            "swap activity",
            "sustained I/O breach",
            "7200-second timeout",
            "missing checkpoint",
            "cleanup failure",
        ],
        "authorized_sha256": {
            "model_config": sha256_file(model_config),
            "curriculum_manifest": sha256_file(curriculum_manifest),
            "official_commit": OFFICIAL_COMMIT,
            "trainer": sha256_file(root / "scripts" / "train_constitutional_hrm_200m_v2.py"),
            "cluster_runner": sha256_file(
                root / "scripts" / "cluster" / "run_constitutional_hrm_200m_v2.sh"
            ),
        },
    }
    atomic_json(args.output.resolve(), manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
