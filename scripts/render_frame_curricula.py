#!/usr/bin/env python3
"""Render and freeze the six registered datasets from complete raw transcripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments/frame_internalization_sft_v1"
DEFAULT_FREEZE = PACKAGE / "rerun_freeze/curriculum_generation_v1/request_manifest.json"
ARM_SPECS = {
    "neutral_reflection": ("neutral", "reflection"),
    "F1_reflection": ("F1", "reflection"),
    "F1_demonstration": ("F1", "demonstration"),
    "F3_reflection": ("F3", "reflection"),
    "F3_demonstration": ("F3", "demonstration"),
    "F3_concrete_reflection": ("F3_concrete", "reflection"),
}
PREAMBLE = re.compile(
    r"^(here(\u2019|')s|here is)\s+(a|the|my)\s+(final\s+|new\s+)?revised[^\n:]{0,120}(:|\n)\s*",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--base-freeze-receipt", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sequence-length", type=int, default=4096)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def scenario_ids_sha256(rows: list[dict[str, Any]]) -> str:
    return sha256_text("\n".join(row["scenario_id"] for row in rows) + "\n")


def strip_preamble(text: str) -> str:
    return PREAMBLE.sub("", text.strip(), count=1).strip()


def render_messages(record: dict[str, Any], style: str) -> list[dict[str, str]]:
    final = strip_preamble(str(record["final"]))
    if not final:
        raise ValueError(f"empty final response after normalization: {record['request_id']}")
    if style == "demonstration":
        return [
            {"role": "user", "content": str(record["dilemma_prompt"])},
            {"role": "assistant", "content": final},
        ]
    transcript = [dict(message) for message in record["transcript"]]
    if len(transcript) != 6 or [message.get("role") for message in transcript] != [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]:
        raise ValueError(f"invalid six-message transcript: {record['request_id']}")
    transcript[-1] = {"role": "assistant", "content": final}
    return transcript


def main() -> int:
    args = parse_args()
    freeze = json.loads(args.freeze.read_text(encoding="utf-8"))
    base_freeze = json.loads(args.base_freeze_receipt.read_text(encoding="utf-8"))
    if (
        base_freeze.get("schema_version") != "frame_internalization_base_freeze.v1"
        or base_freeze.get("passed") is not True
        or base_freeze.get("revision") != freeze["generation"]["model_revision"]
        or Path(base_freeze.get("model_dir", "")).resolve() != args.tokenizer.resolve()
    ):
        raise RuntimeError("token accounting requires the tokenizer from the passed base-freeze receipt")
    dilemma_path = REPO_ROOT / freeze["dilemmas"]["path"]
    dilemmas = {
        row["scenario_id"]: row
        for row in (
            json.loads(line) for line in dilemma_path.read_text(encoding="utf-8").splitlines()
        )
    }
    expected_ids = sorted(dilemmas)
    expected_id_hash = sha256_text("\n".join(expected_ids) + "\n")

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True)
    source_records: dict[str, list[dict[str, Any]]] = {}
    source_hashes: dict[str, str] = {}
    for source_frame in freeze["frames"]:
        raw_path = args.raw_dir / f"{source_frame}.jsonl"
        records = [
            json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()
        ]
        by_id = {record["scenario_id"]: record for record in records}
        if len(by_id) != len(records):
            raise RuntimeError(f"duplicate scenario ID in {raw_path}")
        if sorted(by_id) != expected_ids:
            missing = sorted(set(expected_ids) - set(by_id))[:10]
            extra = sorted(set(by_id) - set(expected_ids))[:10]
            raise RuntimeError(f"incomplete scenario join in {raw_path}; missing={missing}, extra={extra}")
        ordered = [by_id[scenario_id] for scenario_id in expected_ids]
        for record in ordered:
            dilemma = dilemmas[record["scenario_id"]]
            if record.get("source_frame") != source_frame:
                raise RuntimeError(f"source-frame mismatch: {record.get('request_id')}")
            if record.get("source_frame_prompt_sha256") != freeze["frames"][source_frame]["prompt_text_sha256"]:
                raise RuntimeError(f"source-frame prompt hash mismatch: {record.get('request_id')}")
            if record.get("dilemma_prompt") != dilemma["prompt_text"]:
                raise RuntimeError(f"dilemma text mismatch: {record.get('request_id')}")
            if record.get("cluster_id") != dilemma["cluster_id"] or record.get("split") != dilemma["split"]:
                raise RuntimeError(f"split or cluster mismatch: {record.get('request_id')}")
        source_records[source_frame] = ordered
        source_hashes[source_frame] = sha256_file(raw_path)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    arms: dict[str, dict[str, Any]] = {}
    for arm_id, (source_frame, style) in ARM_SPECS.items():
        records = source_records[source_frame]
        arm_dir = args.output_dir / arm_id
        arm_dir.mkdir(parents=True, exist_ok=True)
        paths = {"train": arm_dir / "training.jsonl", "val": arm_dir / "validation.jsonl"}
        handles = {
            split: path.open("w", encoding="utf-8", newline="\n") for split, path in paths.items()
        }
        total_train_tokens = 0
        maximum_tokens = 0
        over_length_count = 0
        split_counts = {"train": 0, "val": 0}
        try:
            for record in records:
                messages = render_messages(record, style)
                tokens = tokenizer.apply_chat_template(messages, tokenize=True)
                token_count = len(tokens)
                maximum_tokens = max(maximum_tokens, token_count)
                over_length_count += int(token_count > args.sequence_length)
                split = record["split"]
                if split not in handles:
                    raise RuntimeError(f"unexpected split {split!r}")
                if split == "train":
                    total_train_tokens += token_count
                split_counts[split] += 1
                row = {
                    "scenario_id": record["scenario_id"],
                    "cluster_id": record["cluster_id"],
                    "arm": arm_id,
                    "messages": messages,
                }
                handles[split].write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        finally:
            for handle in handles.values():
                handle.close()
        arms[arm_id] = {
            "source_frame": source_frame,
            "style": style,
            "scenario_count": len(records),
            "scenario_ids_sha256": scenario_ids_sha256(records),
            "train_count": split_counts["train"],
            "validation_count": split_counts["val"],
            "total_train_tokens": total_train_tokens,
            "maximum_sequence_tokens": maximum_tokens,
            "over_4096_count": over_length_count,
            "training_path": str(paths["train"].resolve()),
            "training_sha256": sha256_file(paths["train"]),
            "validation_path": str(paths["validation"].resolve()),
            "validation_sha256": sha256_file(paths["validation"]),
            "raw_sha256": source_hashes[source_frame],
        }

    pair_counts = [
        arms["F3_reflection"]["total_train_tokens"],
        arms["F3_concrete_reflection"]["total_train_tokens"],
    ]
    pair_spread = (max(pair_counts) - min(pair_counts)) / min(pair_counts)
    passed = bool(
        set(arms) == set(ARM_SPECS)
        and all(arm["scenario_count"] == 5600 for arm in arms.values())
        and all(arm["train_count"] == 5320 for arm in arms.values())
        and all(arm["validation_count"] == 280 for arm in arms.values())
        and all(arm["scenario_ids_sha256"] == expected_id_hash for arm in arms.values())
        and pair_spread <= 0.02
    )
    manifest = {
        "schema_version": "frame_internalization_curriculum_manifest.v1",
        "passed": passed,
        "request_freeze_path": str(args.freeze.resolve()),
        "request_freeze_sha256": sha256_file(args.freeze),
        "base_freeze_receipt_sha256": sha256_file(args.base_freeze_receipt),
        "renderer_sha256": sha256_file(Path(__file__)),
        "tokenizer_path": str(args.tokenizer.resolve()),
        "sequence_length": args.sequence_length,
        "arms": arms,
        "f3_pair_total_token_spread": pair_spread,
        "failure_reasons": [] if passed else ["completeness, scenario identity, or 2 percent token parity failed"],
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(args.manifest), "passed": passed, "f3_pair_spread": pair_spread}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
