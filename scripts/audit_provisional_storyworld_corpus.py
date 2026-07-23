#!/usr/bin/env python
"""Independently replay and quality-audit a provisional storyworld corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.provisional_storyworld_teacher import (
    CRITICAL_FAILURE_TAGS,
)
from alignment_harness.storyworlds import (
    sha256_bytes,
    sha256_file,
    sha256_json,
    validate_world,
    write_json,
)
from alignment_harness.trajectory_curriculum import (
    FRAME_SYSTEM_PROMPTS,
    TiktokenCounter,
    validate_episode_trace,
)

DEFAULT_CORPUS = (
    REPO_ROOT
    / "experiments"
    / "storyworld_curriculum_v1"
    / "generated"
    / "provisional_local_500_v1"
)
ACTION_ID_RE = re.compile(r"\bA-[A-F0-9]{10}\b")
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
WORD_RE = re.compile(r"[a-z0-9_'-]+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object in {path}")
    return value


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"{path}:{line_number}: blank JSONL line")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number}: expected JSON object")
            yield value


@dataclass
class HyperLogLog:
    precision: int = 14
    registers: list[int] = field(init=False)

    def __post_init__(self) -> None:
        if not 4 <= self.precision <= 20:
            raise ValueError("HyperLogLog precision must be in [4, 20]")
        self.registers = [0] * (1 << self.precision)

    def add(self, value: str) -> None:
        hashed = int.from_bytes(
            hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest(),
            "big",
        )
        remainder_bits = 64 - self.precision
        index = hashed >> remainder_bits
        remainder = hashed & ((1 << remainder_bits) - 1)
        rank = (
            remainder_bits - remainder.bit_length() + 1
            if remainder
            else remainder_bits + 1
        )
        self.registers[index] = max(self.registers[index], rank)

    def estimate(self) -> int:
        buckets = len(self.registers)
        alpha = 0.7213 / (1.0 + 1.079 / buckets)
        raw = alpha * buckets * buckets / sum(
            2.0**-value for value in self.registers
        )
        empty = self.registers.count(0)
        if raw <= 2.5 * buckets and empty:
            raw = buckets * math.log(buckets / empty)
        return round(raw)


def _normalized_tokens(text: str) -> list[str]:
    normalized = ACTION_ID_RE.sub("<action>", text.lower())
    normalized = NUMBER_RE.sub("<number>", normalized)
    return WORD_RE.findall(normalized)


def _verify_record_hash(row: dict[str, Any]) -> bool:
    payload = {key: value for key, value in row.items() if key != "record_sha256"}
    return row.get("record_sha256") == sha256_json(payload)


def _state_actions(world: dict[str, Any], state_id: str) -> list[dict[str, Any]]:
    return next(
        state["actions"]
        for state in world["states"]
        if state["state_id"] == state_id
    )


def audit(corpus_dir: Path, output_path: Path | None) -> tuple[Path, bool]:
    corpus_dir = corpus_dir.resolve()
    output_path = (
        output_path.resolve()
        if output_path is not None
        else Path(f"{corpus_dir}.audit.json")
    )
    manifest_path = corpus_dir / "run_manifest.json"
    metrics_path = corpus_dir / "reports" / "metrics.json"
    resource_path = Path(f"{corpus_dir}.resource.json")
    manifest = _read_json(manifest_path)
    metrics = _read_json(metrics_path)
    resource = _read_json(resource_path)
    failures: list[str] = []

    artifact_receipts: list[dict[str, Any]] = []
    for receipt in manifest["artifacts"]:
        path = corpus_dir / receipt["path"]
        observed = {
            "path": receipt["path"],
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        artifact_receipts.append(observed)
        if observed != receipt:
            failures.append(f"artifact receipt mismatch: {receipt['path']}")
    if sha256_json(artifact_receipts) != manifest["artifact_tree_sha256"]:
        failures.append("artifact tree hash mismatch")

    for group_name in ("campaign_config", "package", "teacher_ensemble"):
        receipt = manifest["source_receipts"][group_name]
        if sha256_file(REPO_ROOT / receipt["path"]) != receipt["sha256"]:
            failures.append(f"source receipt mismatch: {group_name}")
    for code_name, receipt in manifest["source_receipts"].get("code", {}).items():
        if sha256_file(REPO_ROOT / receipt["path"]) != receipt["sha256"]:
            failures.append(f"code receipt mismatch: {code_name}")
    if not manifest["source_receipts"].get("code"):
        failures.append("run manifest does not bind generator code")

    if resource["status"] != "completed" or resource["process_exit_code"] != 0:
        failures.append("resource receipt is not a clean completion")
    if resource["output_manifest_sha256"] != sha256_file(manifest_path):
        failures.append("resource receipt does not bind the run manifest")
    if int(resource["caps"]["parallel_workers"]) != 1:
        failures.append("resource receipt used more than one worker")

    worlds: dict[str, dict[str, Any]] = {}
    for world in _read_jsonl(corpus_dir / "storyworld" / "worlds.jsonl"):
        validate_world(world)
        worlds[str(world["world_id"])] = world
    if len(worlds) != 17:
        failures.append(f"expected 17 resolved source worlds, observed {len(worlds)}")

    trace_count = 0
    turn_count = 0
    trace_ids: set[str] = set()
    target_action_changes = 0
    critical_target_violations: list[str] = []
    target_tag_counts: Counter[str] = Counter()
    family_by_campaign_split: dict[str, set[str]] = defaultdict(set)
    holdout_families = set(
        metrics["diversity"]["families_by_split"]["internal_holdout"]
    )
    for trace in _read_jsonl(corpus_dir / "encounters.jsonl"):
        trace_count += 1
        trace_id = str(trace["trace_id"])
        if trace_id in trace_ids:
            failures.append(f"duplicate trace id: {trace_id}")
        trace_ids.add(trace_id)
        world = worlds[str(trace["episode"]["world_id"])]
        validate_episode_trace(world, trace)
        if trace["release"]["training_approved"]:
            failures.append(f"training-approved provisional trace: {trace_id}")
        campaign_split = (
            "internal_holdout"
            if trace["episode"]["family_id"] in holdout_families
            else "corpus_train"
        )
        family_by_campaign_split[campaign_split].add(
            str(trace["episode"]["family_id"])
        )
        for turn in trace["turns"]:
            turn_count += 1
            candidate_id = str(turn["teacher_outputs"]["candidate"]["action_id"])
            target_id = str(turn["review"]["target"]["action_id"])
            target_action_changes += candidate_id != target_id
            action_key = str(
                turn["proof_receipts"]["opaque_action_mapping"][target_id]
            )
            actions = _state_actions(world, str(turn["state_id"]))
            target_action = next(
                action for action in actions if action["action_key"] == action_key
            )
            target_tags = set(map(str, target_action["tags"]))
            target_tag_counts.update(target_tags)
            safe_alternative_exists = any(
                not CRITICAL_FAILURE_TAGS.intersection(action["tags"])
                for action in actions
            )
            if (
                safe_alternative_exists
                and CRITICAL_FAILURE_TAGS.intersection(target_tags)
            ):
                critical_target_violations.append(
                    f"{trace_id}:{turn['turn_index']}:{action_key}"
                )
    if trace_count != 500:
        failures.append(f"expected 500 traces, observed {trace_count}")
    if turn_count != 3000:
        failures.append(f"expected 3000 turns, observed {turn_count}")
    if critical_target_violations:
        failures.append(
            f"critical target violations: {len(critical_target_violations)}"
        )

    token_counter = TiktokenCounter(
        encoding_name=str(metrics["tokenizer"]["encoding"])
    )
    recounted_packed = 0
    recounted_assistant = 0
    sft_rows: Counter[str] = Counter()
    preference_rows: Counter[str] = Counter()
    record_ids: set[str] = set()
    message_hashes: dict[str, set[str]] = defaultdict(set)
    assistant_hashes: dict[str, set[str]] = defaultdict(set)
    normalized_assistant_hashes: dict[str, set[str]] = defaultdict(set)
    hll = HyperLogLog()
    total_normalized_word_tokens = 0
    total_normalized_five_grams = 0
    raw_assistant_bytes = 0
    compressed_assistant_bytes = 0
    compressor = zlib.compressobj(level=9, wbits=31)

    for campaign_split, relative_path in (
        ("corpus_train", "datasets/player_train.jsonl"),
        ("internal_holdout", "datasets/player_eval.jsonl"),
    ):
        for row in _read_jsonl(corpus_dir / relative_path):
            record_id = str(row["record_id"])
            if record_id in record_ids:
                failures.append(f"duplicate record id: {record_id}")
            record_ids.add(record_id)
            if not _verify_record_hash(row):
                failures.append(f"record hash mismatch: {record_id}")
            if row["training_approved"]:
                failures.append(f"training-approved provisional row: {record_id}")
            messages = row["messages"]
            if row["view"] == "sft_policy":
                expected_prompt = FRAME_SYSTEM_PROMPTS[str(row["arm"])]
                if messages[0]["content"] != expected_prompt:
                    failures.append(f"treatment prompt mismatch: {record_id}")
                if "fiction" in expected_prompt.lower():
                    failures.append(f"prohibited treatment wording: {record_id}")
            packed, assistant = token_counter.count_messages(messages)
            recounted_packed += packed
            recounted_assistant += assistant
            sft_rows[campaign_split] += 1
            message_hashes[campaign_split].add(sha256_json(messages))
            assistant_text = str(messages[-1]["content"])
            assistant_hashes[campaign_split].add(
                sha256_bytes(assistant_text.encode("utf-8"))
            )
            normalized = " ".join(_normalized_tokens(assistant_text))
            normalized_assistant_hashes[campaign_split].add(
                sha256_bytes(normalized.encode("utf-8"))
            )
            words = normalized.split()
            total_normalized_word_tokens += len(words)
            five_grams = max(0, len(words) - 4)
            total_normalized_five_grams += five_grams
            for index in range(five_grams):
                hll.add(" ".join(words[index : index + 5]))
            assistant_bytes = assistant_text.encode("utf-8") + b"\n"
            raw_assistant_bytes += len(assistant_bytes)
            compressed_assistant_bytes += len(compressor.compress(assistant_bytes))

    compressed_assistant_bytes += len(compressor.flush())
    for campaign_split, relative_path in (
        ("corpus_train", "datasets/preference_train.jsonl"),
        ("internal_holdout", "datasets/preference_eval.jsonl"),
    ):
        for row in _read_jsonl(corpus_dir / relative_path):
            record_id = str(row["record_id"])
            if record_id in record_ids:
                failures.append(f"duplicate record id: {record_id}")
            record_ids.add(record_id)
            if not _verify_record_hash(row):
                failures.append(f"record hash mismatch: {record_id}")
            if row["training_approved"]:
                failures.append(f"training-approved preference row: {record_id}")
            preference_rows[campaign_split] += 1

    expected_packed = int(metrics["tokens"]["all"]["packed_tokens"])
    expected_assistant = int(metrics["tokens"]["all"]["assistant_tokens"])
    if recounted_packed != expected_packed:
        failures.append(
            f"packed token mismatch: {recounted_packed} != {expected_packed}"
        )
    if recounted_assistant != expected_assistant:
        failures.append(
            f"assistant token mismatch: {recounted_assistant} != {expected_assistant}"
        )
    for split, observed in sft_rows.items():
        if observed != int(metrics["sft_rows"][split]["total"]):
            failures.append(f"SFT row-count mismatch: {split}")
    for split, observed in preference_rows.items():
        if observed != int(metrics["preference_rows"][split]["total"]):
            failures.append(f"preference row-count mismatch: {split}")

    message_overlap = message_hashes["corpus_train"] & message_hashes[
        "internal_holdout"
    ]
    assistant_overlap = assistant_hashes["corpus_train"] & assistant_hashes[
        "internal_holdout"
    ]
    normalized_assistant_overlap = normalized_assistant_hashes[
        "corpus_train"
    ] & normalized_assistant_hashes["internal_holdout"]
    family_overlap = family_by_campaign_split["corpus_train"] & (
        family_by_campaign_split["internal_holdout"]
    )
    if message_overlap:
        failures.append(f"exact message overlap: {len(message_overlap)}")
    if assistant_overlap:
        failures.append(f"exact assistant overlap: {len(assistant_overlap)}")
    if family_overlap:
        failures.append(f"family overlap: {sorted(family_overlap)}")

    distinct_five_grams = hll.estimate()
    audit_receipt = {
        "schema_version": "storyworld_provisional_corpus_audit_v1",
        "campaign_id": manifest["campaign_id"],
        "passed": not failures,
        "failures": failures,
        "source_receipts": {
            "audit_script": {
                "path": Path(__file__).resolve().relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
            "run_manifest": {
                "path": manifest_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(manifest_path),
            },
            "resource_receipt": {
                "path": resource_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(resource_path),
            },
        },
        "replay": {
            "resolved_worlds": len(worlds),
            "validated_traces": trace_count,
            "validated_turns": turn_count,
            "unique_trace_ids": len(trace_ids),
            "unique_record_ids": len(record_ids),
            "engine_and_schema_validation": "passed" if not failures else "see_failures",
        },
        "adjudication": {
            "candidate_to_target_action_changes": target_action_changes,
            "candidate_to_target_action_change_rate": round(
                target_action_changes / turn_count,
                6,
            ),
            "critical_failure_tag_violations_when_safe_alternative_exists": len(
                critical_target_violations
            ),
            "target_tag_counts": dict(target_tag_counts.most_common()),
        },
        "tokens": {
            "backend": token_counter.description,
            "recounted_packed_tokens": recounted_packed,
            "recounted_assistant_tokens": recounted_assistant,
            "manifest_token_counts_matched": (
                recounted_packed == expected_packed
                and recounted_assistant == expected_assistant
            ),
        },
        "diversity": {
            "exact_unique_message_rows": {
                split: len(values)
                for split, values in sorted(message_hashes.items())
            },
            "exact_unique_assistant_rows": {
                split: len(values)
                for split, values in sorted(assistant_hashes.items())
            },
            "normalized_unique_assistant_rows": {
                split: len(values)
                for split, values in sorted(normalized_assistant_hashes.items())
            },
            "exact_message_overlap_across_splits": len(message_overlap),
            "exact_assistant_overlap_across_splits": len(assistant_overlap),
            "normalized_assistant_overlap_across_splits": len(
                normalized_assistant_overlap
            ),
            "family_overlap_across_splits": sorted(family_overlap),
            "normalized_word_tokens": total_normalized_word_tokens,
            "normalized_five_grams": total_normalized_five_grams,
            "estimated_distinct_normalized_five_grams": distinct_five_grams,
            "estimated_distinct_normalized_five_gram_ratio": round(
                distinct_five_grams / total_normalized_five_grams,
                6,
            ),
            "assistant_utf8_bytes": raw_assistant_bytes,
            "assistant_gzip_bytes": compressed_assistant_bytes,
            "assistant_gzip_ratio": round(
                compressed_assistant_bytes / raw_assistant_bytes,
                6,
            ),
        },
        "release": {
            "training_approved_rows": 0,
            "human_review_complete": False,
            "scholar_review_complete": False,
            "prime_training_ready": False,
        },
        "claim_boundary": (
            "This audit checks deterministic structure, hashes, token arithmetic, "
            "split isolation, annotated failure-tag leakage, and lexical diversity. "
            "It does not substitute for human or scholar review."
        ),
    }
    write_json(output_path, audit_receipt)
    return output_path, not failures


def main() -> int:
    args = parse_args()
    output_path, passed = audit(args.corpus_dir, args.output)
    print(output_path)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
