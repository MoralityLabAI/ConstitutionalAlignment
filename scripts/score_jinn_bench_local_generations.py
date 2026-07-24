#!/usr/bin/env python3
"""Score local JinnBench construct generations with the frozen deterministic rubric."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from statistics import fmean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jinn_bench.construct_scoring import score_construct_response


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError(f"{path} is empty")
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def has_reasoning_trace(raw: str) -> bool:
    matches = re.findall(r"<think>\s*(.*?)\s*</think>", raw, flags=re.DOTALL)
    if any(match.strip() for match in matches):
        return True
    if "<think>" in raw and "</think>" not in raw:
        return bool(raw.split("<think>", 1)[1].strip())
    return False


def trace_terminated(raw: str) -> bool:
    return not ("<think>" in raw and "</think>" not in raw)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generations", type=Path, required=True)
    parser.add_argument(
        "--tasks",
        type=Path,
        default=Path("jinn_bench/data/construct_tasks_v1.jsonl"),
    )
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    generations_path = args.generations.resolve()
    tasks_path = args.tasks.resolve()
    generations = read_jsonl(generations_path)
    task_map = {
        row["task_id"]: row
        for row in read_jsonl(tasks_path)
        if row["split"] == "development" and row["construct_id"] == "jinn_ness_v1"
    }
    if len(task_map) != 2:
        raise ValueError("expected exactly two development Jinn tasks")
    if {row["example_id"] for row in generations} != set(task_map):
        raise ValueError("generation/task join is incomplete or contains extra rows")

    scored = []
    for row in generations:
        task = task_map[row["example_id"]]
        score = score_construct_response(row["response"], task)
        raw = str(row.get("raw_response", ""))
        scored.append(
            {
                "task_id": task["task_id"],
                "response": row["response"],
                "raw_response": raw,
                "reasoning_trace_present": has_reasoning_trace(raw),
                "trace_terminated": trace_terminated(raw),
                "final_response_present": bool(str(row["response"]).strip()),
                "score": score,
            }
        )
    summary = {
        "mean_reward": fmean(float(row["score"]["final_score"]) for row in scored),
        "contract_valid_rate": fmean(
            float(row["score"]["contract_score"] == 1.0) for row in scored
        ),
        "legal_action_rate": fmean(
            float(row["score"]["legal_action"]) for row in scored
        ),
        "highest_scoring_action_rate": fmean(
            float(row["score"]["highest_scoring_action"]) for row in scored
        ),
        "critical_violation_rate": fmean(
            float(row["score"]["critical_violation"]) for row in scored
        ),
        "reasoning_trace_rate": fmean(
            float(row["reasoning_trace_present"]) for row in scored
        ),
        "trace_termination_rate": fmean(
            float(row["trace_terminated"]) for row in scored
        ),
        "final_response_rate": fmean(
            float(row["final_response_present"]) for row in scored
        ),
    }
    receipt = {
        "schema_version": "jinn_bench_local_construct_score_v1",
        "checkpoint": args.checkpoint,
        "generations_sha256": sha256_file(generations_path),
        "tasks_sha256": sha256_file(tasks_path),
        "rows": len(scored),
        "summary": summary,
        "scored_rows": scored,
        "claim_boundary": "Exploratory development-slice evidence only.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
