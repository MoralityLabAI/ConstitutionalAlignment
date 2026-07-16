#!/usr/bin/env python3
"""Fit a lightweight lexical router from a constitutional prompting run."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List


TOKEN_RE = re.compile(r"[a-z0-9_]+")
STOPWORDS = {
    "the",
    "and",
    "that",
    "this",
    "with",
    "from",
    "they",
    "them",
    "their",
    "there",
    "into",
    "about",
    "which",
    "would",
    "could",
    "should",
    "have",
    "has",
    "will",
    "what",
    "when",
    "where",
    "while",
    "user",
    "scene",
    "storyworld",
    "encounter",
    "choose",
    "option",
    "fixed",
    "list",
    "page",
}

TARGET_PROFILES = {
    "balanced_helpful": {
        "refusal_hits": 0.0,
        "uncertainty_hits": 1.0,
        "deliberation_hits": 1.1,
        "persona_hits": 1.1,
        "anti_concealment_hits": 0.4,
    },
    "strict_safety": {
        "refusal_hits": 0.35,
        "uncertainty_hits": 1.0,
        "deliberation_hits": 1.5,
        "persona_hits": 3.0,
        "anti_concealment_hits": 0.4,
    },
    "truth_explicit": {
        "refusal_hits": 0.0,
        "uncertainty_hits": 1.75,
        "deliberation_hits": 0.35,
        "persona_hits": 1.3,
        "anti_concealment_hits": 0.65,
    },
}


def read_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def tokenize(text: str) -> List[str]:
    return [tok for tok in TOKEN_RE.findall(text.lower()) if tok not in STOPWORDS and len(tok) > 2]


def generic_score_row(row: dict) -> float:
    metrics = row.get("metrics", {}) or {}
    return (
        1.0 * float(metrics.get("anti_concealment_hits", 0))
        + 0.8 * float(metrics.get("uncertainty_hits", 0))
        + 0.6 * float(metrics.get("deliberation_hits", 0))
        + 0.4 * float(metrics.get("persona_hits", 0))
        + 0.3 * float(metrics.get("refusal_hits", 0))
        - 1.0 * float(metrics.get("blandness_flag", 0))
    )


def constitution_alignment_score(row: dict, constitution_id: str) -> float:
    metrics = row.get("metrics", {}) or {}
    target = TARGET_PROFILES.get(constitution_id, {})
    score = 0.0
    for key, target_value in target.items():
        observed = float(metrics.get(key, 0.0) or 0.0)
        score -= abs(observed - target_value)
    score -= 0.5 * float(metrics.get("blandness_flag", 0) or 0.0)
    score += 0.1 * generic_score_row(row)
    return score


def discriminative_weight(target_row: dict, competing_rows: List[dict]) -> float:
    target_constitution = str(target_row.get("constitution_id", "") or "")
    target_score = constitution_alignment_score(target_row, target_constitution)
    competing_scores = [
        constitution_alignment_score(row, str(row.get("constitution_id", "") or ""))
        for row in competing_rows
        if row is not target_row
    ]
    margin = target_score if not competing_scores else target_score - max(competing_scores)
    generic_bonus = max(0.0, generic_score_row(target_row)) * 0.1
    return max(0.0, margin) + generic_bonus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--top-k", type=int, default=48)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    generations = list(run_dir.glob("*/generations.jsonl"))
    if not generations:
        raise SystemExit(f"No generations found under {run_dir}")

    by_prompt: Dict[str, List[dict]] = defaultdict(list)
    for gen_file in generations:
        for row in read_jsonl(gen_file):
            by_prompt[str(row.get("prompt_id", ""))].append(row)

    model = {
        "router_type": "lexical_centroid_v1",
        "source_run_dir": str(run_dir),
        "constitutions": {},
        "top_k": args.top_k,
    }

    weighted_aggregates: Dict[str, Counter[str]] = defaultdict(Counter)
    prompt_counts: Dict[str, int] = defaultdict(int)
    for _prompt_id, rows in by_prompt.items():
        for row in rows:
            constitution_id = str(row.get("constitution_id", "") or "")
            weight = discriminative_weight(row, rows)
            if weight <= 0:
                continue
            prompt_counts[constitution_id] += 1
            counts = Counter(tokenize(str(row.get("prompt_text", "") or "")))
            for term, freq in counts.items():
                weighted_aggregates[constitution_id][term] += int(round(freq * weight * 10))

    for constitution_id, aggregate in weighted_aggregates.items():
        top_terms = aggregate.most_common(args.top_k)
        norm = math.sqrt(sum(float(v) * float(v) for _, v in top_terms)) or 1.0
        model["constitutions"][constitution_id] = {
            "prompt_count": prompt_counts[constitution_id],
            "weights": {term: round(freq / norm, 6) for term, freq in top_terms},
        }

    weight_vectors = [
        tuple(sorted((spec.get("weights", {}) or {}).items()))
        for spec in model["constitutions"].values()
    ]
    model["degenerate"] = len(set(weight_vectors)) <= 1 if weight_vectors else True
    if model["degenerate"]:
        model["warning"] = (
            "Constitution weight vectors collapsed to the same profile. "
            "Fallback to heuristic routing until the prompt study yields discriminative signals."
        )
    model["scoring"] = "prompt_margin_over_best_competitor_v1"

    output_path = Path(args.output_json).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
