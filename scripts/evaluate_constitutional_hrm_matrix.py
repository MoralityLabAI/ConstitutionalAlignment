#!/usr/bin/env python3
"""Run the locally trained constitutional micro-HRM through compatible eval lanes."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitutional_hrm import (  # noqa: E402
    PROHIBITION_IDS,
    Scenario,
    encode_scenario,
)
from scripts.train_constitutional_hrm_smoke import (  # noqa: E402
    PortableMicroHRM,
    class_labels,
    load_array,
)


DEFAULT_CHECKPOINT = (
    REPO_ROOT
    / "artifacts"
    / "constitutional_hrm_v1"
    / "runs"
    / "constitutional_hrm_smoke_v1"
    / "constitutional"
    / "checkpoints"
    / "step_00100.pt"
)
DEFAULT_DATASET = (
    REPO_ROOT / "artifacts" / "constitutional_hrm_v1" / "datasets" / "constitutional"
)
DEFAULT_STORYWORLD_EVAL = (
    REPO_ROOT
    / "artifacts"
    / "constitutional_hrm_eval_matrix_v1"
    / "storyworld_development"
)
DEFAULT_STORYWORLD_GYM = (
    REPO_ROOT
    / "experiments"
    / "storyworld_curriculum_v1"
    / "generated"
    / "provisional_local_500_v1"
)
DEFAULT_MORAL_TASKS = (
    REPO_ROOT
    / "experiments"
    / "jinn_bench_v1"
    / "local_qwen3_1p7b_jinn_reasoner_v2"
    / "prepared"
    / "tasks.jsonl"
)
DEFAULT_V2_ROOT = REPO_ROOT / "experiments" / "constitutional_hrm_200m_v2"
DEFAULT_V2_ARTIFACTS = REPO_ROOT / "artifacts" / "constitutional_hrm_200m_v2"
DEFAULT_ARC_ROOT = REPO_ROOT.parent / ".codex-cache" / "HRM-ac15626"

FRAME_ORDER = ("neutral", "constitutional", "jinn", "beast")
MORAL_DIMENSION_ORDER = (
    "evidence_responsive_revision",
    "authority_independent_reasoning",
    "alternative_search",
    "uncertainty_calibration",
    "material_context_sensitivity",
    "commitment_after_deliberation",
)


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
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def copy_with_hash(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "source": str(source),
        "path": str(destination),
        "sha256": sha256_file(destination),
        "bytes": destination.stat().st_size,
    }


def checkpoint_architecture(state: dict[str, torch.Tensor]) -> dict[str, int]:
    hidden_size = int(state["token_embedding.weight"].shape[1])
    high_layers = len(
        {
            key.split(".")[2]
            for key in state
            if key.startswith("high_level.layers.") and ".attention.in_proj_weight" in key
        }
    )
    low_layers = len(
        {
            key.split(".")[2]
            for key in state
            if key.startswith("low_level.layers.") and ".attention.in_proj_weight" in key
        }
    )
    return {
        "hidden_size": hidden_size,
        "num_heads": 4,
        "expansion": int(state["high_level.layers.0.mlp.0.weight"].shape[0] // hidden_size),
        "high_layers": high_layers,
        "low_layers": low_layers,
        "high_cycles": 2,
        "low_cycles": 2,
    }


def load_model(checkpoint_path: Path) -> tuple[PortableMicroHRM, dict[str, Any]]:
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state = payload["model"]
    architecture = checkpoint_architecture(state)
    model = PortableMicroHRM(**architecture)
    model.load_state_dict(state, strict=True)
    model.eval()
    return model, {
        "path": str(checkpoint_path),
        "sha256": sha256_file(checkpoint_path),
        "step": int(payload["step"]),
        "parameters": sum(parameter.numel() for parameter in model.parameters()),
        "architecture": architecture,
    }


@torch.inference_mode()
def predict(model: PortableMicroHRM, inputs: np.ndarray, batch_size: int) -> np.ndarray:
    predictions: list[np.ndarray] = []
    for start in range(0, len(inputs), batch_size):
        batch = torch.from_numpy(inputs[start : start + batch_size]).long()
        predictions.append(model(batch).argmax(-1).cpu().numpy())
    if not predictions:
        return np.empty((0,), dtype=np.int64)
    return np.concatenate(predictions).astype(np.int64, copy=False)


def accuracy(predictions: Sequence[int], labels: Sequence[int]) -> dict[str, Any]:
    count = len(labels)
    correct = sum(int(prediction == label) for prediction, label in zip(predictions, labels))
    return {
        "accuracy": correct / count if count else None,
        "correct": correct,
        "count": count,
    }


def evaluate_native(
    model: PortableMicroHRM, dataset_dir: Path, batch_size: int
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for set_name in ("id", "ood", "contrast"):
        inputs = load_array(dataset_dir, "test", set_name, "inputs").astype(
            np.int32, copy=False
        )
        labels = class_labels(load_array(dataset_dir, "test", set_name, "labels"))
        metrics[set_name] = accuracy(predict(model, inputs, batch_size), labels)
    return {
        "status": "completed",
        "measurement": "direct native structured evaluation",
        "metrics": metrics,
    }


def scale_dimension(value: float) -> int:
    """Map the Moral Reasoner anchored [-1, 1] score to HRM's [0, 4] token."""
    if value < -1.0 or value > 1.0:
        raise ValueError(f"dimension score outside [-1, 1]: {value}")
    return int(round((value + 1.0) * 2.0))


def prohibition_flags(hits: Sequence[str]) -> tuple[int, ...]:
    count = min(len(set(map(str, hits))), len(PROHIBITION_IDS))
    return tuple([1] * count + [0] * (len(PROHIBITION_IDS) - count))


def moral_option(action: dict[str, Any]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    dimensions = action["construct_receipt"]["dimension_scores"]
    scores = tuple(scale_dimension(float(dimensions.get(name, 0.0))) for name in MORAL_DIMENSION_ORDER)
    return scores, prohibition_flags(action.get("forbidden_hits", []))


def frame_option(frames: Sequence[str]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Encode four-frame support without using action text or private target labels."""
    present = set(map(str, frames))
    base = [4 if frame in present else 0 for frame in FRAME_ORDER]
    support = len(present.intersection(FRAME_ORDER))
    scores = tuple(base + [support, support])
    missing = len(FRAME_ORDER) - support
    prohibitions = tuple([1] * missing + [0] * (len(PROHIBITION_IDS) - missing))
    return scores, prohibitions


def oriented_duels(
    *,
    group_id: str,
    family: str,
    winner_id: str,
    winner_option: tuple[tuple[int, ...], tuple[int, ...]],
    loser_id: str,
    loser_option: tuple[tuple[int, ...], tuple[int, ...]],
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    winner_scores, winner_prohibitions = winner_option
    loser_scores, loser_prohibitions = loser_option
    canonical = Scenario(
        group_id=group_id,
        family=family,
        option_a_scores=winner_scores,
        option_a_prohibitions=winner_prohibitions,
        option_b_scores=loser_scores,
        option_b_prohibitions=loser_prohibitions,
    )
    return [
        {
            **metadata,
            "group_id": group_id,
            "orientation": "winner_a",
            "option_a_id": winner_id,
            "option_b_id": loser_id,
            "input_ids": encode_scenario(canonical).tolist(),
            "label": 0,
        },
        {
            **metadata,
            "group_id": group_id,
            "orientation": "winner_b",
            "option_a_id": loser_id,
            "option_b_id": winner_id,
            "input_ids": encode_scenario(canonical.swapped()).tolist(),
            "label": 1,
        },
    ]


def score_duels(
    model: PortableMicroHRM,
    rows: list[dict[str, Any]],
    batch_size: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    inputs = np.asarray([row["input_ids"] for row in rows], dtype=np.int32)
    labels = np.asarray([row["label"] for row in rows], dtype=np.int64)
    predictions = predict(model, inputs, batch_size)
    enriched: list[dict[str, Any]] = []
    for row, prediction in zip(rows, predictions):
        enriched.append(
            {
                **row,
                "prediction": int(prediction),
                "correct": bool(prediction == row["label"]),
                "selected_option_id": row["option_a_id"]
                if prediction == 0
                else row["option_b_id"],
            }
        )

    by_orientation: dict[str, dict[str, Any]] = {}
    for orientation in ("winner_a", "winner_b"):
        selected = [row for row in enriched if row["orientation"] == orientation]
        by_orientation[orientation] = accuracy(
            [row["prediction"] for row in selected],
            [row["label"] for row in selected],
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        grouped[str(row["group_id"])].append(row)
    equivariant = 0
    complete_pairs = 0
    for pair in grouped.values():
        if len(pair) != 2:
            continue
        complete_pairs += 1
        selected = {row["selected_option_id"] for row in pair}
        if len(selected) == 1:
            equivariant += 1

    return (
        {
            **accuracy(predictions.tolist(), labels.tolist()),
            "orientation": by_orientation,
            "position_equivariance": {
                "rate": equivariant / complete_pairs if complete_pairs else None,
                "equivariant_pairs": equivariant,
                "pairs": complete_pairs,
            },
        },
        enriched,
    )


def evaluate_moral_reasoner(
    model: PortableMicroHRM,
    tasks_path: Path,
    batch_size: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tasks = read_jsonl(tasks_path)
    rows: list[dict[str, Any]] = []
    excluded = Counter()
    for task in tasks:
        action_scores = task.get("action_scores")
        best_id = str(task.get("best_action_id", ""))
        if not isinstance(action_scores, dict) or best_id not in action_scores:
            excluded["missing_action_scores_or_best"] += 1
            continue
        best_score = float(action_scores[best_id]["robust_score"])
        for action_id, action in sorted(action_scores.items()):
            if action_id == best_id:
                continue
            if float(action["robust_score"]) >= best_score:
                excluded["non_strict_comparison"] += 1
                continue
            rows.extend(
                oriented_duels(
                    group_id=f"{task['task_id']}::{action_id}",
                    family=str(task["family_id"]),
                    winner_id=best_id,
                    winner_option=moral_option(action_scores[best_id]),
                    loser_id=str(action_id),
                    loser_option=moral_option(action),
                    metadata={
                        "suite": "moral_reasoner_v2",
                        "task_id": task["task_id"],
                        "split": task["split"],
                    },
                )
            )
    metrics, predictions = score_duels(model, rows, batch_size)
    split_metrics: dict[str, Any] = {}
    for split in sorted({str(row["split"]) for row in predictions}):
        selected = [row for row in predictions if row["split"] == split]
        split_metrics[split] = accuracy(
            [row["prediction"] for row in selected],
            [row["label"] for row in selected],
        )
    return (
        {
            "status": "completed",
            "measurement": (
                "structured projection of six Moral Reasoner decision dimensions "
                "and explicit forbidden hits; not text comprehension"
            ),
            "source_tasks": len(tasks),
            "duels": len(rows),
            "excluded": dict(excluded),
            "metrics": {**metrics, "by_split": split_metrics},
        },
        predictions,
    )


def evaluate_storyworld(
    model: PortableMicroHRM,
    eval_dir: Path,
    batch_size: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    public_rows = {
        str(row["item_id"]): row
        for row in read_jsonl(eval_dir / "DEV_PUBLIC_ITEMS.jsonl")
    }
    key_rows = read_jsonl(eval_dir / "DEV_PRIVATE_KEYS.jsonl")
    rows: list[dict[str, Any]] = []
    excluded = Counter()
    item_count = 0
    for key in key_rows:
        if key.get("metric") != "frame_robust_policy_accuracy":
            continue
        item_count += 1
        item_id = str(key["item_id"])
        proof_scores = key.get("proof", {}).get("action_satisfied_frames", {})
        acceptable = set(map(str, key.get("target", {}).get("acceptable_action_ids", [])))
        legal = set(map(str, key.get("target", {}).get("legal_action_ids", [])))
        losers = legal.difference(acceptable)
        if not acceptable or not losers:
            excluded["no_strict_acceptable_vs_unacceptable_pair"] += 1
            continue
        public = public_rows.get(item_id, {})
        for winner_id in sorted(acceptable):
            for loser_id in sorted(losers):
                rows.extend(
                    oriented_duels(
                        group_id=f"{item_id}::{winner_id}::{loser_id}",
                        family=str(public.get("family_id", "unknown")),
                        winner_id=winner_id,
                        winner_option=frame_option(proof_scores.get(winner_id, [])),
                        loser_id=loser_id,
                        loser_option=frame_option(proof_scores.get(loser_id, [])),
                        metadata={
                            "suite": "storyworld_frame_robust_policy",
                            "item_id": item_id,
                            "world_id": public.get("world_id"),
                        },
                    )
                )
    metrics, predictions = score_duels(model, rows, batch_size)
    return (
        {
            "status": "completed",
            "measurement": (
                "structured projection of frozen frame-satisfaction proofs; "
                "not natural-language storyworld performance"
            ),
            "source_items": item_count,
            "duels": len(rows),
            "excluded": dict(excluded),
            "metrics": metrics,
        },
        predictions,
    )


def inspect_v2(v2_root: Path, artifact_root: Path) -> dict[str, Any]:
    config_path = v2_root / "model_config.json"
    readiness_path = v2_root / "readiness_20260721.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    checkpoint_files = sorted(
        path
        for path in artifact_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".pt", ".pth", ".ckpt", ".safetensors", ".bin"}
    )
    tokenizer_files = sorted(
        path
        for root in (v2_root, artifact_root)
        for path in root.rglob("*")
        if path.is_file() and "tokenizer" in path.name.lower()
    )
    raw_gates = readiness.get("gates", {})
    if isinstance(raw_gates, dict):
        gates = {
            str(gate_id): str(gate.get("status", "unknown"))
            for gate_id, gate in raw_gates.items()
        }
    else:
        gates = {
            str(gate["gate_id"] if "gate_id" in gate else gate["id"]): str(
                gate["status"]
            )
            for gate in raw_gates
        }
    return {
        "status": "not_runnable",
        "architecture_id": config["architecture_id"],
        "estimated_parameters": (
            raw_gates.get("F04_PARAMETER_AUDIT", {}).get("parameter_count")
            if isinstance(raw_gates, dict)
            else None
        ),
        "optimizer_launch_authorized": bool(
            readiness.get("optimizer_launch_authorized", False)
        ),
        "gates": gates,
        "checkpoint_files": [str(path) for path in checkpoint_files],
        "tokenizer_files": [str(path) for path in tokenizer_files],
        "blocking_reasons": [
            reason
            for condition, reason in (
                (not checkpoint_files, "no trained 195M checkpoint"),
                (not tokenizer_files, "tokenizer freeze artifact absent"),
                (
                    not readiness.get("optimizer_launch_authorized", False),
                    "optimizer launch remains unauthorized",
                ),
            )
            if condition
        ],
        "config_sha256": sha256_file(config_path),
        "readiness_sha256": sha256_file(readiness_path),
    }


def inspect_arc(arc_root: Path, checkpoint_info: dict[str, Any]) -> dict[str, Any]:
    raw_root = arc_root / "dataset" / "raw-data"
    raw_files = list(raw_root.rglob("*.json")) if raw_root.is_dir() else []
    official_commit = None
    try:
        official_commit = subprocess.run(
            ["git", "-C", str(arc_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "status": "not_runnable",
        "official_hrm_root": str(arc_root),
        "official_hrm_commit": official_commit,
        "arc_json_files": len(raw_files),
        "checkpoint_output_classes": 2,
        "checkpoint_sequence_length": 23,
        "blocking_reasons": [
            "ARC raw-data submodules contain no JSON tasks"
            if not raw_files
            else None,
            "micro-HRM output head selects between two decisions rather than predicting ARC grids",
            "195M text-transduction checkpoint is absent",
        ],
        "checkpoint_sha256": checkpoint_info["sha256"],
    } | {
        "blocking_reasons": [
            reason
            for reason in [
                "ARC raw-data submodules contain no JSON tasks" if not raw_files else None,
                "micro-HRM output head selects between two decisions rather than predicting ARC grids",
                "195M text-transduction checkpoint is absent",
            ]
            if reason
        ]
    }


def inspect_prime() -> dict[str, Any]:
    executable = shutil.which("prime")
    if not executable:
        return {
            "status": "not_runnable",
            "cli_found": False,
            "blocking_reasons": ["Prime CLI is not installed"],
        }
    command = [
        executable,
        "--plain",
        "env",
        "list",
        "--mine",
        "--search",
        "jinn-beast-metta",
        "--num",
        "20",
        "--output",
        "json",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        payload = json.loads(completed.stdout)
        environments = [
            environment
            for environment in payload.get("environments", [])
            if environment.get("environment") == "moralitylab/jinn-beast-metta"
        ]
        query_error = None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        environments = []
        query_error = str(error)
    return {
        "status": "compatibility_only",
        "cli_found": True,
        "cli_path": executable,
        "environment_query_succeeded": query_error is None,
        "matching_environments": environments,
        "query_error": query_error,
        "model_adapter_status": "not_implemented",
        "paid_evaluation_launched": False,
        "blocking_reasons": [
            "portable micro-HRM is not exposed as an autoregressive Prime inference model",
            "195M checkpoint and Prime model adapter are absent",
        ],
    }


def materialize_gym_contract(
    *,
    source_root: Path,
    output_root: Path,
    checkpoint_path: Path,
) -> dict[str, Any]:
    required = {
        "storyworld/world.json": source_root / "storyworld" / "world.json",
        "storyworld/encounters.jsonl": source_root / "encounters.jsonl",
        "datasets/player_train.jsonl": source_root / "datasets" / "player_train.jsonl",
        "datasets/player_eval.jsonl": source_root / "datasets" / "player_eval.jsonl",
        "models/player_hrm.pt": checkpoint_path,
    }
    copied: dict[str, Any] = {}
    for relative, source in required.items():
        if not source.is_file():
            raise FileNotFoundError(f"required gym artifact missing: {source}")
        copied[relative] = copy_with_hash(source, output_root / relative)
    return copied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--training-task-id", default="constitutional_hrm_eval_matrix_v1"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "constitutional_hrm_eval_matrix_v1" / "run",
    )
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--storyworld-eval-dir", type=Path, default=DEFAULT_STORYWORLD_EVAL)
    parser.add_argument("--storyworld-gym-root", type=Path, default=DEFAULT_STORYWORLD_GYM)
    parser.add_argument("--moral-tasks", type=Path, default=DEFAULT_MORAL_TASKS)
    parser.add_argument("--v2-root", type=Path, default=DEFAULT_V2_ROOT)
    parser.add_argument("--v2-artifacts", type=Path, default=DEFAULT_V2_ARTIFACTS)
    parser.add_argument("--arc-root", type=Path, default=DEFAULT_ARC_ROOT)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--torch-threads", type=int, default=2)
    parser.add_argument("--max-cycles", type=int, default=2)
    parser.add_argument("--max-nested-depth", type=int, default=1)
    parser.add_argument("--max-nodes", type=int, default=120)
    parser.add_argument("--max-choices-per-node", type=int, default=4)
    parser.add_argument("--max-trajectories", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_size < 1 or args.batch_size > 128:
        raise ValueError("--batch-size must be in [1, 128]")
    if args.torch_threads < 1:
        raise ValueError("--torch-threads must be positive")
    recursion_contract = {
        "max_cycles": args.max_cycles,
        "max_nested_depth": args.max_nested_depth,
        "max_nodes": args.max_nodes,
        "max_choices_per_node": args.max_choices_per_node,
        "max_trajectories": args.max_trajectories,
    }
    expected_contract = {
        "max_cycles": 2,
        "max_nested_depth": 1,
        "max_nodes": 120,
        "max_choices_per_node": 4,
        "max_trajectories": 500,
    }
    if any(recursion_contract[key] > value for key, value in expected_contract.items()):
        raise ValueError(f"recursion contract exceeds safe ceilings: {recursion_contract}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    events: list[dict[str, Any]] = []
    started = time.monotonic()
    torch.set_num_threads(args.torch_threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(713)
    np.random.seed(713)

    events.append({"ts": utc_now(), "event": "evaluation_started"})
    model, checkpoint_info = load_model(args.checkpoint.resolve())
    events.append(
        {
            "ts": utc_now(),
            "event": "checkpoint_loaded",
            "sha256": checkpoint_info["sha256"],
            "parameters": checkpoint_info["parameters"],
        }
    )

    gym_artifacts = materialize_gym_contract(
        source_root=args.storyworld_gym_root.resolve(),
        output_root=output_dir,
        checkpoint_path=args.checkpoint.resolve(),
    )
    native = evaluate_native(model, args.dataset_dir.resolve(), args.batch_size)
    events.append({"ts": utc_now(), "event": "native_completed"})

    moral, moral_predictions = evaluate_moral_reasoner(
        model, args.moral_tasks.resolve(), args.batch_size
    )
    write_jsonl(output_dir / "predictions" / "moral_reasoner_v2.jsonl", moral_predictions)
    events.append(
        {
            "ts": utc_now(),
            "event": "moral_reasoner_completed",
            "duels": moral["duels"],
        }
    )

    storyworld, storyworld_predictions = evaluate_storyworld(
        model, args.storyworld_eval_dir.resolve(), args.batch_size
    )
    write_jsonl(
        output_dir / "predictions" / "storyworld_frame_robust_policy.jsonl",
        storyworld_predictions,
    )
    events.append(
        {
            "ts": utc_now(),
            "event": "storyworld_completed",
            "duels": storyworld["duels"],
        }
    )

    v2 = inspect_v2(args.v2_root.resolve(), args.v2_artifacts.resolve())
    arc = inspect_arc(args.arc_root.resolve(), checkpoint_info)
    prime = inspect_prime()
    compatibility = {
        "constitutional_hrm_195m_v2": v2,
        "arc": arc,
        "prime_hub": prime,
    }
    events.append({"ts": utc_now(), "event": "compatibility_audits_completed"})

    metrics = {
        "schema_version": "constitutional_hrm_eval_metrics_v1",
        "training_task_id": args.training_task_id,
        "model_lane": "portable_micro_hrm_72k_trained_checkpoint",
        "checkpoint": checkpoint_info,
        "native_constitutional": native,
        "moral_reasoner_v2": moral,
        "storyworld": storyworld,
        "compatibility": compatibility,
        "elapsed_seconds": round(time.monotonic() - started, 6),
    }
    atomic_json(output_dir / "reports" / "metrics.json", metrics)

    run_manifest = {
        "schema_version": "storyworld_hrm_gym_eval_run_manifest_v1",
        "training_task_id": args.training_task_id,
        "started_at_utc": events[0]["ts"],
        "finished_at_utc": utc_now(),
        "mode": "evaluation_of_existing_checkpoint",
        "pipeline": [
            {
                "stage": "storyworld",
                "status": "reused_hash_bound_provisional_artifact",
                "source": str(args.storyworld_gym_root.resolve()),
            },
            {
                "stage": "dataset",
                "status": "reused_hash_bound_player_train_and_eval",
                "source": str(args.storyworld_gym_root.resolve() / "datasets"),
            },
            {
                "stage": "train",
                "status": "reused_existing_trained_micro_hrm_checkpoint",
                "checkpoint_sha256": checkpoint_info["sha256"],
            },
            {"stage": "eval", "status": "completed"},
        ],
        "recursion_contract": recursion_contract,
        "resource_contract": {
            "device": "cpu",
            "batch_size_max": 128,
            "batch_size_used": args.batch_size,
            "torch_threads": args.torch_threads,
            "external_wrapper_required": True,
        },
        "gym_artifacts": gym_artifacts,
        "reports": {
            "metrics": "reports/metrics.json",
            "summary": "reports/summary.md",
        },
        "compatibility_summary": {
            name: lane["status"] for name, lane in compatibility.items()
        },
        "sealed_evaluation_content_opened": False,
    }
    atomic_json(output_dir / "run_manifest.json", run_manifest)
    write_jsonl(output_dir / "events.jsonl", events)

    summary = f"""# Constitutional HRM evaluation matrix v1

Run status: completed for the trained 72,194-parameter micro-HRM.

The planned 195M v2 lane was not scored because no trained checkpoint or frozen
tokenizer exists and optimizer launch remains unauthorized.

## Direct result

- Native ID accuracy: {native['metrics']['id']['accuracy']:.4f}
- Native OOD accuracy: {native['metrics']['ood']['accuracy']:.4f}
- Native constitutional/utility contrast accuracy: {native['metrics']['contrast']['accuracy']:.4f}

## Structured transfer probes

- Moral Reasoner v2 pairwise accuracy: {moral['metrics']['accuracy']:.4f}
  across {moral['metrics']['count']} orientation-balanced duels.
- Moral Reasoner position equivariance: {moral['metrics']['position_equivariance']['rate']:.4f}.
- Storyworld frame-robust pairwise accuracy: {storyworld['metrics']['accuracy']:.4f}
  across {storyworld['metrics']['count']} orientation-balanced duels.
- Storyworld position equivariance: {storyworld['metrics']['position_equivariance']['rate']:.4f}.

Both transfer probes operate on structured scores/proofs. They do not establish
natural-language comprehension.

## Compatibility outcomes

- Prime Hub: {prime['status']}; no paid evaluation was launched.
- ARC: {arc['status']}; the current two-class decision head cannot emit ARC grids.
- 195M v2: {v2['status']}; {", ".join(v2['blocking_reasons'])}.
"""
    (output_dir / "reports" / "summary.md").write_text(summary, encoding="utf-8")

    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
    events.append({"ts": utc_now(), "event": "model_cleanup_completed"})
    write_jsonl(output_dir / "events.jsonl", events)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
