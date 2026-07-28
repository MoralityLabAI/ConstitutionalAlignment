#!/usr/bin/env python3
"""Train one arm/seed of the pinned 195.6M official-HRM constitutional model."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib
import json
import math
import os
import random
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

OFFICIAL_COMMIT = "ac15626f8db096a63c775b84c9dc868776a6feda"
ARMS = (
    "constitutional_metta",
    "constitutional_text_only",
    "utility_control",
    "shuffled_control",
)
SEEDS = (713, 719)
STOP_REQUESTED = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def git_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout.strip()


def _signal_stop(signum: int, _frame: Any) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=ARMS)
    parser.add_argument("--seed", required=True, type=int, choices=SEEDS)
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--official-root", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--authorization-receipt", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-wall-seconds", type=int, default=7200)
    parser.add_argument("--max-optimizer-steps", type=int, default=100000)
    parser.add_argument("--checkpoint-steps", type=int, default=250)
    parser.add_argument("--checkpoint-seconds", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--gradient-accumulation", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=0.1)
    parser.add_argument("--gradient-clip", type=float, default=1.0)
    parser.add_argument("--gpu-memory-fraction", type=float, default=0.90)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--cluster-drill", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def validate_authorization(
    *,
    receipt_path: Path,
    model_config_path: Path,
    dataset_dir: Path,
    official_root: Path,
    require_optimizer_authorization: bool,
) -> dict[str, Any]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if require_optimizer_authorization:
        if receipt.get("gate_id") != "F09A_TWO_HOUR_SPEND_AUTHORIZATION":
            raise ValueError("optimizer work requires an F09A authorization receipt")
        if receipt.get("status") != "authorized" or not receipt.get(
            "optimizer_launch_authorized", False
        ):
            raise ValueError("optimizer work has not received F09A authorization")
    else:
        if receipt.get("gate_id") != "F08A_OFFLINE_CLUSTER_PACKAGE":
            raise ValueError("dry-run receipt is not an F08A package receipt")
        if receipt.get("status") != "passed":
            raise ValueError("offline package receipt has not passed")
    expected = receipt["authorized_sha256"]
    observed = {
        "model_config": sha256_file(model_config_path),
        "curriculum_manifest": sha256_file(dataset_dir / "manifest.json"),
    }
    official = git_commit(official_root)
    if official != OFFICIAL_COMMIT:
        raise ValueError(f"official HRM commit drift: {official}")
    if expected["model_config"] != observed["model_config"]:
        raise ValueError("model config differs from the authorization receipt")
    if expected["curriculum_manifest"] != observed["curriculum_manifest"]:
        raise ValueError("curriculum manifest differs from the authorization receipt")
    if expected["official_commit"] != official:
        raise ValueError("official HRM commit differs from the authorization receipt")
    return {
        "receipt": str(receipt_path),
        "observed_sha256": observed,
        "official_commit": official,
    }


def validate_dataset(
    dataset_dir: Path, arm: str, *, require_production: bool = True
) -> tuple[np.ndarray, np.ndarray]:
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    if require_production and manifest.get("mode") != "production":
        raise ValueError("optimizer launch requires a production curriculum")
    if require_production and manifest["counts"]["train_examples"] != 96_000:
        raise ValueError("optimizer launch requires exactly 96,000 train examples")
    inputs_path = dataset_dir / "common" / "train_inputs.npy"
    labels_path = dataset_dir / "arms" / arm / "train_labels.npy"
    expected_hashes = manifest["file_sha256"]
    for path in (inputs_path, labels_path):
        relative = str(path.relative_to(dataset_dir)).replace("\\", "/")
        if sha256_file(path) != expected_hashes[relative]:
            raise ValueError(f"dataset hash drift: {relative}")
    inputs = np.load(inputs_path, mmap_mode="r")
    labels = np.load(labels_path, mmap_mode="r")
    if (
        require_production
        and inputs.shape != (96_000, 512)
        or labels.shape != inputs.shape
        or inputs.shape[1] != 512
    ):
        raise ValueError(f"unexpected train array shapes: {inputs.shape}, {labels.shape}")
    return inputs, labels


def model_dict(model_config: dict[str, Any], batch_size: int) -> dict[str, Any]:
    architecture = model_config["architecture"]
    return {
        "batch_size": batch_size,
        "vocab_size": int(architecture["vocab_size"]),
        "seq_len": int(architecture["seq_len"]),
        "num_puzzle_identifiers": 1,
        "causal": False,
        "H_cycles": int(architecture["high_cycles"]),
        "L_cycles": int(architecture["low_cycles"]),
        "H_layers": int(architecture["high_layers"]),
        "L_layers": int(architecture["low_layers"]),
        "hidden_size": int(architecture["hidden_size"]),
        "expansion": float(architecture["expansion"]),
        "num_heads": int(architecture["num_heads"]),
        "pos_encodings": str(architecture["position_encoding"]),
        "puzzle_emb_ndim": 0,
        "halt_max_steps": 1,
        "halt_exploration_prob": 0.0,
        "forward_dtype": "bfloat16",
    }


def process_gpu_memory_mb() -> float:
    try:
        output = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        total = 0.0
        for line in output.splitlines():
            fields = [item.strip() for item in line.split(",")]
            if len(fields) == 2 and int(fields[0]) == os.getpid():
                total += float(fields[1])
        return total
    except (OSError, subprocess.SubprocessError, ValueError):
        return -1.0


def process_swap_kb() -> int:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmSwap:"):
                return int(line.split()[1])
    except OSError:
        return -1
    return -1


def cosine_lr(step: int, total_steps: int, base_lr: float) -> float:
    warmup = min(50, max(1, total_steps // 20))
    if step < warmup:
        return base_lr * (step + 1) / warmup
    progress = (step - warmup) / max(1, total_steps - warmup)
    return base_lr * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * progress)))


def save_checkpoint(
    *,
    output_dir: Path,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    optimizer_step: int,
    micro_step: int,
    elapsed_seconds: float,
    config: dict[str, Any],
) -> Path:
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    path = checkpoint_dir / f"step_{optimizer_step:07d}.pt"
    temporary = path.with_suffix(".pt.tmp")
    torch.save(
        {
            "schema_version": "constitutional_hrm_checkpoint_v2",
            "optimizer_step": optimizer_step,
            "micro_step": micro_step,
            "elapsed_seconds": elapsed_seconds,
            "model_config": config,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "torch_rng_state": torch.get_rng_state(),
            "cuda_rng_state": torch.cuda.get_rng_state(),
        },
        temporary,
    )
    os.replace(temporary, path)
    checkpoints = sorted(checkpoint_dir.glob("step_*.pt"))
    for stale in checkpoints[:-2]:
        stale.unlink()
    atomic_json(
        output_dir / "latest_checkpoint.json",
        {
            "path": str(path),
            "sha256": sha256_file(path),
            "optimizer_step": optimizer_step,
            "generated_at_utc": utc_now(),
        },
    )
    return path


def save_model_export(
    *,
    output_dir: Path,
    model: torch.nn.Module,
    optimizer_step: int,
    config: dict[str, Any],
) -> Path:
    export_path = output_dir / f"model_step_{optimizer_step:07d}.pt"
    temporary = export_path.with_suffix(".pt.tmp")
    torch.save(
        {
            "schema_version": "constitutional_hrm_model_export_v2",
            "optimizer_step": optimizer_step,
            "model_config": config,
            "model": model.state_dict(),
        },
        temporary,
    )
    os.replace(temporary, export_path)
    atomic_json(
        output_dir / "model_export.json",
        {
            "path": str(export_path),
            "sha256": sha256_file(export_path),
            "optimizer_step": optimizer_step,
            "generated_at_utc": utc_now(),
        },
    )
    return export_path


def main() -> int:
    args = parse_args()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, _signal_stop)
    output_dir = args.output_dir.resolve()
    events_path = output_dir / "events.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path.write_text("", encoding="utf-8")
    started = time.monotonic()
    status = "preparing"
    abort_reason = ""
    checkpoint_path: Path | None = None
    model_export_path: Path | None = None
    optimizer_step = 0
    micro_step = 0
    peak_gpu_memory_mb = 0.0
    receipt: dict[str, Any] = {
        "schema_version": "constitutional_hrm_train_receipt_v2",
        "arm": args.arm,
        "seed": args.seed,
        "status": status,
        "started_at_utc": utc_now(),
        "caps": {
            "max_wall_seconds": args.max_wall_seconds,
            "gpu_memory_fraction": args.gpu_memory_fraction,
            "batch_size": args.batch_size,
            "gradient_accumulation": args.gradient_accumulation,
            "checkpoint_steps": args.checkpoint_steps,
            "checkpoint_seconds": args.checkpoint_seconds,
        },
    }
    atomic_json(output_dir / "train_receipt.json", receipt)
    model = None
    optimizer = None
    carry = None
    inputs = None
    labels = None
    try:
        authorization = validate_authorization(
            receipt_path=args.authorization_receipt.resolve(),
            model_config_path=args.model_config.resolve(),
            dataset_dir=args.dataset_dir.resolve(),
            official_root=args.official_root.resolve(),
            require_optimizer_authorization=not args.dry_run,
        )
        inputs, labels = validate_dataset(
            args.dataset_dir.resolve(),
            args.arm,
            require_production=not args.dry_run,
        )
        if args.dry_run:
            status = "dry_run_passed"
            receipt.update(
                {
                    "status": status,
                    "authorization": authorization,
                    "dataset_shapes": [list(inputs.shape), list(labels.shape)],
                }
            )
            atomic_json(output_dir / "train_receipt.json", receipt)
            return 0
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for the 195.6M optimizer launch")
        if args.cluster_drill and (
            args.max_optimizer_steps > 1
            or args.batch_size > 1
            or args.gradient_accumulation > 1
            or args.max_wall_seconds > 300
        ):
            raise ValueError(
                "cluster drill is limited to one optimizer step, batch 1, "
                "accumulation 1, and 300 seconds"
            )
        if not 0.10 <= args.gpu_memory_fraction <= 0.95:
            raise ValueError("gpu-memory-fraction must be in [0.10, 0.95]")
        if process_swap_kb() > 0:
            raise RuntimeError("swap is already active for the training process")

        torch.cuda.set_per_process_memory_fraction(args.gpu_memory_fraction, 0)
        torch.manual_seed(args.seed)
        torch.cuda.manual_seed_all(args.seed)
        np.random.seed(args.seed)
        random.seed(args.seed)
        torch.set_float32_matmul_precision("high")
        model_config = json.loads(args.model_config.read_text(encoding="utf-8"))
        config = model_dict(model_config, args.batch_size)
        sys.path.insert(0, str(args.official_root.resolve()))
        model_module = importlib.import_module("models.hrm.hrm_act_v1")
        losses_module = importlib.import_module("models.losses")
        with torch.device("cuda"):
            model = losses_module.ACTLossHead(
                model_module.HierarchicalReasoningModel_ACTV1(config),
                loss_type="softmax_cross_entropy",
            )
        if args.compile:
            model = torch.compile(model, dynamic=False)
        model.train()
        parameter_count = sum(parameter.numel() for parameter in model.parameters())
        if not 190_000_000 <= parameter_count <= 205_000_000:
            raise RuntimeError(f"parameter count outside authorization band: {parameter_count}")
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=args.learning_rate,
            betas=(0.9, 0.95),
            weight_decay=args.weight_decay,
        )
        order_generator = np.random.default_rng(args.seed)
        order = order_generator.permutation(len(inputs))
        order_position = 0
        optimizer.zero_grad(set_to_none=True)
        last_checkpoint = time.monotonic()
        status = "running"
        append_jsonl(
            events_path,
            {
                "ts": utc_now(),
                "event": "optimizer_launch",
                "parameter_count": parameter_count,
                "authorization": authorization,
            },
        )

        while optimizer_step < args.max_optimizer_steps:
            elapsed = time.monotonic() - started
            if STOP_REQUESTED:
                abort_reason = "signal_stop"
                break
            if elapsed >= args.max_wall_seconds:
                status = "completed_wall_cap"
                break
            if order_position + args.batch_size > len(order):
                order = order_generator.permutation(len(inputs))
                order_position = 0
            indices = order[order_position : order_position + args.batch_size]
            order_position += args.batch_size
            batch = {
                "inputs": torch.from_numpy(np.asarray(inputs[indices])).cuda(
                    non_blocking=True
                ),
                "labels": torch.from_numpy(np.asarray(labels[indices])).cuda(
                    non_blocking=True
                ),
                "puzzle_identifiers": torch.zeros(
                    (args.batch_size,), dtype=torch.int32, device="cuda"
                ),
            }
            if carry is None:
                with torch.device("cuda"):
                    carry = model.initial_carry(batch)
            carry, loss, metrics, _, _ = model(
                carry=carry,
                batch=batch,
                return_keys=[],
            )
            if not torch.isfinite(loss.detach()):
                abort_reason = "non_finite_loss"
                break
            scaled_loss = loss / (args.batch_size * args.gradient_accumulation)
            scaled_loss.backward()
            micro_step += 1
            if micro_step % args.gradient_accumulation == 0:
                gradient_norm = torch.nn.utils.clip_grad_norm_(
                    model.parameters(), args.gradient_clip
                )
                if not torch.isfinite(gradient_norm):
                    abort_reason = "non_finite_gradient_norm"
                    break
                lr = cosine_lr(
                    optimizer_step,
                    args.max_optimizer_steps,
                    args.learning_rate,
                )
                for group in optimizer.param_groups:
                    group["lr"] = lr
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                optimizer_step += 1
                now = time.monotonic()
                gpu_memory_mb = process_gpu_memory_mb()
                peak_gpu_memory_mb = max(peak_gpu_memory_mb, gpu_memory_mb)
                swap_kb = process_swap_kb()
                if swap_kb > 0:
                    abort_reason = "swap_activity"
                    break
                append_jsonl(
                    events_path,
                    {
                        "ts": utc_now(),
                        "event": "optimizer_step",
                        "optimizer_step": optimizer_step,
                        "micro_step": micro_step,
                        "loss": float(loss.detach()),
                        "gradient_norm": float(gradient_norm.detach()),
                        "lr": lr,
                        "gpu_memory_mb": gpu_memory_mb,
                        "swap_kb": swap_kb,
                        "elapsed_seconds": now - started,
                        "accuracy_sum": float(metrics["accuracy"].detach()),
                        "count": float(metrics["count"].detach()),
                    },
                )
                if (
                    optimizer_step % args.checkpoint_steps == 0
                    or now - last_checkpoint >= args.checkpoint_seconds
                ):
                    checkpoint_path = save_checkpoint(
                        output_dir=output_dir,
                        model=model,
                        optimizer=optimizer,
                        optimizer_step=optimizer_step,
                        micro_step=micro_step,
                        elapsed_seconds=now - started,
                        config=config,
                    )
                    last_checkpoint = time.monotonic()
            del batch, scaled_loss, loss, metrics

        if optimizer_step > 0 and (
            checkpoint_path is None
            or checkpoint_path.stem != f"step_{optimizer_step:07d}"
        ):
            checkpoint_path = save_checkpoint(
                output_dir=output_dir,
                model=model,
                optimizer=optimizer,
                optimizer_step=optimizer_step,
                micro_step=micro_step,
                elapsed_seconds=time.monotonic() - started,
                config=config,
            )
        if optimizer_step > 0:
            model_export_path = save_model_export(
                output_dir=output_dir,
                model=model,
                optimizer_step=optimizer_step,
                config=config,
            )
        if abort_reason:
            status = "aborted"
        elif status == "running":
            status = "completed_step_cap"
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        abort_reason = f"{type(exc).__name__}: {exc}"
        append_jsonl(
            events_path,
            {"ts": utc_now(), "event": "exception", "reason": abort_reason},
        )
    finally:
        receipt.update(
            {
                "status": status,
                "abort_reason": abort_reason,
                "optimizer_step": optimizer_step,
                "micro_step": micro_step,
                "elapsed_seconds": time.monotonic() - started,
                "peak_process_gpu_memory_mb": peak_gpu_memory_mb,
                "latest_checkpoint": str(checkpoint_path) if checkpoint_path else None,
                "model_export": (
                    str(model_export_path) if model_export_path else None
                ),
                "finished_at_utc": utc_now(),
            }
        )
        carry = None
        inputs = None
        labels = None
        if optimizer is not None:
            optimizer.zero_grad(set_to_none=True)
        optimizer = None
        model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
        receipt["cleanup"] = {
            "cuda_memory_allocated_after": (
                int(torch.cuda.memory_allocated()) if torch.cuda.is_available() else 0
            ),
            "cuda_memory_reserved_after": (
                int(torch.cuda.memory_reserved()) if torch.cuda.is_available() else 0
            ),
            "process_swap_kb_after": process_swap_kb(),
        }
        atomic_json(output_dir / "train_receipt.json", receipt)
    return 0 if status.startswith("completed") or status == "dry_run_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
