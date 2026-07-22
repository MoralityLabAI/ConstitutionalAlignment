#!/usr/bin/env python3
"""Build one cumulative score-gated SFT dataset from local storyworld rollouts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.local_storyworld_dag import (  # noqa: E402
    DATASET_SCHEMA,
    ROLLOUT_SCHEMA,
    build_fresh_training_rows,
    cycle_config,
    dataset_manifest,
    load_jsonl,
    load_plan,
)
from alignment_harness.storyworlds import sha256_file, write_json, write_jsonl  # noqa: E402


DEFAULT_PLAN = REPO_ROOT / "experiments" / "local_storyworld_dag_v1" / "cycle_plan.json"
DEFAULT_BASE_DATASET = REPO_ROOT / "data" / "jinn_qwen3b_metta_curriculum_v1"
DEFAULT_TOKENIZER = Path(r"D:\Research_Engine\models\Qwen3-1.7B-70d244c")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--cycle", type=int, required=True)
    parser.add_argument("--rollouts", required=True)
    parser.add_argument("--base-dataset-dir", default=str(DEFAULT_BASE_DATASET))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--tokenizer-id", default=str(DEFAULT_TOKENIZER))
    parser.add_argument("--constitution-id", default="jinn_tiny_mutazili_v1")
    parser.add_argument("--local-files-only", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def render_messages(tokenizer: Any, messages: list[dict[str, str]]) -> list[int]:
    if getattr(tokenizer, "chat_template", None):
        try:
            rendered = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
                enable_thinking=False,
            )
        except TypeError:
            rendered = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
    else:
        rendered = "\n".join(
            f"<|{message['role']}|>\n{message['content']}" for message in messages
        )
    return tokenizer(rendered, add_special_tokens=False)["input_ids"]


def validate_rollouts(
    episodes: list[dict[str, Any]], cycle: int, plan_sha256: str
) -> None:
    if not episodes:
        raise ValueError("rollout file is empty")
    for episode in episodes:
        if episode.get("schema_version") != ROLLOUT_SCHEMA:
            raise ValueError("unexpected rollout schema")
        if int(episode.get("cycle", -1)) != cycle:
            raise ValueError("rollout cycle does not match requested cycle")
        if episode.get("lane") != "train":
            raise ValueError("holdout rollouts cannot produce training data")
        if episode.get("plan_sha256") != plan_sha256:
            raise ValueError("rollout plan hash does not match the frozen plan")
        if episode.get("world_review_status") != "pending":
            raise ValueError("this exploratory builder expects explicitly pending worlds")
        if not episode.get("terminal"):
            raise ValueError("incomplete episode cannot produce training data")


def main() -> int:
    args = parse_args()
    plan_path = Path(args.plan).resolve()
    plan, plan_receipt = load_plan(plan_path)
    config = cycle_config(plan, args.cycle)
    rollout_path = Path(args.rollouts).resolve()
    episodes = load_jsonl(rollout_path)
    validate_rollouts(episodes, args.cycle, plan_receipt["plan_sha256"])

    expected_pairs = {
        (Path(item["path"]).name, int(seed))
        for item in config["train_worlds"]
        for seed in config["train_seeds"]
    }
    actual_pairs = {
        (Path(item["world_source_path"]).name, int(item["seed"])) for item in episodes
    }
    if actual_pairs != expected_pairs:
        raise ValueError(
            f"rollout universe mismatch; missing={sorted(expected_pairs - actual_pairs)} "
            f"extra={sorted(actual_pairs - expected_pairs)}"
        )

    base_dir = Path(args.base_dataset_dir).resolve()
    base_train_path = base_dir / "train.jsonl"
    base_val_path = base_dir / "val.jsonl"
    base_train = load_jsonl(base_train_path)
    base_val = load_jsonl(base_val_path)
    fresh_rows = build_fresh_training_rows(
        episodes,
        max_new_rows=int(config["max_new_rows"]),
        constitution_id=args.constitution_id,
    )
    manifest = dataset_manifest(
        base_train,
        base_val,
        fresh_rows,
        rollout_path,
        plan_receipt,
        args.cycle,
    )

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        args.tokenizer_id,
        trust_remote_code=True,
        use_fast=True,
        local_files_only=args.local_files_only,
    )
    max_length = int(config["training"]["max_seq_length"])
    token_lengths = [len(render_messages(tokenizer, row["messages"])) for row in fresh_rows]
    oversized = [
        (row["example_id"], length)
        for row, length in zip(fresh_rows, token_lengths)
        if length > max_length
    ]
    if oversized:
        raise ValueError(
            f"fresh rows exceed max_seq_length={max_length}: {oversized[:8]}"
        )

    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "train.jsonl"
    val_path = output_dir / "val.jsonl"
    fresh_path = output_dir / "fresh_train.jsonl"
    write_jsonl(train_path, [*base_train, *fresh_rows])
    write_jsonl(val_path, base_val)
    write_jsonl(fresh_path, fresh_rows)
    manifest.update(
        {
            "schema_version": DATASET_SCHEMA,
            "status": "ready_for_guarded_local_training",
            "base_dataset_dir": str(base_dir),
            "base_train_sha256": sha256_file(base_train_path),
            "base_val_sha256": sha256_file(base_val_path),
            "tokenizer_id": str(Path(args.tokenizer_id).resolve()),
            "max_seq_length": max_length,
            "fresh_min_tokens": min(token_lengths),
            "fresh_max_tokens": max(token_lengths),
            "fresh_mean_tokens": round(sum(token_lengths) / len(token_lengths), 3),
            "train_sha256": sha256_file(train_path),
            "val_sha256": sha256_file(val_path),
            "fresh_train_sha256": sha256_file(fresh_path),
        }
    )
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
