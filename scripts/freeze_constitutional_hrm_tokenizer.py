#!/usr/bin/env python3
"""Freeze the 32K tokenizer for the constitutional HRM v2 lane."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from tokenizers import Tokenizer, decoders, normalizers, pre_tokenizers
from tokenizers.models import BPE
from tokenizers.trainers import BpeTrainer

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORYWORLD_TRAIN = (
    REPO_ROOT
    / "experiments"
    / "storyworld_curriculum_v1"
    / "generated"
    / "provisional_local_500_v1"
    / "datasets"
    / "player_train.jsonl"
)
DEFAULT_MORAL_TASKS = (
    REPO_ROOT
    / "experiments"
    / "jinn_bench_v1"
    / "local_qwen3_1p7b_jinn_reasoner_v2"
    / "prepared"
    / "tasks.jsonl"
)
DEFAULT_PROMPT_BUNDLE = (
    REPO_ROOT
    / "artifacts"
    / "constitutional_hrm_200m_v2"
    / "generated"
    / "system_prompt_bundle_v2.json"
)

BASE_SPECIAL_TOKENS = (
    "<|pad|>",
    "<|bos|>",
    "<|eos|>",
    "<|unk|>",
    "<|mask|>",
)
DECISION_TOKENS = tuple(f"<|decision:{index}|>" for index in range(4))
PROHIBITION_COUNT_TOKENS = tuple(f"<|pcount:{index}|>" for index in range(6))
WEIGHTED_SCORE_TOKENS = tuple(f"<|weighted:{index}|>" for index in range(73))
CRITICAL_SCORE_TOKENS = tuple(f"<|critical:{index}|>" for index in range(13))
HIGH_SCORE_TOKENS = tuple(f"<|high:{index}|>" for index in range(13))
RULE_TOKENS = (
    "<|rule:fewer_prohibitions|>",
    "<|rule:weighted_tenets|>",
    "<|rule:critical_subtotal|>",
    "<|rule:high_subtotal|>",
    "<|rule:utility|>",
    "<|rule:shuffled|>",
)
BIT_TOKENS = ("<|bit:0|>", "<|bit:1|>")
COUNTERPRESSURE_TOKENS = (
    "<|counterpressure:none|>",
    "<|counterpressure:adl|>",
    "<|counterpressure:aql|>",
    "<|counterpressure:sidq|>",
    "<|counterpressure:ihsan|>",
    "<|counterpressure:amanah|>",
    "<|counterpressure:rahmah|>",
)
TARGET_SPECIAL_TOKENS = (
    DECISION_TOKENS
    + PROHIBITION_COUNT_TOKENS
    + WEIGHTED_SCORE_TOKENS
    + CRITICAL_SCORE_TOKENS
    + HIGH_SCORE_TOKENS
    + RULE_TOKENS
    + BIT_TOKENS
    + COUNTERPRESSURE_TOKENS
)
ALL_SPECIAL_TOKENS = BASE_SPECIAL_TOKENS + TARGET_SPECIAL_TOKENS


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


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number} is not an object")
            yield row


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def storyworld_strings(path: Path, counters: Counter[str]) -> Iterator[str]:
    for row in iter_jsonl(path):
        if row.get("source_split") != "train":
            raise ValueError(f"non-train storyworld row in tokenizer corpus: {row.get('record_id')}")
        counters["storyworld_rows"] += 1
        for message in row.get("messages", []):
            content = message.get("content")
            if isinstance(content, str) and content:
                counters["storyworld_messages"] += 1
                yield content


def moral_strings(path: Path, counters: Counter[str]) -> Iterator[str]:
    for row in iter_jsonl(path):
        if row.get("split") != "candidate_train":
            counters["moral_rows_excluded_non_train"] += 1
            continue
        counters["moral_rows"] += 1
        for field in ("system_prompt", "prompt"):
            value = row.get(field)
            if isinstance(value, str) and value:
                yield value
        for fact in row.get("visible_facts", []):
            if isinstance(fact, dict) and isinstance(fact.get("text"), str):
                yield str(fact["text"])
        for action in row.get("action_scores", {}).values():
            if isinstance(action, dict) and isinstance(action.get("text"), str):
                yield str(action["text"])


def corpus_iterator(
    *,
    constitution_path: Path,
    prompt_bundle_path: Path,
    storyworld_train_path: Path,
    moral_tasks_path: Path,
    counters: Counter[str],
    prompt_repetitions: int = 64,
) -> Iterator[str]:
    constitution = constitution_path.read_text(encoding="utf-8")
    counters["constitution_documents"] += 1
    yield constitution

    prompt_bundle = json.loads(prompt_bundle_path.read_text(encoding="utf-8"))
    for prompt_id in sorted(prompt_bundle["prompts"]):
        for _ in range(prompt_repetitions):
            counters["prompt_documents"] += 1
            yield str(prompt_bundle["prompts"][prompt_id]["text"])

    yield from storyworld_strings(storyworld_train_path, counters)
    yield from moral_strings(moral_tasks_path, counters)

    schema_preamble = {
        "input_fields": [
            "evidence",
            "options",
            "counterpressure",
            "decision",
            "reflection",
            "tenets_defended",
            "constitutional_defense",
        ],
        "tenets": ["adl", "aql", "sidq", "ihsan", "amanah", "rahmah"],
        "prohibitions": ["kidhb", "fasad", "dhulm", "dharar", "ghurur"],
    }
    counters["schema_documents"] += 1
    yield canonical_json(schema_preamble)


def build_tokenizer(
    corpus: Iterable[str],
    *,
    vocab_size: int,
    minimum_frequency: int,
    added_tokens: Iterable[str] = (),
) -> Tokenizer:
    if vocab_size <= len(ALL_SPECIAL_TOKENS) + 256:
        raise ValueError("vocab size is too small for byte alphabet and reserved tokens")
    tokenizer = Tokenizer(BPE(unk_token="<|unk|>"))
    tokenizer.normalizer = normalizers.NFC()
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    trainer = BpeTrainer(
        vocab_size=vocab_size,
        min_frequency=minimum_frequency,
        show_progress=False,
        special_tokens=list(ALL_SPECIAL_TOKENS),
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
    )
    tokenizer.train_from_iterator(corpus, trainer=trainer)
    tokenizer.add_tokens(list(added_tokens))
    trained_size = tokenizer.get_vocab_size(with_added_tokens=True)
    if trained_size > vocab_size:
        raise ValueError(f"trained vocabulary {trained_size} exceeds requested {vocab_size}")
    if trained_size < vocab_size:
        tokenizer.add_special_tokens(
            [f"<|unused:{index:05d}|>" for index in range(vocab_size - trained_size)]
        )
    return tokenizer


def prompt_token_audit(tokenizer: Tokenizer, prompt_bundle_path: Path) -> dict[str, Any]:
    prompt_bundle = json.loads(prompt_bundle_path.read_text(encoding="utf-8"))
    return {
        prompt_id: {
            "tokens": len(tokenizer.encode(str(item["text"])).ids),
            "source_sha256": item["sha256"],
        }
        for prompt_id, item in sorted(prompt_bundle["prompts"].items())
    }


def target_token_audit(tokenizer: Tokenizer) -> dict[str, Any]:
    ids: dict[str, int] = {}
    failures: list[str] = []
    for token in ALL_SPECIAL_TOKENS:
        encoded = tokenizer.encode(token)
        if len(encoded.ids) != 1 or encoded.tokens != [token]:
            failures.append(token)
            continue
        ids[token] = int(encoded.ids[0])
    return {
        "passed": not failures and len(set(ids.values())) == len(ALL_SPECIAL_TOKENS),
        "ids": ids,
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--constitution", type=Path, default=REPO_ROOT / "constitution.md")
    parser.add_argument("--prompt-bundle", type=Path, default=DEFAULT_PROMPT_BUNDLE)
    parser.add_argument("--storyworld-train", type=Path, default=DEFAULT_STORYWORLD_TRAIN)
    parser.add_argument("--moral-tasks", type=Path, default=DEFAULT_MORAL_TASKS)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "constitutional_hrm_200m_v2" / "tokenizer",
    )
    parser.add_argument("--vocab-size", type=int, default=32768)
    parser.add_argument("--minimum-frequency", type=int, default=1)
    parser.add_argument("--prompt-repetitions", type=int, default=64)
    parser.add_argument("--prompt-token-budget", type=int, default=320)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.prompt_repetitions < 1:
        raise ValueError("--prompt-repetitions must be positive")
    sources = {
        "constitution": args.constitution.resolve(),
        "prompt_bundle": args.prompt_bundle.resolve(),
        "storyworld_train": args.storyworld_train.resolve(),
        "moral_tasks": args.moral_tasks.resolve(),
    }
    for source in sources.values():
        if not source.is_file():
            raise FileNotFoundError(source)

    counters: Counter[str] = Counter()
    prompt_bundle = json.loads(sources["prompt_bundle"].read_text(encoding="utf-8"))
    prompt_atoms = sorted(
        {
            line
            for prompt in prompt_bundle["prompts"].values()
            for line in str(prompt["text"]).splitlines()
            if len(line.strip()) >= 16
        },
        key=lambda line: (-len(line), line),
    )
    tokenizer = build_tokenizer(
        corpus_iterator(
            constitution_path=sources["constitution"],
            prompt_bundle_path=sources["prompt_bundle"],
            storyworld_train_path=sources["storyworld_train"],
            moral_tasks_path=sources["moral_tasks"],
            counters=counters,
            prompt_repetitions=args.prompt_repetitions,
        ),
        vocab_size=args.vocab_size,
        minimum_frequency=args.minimum_frequency,
        added_tokens=prompt_atoms,
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer_path = output_dir / "tokenizer.json"
    tokenizer.save(str(tokenizer_path), pretty=True)

    special = target_token_audit(tokenizer)
    prompt_audit = prompt_token_audit(tokenizer, sources["prompt_bundle"])
    actual_vocab_size = tokenizer.get_vocab_size(with_added_tokens=True)
    unused_token_count = sum(
        1 for token in tokenizer.get_vocab() if token.startswith("<|unused:")
    )
    checks = {
        "vocab_size_exact": actual_vocab_size == args.vocab_size,
        "reserved_tokens_single_and_unique": special["passed"],
        "full_prompt_within_budget": prompt_audit["constitution_metta_full"]["tokens"]
        <= args.prompt_token_budget,
        "storyworld_only_train": counters["storyworld_rows"] > 0,
        "moral_non_train_excluded": counters["moral_rows_excluded_non_train"] > 0,
    }
    config = {
        "schema_version": "constitutional_hrm_tokenizer_config_v1",
        "tokenizer_class": "tokenizers.ByteLevelBPETokenizer",
        "normalizer": "NFC",
        "pre_tokenizer": "ByteLevel(add_prefix_space=false)",
        "vocab_size": actual_vocab_size,
        "model_max_length": 512,
        "pad_token": "<|pad|>",
        "pad_token_id": tokenizer.token_to_id("<|pad|>"),
        "bos_token": "<|bos|>",
        "bos_token_id": tokenizer.token_to_id("<|bos|>"),
        "eos_token": "<|eos|>",
        "eos_token_id": tokenizer.token_to_id("<|eos|>"),
        "unk_token": "<|unk|>",
        "unk_token_id": tokenizer.token_to_id("<|unk|>"),
        "mask_token": "<|mask|>",
        "mask_token_id": tokenizer.token_to_id("<|mask|>"),
        "target_special_tokens": list(TARGET_SPECIAL_TOKENS),
        "prompt_atoms": prompt_atoms,
        "target_token_ids": {
            token: special["ids"][token]
            for token in TARGET_SPECIAL_TOKENS
            if token in special["ids"]
        },
    }
    atomic_json(output_dir / "tokenizer_config.json", config)
    receipt = {
        "schema_version": "constitutional_hrm_tokenizer_freeze_receipt_v1",
        "gate_id": "F06_TOKENIZER_FREEZE",
        "status": "passed" if all(checks.values()) else "failed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "source_files": {
            name: {
                "path": str(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for name, path in sources.items()
        },
        "corpus_counts": dict(counters),
        "tokenizer": {
            "path": str(tokenizer_path),
            "sha256": sha256_file(tokenizer_path),
            "vocab_size": actual_vocab_size,
            "minimum_frequency": args.minimum_frequency,
            "prompt_repetitions": args.prompt_repetitions,
            "prompt_atom_count": len(prompt_atoms),
            "reserved_token_count": len(ALL_SPECIAL_TOKENS),
            "unused_capacity_tokens": unused_token_count,
        },
        "prompt_token_audit": prompt_audit,
        "reserved_token_audit": {
            "passed": special["passed"],
            "failures": special["failures"],
            "unique_ids": len(set(special["ids"].values())),
        },
        "split_policy": {
            "storyworld_source_split": "train_only",
            "moral_source_split": "candidate_train_only",
            "development_included": False,
            "sealed_evaluation_included": False,
        },
    }
    atomic_json(output_dir / "freeze_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
