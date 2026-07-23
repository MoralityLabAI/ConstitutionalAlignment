#!/usr/bin/env python3
"""Run the fail-closed PrimeLab F04 environment and offline-runtime probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


EXPECTED_GPU_MEMORY_MIB = 80 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def git_output(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def parse_nvidia_inventory(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            raise ValueError(f"unexpected nvidia-smi inventory row: {line}")
        rows.append(
            {
                "index": int(parts[0]),
                "name": parts[1],
                "memory_total_mib": int(parts[2]),
                "driver_version": parts[3],
                "uuid": parts[4],
            }
        )
    return rows


def gpu_inventory() -> list[dict[str, Any]]:
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,driver_version,uuid",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    return parse_nvidia_inventory(output)


def gpu_compute_apps() -> list[str]:
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"nvidia-smi compute-app query failed: {result.stderr}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=30)


def run_with_timeout(
    command: Sequence[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> int:
    with (
        stdout_path.open("w", encoding="utf-8") as stdout_handle,
        stderr_path.open("w", encoding="utf-8") as stderr_handle,
    ):
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            start_new_session=True,
        )
        try:
            return process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            terminate_process_group(process)
            return 124


def network_namespace_available(python: Path) -> bool:
    code = (
        "import socket\n"
        "try:\n"
        " socket.create_connection(('1.1.1.1', 53), timeout=1)\n"
        "except OSError:\n"
        " raise SystemExit(0)\n"
        "raise SystemExit(2)\n"
    )
    result = subprocess.run(
        ["unshare", "--net", "--", str(python), "-c", code],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--maximum-wall-clock-seconds", type=int, default=1800)
    parser.add_argument("--maximum-gpu-hours", type=float, default=0.5)
    parser.add_argument("--maximum-output-bytes", type=int, default=1073741824)
    parser.add_argument("--checkpoint-every-requests", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    model_dir = args.model_dir.resolve()
    output_dir = args.output_dir.resolve()
    python = args.python.resolve()
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite output directory: {output_dir}")
    if (
        min(
            args.maximum_wall_clock_seconds,
            args.maximum_gpu_hours,
            args.maximum_output_bytes,
            args.checkpoint_every_requests,
        )
        <= 0
    ):
        raise ValueError("all inference caps must be positive")
    if git_output(repo_root, "rev-parse", "HEAD") != args.source_commit:
        raise RuntimeError("source commit does not match the frozen F04 command")
    if git_output(repo_root, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("tracked worktree must be clean")
    if not model_dir.is_dir():
        raise FileNotFoundError(f"model directory is missing: {model_dir}")

    output_dir.mkdir(parents=True)
    started_at = datetime.now(tz=timezone.utc)
    runtime_receipt = output_dir / "primelab_base_runtime_receipt.json"
    stdout_path = output_dir / "runtime.stdout.log"
    stderr_path = output_dir / "runtime.stderr.log"
    environment_lock = output_dir / "environment_lock.txt"
    lock_lines = sorted(
        line.strip()
        for line in subprocess.check_output(
            [str(python), "-m", "pip", "freeze", "--all"], text=True
        ).splitlines()
        if line.strip()
    )
    environment_lock.write_text("\n".join(lock_lines) + "\n", encoding="utf-8")
    inventory = gpu_inventory()
    network_isolated = network_namespace_available(python)
    gpu_topology_passed = bool(
        len(inventory) == 1
        and "A100" in inventory[0]["name"]
        and inventory[0]["memory_total_mib"] >= EXPECTED_GPU_MEMORY_MIB
    )
    gpu_hour_cap_passed = (
        args.maximum_wall_clock_seconds <= args.maximum_gpu_hours * 3600
    )
    preflight_failures = []
    if not gpu_topology_passed:
        preflight_failures.append("exact_single_a100_80gb_topology")
    if not gpu_hour_cap_passed:
        preflight_failures.append("gpu_hour_cap_covers_wall_clock")
    if not network_isolated:
        preflight_failures.append("hard_linux_network_namespace")
    if preflight_failures:
        compute_apps_after = gpu_compute_apps()
        summary = {
            "schema_version": "frame_internalization_primelab_f04_probe.v1",
            "status": "failed",
            "passed": False,
            "started_at_utc": started_at.isoformat(),
            "finished_at_utc": datetime.now(tz=timezone.utc).isoformat(),
            "source_commit": args.source_commit,
            "gpu_inventory": inventory,
            "environment_lock": str(environment_lock),
            "environment_lock_sha256": sha256_file(environment_lock),
            "runtime_receipt": str(runtime_receipt),
            "runtime_receipt_sha256": None,
            "runtime_exit_code": None,
            "network_isolation": {
                "method": "linux_network_namespace",
                "passed": network_isolated,
            },
            "inference_caps": {
                "maximum_wall_clock_seconds": args.maximum_wall_clock_seconds,
                "maximum_gpu_hours": args.maximum_gpu_hours,
                "maximum_output_bytes": args.maximum_output_bytes,
                "checkpoint_every_requests": args.checkpoint_every_requests,
            },
            "observed_output_bytes": directory_bytes(output_dir),
            "cleanup": {
                "required": True,
                "compute_apps_after": compute_apps_after,
                "passed": not compute_apps_after,
            },
            "preflight_failures": preflight_failures,
            "stdout_sha256": None,
            "stderr_sha256": None,
        }
        write_json(output_dir / "f04_probe_summary.json", summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 2

    command = [
        "unshare",
        "--net",
        "--",
        str(python),
        str(repo_root / "scripts/audit_qwen3_1p7b_local_runtime.py"),
        "--model-dir",
        str(model_dir),
        "--venue",
        "primelab",
        "--source-commit",
        args.source_commit,
        "--output",
        str(runtime_receipt),
        "--verification-date",
        started_at.date().isoformat(),
    ]
    exit_code = run_with_timeout(
        command,
        repo_root,
        stdout_path,
        stderr_path,
        args.maximum_wall_clock_seconds,
    )
    runtime = (
        json.loads(runtime_receipt.read_text(encoding="utf-8"))
        if runtime_receipt.is_file()
        else None
    )
    output_bytes = directory_bytes(output_dir)
    compute_apps_after = gpu_compute_apps()
    passed = bool(
        exit_code == 0
        and runtime
        and runtime.get("passed") is True
        and output_bytes <= args.maximum_output_bytes
        and not compute_apps_after
    )
    summary = {
        "schema_version": "frame_internalization_primelab_f04_probe.v1",
        "status": "complete" if passed else "failed",
        "passed": passed,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "source_commit": args.source_commit,
        "gpu_inventory": inventory,
        "environment_lock": str(environment_lock),
        "environment_lock_sha256": sha256_file(environment_lock),
        "runtime_receipt": str(runtime_receipt),
        "runtime_receipt_sha256": (
            sha256_file(runtime_receipt) if runtime_receipt.is_file() else None
        ),
        "runtime_exit_code": exit_code,
        "network_isolation": {
            "method": "linux_network_namespace",
            "passed": network_isolated,
        },
        "gpu_topology_passed": gpu_topology_passed,
        "gpu_hour_cap_passed": gpu_hour_cap_passed,
        "inference_caps": {
            "maximum_wall_clock_seconds": args.maximum_wall_clock_seconds,
            "maximum_gpu_hours": args.maximum_gpu_hours,
            "maximum_output_bytes": args.maximum_output_bytes,
            "checkpoint_every_requests": args.checkpoint_every_requests,
        },
        "observed_output_bytes": output_bytes,
        "cleanup": {
            "required": True,
            "compute_apps_after": compute_apps_after,
            "passed": not compute_apps_after,
        },
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
    }
    write_json(output_dir / "f04_probe_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
