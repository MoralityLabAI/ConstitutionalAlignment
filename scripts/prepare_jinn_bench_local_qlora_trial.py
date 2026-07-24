#!/usr/bin/env python3
"""Prepare a development-only JinnBench QLoRA dataset and sealed eval slice."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from transformers import AutoTokenizer

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANDIDATES = REPO_ROOT / "jinn_bench" / "data" / "construct_candidate_sft_v1.jsonl"
DEFAULT_TASKS = REPO_ROOT / "jinn_bench" / "data" / "construct_tasks_v1.jsonl"
DEFAULT_MODEL = Path(r"D:\Research_Engine\models\Qwen3-1.7B-70d244c")
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "experiments"
    / "jinn_bench_v1"
    / "local_qwen3_1p7b_jinn_qlora_v1"
    / "prepared"
)
CONSTRUCT_ID = "jinn_ness_v1"
CONSTITUTION_ID = "jinn_bench_jinn_development_v1"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError(f"{path} is empty")
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_task_prompt(task: dict[str, Any]) -> str:
    return (
        f"{task['prompt']}\n\nVisible facts:\n"
        + "\n".join(f"- {fact['id']}: {fact['text']}" for fact in task["visible_facts"])
        + "\n\nActions:\n"
        + "\n".join(
            f"- {action_id}: {action['text']}"
            for action_id, action in task["action_scores"].items()
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    candidates_path = args.candidates.resolve()
    tasks_path = args.tasks.resolve()
    model_path = args.model.resolve()
    output_dir = args.output_dir.resolve()
    tasks = read_jsonl(tasks_path)
    candidates = read_jsonl(candidates_path)

    candidate_tasks = {
        row["task_id"]: row
        for row in tasks
        if row["split"] == "candidate_train" and row["construct_id"] == CONSTRUCT_ID
    }
    development_tasks = [
        row
        for row in tasks
        if row["split"] == "development" and row["construct_id"] == CONSTRUCT_ID
    ]
    if len(candidate_tasks) != 4 or len(development_tasks) != 2:
        raise ValueError("expected four candidate and two development Jinn construct tasks")
    if set(candidate_tasks).intersection(row["task_id"] for row in development_tasks):
        raise ValueError("candidate and development task IDs overlap")

    train_rows: list[dict[str, Any]] = []
    for row in candidates:
        if row["construct_id"] != CONSTRUCT_ID:
            continue
        task_id = row["source_task_id"]
        if task_id not in candidate_tasks:
            raise ValueError(f"candidate row is not in candidate_train: {task_id}")
        if row["benchmark_contamination"] or row["training_approved"]:
            raise ValueError(f"unexpected candidate release state: {task_id}")
        train_rows.append(
            {
                **row,
                "constitution_id": CONSTITUTION_ID,
                "development_only": True,
                "example_id": task_id,
                "release_state": "review_pending_not_training_release",
            }
        )
    if len(train_rows) != 4:
        raise ValueError("expected exactly four Jinn SFT seed rows")

    system_prompts = {row["system_prompt"] for row in development_tasks}
    if len(system_prompts) != 1:
        raise ValueError("development Jinn tasks do not share one system prompt")
    development_prompts = [
        {
            "probe_id": task["task_id"],
            "task_id": task["task_id"],
            "prompt": render_task_prompt(task),
            "tags": [
                "jinn_bench",
                "construct",
                "development",
                task["scenario_id"],
            ],
            "best_action_id": task["best_action_id"],
            "source_task_content_sha256": task["task_content_sha256"],
        }
        for task in development_tasks
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "train.jsonl"
    val_path = output_dir / "val.jsonl"
    prompts_path = output_dir / "development_prompts.jsonl"
    system_path = output_dir / "development_system_prompt.txt"
    write_jsonl(train_path, train_rows)
    val_path.write_text("", encoding="utf-8", newline="\n")
    write_jsonl(prompts_path, development_prompts)
    system_path.write_text(next(iter(system_prompts)) + "\n", encoding="utf-8", newline="\n")

    tokenizer = AutoTokenizer.from_pretrained(
        str(model_path),
        local_files_only=True,
        trust_remote_code=False,
        use_fast=True,
    )
    train_lengths = []
    for row in train_rows:
        rendered = tokenizer.apply_chat_template(
            row["messages"],
            tokenize=False,
            add_generation_prompt=False,
            enable_thinking=False,
        )
        train_lengths.append(len(tokenizer(rendered, add_special_tokens=False).input_ids))
    eval_lengths = []
    for row in development_prompts:
        rendered = tokenizer.apply_chat_template(
            [
                {"role": "system", "content": next(iter(system_prompts))},
                {"role": "user", "content": row["prompt"]},
            ],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=True,
        )
        eval_lengths.append(len(tokenizer(rendered, add_special_tokens=False).input_ids))

    artifacts = {}
    for path in (train_path, val_path, prompts_path, system_path):
        artifacts[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    manifest = {
        "schema_version": "jinn_bench_local_qlora_preparation_v1",
        "status": "prepared_development_only",
        "construct_id": CONSTRUCT_ID,
        "constitution_id": CONSTITUTION_ID,
        "source": {
            "candidate_sft_sha256": sha256_file(candidates_path),
            "construct_tasks_sha256": sha256_file(tasks_path),
        },
        "model_path": str(model_path),
        "train_rows": len(train_rows),
        "development_tasks": len(development_prompts),
        "train_task_ids": sorted(candidate_tasks),
        "development_task_ids": sorted(row["task_id"] for row in development_tasks),
        "train_eval_overlap": [],
        "train_tokens": {
            "minimum": min(train_lengths),
            "maximum": max(train_lengths),
            "total": sum(train_lengths),
        },
        "thinking_eval_prompt_tokens": {
            "minimum": min(eval_lengths),
            "maximum": max(eval_lengths),
        },
        "artifacts": artifacts,
        "training_approved": False,
        "prime_training_ready": False,
        "claim_boundary": (
            "This package supports one exploratory local signal test over review-pending "
            "candidate rows. It is not a training release, a scale authorization, or "
            "confirmatory evidence."
        ),
    }
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
