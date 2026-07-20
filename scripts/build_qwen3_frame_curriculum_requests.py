#!/usr/bin/env python3
"""Freeze the six-arm curriculum requests against the Qwen3-1.7B inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.build_frame_curriculum_requests import (
        ARM_DERIVATIONS,
        DEFAULT_DILEMMAS,
        FRAME_SOURCES,
        PRACTICE_INSTRUCTIONS,
        canonical_sha256,
        read_frame,
        read_json,
        rel,
        sha256_file,
        sha256_text,
    )
except ModuleNotFoundError:
    from build_frame_curriculum_requests import (  # type: ignore[no-redef]
        ARM_DERIVATIONS,
        DEFAULT_DILEMMAS,
        FRAME_SOURCES,
        PRACTICE_INSTRUCTIONS,
        canonical_sha256,
        read_frame,
        read_json,
        rel,
        sha256_file,
        sha256_text,
    )


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments/frame_internalization_sft_v1"
DEFAULT_OUTPUT_DIR = PACKAGE / "rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1"
DEFAULT_MODEL_INVENTORY = (
    PACKAGE / "rerun_freeze/qwen3_1p7b_v1/model_tokenizer_remote_inventory_v1.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dilemmas", type=Path, default=DEFAULT_DILEMMAS)
    parser.add_argument("--model-inventory", type=Path, default=DEFAULT_MODEL_INVENTORY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--freeze-date", default="2026-07-20")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dilemmas = [json.loads(line) for line in args.dilemmas.read_text(encoding="utf-8").splitlines()]
    expected_ids = [f"d{index:05d}" for index in range(5600)]
    observed_ids = [row.get("scenario_id") for row in dilemmas]
    if observed_ids != expected_ids:
        raise RuntimeError("dilemma pool must be the ordered d00000..d05599 set")
    if sum(row.get("split") == "train" for row in dilemmas) != 5320:
        raise RuntimeError("dilemma pool must contain exactly 5,320 train rows")
    if sum(row.get("split") == "val" for row in dilemmas) != 280:
        raise RuntimeError("dilemma pool must contain exactly 280 validation rows")

    model_inventory = read_json(args.model_inventory)
    if model_inventory.get("repository") != "Qwen/Qwen3-1.7B":
        raise RuntimeError("Qwen3-1.7B inventory is required")
    if model_inventory.get("revision") != "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e":
        raise RuntimeError("Qwen3-1.7B revision drifted")

    frames = {}
    for frame_id, path in FRAME_SOURCES.items():
        text, file_hash = read_frame(frame_id, path)
        frames[frame_id] = {
            "path": rel(path),
            "file_sha256": file_hash,
            "prompt_text_sha256": sha256_text(text),
            "derived_arms": ARM_DERIVATIONS[frame_id],
        }
    generation = {
        "model_repository": model_inventory["repository"],
        "model_revision": model_inventory["revision"],
        "chat_template_mode": "official_qwen3_enable_thinking_true",
        "max_tokens_per_turn": 2500,
        "temperature": 0.7,
        "top_p": 0.8,
        "turns": ["draft", "critique", "revise"],
        "instructions": PRACTICE_INSTRUCTIONS,
        "retry_attempts": 4,
        "paired_seed_rule": "seed + integer scenario index; identical across source frames",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    request_path = args.output_dir / "requests.jsonl"
    with request_path.open("w", encoding="utf-8", newline="\n") as handle:
        for frame_id in FRAME_SOURCES:
            for row in dilemmas:
                scenario_index = int(row["scenario_id"][1:])
                request = {
                    "request_id": f"{frame_id}:{row['scenario_id']}",
                    "source_frame": frame_id,
                    "source_frame_prompt_sha256": frames[frame_id]["prompt_text_sha256"],
                    "scenario_id": row["scenario_id"],
                    "cluster_id": row["cluster_id"],
                    "source": row["source"],
                    "split": row["split"],
                    "prompt_text_sha256": sha256_text(row["prompt_text"]),
                    "generation_seed": args.seed + scenario_index,
                }
                handle.write(json.dumps(request, ensure_ascii=False, sort_keys=True) + "\n")

    config = {
        "schema_version": "frame_internalization_curriculum_request_freeze.v1",
        "freeze_id": "qwen3_1p7b_curriculum_requests_v1",
        "freeze_date": args.freeze_date,
        "status": "requests_frozen_generation_pending",
        "passed": False,
        "request_count": len(FRAME_SOURCES) * len(dilemmas),
        "source_frame_count": len(FRAME_SOURCES),
        "registered_training_arm_count": sum(len(value) for value in ARM_DERIVATIONS.values()),
        "dilemma_count": len(dilemmas),
        "train_count_per_source_frame": 5320,
        "validation_count_per_source_frame": 280,
        "dilemmas": {"path": rel(args.dilemmas), "sha256": sha256_file(args.dilemmas)},
        "model_inventory": {
            "path": rel(args.model_inventory),
            "sha256": sha256_file(args.model_inventory),
        },
        "frames": frames,
        "generation": generation,
        "generation_config_sha256": canonical_sha256(generation),
        "requests": {"path": rel(request_path), "sha256": sha256_file(request_path)},
        "builder": {"path": rel(Path(__file__)), "sha256": sha256_file(Path(__file__))},
        "historical_boundary": {
            "replaces_intellect_request_pack_for_new_execution": True,
            "modifies_or_relabels_original_intellect_pack": False,
            "historical_intellect_reproduction_claimed": False,
        },
        "completion_requirements": [
            "generate one complete six-message transcript for every frozen request",
            "render all six registered arm datasets from exact scenario joins",
            "verify F3_reflection and F3_concrete_reflection total train-token spread is at most 0.02",
        ],
    }
    config_path = args.output_dir / "request_manifest.json"
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"manifest": str(config_path), "requests": config["request_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
