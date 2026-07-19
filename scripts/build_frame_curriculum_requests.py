#!/usr/bin/env python3
"""Freeze paired draft/critique/revise requests for the six-arm curriculum."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments/frame_internalization_sft_v1"
DEFAULT_DILEMMAS = PACKAGE / "rerun_freeze/curriculum_source_v1/dilemmas.jsonl"
DEFAULT_OUTPUT_DIR = PACKAGE / "rerun_freeze/curriculum_generation_v1"
MODEL_INVENTORY = PACKAGE / "rerun_freeze/model_tokenizer_remote_inventory_v1.json"
FRAME_SOURCES = {
    "neutral": DEFAULT_OUTPUT_DIR / "frames/neutral.txt",
    "F1": PACKAGE
    / "predecessor_recovery/session_extracted/experiment_1/recovered_worktree/frames/"
    "F1_constitutional.txt",
    "F3": PACKAGE / "frame_cards/F3_v2.json",
    "F3_concrete": PACKAGE / "frame_cards/F3_concrete_v2.json",
}
ARM_DERIVATIONS = {
    "neutral": ["neutral_reflection"],
    "F1": ["F1_reflection", "F1_demonstration"],
    "F3": ["F3_reflection", "F3_demonstration"],
    "F3_concrete": ["F3_concrete_reflection"],
}
PRACTICE_INSTRUCTIONS = {
    "draft": (
        "Here is a moral dilemma to work through:\n\n{dilemma}\n\nWrite a first-draft "
        "response that gives your honest guidance on how to think about it. A few "
        "paragraphs is fine."
    ),
    "critique": (
        "Now critique your own draft. Where does it fall short, gloss over a hard "
        "part, or fail to live up to the standard you hold yourself to? Be specific "
        "and unsparing."
    ),
    "revise": (
        "Now write a revised, improved response that addresses your critique. Write only "
        "the revised response, without an introduction or commentary about the revision."
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dilemmas", type=Path, default=DEFAULT_DILEMMAS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--freeze-date", default="2026-07-19")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(payload)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def read_frame(frame_id: str, path: Path) -> tuple[str, str]:
    if frame_id in {"F3", "F3_concrete"}:
        document = read_json(path)
        return str(document["prompt_text"]), sha256_file(path)
    return path.read_text(encoding="utf-8").strip(), sha256_file(path)


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


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

    model_inventory = read_json(MODEL_INVENTORY)
    frames: dict[str, dict[str, Any]] = {}
    frame_texts: dict[str, str] = {}
    for frame_id, path in FRAME_SOURCES.items():
        text, file_hash = read_frame(frame_id, path)
        frame_texts[frame_id] = text
        frames[frame_id] = {
            "path": rel(path),
            "file_sha256": file_hash,
            "prompt_text_sha256": sha256_text(text),
            "derived_arms": ARM_DERIVATIONS[frame_id],
        }

    generation = {
        "model_repository": model_inventory["repository"],
        "model_revision": model_inventory["revision"],
        "max_tokens_per_turn": 2500,
        "temperature": 0.7,
        "top_p": 0.8,
        "turns": ["draft", "critique", "revise"],
        "instructions": PRACTICE_INSTRUCTIONS,
        "retry_attempts": 4,
        "paired_seed_rule": "seed + integer scenario index; identical across source frames",
    }
    request_path = args.output_dir / "requests.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)
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
        "model_inventory": {"path": rel(MODEL_INVENTORY), "sha256": sha256_file(MODEL_INVENTORY)},
        "frames": frames,
        "generation": generation,
        "generation_config_sha256": canonical_sha256(generation),
        "requests": {"path": rel(request_path), "sha256": sha256_file(request_path)},
        "builder": {"path": rel(Path(__file__)), "sha256": sha256_file(Path(__file__))},
        "completion_requirements": [
            "generate one complete six-message transcript for every frozen request",
            "render all six registered arm datasets from exact scenario joins",
            "verify F3_reflection and F3_concrete_reflection total train-token spread is at most 0.02",
        ],
    }
    config_path = args.output_dir / "request_manifest.json"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(config_path), "requests": config["request_count"], "status": config["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
