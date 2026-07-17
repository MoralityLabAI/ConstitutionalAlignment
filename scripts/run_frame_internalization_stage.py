#!/usr/bin/env python3
"""Run one frame-internalization compute stage inside a capped Slurm allocation."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAN = (
    REPO_ROOT
    / "experiments"
    / "frame_internalization_sft_v1"
    / "compute_stage_plan_v1.json"
)
DEFAULT_AMENDMENT = (
    REPO_ROOT
    / "experiments"
    / "frame_internalization_sft_v1"
    / "protocol_amendment_v2.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("pilot", "overnight"), required=True)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--training-task-id", required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--checkpoint-every-steps", type=int, required=True)
    parser.add_argument("--checkpoint-every-minutes", type=int, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the frozen plan and command shape without requiring Slurm or starting it.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("an explicit command is required after --")
    return args


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_text(parts: list[str]) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_utc(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("authorization timestamp must include a UTC offset")
    return parsed.astimezone(dt.timezone.utc)


def validate_authorization(
    path: Path,
    args: argparse.Namespace,
    command_hash: str,
    plan_path: Path,
) -> dict[str, Any]:
    authorization = read_json(path)
    failures: list[str] = []
    expected_state = "pilot_ready" if args.stage == "pilot" else "overnight_promotion_passed"
    checks = {
        "schema_version": authorization.get("schema_version")
        == "frame_internalization_compute_authorization.v1",
        "stage": authorization.get("stage") == args.stage,
        "training_task_id": authorization.get("training_task_id") == args.training_task_id,
        "authorized": authorization.get("authorized") is True,
        "not_example": authorization.get("example") is False,
        "human_approver_id": bool(authorization.get("human_approver_id")),
        "all_required_gates_passed": authorization.get("all_required_gates_passed") is True,
        "command_sha256": authorization.get("command_sha256") == command_hash,
        "run_directory": Path(str(authorization.get("run_directory", ""))).resolve()
        == args.run_dir.resolve(),
        "checkpoint_every_steps": authorization.get("checkpoint_every_steps")
        == args.checkpoint_every_steps,
        "checkpoint_every_minutes": authorization.get("checkpoint_every_minutes")
        == args.checkpoint_every_minutes,
        "compute_stage_plan_sha256": authorization.get("compute_stage_plan_sha256")
        == sha256_file(plan_path),
        "protocol_amendment_sha256": authorization.get("protocol_amendment_sha256")
        == sha256_file(DEFAULT_AMENDMENT),
        "evidence_required_state": authorization.get("evidence_receipt", {}).get(
            "required_state"
        )
        == expected_state,
    }
    failures.extend(name for name, passed in checks.items() if not passed)
    try:
        expires_at = parse_utc(str(authorization.get("expires_at", "")))
        authorized_at = parse_utc(str(authorization.get("authorized_at", "")))
        now = dt.datetime.now(dt.timezone.utc)
        if not authorized_at <= now < expires_at:
            failures.append("authorization_time_window")
    except (TypeError, ValueError):
        failures.append("authorization_timestamps")

    evidence = authorization.get("evidence_receipt", {})
    evidence_path = Path(str(evidence.get("path", "")))
    evidence_path = evidence_path if evidence_path.is_absolute() else REPO_ROOT / evidence_path
    if not evidence_path.is_file():
        failures.append("evidence_receipt_missing")
    else:
        if sha256_file(evidence_path) != evidence.get("sha256"):
            failures.append("evidence_receipt_hash")
        else:
            evidence_doc = read_json(evidence_path)
            if args.stage == "pilot" and evidence_doc.get("pilot_ready") is not True:
                failures.append("evidence_pilot_not_ready")
            if args.stage == "overnight" and evidence_doc.get("promotion_passed") is not True:
                failures.append("evidence_overnight_promotion_not_passed")
    if failures:
        raise RuntimeError("compute authorization failed: " + ", ".join(sorted(set(failures))))
    return authorization


def directory_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for candidate in path.rglob("*"):
        try:
            if candidate.is_file() and not candidate.is_symlink():
                total += candidate.stat().st_size
        except OSError:
            continue
    return total


def newest_checkpoint(root: Path) -> tuple[str | None, float | None]:
    if not root.exists():
        return None, None
    newest_path: Path | None = None
    newest_mtime: float | None = None
    for candidate in root.rglob("*"):
        try:
            mtime = candidate.stat().st_mtime
        except OSError:
            continue
        if newest_mtime is None or mtime > newest_mtime:
            newest_path = candidate
            newest_mtime = mtime
    return str(newest_path) if newest_path else None, newest_mtime


def parse_slurm_time(value: str) -> int:
    match = re.fullmatch(r"(?:(\d+)-)?(\d+):(\d+):(\d+)", value)
    if match:
        days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
        return days * 86400 + hours * 3600 + minutes * 60 + seconds
    match = re.fullmatch(r"(\d+):(\d+)", value)
    if match:
        minutes, seconds = (int(part) for part in match.groups())
        return minutes * 60 + seconds
    raise ValueError(f"unrecognized Slurm TimeLimit: {value}")


def slurm_preflight(stage_cap: dict[str, Any], resource_caps: dict[str, Any]) -> dict[str, Any]:
    job_id = os.environ.get("SLURM_JOB_ID")
    if not job_id:
        raise RuntimeError("execution requires a Slurm allocation (SLURM_JOB_ID is absent)")
    nodes = int(os.environ.get("SLURM_NNODES", "0"))
    cpus = int(os.environ.get("SLURM_CPUS_PER_TASK", "0"))
    submission = resource_caps["slurm_submission_caps"]
    if nodes != int(submission["nodes"]):
        raise RuntimeError(f"expected exactly {submission['nodes']} Slurm node, observed {nodes}")
    if not 1 <= cpus <= int(submission["cpus_per_task"]):
        raise RuntimeError(
            f"SLURM_CPUS_PER_TASK must be 1..{submission['cpus_per_task']}, observed {cpus}"
        )

    visible = [item for item in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if item]
    if len(visible) != int(resource_caps["gpus"]):
        raise RuntimeError(
            f"expected exactly {resource_caps['gpus']} CUDA-visible GPUs, observed {len(visible)}"
        )

    if not shutil.which("scontrol"):
        raise RuntimeError("scontrol is required to verify the scheduler wall-clock cap")
    job = subprocess.run(
        ["scontrol", "show", "job", "-o", job_id],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    match = re.search(r"(?:^|\s)TimeLimit=([^\s]+)", job)
    if not match:
        raise RuntimeError("Slurm job record does not expose TimeLimit")
    allocation_seconds = parse_slurm_time(match.group(1))
    if allocation_seconds > int(stage_cap["wall_clock_seconds"]):
        raise RuntimeError(
            f"Slurm TimeLimit {allocation_seconds}s exceeds frozen cap "
            f"{stage_cap['wall_clock_seconds']}s"
        )

    mem_per_node = int(os.environ.get("SLURM_MEM_PER_NODE", "0") or 0)
    mem_per_cpu = int(os.environ.get("SLURM_MEM_PER_CPU", "0") or 0)
    allocated_mem_mib = mem_per_node or (mem_per_cpu * cpus)
    memory_cap_mib = int(submission["memory_gib"]) * 1024
    if not 1 <= allocated_mem_mib <= memory_cap_mib:
        raise RuntimeError(
            f"Slurm memory allocation must be 1..{memory_cap_mib} MiB, observed "
            f"{allocated_mem_mib} MiB"
        )
    return {
        "slurm_job_id": job_id,
        "nodes": nodes,
        "cpus_per_task": cpus,
        "memory_mib": allocated_mem_mib,
        "allocation_seconds": allocation_seconds,
        "visible_gpu_count": len(visible),
    }


def gpu_sample(expected_type: str) -> dict[str, Any]:
    if not shutil.which("nvidia-smi"):
        raise RuntimeError("nvidia-smi is required for GPU identity and health checks")
    query = (
        "name,temperature.gpu,memory.used,memory.total,"
        "ecc.errors.uncorrected.volatile.total"
    )
    result = subprocess.run(
        ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            raise RuntimeError(f"unexpected nvidia-smi row: {line}")
        name, temperature, memory_used, memory_total, uncorrected = parts
        if expected_type.lower() not in name.lower():
            raise RuntimeError(f"expected {expected_type}, observed {name}")
        rows.append(
            {
                "name": name,
                "temperature_c": int(temperature),
                "memory_used_mib": int(memory_used),
                "memory_total_mib": int(memory_total),
                "uncorrected_ecc": None if uncorrected in {"N/A", "[N/A]"} else int(uncorrected),
            }
        )
    return {"gpus": rows}


def stop_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=30)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass


def main() -> int:
    args = parse_args()
    plan_path = args.plan.resolve()
    plan = read_json(plan_path)
    if plan.get("schema_version") != "frame_internalization_compute_stage_plan.v1":
        raise ValueError("unexpected compute stage plan schema_version")
    if plan.get("status") != "frozen":
        raise ValueError("compute stage plan status drifted")
    caps = plan["hard_resource_caps"]
    stage_cap = caps[args.stage]
    checkpoint = plan["checkpoint_contract"]
    if not 1 <= args.checkpoint_every_steps <= int(checkpoint["maximum_steps_between_checkpoints"]):
        raise ValueError("checkpoint step interval exceeds the frozen cap")
    if not 1 <= args.checkpoint_every_minutes <= int(
        checkpoint["maximum_minutes_between_checkpoints"]
    ):
        raise ValueError("checkpoint time interval exceeds the frozen cap")
    command_hash = sha256_text(args.command)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run_valid",
                    "stage": args.stage,
                    "training_task_id": args.training_task_id,
                    "plan": str(plan_path),
                    "command_sha256": command_hash,
                    "wall_clock_cap_seconds": stage_cap["wall_clock_seconds"],
                    "maximum_gpu_hours": stage_cap["maximum_gpu_hours"],
                    "authorization_would_be_required_for_execution": True,
                    "execution_started": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    authorization_path = args.authorization.resolve()
    authorization = validate_authorization(
        authorization_path, args, command_hash, plan_path
    )
    run_dir = args.run_dir.resolve()
    checkpoint_root = args.checkpoint_root.resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        raise RuntimeError("run directory must be absent or empty at first launch")
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    event_path = run_dir / "stage_events.jsonl"
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"

    def event(name: str, details: dict[str, Any]) -> None:
        row = {
            "schema_version": "frame_internalization_stage_event.v1",
            "timestamp_utc": utc_now(),
            "training_task_id": args.training_task_id,
            "stage": args.stage,
            "event": name,
            "example": False,
            "details": details,
        }
        with event_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    preflight = slurm_preflight(stage_cap, caps)
    initial_gpu = gpu_sample(str(caps["gpu_type"]))
    if len(initial_gpu["gpus"]) != int(caps["gpus"]):
        raise RuntimeError("nvidia-smi GPU count does not match the frozen allocation")
    event(
        "preflight",
        {
            **preflight,
            "gpu_type": caps["gpu_type"],
            "command_sha256": command_hash,
            "wall_clock_cap_seconds": stage_cap["wall_clock_seconds"],
            "checkpoint_every_steps": args.checkpoint_every_steps,
            "checkpoint_every_minutes": args.checkpoint_every_minutes,
            "authorization_sha256": sha256_file(authorization_path),
            "human_approver_id": authorization["human_approver_id"],
        },
    )

    environment = os.environ.copy()
    environment["OMP_NUM_THREADS"] = str(preflight["cpus_per_task"])
    environment["FRAME_TRAINING_TASK_ID"] = args.training_task_id
    environment["FRAME_STAGE"] = args.stage
    environment["FRAME_RUN_DIR"] = str(run_dir)
    environment["FRAME_CHECKPOINT_ROOT"] = str(checkpoint_root)
    environment["FRAME_CHECKPOINT_EVERY_STEPS"] = str(args.checkpoint_every_steps)
    environment["FRAME_CHECKPOINT_EVERY_MINUTES"] = str(args.checkpoint_every_minutes)

    started = time.monotonic()
    abort_reason: str | None = None
    high_temperature_samples = 0
    last_gpu_sample = 0.0
    last_checkpoint_path: str | None = None
    last_checkpoint_mtime: float | None = None
    with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
        process = subprocess.Popen(
            args.command,
            cwd=REPO_ROOT,
            env=environment,
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=(os.name == "posix"),
        )
        event("started", {"pid": process.pid, "run_directory": str(run_dir)})
        while process.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed >= int(stage_cap["wall_clock_seconds"]):
                abort_reason = "wall_clock_cap_reached"
                break
            size = directory_bytes(run_dir)
            if size > int(stage_cap["maximum_run_directory_bytes"]):
                abort_reason = "run_directory_byte_cap_exceeded"
                break
            path, mtime = newest_checkpoint(checkpoint_root)
            if path and mtime and (path != last_checkpoint_path or mtime != last_checkpoint_mtime):
                last_checkpoint_path, last_checkpoint_mtime = path, mtime
                event("checkpoint", {"path": path, "observed_mtime": mtime})
            checkpoint_lag = elapsed if last_checkpoint_mtime is None else time.time() - last_checkpoint_mtime
            maximum_lag = (args.checkpoint_every_minutes + 10) * 60
            if checkpoint_lag > maximum_lag:
                abort_reason = "required_checkpoint_more_than_ten_minutes_late"
                break
            if elapsed - last_gpu_sample >= 60:
                sample = gpu_sample(str(caps["gpu_type"]))
                if len(sample["gpus"]) != int(caps["gpus"]):
                    abort_reason = "allocated_gpu_lost"
                    break
                if any((row["uncorrected_ecc"] or 0) > 0 for row in sample["gpus"]):
                    abort_reason = "uncorrectable_ecc_event"
                    break
                if any(row["temperature_c"] >= 90 for row in sample["gpus"]):
                    high_temperature_samples += 1
                else:
                    high_temperature_samples = 0
                if high_temperature_samples >= 2:
                    abort_reason = "gpu_temperature_at_or_above_90c_for_two_samples"
                    break
                event("resource_sample", {**sample, "run_directory_bytes": size})
                last_gpu_sample = elapsed
            time.sleep(5)

        if abort_reason:
            event("abort", {"reason": abort_reason, "elapsed_seconds": round(time.monotonic() - started, 3)})
            stop_process_tree(process)
        return_code = process.wait()

    elapsed = time.monotonic() - started
    if not abort_reason and return_code == 0:
        event("completed", {"return_code": return_code, "elapsed_seconds": round(elapsed, 3)})
    elif not abort_reason:
        abort_reason = "child_process_nonzero_exit"
        event("abort", {"reason": abort_reason, "return_code": return_code, "elapsed_seconds": round(elapsed, 3)})

    surviving = int(process.poll() is None)
    final_bytes = directory_bytes(run_dir)
    event(
        "cleanup",
        {
            "surviving_child_processes": surviving,
            "run_directory_bytes": final_bytes,
            "result": "clean" if surviving == 0 else "failed",
            "abort_reason": abort_reason,
        },
    )
    return 0 if abort_reason is None and return_code == 0 and surviving == 0 else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
