#!/usr/bin/env python3
"""Compare matched base and adapter Jinn v2 reasoning traces."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from statistics import fmean
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def trace_text(row: dict[str, Any]) -> str:
    raw = str(row.get("raw_response", ""))
    if "<think>" in raw:
        raw = raw.split("<think>", 1)[1]
    if "</think>" in raw:
        raw = raw.split("</think>", 1)[0]
    return raw.strip()


def trace_features(row: dict[str, Any], prompt: dict[str, Any]) -> dict[str, Any]:
    text = trace_text(row)
    lower = text.lower()
    action_ids = re.findall(r"(?m)^- ([a-z0-9_]+):", prompt["prompt"])
    evidence_ids = re.findall(r"(?m)^- ([A-Z0-9-]+):", prompt["prompt"])
    mentioned_actions = sorted(
        action_id for action_id in action_ids if action_id.lower() in lower
    )
    mentioned_evidence = sorted(
        evidence_id for evidence_id in evidence_ids if evidence_id.lower() in lower
    )
    return {
        "chars": len(text),
        "words": len(re.findall(r"\S+", text)),
        "action_coverage": (
            len(mentioned_actions) / len(action_ids) if action_ids else 0.0
        ),
        "evidence_coverage": (
            len(mentioned_evidence) / len(evidence_ids) if evidence_ids else 0.0
        ),
        "revision_language": bool(
            re.search(
                r"\b(revise|revision|change|changed|update|cross|contradict|conflict)\w*",
                lower,
            )
        ),
        "uncertainty_language": bool(
            re.search(r"\b(uncertain|uncertainty|bounded|material|confidence)\b", lower)
        ),
        "explicit_comparison": bool(
            re.search(r"\b(compare|alternative|option|versus|viable)\w*", lower)
        ),
        "decision_language": bool(
            re.search(r"\b(decide|decision|choose|select|therefore)\w*", lower)
        ),
        "trace_terminated": "</think>" in str(row.get("raw_response", "")),
        "final_response_present": bool(str(row.get("response", "")).strip()),
        "mentioned_actions": mentioned_actions,
        "mentioned_evidence": mentioned_evidence,
        "trace_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "mean_words": fmean(row["words"] for row in rows),
        "mean_action_coverage": fmean(row["action_coverage"] for row in rows),
        "mean_evidence_coverage": fmean(row["evidence_coverage"] for row in rows),
        "revision_language_rate": fmean(
            float(row["revision_language"]) for row in rows
        ),
        "uncertainty_language_rate": fmean(
            float(row["uncertainty_language"]) for row in rows
        ),
        "explicit_comparison_rate": fmean(
            float(row["explicit_comparison"]) for row in rows
        ),
        "decision_language_rate": fmean(
            float(row["decision_language"]) for row in rows
        ),
        "trace_termination_rate": fmean(
            float(row["trace_terminated"]) for row in rows
        ),
        "final_response_rate": fmean(
            float(row["final_response_present"]) for row in rows
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-generations", type=Path, required=True)
    parser.add_argument("--adapter-generations", type=Path, required=True)
    parser.add_argument("--sentinel-prompts", type=Path, required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    base_path = args.base_generations.resolve()
    adapter_path = args.adapter_generations.resolve()
    prompts_path = args.sentinel_prompts.resolve()
    prompts = read_jsonl(prompts_path)
    expected_ids = [row["probe_id"] for row in prompts]
    base_map = {row["example_id"]: row for row in read_jsonl(base_path)}
    adapter_map = {row["example_id"]: row for row in read_jsonl(adapter_path)}
    if not set(expected_ids).issubset(base_map):
        raise ValueError("base generations do not cover every trace sentinel")
    if set(expected_ids) != set(adapter_map):
        raise ValueError("adapter trace generation join is incomplete")

    matched = []
    base_features = []
    adapter_features = []
    for prompt in prompts:
        example_id = prompt["probe_id"]
        base = trace_features(base_map[example_id], prompt)
        adapter = trace_features(adapter_map[example_id], prompt)
        base_features.append(base)
        adapter_features.append(adapter)
        matched.append(
            {
                "example_id": example_id,
                "family_id": prompt["family_id"],
                "variant_id": prompt["variant_id"],
                "base": base,
                "adapter": adapter,
                "trace_changed": base["trace_sha256"] != adapter["trace_sha256"],
            }
        )
    receipt = {
        "schema_version": "jinn_reasoner_v2_trace_lane_comparison_v1",
        "checkpoint": args.checkpoint,
        "rows": len(matched),
        "base_generations_sha256": sha256_file(base_path),
        "adapter_generations_sha256": sha256_file(adapter_path),
        "sentinel_prompts_sha256": sha256_file(prompts_path),
        "base_summary": aggregate(base_features),
        "adapter_summary": aggregate(adapter_features),
        "changed_trace_rate": fmean(float(row["trace_changed"]) for row in matched),
        "matched_rows": matched,
        "claim_boundary": "Exploratory lexical trace comparison; not evidence of hidden-state movement.",
    }
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
