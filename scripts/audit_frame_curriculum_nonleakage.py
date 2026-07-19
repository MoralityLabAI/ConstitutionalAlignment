#!/usr/bin/env python3
"""Audit curriculum text against every frozen evaluation universe."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments/frame_internalization_sft_v1"
DEFAULT_DILEMMAS = PACKAGE / "rerun_freeze/curriculum_source_v1/dilemmas.jsonl"
DEFAULT_MANIFEST = PACKAGE / "rerun_freeze/curriculum_manifest_v1.json"
EVALUATION_PATHS = (
    PACKAGE / "rerun_freeze/evaluation_universes_v1/harmful_queries.jsonl",
    PACKAGE / "rerun_freeze/evaluation_universes_v1/benign_queries.jsonl",
    PACKAGE / "rerun_freeze/evaluation_universes_v1/override_queries.jsonl",
    REPO_ROOT
    / "data/storyworld_sources/constitutional_alignment_20260715_v1/evaluation/"
    "mihna_ca_eval_v2.encounter_prompts.jsonl",
)
TOKEN = re.compile(r"[a-z0-9]+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-prompts-only", action="store_true")
    parser.add_argument("--dilemmas", type=Path, default=DEFAULT_DILEMMAS)
    parser.add_argument("--curriculum-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--curriculum-dir", type=Path)
    parser.add_argument("--evaluation", type=Path, action="append")
    parser.add_argument("--ngram-size", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text: str) -> str:
    return " ".join(TOKEN.findall(text.lower()))


def ngrams(text: str, n: int) -> set[str]:
    tokens = normalize(text).split()
    return {" ".join(tokens[index : index + n]) for index in range(len(tokens) - n + 1)}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract_eval_text(row: dict[str, Any]) -> str:
    for key in ("text", "prompt_text", "query"):
        if row.get(key):
            return str(row[key])
    raise ValueError("evaluation row has no registered text field")


def source_units(args: argparse.Namespace) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    if args.source_prompts_only:
        rows = read_jsonl(args.dilemmas)
        units = [(str(row["scenario_id"]), str(row["prompt_text"])) for row in rows]
        bindings = [{"path": str(args.dilemmas.resolve()), "sha256": sha256_file(args.dilemmas)}]
        return units, bindings
    if args.curriculum_dir is None:
        raise ValueError("--curriculum-dir is required unless --source-prompts-only is used")
    manifest = json.loads(args.curriculum_manifest.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "frame_internalization_curriculum_manifest.v1":
        raise ValueError("unexpected curriculum manifest schema")
    if manifest.get("passed") is not True:
        raise ValueError("curriculum manifest has not passed")
    units: list[tuple[str, str]] = []
    bindings: list[dict[str, Any]] = [
        {"path": str(args.curriculum_manifest.resolve()), "sha256": sha256_file(args.curriculum_manifest)}
    ]
    for arm_id in sorted(manifest["arms"]):
        for split, filename in (("train", "training.jsonl"), ("validation", "validation.jsonl")):
            path = args.curriculum_dir / arm_id / filename
            bindings.append({"path": str(path.resolve()), "sha256": sha256_file(path)})
            for row in read_jsonl(path):
                for message_index, message in enumerate(row["messages"]):
                    units.append(
                        (
                            f"{arm_id}:{split}:{row['scenario_id']}:{message_index}",
                            str(message["content"]),
                        )
                    )
    return units, bindings


def main() -> int:
    args = parse_args()
    if args.ngram_size < 2:
        raise ValueError("--ngram-size must be at least 2")
    evaluations = args.evaluation or list(EVALUATION_PATHS)
    eval_units: list[tuple[str, str, str]] = []
    eval_bindings: list[dict[str, Any]] = []
    for path in evaluations:
        path = path.resolve()
        eval_bindings.append({"path": str(path), "sha256": sha256_file(path)})
        for index, row in enumerate(read_jsonl(path)):
            eval_id = str(row.get("prompt_id") or row.get("override_prompt_id") or index)
            eval_units.append((path.name, eval_id, extract_eval_text(row)))

    eval_exact = {text for _, _, text in eval_units}
    eval_normalized = {normalize(text) for _, _, text in eval_units}
    eval_ngrams: dict[str, list[tuple[str, str]]] = {}
    for universe, eval_id, text in eval_units:
        for gram in ngrams(text, args.ngram_size):
            eval_ngrams.setdefault(gram, []).append((universe, eval_id))

    units, source_bindings = source_units(args)
    exact_matches: list[dict[str, str]] = []
    normalized_matches: list[dict[str, str]] = []
    ngram_matches: list[dict[str, str]] = []
    exact_count = normalized_count = ngram_count = 0
    for unit_id, text in units:
        if text in eval_exact:
            exact_count += 1
            if len(exact_matches) < 20:
                exact_matches.append({"unit_id": unit_id, "sha256": hashlib.sha256(text.encode()).hexdigest()})
        normalized = normalize(text)
        if normalized in eval_normalized:
            normalized_count += 1
            if len(normalized_matches) < 20:
                normalized_matches.append(
                    {"unit_id": unit_id, "normalized_sha256": hashlib.sha256(normalized.encode()).hexdigest()}
                )
        shared = sorted(ngrams(text, args.ngram_size).intersection(eval_ngrams))
        if shared:
            ngram_count += 1
            if len(ngram_matches) < 20:
                gram = shared[0]
                ngram_matches.append(
                    {
                        "unit_id": unit_id,
                        "ngram_sha256": hashlib.sha256(gram.encode()).hexdigest(),
                        "evaluation_universe": eval_ngrams[gram][0][0],
                        "evaluation_id": eval_ngrams[gram][0][1],
                    }
                )

    passed = exact_count == normalized_count == ngram_count == 0
    final_mode = not args.source_prompts_only
    receipt = {
        "schema_version": (
            "frame_internalization_nonleakage_audit.v1"
            if final_mode
            else "frame_internalization_nonleakage_precursor.v1"
        ),
        "scope": "complete_six_arm_curricula" if final_mode else "frozen_source_prompts_only",
        "status": "passed" if final_mode and passed else (
            "source_prompts_passed_generated_text_pending" if passed else "overlap_detected"
        ),
        "passed": passed,
        "gate_satisfying": final_mode and passed,
        "auditor_sha256": sha256_file(Path(__file__)),
        "ngram_size": args.ngram_size,
        "source_unit_count": len(units),
        "evaluation_unit_count": len(eval_units),
        "source_bindings": source_bindings,
        "evaluation_bindings": eval_bindings,
        "exact_overlap_count": exact_count,
        "normalized_overlap_count": normalized_count,
        "ngram_overlap_count": ngram_count,
        "examples": {
            "exact": exact_matches,
            "normalized": normalized_matches,
            "ngram": ngram_matches,
        },
        "completion_requirement": (
            None
            if final_mode
            else "rerun this audit over the rendered six-arm curriculum before pilot authorization"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "passed": passed, "gate_satisfying": receipt["gate_satisfying"]}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
