#!/usr/bin/env python3
"""Evaluate all eight arm/seed model exports on the frozen unsealed suites."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ARMS = (
    "constitutional_metta",
    "constitutional_text_only",
    "utility_control",
    "shuffled_control",
)
SEEDS = (713, 719)


def sha256_file(path: Path) -> str:
    import hashlib

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
    parser.add_argument("--checkpoint-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--official-root",
        type=Path,
        default=REPO_ROOT.parent / ".codex-cache" / "HRM-ac15626",
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--gpu-memory-fraction", type=float, default=0.80)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-examples-per-suite", type=int)
    return parser.parse_args()


def discover_exports(checkpoint_root: Path) -> dict[tuple[str, int], Path]:
    exports: dict[tuple[str, int], Path] = {}
    for arm in ARMS:
        for seed in SEEDS:
            job = checkpoint_root / f"{arm}__seed_{seed}"
            receipt_path = job / "model_export.json"
            if not receipt_path.is_file():
                raise FileNotFoundError(receipt_path)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            recorded = Path(str(receipt["path"]))
            checkpoint = (
                recorded
                if recorded.is_file()
                else receipt_path.parent / recorded.name
            )
            if not checkpoint.is_file():
                raise FileNotFoundError(checkpoint)
            if sha256_file(checkpoint) != str(receipt["sha256"]):
                raise ValueError(f"model export hash drift: {checkpoint}")
            exports[(arm, seed)] = checkpoint.resolve()
    if len(exports) != len(ARMS) * len(SEEDS):
        raise AssertionError("expected exactly eight arm/seed model exports")
    return exports


def decision_rate(receipt: dict[str, Any], condition: str) -> float:
    value = receipt["suites"]["constitutional_validation"]["metrics"][
        "by_condition"
    ][condition]["decision"]["rate"]
    if value is None:
        raise ValueError(f"missing decision rate for {condition}")
    return float(value)


def summarize_matrix(
    receipts: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    per_job: dict[str, Any] = {}
    for (arm, seed), receipt in sorted(receipts.items()):
        per_job[f"{arm}__seed_{seed}"] = {
            "checkpoint_sha256": receipt["checkpoint"]["sha256"],
            "suites": {
                suite: suite_receipt["metrics"]
                for suite, suite_receipt in receipt["suites"].items()
            },
        }
    pilot_primary = {}
    both_primary_clear = True
    for seed in SEEDS:
        metta = receipts[("constitutional_metta", seed)]
        full = decision_rate(metta, "constitution_metta_full")
        removed = decision_rate(metta, "constitution_removed")
        text_removed = decision_rate(
            receipts[("constitutional_text_only", seed)],
            "constitution_removed",
        )
        shuffled_removed = decision_rate(
            receipts[("shuffled_control", seed)],
            "constitution_removed",
        )
        seed_clear = full >= 0.80 and removed >= 0.70
        both_primary_clear &= seed_clear
        pilot_primary[str(seed)] = {
            "full_prompt_decision_accuracy": full,
            "prompt_removed_decision_accuracy": removed,
            "metta_delta_over_text_only_removed": removed - text_removed,
            "metta_delta_over_shuffled_removed": removed - shuffled_removed,
            "primary_thresholds_clear": seed_clear,
        }
    return {
        "per_job": per_job,
        "pilot_primary": pilot_primary,
        "pilot_thresholds_met_for_both_seeds": both_primary_clear,
        "overnight_spend_authorized": False,
    }


def main() -> int:
    args = parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output}")
    output.mkdir(parents=True)
    receipt: dict[str, Any] = {
        "schema_version": "constitutional_hrm_direct_matrix_receipt_v2",
        "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "sealed_test_opened": False,
        "jobs": {},
    }
    atomic_json(output / "matrix_receipt.json", receipt)
    try:
        exports = discover_exports(args.checkpoint_root.resolve())
        evaluations: dict[tuple[str, int], dict[str, Any]] = {}
        for (arm, seed), checkpoint in exports.items():
            job_id = f"{arm}__seed_{seed}"
            job_output = output / job_id
            command = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "evaluate_constitutional_hrm_195m_v2.py"),
                "--checkpoint",
                str(checkpoint),
                "--official-root",
                str(args.official_root.resolve()),
                "--output-dir",
                str(job_output),
                "--device",
                args.device,
                "--gpu-memory-fraction",
                str(args.gpu_memory_fraction),
                "--batch-size",
                str(args.batch_size),
                "--include-constitutional-validation",
            ]
            if args.max_examples_per_suite is not None:
                command.extend(
                    [
                        "--max-examples-per-suite",
                        str(args.max_examples_per_suite),
                    ]
                )
            completed = subprocess.run(
                command,
                check=False,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=7200,
            )
            (output / f"{job_id}.stdout.log").write_text(
                completed.stdout,
                encoding="utf-8",
            )
            (output / f"{job_id}.stderr.log").write_text(
                completed.stderr,
                encoding="utf-8",
            )
            evaluation = json.loads(
                (job_output / "evaluation_receipt.json").read_text(
                    encoding="utf-8"
                )
            )
            if completed.returncode != 0 or evaluation["status"] != "completed":
                raise RuntimeError(f"direct evaluation failed for {job_id}")
            if evaluation["sealed_test_opened"]:
                raise RuntimeError("unsealed matrix unexpectedly opened sealed data")
            evaluations[(arm, seed)] = evaluation
            receipt["jobs"][job_id] = {
                "status": "completed",
                "checkpoint_sha256": evaluation["checkpoint"]["sha256"],
                "receipt": str(job_output / "evaluation_receipt.json"),
            }
            atomic_json(output / "matrix_receipt.json", receipt)
        receipt["summary"] = summarize_matrix(evaluations)
        receipt["status"] = "completed"
        return_code = 0
    except Exception as error:  # noqa: BLE001
        receipt["status"] = "failed"
        receipt["error"] = f"{type(error).__name__}: {error}"
        return_code = 1
    receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    atomic_json(output / "matrix_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
