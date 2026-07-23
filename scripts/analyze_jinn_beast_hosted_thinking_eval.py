#!/usr/bin/env python3
"""Export and analyze a Prime-hosted Jinn-Beast thinking evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import types
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean, median
from typing import Any

WORD_PATTERN = re.compile(r"[a-z0-9_'-]+")
FRAME_ORDER = ("neutral", "constitutional", "jinn", "beast")
FRAME_LANGUAGE_PATTERNS = {
    "neutral": re.compile(r"\bneutral\b", re.IGNORECASE),
    "constitutional": re.compile(r"\bconstitution(?:al)?\b", re.IGNORECASE),
    "jinn": re.compile(r"\bjinn\b", re.IGNORECASE),
    "beast": re.compile(r"\bbeast\b", re.IGNORECASE),
    "accountability": re.compile(r"\baccountab\w*\b", re.IGNORECASE),
    "witness": re.compile(r"\bwitness\w*\b", re.IGNORECASE),
    "scrutiny": re.compile(r"\bscrutin\w*\b", re.IGNORECASE),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def install_windows_fcntl_stub() -> None:
    if os.name != "nt" or "fcntl" in sys.modules:
        return
    module = types.ModuleType("fcntl")
    module.LOCK_EX = 2
    module.LOCK_UN = 8
    module.LOCK_NB = 4
    module.flock = lambda *args: None
    sys.modules["fcntl"] = module


def fetch_samples(evaluation_id: str) -> list[dict[str, Any]]:
    install_windows_fcntl_stub()
    from prime_cli.client import APIClient
    from prime_evals import EvalsClient

    client = EvalsClient(APIClient())
    first_page = client.get_samples(evaluation_id, page=1, limit=100)
    total_pages = int(first_page["total_pages"])
    rows = list(first_page["samples"])
    for page in range(2, total_pages + 1):
        rows.extend(client.get_samples(evaluation_id, page=page, limit=100)["samples"])
    if len(rows) != int(first_page["total"]):
        raise ValueError(
            f"sample export incomplete: expected {first_page['total']}, got {len(rows)}"
        )
    return rows


def final_message(sample: dict[str, Any]) -> dict[str, Any]:
    completion = sample.get("completion")
    if not isinstance(completion, list) or not completion:
        return {}
    value = completion[-1]
    return value if isinstance(value, dict) else {}


def repeated_ngram_stats(text: str, width: int = 8) -> tuple[float, int]:
    tokens = WORD_PATTERN.findall(text.casefold())
    if len(tokens) < width:
        return 0.0, 0
    windows = [tuple(tokens[index : index + width]) for index in range(len(tokens) - width + 1)]
    counts = Counter(windows)
    repeated = sum(count - 1 for count in counts.values())
    return repeated / len(windows), max(counts.values())


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("cannot compute a percentile over no values")
    ordered = sorted(values)
    rank = max(1, int((percentile * len(ordered)) + 0.999999999))
    return ordered[min(rank, len(ordered)) - 1]


def metric(sample: dict[str, Any], name: str) -> float:
    info = sample.get("info") or {}
    metrics = info.get("metrics") or {}
    return float(metrics.get(name, 0.0))


def sample_record(sample: dict[str, Any]) -> dict[str, Any]:
    info = sample.get("info") or {}
    message = final_message(sample)
    content = message.get("content")
    reasoning = str(message.get("reasoning_content") or "")
    repetition_fraction, max_ngram_count = repeated_ngram_stats(reasoning)
    tokens = info.get("token_usage") or {}
    return {
        "example_id": int(sample["example_id"]),
        "rollout_number": int(sample["rollout_number"]),
        "trace_id": str(sample["trace_id"]),
        "frame": str(info["frame"]),
        "pair_id": str(info["pair_id"]),
        "scenario_id": str(info["scenario_id"]),
        "reward": float(sample["reward"]),
        "content_present": isinstance(content, str) and bool(content.strip()),
        "content": content,
        "reasoning": reasoning,
        "reasoning_characters": len(reasoning),
        "repeat_8gram_fraction": repetition_fraction,
        "max_8gram_count": max_ngram_count,
        "is_truncated": bool(info.get("is_truncated")),
        "output_tokens": int(tokens.get("final_output_tokens", 0)),
        "input_tokens": int(tokens.get("final_input_tokens", 0)),
        "metrics": dict(info.get("metrics") or {}),
        "frame_language_present": {
            name: bool(pattern.search(reasoning))
            for name, pattern in FRAME_LANGUAGE_PATTERNS.items()
        },
        "raw_sample": sample,
    }


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("evaluation contains no samples")
    output_tokens = [float(row["output_tokens"]) for row in records]
    reasoning_characters = [float(row["reasoning_characters"]) for row in records]
    rewards = [float(row["reward"]) for row in records]
    total_input_tokens = sum(int(row["input_tokens"]) for row in records)
    total_output_tokens = sum(int(row["output_tokens"]) for row in records)

    by_frame: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_frame[str(row["frame"])].append(row)
        by_pair[str(row["pair_id"])].append(row)
    if set(by_frame) != set(FRAME_ORDER):
        raise ValueError(f"unexpected frame universe: {sorted(by_frame)}")

    frame_summaries: dict[str, Any] = {}
    for frame in FRAME_ORDER:
        rows = by_frame[frame]
        frame_summaries[frame] = {
            "rollouts": len(rows),
            "mean_reward": fmean(float(row["reward"]) for row in rows),
            "median_reward": median(float(row["reward"]) for row in rows),
            "content_present_rate": fmean(float(row["content_present"]) for row in rows),
            "strict_contract_rate": fmean(
                metric(row["raw_sample"], "contract_valid") for row in rows
            ),
            "truncated_rate": fmean(float(row["is_truncated"]) for row in rows),
            "evidence_grounding_rate": fmean(
                metric(row["raw_sample"], "evidence_grounding") for row in rows
            ),
            "critical_violation_rate": fmean(
                metric(row["raw_sample"], "critical_violation") for row in rows
            ),
            "mean_output_tokens": fmean(float(row["output_tokens"]) for row in rows),
            "mean_reasoning_characters": fmean(
                float(row["reasoning_characters"]) for row in rows
            ),
            "mean_repeat_8gram_fraction": fmean(
                float(row["repeat_8gram_fraction"]) for row in rows
            ),
            "frame_language_presence_rates": {
                name: fmean(float(row["frame_language_present"][name]) for row in rows)
                for name in FRAME_LANGUAGE_PATTERNS
            },
        }

    strict_rows = [
        row for row in records if metric(row["raw_sample"], "contract_valid") == 1.0
    ]
    pair_decisions: dict[str, set[str]] = defaultdict(set)
    for row in strict_rows:
        content = str(row["content"])
        decision = str(json.loads(content)["decision"])
        pair_decisions[str(row["pair_id"])].add(decision)

    full_frame_pairs = 0
    for pair_rows in by_pair.values():
        valid_frames = {
            str(row["frame"])
            for row in pair_rows
            if metric(row["raw_sample"], "contract_valid") == 1.0
        }
        full_frame_pairs += int(valid_frames == set(FRAME_ORDER))

    pair_frame_means: dict[str, dict[str, float]] = {}
    for pair_id, pair_rows in by_pair.items():
        frame_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in pair_rows:
            frame_rows[str(row["frame"])].append(row)
        pair_frame_means[pair_id] = {
            frame: fmean(float(row["reward"]) for row in frame_rows[frame])
            for frame in FRAME_ORDER
        }
    paired_reward_deltas = {
        f"{frame}_minus_neutral": fmean(
            values[frame] - values["neutral"] for values in pair_frame_means.values()
        )
        for frame in FRAME_ORDER
        if frame != "neutral"
    }

    content_rows = [row for row in records if row["content_present"]]
    return {
        "rollouts": len(records),
        "pair_count": len(by_pair),
        "mean_reward": fmean(rewards),
        "median_reward": median(rewards),
        "zero_reward_rate": fmean(float(value == 0.0) for value in rewards),
        "content_present_count": len(content_rows),
        "content_present_rate": len(content_rows) / len(records),
        "strict_contract_count": len(strict_rows),
        "strict_contract_rate": len(strict_rows) / len(records),
        "truncated_count": sum(int(row["is_truncated"]) for row in records),
        "truncated_rate": fmean(float(row["is_truncated"]) for row in records),
        "legal_action_count": sum(
            int(metric(row["raw_sample"], "legal_action") == 1.0) for row in records
        ),
        "highest_scoring_legal_action_count": sum(
            int(metric(row["raw_sample"], "action_quality") > 0.0) for row in records
        ),
        "evidence_grounding_count": sum(
            int(metric(row["raw_sample"], "evidence_grounding") == 1.0)
            for row in records
        ),
        "critical_violation_count": sum(
            int(metric(row["raw_sample"], "critical_violation") > 0.0)
            for row in records
        ),
        "bracket_wrapped_evidence_count": sum(
            int('"[' in str(row["content"])) for row in content_rows
        ),
        "code_fenced_content_count": sum(
            int("```" in str(row["content"])) for row in content_rows
        ),
        "token_usage": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "mean_input_tokens": total_input_tokens / len(records),
            "mean_output_tokens": fmean(output_tokens),
            "median_output_tokens": median(output_tokens),
            "p95_output_tokens_nearest_rank": nearest_rank(output_tokens, 0.95),
            "mean_reasoning_characters": fmean(reasoning_characters),
            "median_reasoning_characters": median(reasoning_characters),
            "p95_reasoning_characters_nearest_rank": nearest_rank(
                reasoning_characters, 0.95
            ),
        },
        "repetition": {
            "metric": "duplicate fraction over normalized overlapping 8-word windows",
            "mean_repeat_8gram_fraction": fmean(
                float(row["repeat_8gram_fraction"]) for row in records
            ),
            "p95_repeat_8gram_fraction_nearest_rank": nearest_rank(
                [float(row["repeat_8gram_fraction"]) for row in records], 0.95
            ),
            "maximum_8gram_count": max(int(row["max_8gram_count"]) for row in records),
        },
        "matched_action_consistency": {
            "pairs_with_any_strict_answer": len(pair_decisions),
            "pairs_with_consistent_strict_decision": sum(
                int(len(decisions) == 1) for decisions in pair_decisions.values()
            ),
            "pairs_with_strict_answer_in_all_four_frames": full_frame_pairs,
            "paired_mean_reward_deltas": paired_reward_deltas,
        },
        "by_frame": frame_summaries,
        "estimated_inference_cost_usd": (
            (total_input_tokens * 0.1) + (total_output_tokens * 0.3)
        )
        / 1_000_000,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-id", required=True)
    parser.add_argument("--trace-output", required=True)
    parser.add_argument("--analysis-output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evaluation_id = str(args.evaluation_id)
    trace_path = Path(args.trace_output).resolve()
    analysis_path = Path(args.analysis_output).resolve()
    samples = fetch_samples(evaluation_id)
    records = [sample_record(sample) for sample in samples]
    write_jsonl(trace_path, [row["raw_sample"] for row in records])
    analysis = {
        "schema_version": "jinn_beast_metta_hosted_thinking_analysis_v1",
        "status": "complete",
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "evaluation_id": evaluation_id,
        "trace_export": {
            "path": display_path(trace_path),
            "rows": len(records),
            "bytes": trace_path.stat().st_size,
            "sha256": sha256_file(trace_path),
        },
        "analysis": summarize_records(records),
        "interpretation_boundary": (
            "Development-only model-output analysis. Frame-language measurements "
            "are descriptive text statistics."
        ),
    }
    write_json(analysis_path, analysis)
    print(json.dumps(analysis, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
