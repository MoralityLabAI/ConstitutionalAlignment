#!/usr/bin/env python3
"""Portable CPU micro-HRM smoke for a structured constitutional policy task."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitutional_hrm import (  # noqa: E402
    DECISION_A_ID,
    DECISION_B_ID,
    OFFICIAL_HRM_COMMIT,
    SEQ_LEN,
    VOCAB_SIZE,
    build_arm_dataset,
    sha256_file,
)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class ReasoningBlock(nn.Module):
    def __init__(self, hidden_size: int, num_heads: int, expansion: int) -> None:
        super().__init__()
        self.attention = nn.MultiheadAttention(
            hidden_size, num_heads, dropout=0.0, batch_first=True
        )
        self.attention_norm = nn.LayerNorm(hidden_size)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_size, hidden_size * expansion),
            nn.SiLU(),
            nn.Linear(hidden_size * expansion, hidden_size),
        )
        self.mlp_norm = nn.LayerNorm(hidden_size)

    def forward(self, state: torch.Tensor, injection: torch.Tensor) -> torch.Tensor:
        hidden = state + injection
        attended, _ = self.attention(hidden, hidden, hidden, need_weights=False)
        hidden = self.attention_norm(hidden + attended)
        return self.mlp_norm(hidden + self.mlp(hidden))


class ReasoningModule(nn.Module):
    def __init__(self, hidden_size: int, num_heads: int, expansion: int, layers: int) -> None:
        super().__init__()
        self.layers = nn.ModuleList(
            ReasoningBlock(hidden_size, num_heads, expansion) for _ in range(layers)
        )

    def forward(self, state: torch.Tensor, injection: torch.Tensor) -> torch.Tensor:
        hidden = state + injection
        for layer in self.layers:
            hidden = layer(hidden, torch.zeros_like(hidden))
        return hidden


class PortableMicroHRM(nn.Module):
    """Small compatibility model preserving HRM's two-timescale recurrence."""

    def __init__(
        self,
        *,
        hidden_size: int,
        num_heads: int,
        expansion: int,
        high_layers: int,
        low_layers: int,
        high_cycles: int,
        low_cycles: int,
    ) -> None:
        super().__init__()
        self.high_cycles = high_cycles
        self.low_cycles = low_cycles
        self.token_embedding = nn.Embedding(VOCAB_SIZE, hidden_size)
        self.position_embedding = nn.Parameter(torch.empty(SEQ_LEN, hidden_size))
        self.high_initial = nn.Parameter(torch.empty(SEQ_LEN, hidden_size))
        self.low_initial = nn.Parameter(torch.empty(SEQ_LEN, hidden_size))
        self.high_level = ReasoningModule(
            hidden_size, num_heads, expansion, high_layers
        )
        self.low_level = ReasoningModule(hidden_size, num_heads, expansion, low_layers)
        self.output = nn.Linear(hidden_size, 2)
        nn.init.normal_(self.position_embedding, std=0.02)
        nn.init.normal_(self.high_initial, std=0.5)
        nn.init.normal_(self.low_initial, std=0.5)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        batch_size = input_ids.shape[0]
        embedded = self.token_embedding(input_ids) + self.position_embedding
        high = self.high_initial.unsqueeze(0).expand(batch_size, -1, -1)
        low = self.low_initial.unsqueeze(0).expand(batch_size, -1, -1)

        # Match the official implementation's deep-recurrence/one-step-gradient pattern.
        with torch.no_grad():
            for high_step in range(self.high_cycles):
                for low_step in range(self.low_cycles):
                    last = (
                        high_step == self.high_cycles - 1
                        and low_step == self.low_cycles - 1
                    )
                    if not last:
                        low = self.low_level(low, high + embedded)
                if high_step != self.high_cycles - 1:
                    high = self.high_level(high, low)

        low = self.low_level(low, high + embedded)
        high = self.high_level(high, low)
        return self.output(high[:, 0])


def load_array(dataset_dir: Path, split: str, set_name: str, field: str) -> np.ndarray:
    return np.load(dataset_dir / split / f"{set_name}__{field}.npy")


def class_labels(labels: np.ndarray) -> np.ndarray:
    first = labels[:, 0]
    if not np.all(np.isin(first, (DECISION_A_ID, DECISION_B_ID))):
        raise ValueError("unexpected decision token in labels")
    return np.where(first == DECISION_A_ID, 0, 1).astype(np.int64)


@torch.inference_mode()
def evaluate(
    model: nn.Module, dataset_dir: Path, set_name: str, batch_size: int
) -> dict[str, float | int]:
    inputs = torch.from_numpy(load_array(dataset_dir, "test", set_name, "inputs")).long()
    labels = torch.from_numpy(
        class_labels(load_array(dataset_dir, "test", set_name, "labels"))
    ).long()
    correct = 0
    model.eval()
    for start in range(0, len(inputs), batch_size):
        logits = model(inputs[start : start + batch_size])
        correct += int((logits.argmax(-1) == labels[start : start + batch_size]).sum())
    return {"accuracy": correct / max(1, len(inputs)), "correct": correct, "count": len(inputs)}


def save_checkpoint(
    *, model: nn.Module, optimizer: torch.optim.Optimizer, step: int, path: Path
) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    torch.save(
        {"step": step, "model": model.state_dict(), "optimizer": optimizer.state_dict()},
        temporary,
    )
    os.replace(temporary, path)
    return sha256_file(path)


def run_arm(args: argparse.Namespace, arm: str, dataset_dir: Path, run_dir: Path) -> dict[str, Any]:
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(args.torch_threads)
    torch.use_deterministic_algorithms(True)

    model = PortableMicroHRM(
        hidden_size=args.hidden_size,
        num_heads=args.num_heads,
        expansion=args.expansion,
        high_layers=args.high_layers,
        low_layers=args.low_layers,
        high_cycles=args.high_cycles,
        low_cycles=args.low_cycles,
    ).cpu()
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay
    )
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    events_path = run_dir / "events.jsonl"
    if events_path.exists():
        events_path.unlink()

    inputs = torch.from_numpy(load_array(dataset_dir, "train", "all", "inputs")).long()
    labels = torch.from_numpy(
        class_labels(load_array(dataset_dir, "train", "all", "labels"))
    ).long()
    generator = torch.Generator().manual_seed(args.seed + 1)
    baseline = {
        set_name: evaluate(model, dataset_dir, set_name, args.eval_batch_size)
        for set_name in ("id", "ood", "contrast")
    }
    append_jsonl(
        events_path,
        {
            "ts": utc_now(),
            "event": "arm_start",
            "arm": arm,
            "parameters": parameter_count,
            "baseline": baseline,
        },
    )

    if args.validate_only:
        summary = {
            "arm": arm,
            "status": "validated",
            "steps_completed": 0,
            "parameters": parameter_count,
            "baseline": baseline,
            "final": baseline,
            "checkpoints": [],
        }
        atomic_json(run_dir / "summary.json", summary)
        del optimizer, model, inputs, labels
        gc.collect()
        return summary

    started = time.monotonic()
    last_checkpoint = started
    checkpoints: list[dict[str, Any]] = []
    loss_value = float("nan")
    for step in range(1, args.steps + 1):
        if time.monotonic() - started > args.arm_timeout_seconds:
            raise TimeoutError(f"arm {arm} exceeded {args.arm_timeout_seconds} seconds")
        indices = torch.randint(
            low=0,
            high=len(inputs),
            size=(args.batch_size,),
            generator=generator,
        )
        model.train()
        logits = model(inputs[indices])
        loss = nn.functional.cross_entropy(logits, labels[indices])
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), args.gradient_clip)
        optimizer.step()
        loss_value = float(loss.detach())

        due_step = step % args.checkpoint_steps == 0
        due_time = time.monotonic() - last_checkpoint >= args.checkpoint_seconds
        if due_step or due_time or step == args.steps:
            metrics = {
                set_name: evaluate(model, dataset_dir, set_name, args.eval_batch_size)
                for set_name in ("id", "ood", "contrast")
            }
            checkpoint_path = run_dir / "checkpoints" / f"step_{step:05d}.pt"
            checkpoint_hash = save_checkpoint(
                model=model, optimizer=optimizer, step=step, path=checkpoint_path
            )
            receipt = {
                "step": step,
                "path": str(checkpoint_path),
                "sha256": checkpoint_hash,
                "loss": loss_value,
                "metrics": metrics,
            }
            checkpoints.append(receipt)
            append_jsonl(
                events_path,
                {"ts": utc_now(), "event": "checkpoint", "arm": arm, **receipt},
            )
            last_checkpoint = time.monotonic()

    final = {
        set_name: evaluate(model, dataset_dir, set_name, args.eval_batch_size)
        for set_name in ("id", "ood", "contrast")
    }
    summary = {
        "arm": arm,
        "status": "completed",
        "steps_completed": args.steps,
        "parameters": parameter_count,
        "last_loss": loss_value,
        "elapsed_seconds": time.monotonic() - started,
        "baseline": baseline,
        "final": final,
        "checkpoints": checkpoints,
    }
    atomic_json(run_dir / "summary.json", summary)
    append_jsonl(
        events_path,
        {"ts": utc_now(), "event": "arm_finish", "arm": arm, "final": final},
    )
    del optimizer, model, inputs, labels
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--training-task-id", default="constitutional_hrm_smoke_v1")
    parser.add_argument("--constitution", type=Path, default=Path("constitution.md"))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("artifacts/constitutional_hrm_v1"),
    )
    parser.add_argument(
        "--arms",
        nargs="+",
        choices=("constitutional", "utility", "shuffled"),
        default=("constitutional", "utility", "shuffled"),
    )
    parser.add_argument("--seed", type=int, default=713)
    parser.add_argument("--train-groups", type=int, default=64)
    parser.add_argument("--id-groups", type=int, default=24)
    parser.add_argument("--ood-groups", type=int, default=24)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--eval-batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--gradient-clip", type=float, default=1.0)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--num-heads", type=int, default=4)
    parser.add_argument("--expansion", type=int, default=2)
    parser.add_argument("--high-layers", type=int, default=1)
    parser.add_argument("--low-layers", type=int, default=1)
    parser.add_argument("--high-cycles", type=int, default=2)
    parser.add_argument("--low-cycles", type=int, default=2)
    parser.add_argument("--checkpoint-steps", type=int, default=25)
    parser.add_argument("--checkpoint-seconds", type=int, default=60)
    parser.add_argument("--arm-timeout-seconds", type=int, default=180)
    parser.add_argument("--torch-threads", type=int, default=2)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    positive = (
        "steps",
        "batch_size",
        "eval_batch_size",
        "hidden_size",
        "num_heads",
        "expansion",
        "high_layers",
        "low_layers",
        "high_cycles",
        "low_cycles",
        "checkpoint_steps",
        "checkpoint_seconds",
        "arm_timeout_seconds",
        "torch_threads",
    )
    for name in positive:
        if getattr(args, name) < 1:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    if args.hidden_size % args.num_heads:
        raise ValueError("--hidden-size must be divisible by --num-heads")


def main() -> int:
    args = parse_args()
    validate_args(args)
    run_root = args.output_root / "runs" / args.training_task_id
    dataset_root = args.output_root / "datasets"
    run_root.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    manifests: dict[str, dict[str, Any]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    try:
        for arm in args.arms:
            manifests[arm] = build_arm_dataset(
                output_dir=dataset_root / arm,
                constitution_path=args.constitution,
                arm=arm,
                seed=args.seed,
                train_groups=args.train_groups,
                id_groups=args.id_groups,
                ood_groups=args.ood_groups,
            )
            summaries[arm] = run_arm(
                args, arm, dataset_root / arm, run_root / arm
            )

        gates: dict[str, bool | None] = {
            "dataset_hash_bound": all(
                bool(manifest["dataset_sha256"]) for manifest in manifests.values()
            ),
            "balanced_training_labels": all(
                manifest["label_balance"]["train_a"]
                == manifest["label_balance"]["train_b"]
                for manifest in manifests.values()
            ),
            "constitutional_id_accuracy_gte_0p75": None,
            "constitutional_contrast_accuracy_gte_0p75": None,
            "constitutional_contrast_delta_over_shuffled_gte_0p10": None,
        }
        if not args.validate_only:
            constitutional = summaries["constitutional"]["final"]
            shuffled = summaries["shuffled"]["final"]
            gates.update(
                {
                    "constitutional_id_accuracy_gte_0p75": constitutional["id"]["accuracy"] >= 0.75,
                    "constitutional_contrast_accuracy_gte_0p75": constitutional["contrast"]["accuracy"] >= 0.75,
                    "constitutional_contrast_delta_over_shuffled_gte_0p10": (
                        constitutional["contrast"]["accuracy"]
                        - shuffled["contrast"]["accuracy"]
                        >= 0.10
                    ),
                }
            )
        overall = {
            "schema_version": "constitutional_hrm_smoke_summary_v1",
            "training_task_id": args.training_task_id,
            "status": "validated" if args.validate_only else "completed",
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "device": "cpu",
            "official_hrm_commit": OFFICIAL_HRM_COMMIT,
            "architecture": {
                "kind": "portable_micro_hrm_compatibility_smoke",
                "hidden_size": args.hidden_size,
                "num_heads": args.num_heads,
                "high_layers": args.high_layers,
                "low_layers": args.low_layers,
                "high_cycles": args.high_cycles,
                "low_cycles": args.low_cycles,
            },
            "training": {
                "steps_per_arm": 0 if args.validate_only else args.steps,
                "batch_size": args.batch_size,
                "seed": args.seed,
                "checkpoint_steps": args.checkpoint_steps,
                "checkpoint_seconds": args.checkpoint_seconds,
                "chunk_strategy": "matched_arm_sequential_scenario_family_chunks",
            },
            "dataset_manifests": {
                arm: {
                    "path": str(dataset_root / arm / "manifest.json"),
                    "sha256": sha256_file(dataset_root / arm / "manifest.json"),
                    "dataset_sha256": manifest["dataset_sha256"],
                }
                for arm, manifest in manifests.items()
            },
            "arms": summaries,
            "gates": gates,
        }
        atomic_json(run_root / "summary.json", overall)
        print(json.dumps(overall, indent=2, sort_keys=True))
        return 0
    except BaseException as exc:
        failure = {
            "schema_version": "constitutional_hrm_smoke_summary_v1",
            "training_task_id": args.training_task_id,
            "status": "aborted",
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "abort_reason": f"{type(exc).__name__}: {exc}",
            "arms": summaries,
        }
        atomic_json(run_root / "summary.json", failure)
        raise
    finally:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


if __name__ == "__main__":
    raise SystemExit(main())
