"""Freeze and summarize a local Prime Jinn/Beast construct evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

EXPECTED_CONSTRUCTS = frozenset({"jinn_ness_v1", "beast_from_earth_witness_v1"})
EXPECTED_BASE_MODEL = "Qwen/Qwen3.5-4B"
DIMENSION_METRICS = (
    "accountable_choice",
    "entrusted_stewardship",
    "truth_under_concealment",
    "evidence_bounded_reason",
    "justice_without_scapegoat",
    "repair_preservation",
    "grounded_witness",
    "public_legibility",
    "courage_under_pressure",
    "proportionate_exposure",
    "evidence_over_spectacle",
    "repair_after_testimony",
)
CORE_METRICS = (
    "constitutional_policy",
    "contract_valid",
    "legal_action",
    "action_quality",
    "evidence_grounding",
    "uncertainty_match",
    "review_match",
    "critical_violation",
    "proxy_regret",
    "highest_scoring_action",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"{path}:{line_number} must contain an object")
        rows.append(value)
    if not rows:
        raise ValueError(f"{path} is empty")
    return rows


def completion_message(row: dict[str, Any]) -> dict[str, Any]:
    completion = row.get("completion")
    if isinstance(completion, dict):
        return completion
    if isinstance(completion, list) and completion:
        message = completion[-1]
        if isinstance(message, dict):
            return message
    return {}


def metric(row: dict[str, Any], metric_id: str) -> float:
    metrics = row.get("metrics")
    if isinstance(metrics, dict) and metric_id in metrics:
        return float(metrics[metric_id])
    return float(row.get(metric_id, 0.0))


def parse_final_json(content: Any) -> dict[str, Any] | None:
    if not isinstance(content, str) or not content.strip():
        return None
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def categorical(value: Any) -> str:
    if value is None:
        return "<missing>"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rollouts": len(rows),
        "mean_reward": fmean(float(row["reward"]) for row in rows),
        "truncated_rate": fmean(float(bool(row.get("is_truncated"))) for row in rows),
        "metrics": {
            metric_id: fmean(metric(row, metric_id) for row in rows)
            for metric_id in (*CORE_METRICS, *DIMENSION_METRICS)
        },
    }


def validate_model(model: Any) -> None:
    if model == EXPECTED_BASE_MODEL:
        return
    if not isinstance(model, str):
        raise TypeError(f"model must be a string, got {model!r}")
    prefix = f"{EXPECTED_BASE_MODEL}:"
    adapter_id = model.removeprefix(prefix)
    normalized_adapter_id = adapter_id.replace("-", "").replace("_", "")
    if not model.startswith(prefix) or not normalized_adapter_id.isalnum():
        raise ValueError(f"unexpected model: {model!r}")


def evaluation_viewer_url(evaluation_id: str) -> str | None:
    if len(evaluation_id) == 24 and evaluation_id.isalnum():
        return f"https://app.primeintellect.ai/dashboard/evaluations/{evaluation_id}"
    return None


def summarize(
    metadata: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_rows = int(metadata["num_examples"]) * int(
        metadata["rollouts_per_example"]
    )
    if len(rows) != expected_rows:
        raise ValueError(f"expected {expected_rows} rows, found {len(rows)}")
    if metadata.get("env_id") != "moralitylab/jinn-beast-metta":
        raise ValueError(f"unexpected environment: {metadata.get('env_id')!r}")
    validate_model(metadata.get("model"))
    if metadata.get("env_args", {}).get("task_mode") != "constructs":
        raise ValueError("evaluation did not use task_mode=constructs")
    thinking = (
        metadata.get("sampling_args", {})
        .get("extra_body", {})
        .get("chat_template_kwargs", {})
        .get("enable_thinking")
    )
    if thinking is not True:
        raise ValueError("evaluation did not freeze enable_thinking=true")

    by_construct: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    parsed_rows: list[dict[str, Any]] = []
    reasoning_characters: list[int] = []
    input_tokens = 0
    output_tokens = 0
    reasoning_count = 0
    content_count = 0
    error_count = 0
    for row in rows:
        info = row.get("info")
        if not isinstance(info, dict):
            raise TypeError("each row must contain an info object")
        if info.get("split") != "development":
            raise ValueError(f"unexpected split: {info.get('split')!r}")
        construct_id = str(info["construct_id"])
        task_id = str(info["task_id"])
        by_construct[construct_id].append(row)
        by_task[task_id].append(row)

        message = completion_message(row)
        content = message.get("content")
        reasoning = message.get("reasoning_content")
        if isinstance(content, str) and content.strip():
            content_count += 1
        if isinstance(reasoning, str) and reasoning.strip():
            reasoning_count += 1
            reasoning_characters.append(len(reasoning))
        parsed = parse_final_json(content)
        if parsed is not None:
            parsed_rows.append(parsed)
        if row.get("error"):
            error_count += 1
        usage = row.get("token_usage")
        if isinstance(usage, dict):
            input_tokens += int(usage.get("final_input_tokens", 0))
            output_tokens += int(usage.get("final_output_tokens", 0))

    if set(by_construct) != EXPECTED_CONSTRUCTS:
        raise ValueError(f"unexpected construct universe: {sorted(by_construct)}")
    expected_rollouts = int(metadata["rollouts_per_example"])
    bad_task_counts = {
        task_id: len(task_rows)
        for task_id, task_rows in by_task.items()
        if len(task_rows) != expected_rollouts
    }
    if bad_task_counts:
        raise ValueError(f"incomplete task joins: {bad_task_counts}")

    uncertainty_values = Counter(
        categorical(parsed.get("uncertainty")) for parsed in parsed_rows
    )
    review_values = Counter(
        categorical(parsed.get("review_required")) for parsed in parsed_rows
    )
    decision_values = Counter(
        categorical(parsed.get("decision")) for parsed in parsed_rows
    )
    all_metrics = {
        metric_id: fmean(metric(row, metric_id) for row in rows)
        for metric_id in (*CORE_METRICS, *DIMENSION_METRICS)
    }
    return {
        "rollouts": len(rows),
        "tasks": len(by_task),
        "constructs": len(by_construct),
        "error_count": error_count,
        "error_rate": error_count / len(rows),
        "reasoning_trace_count": reasoning_count,
        "reasoning_trace_rate": reasoning_count / len(rows),
        "content_count": content_count,
        "content_rate": content_count / len(rows),
        "parsed_final_json_count": len(parsed_rows),
        "parsed_final_json_rate": len(parsed_rows) / len(rows),
        "truncated_count": sum(int(bool(row.get("is_truncated"))) for row in rows),
        "truncated_rate": fmean(float(bool(row.get("is_truncated"))) for row in rows),
        "mean_reward": fmean(float(row["reward"]) for row in rows),
        "zero_reward_rate": fmean(float(float(row["reward"]) == 0.0) for row in rows),
        "metrics": all_metrics,
        "final_answer_values": {
            "uncertainty": dict(sorted(uncertainty_values.items())),
            "review_required": dict(sorted(review_values.items())),
            "decision": dict(sorted(decision_values.items())),
        },
        "token_usage": {
            "total_input_tokens": input_tokens,
            "total_output_tokens": output_tokens,
            "mean_input_tokens": input_tokens / len(rows),
            "mean_output_tokens": output_tokens / len(rows),
            "mean_reasoning_characters": (
                fmean(reasoning_characters) if reasoning_characters else 0.0
            ),
        },
        "estimated_inference_cost_usd": ((input_tokens * 0.1) + (output_tokens * 0.3))
        / 1_000_000,
        "by_construct": {
            construct_id: summarize_group(construct_rows)
            for construct_id, construct_rows in sorted(by_construct.items())
        },
        "by_task": {
            task_id: summarize_group(task_rows)
            for task_id, task_rows in sorted(by_task.items())
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-dir", type=Path, required=True)
    parser.add_argument("--evaluation-id", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    eval_dir = args.eval_dir.resolve()
    metadata_path = eval_dir / "metadata.json"
    results_path = eval_dir / "results.jsonl"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise TypeError("metadata.json must contain an object")
    rows = load_jsonl(results_path)
    summary = summarize(metadata, rows)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_metadata_path = output_dir / f"{args.label}_metadata.json"
    raw_results_path = output_dir / f"{args.label}_results.jsonl"
    analysis_path = output_dir / f"{args.label}_analysis.json"
    raw_metadata_path.write_text(
        metadata_path.read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="\n",
    )
    raw_results_path.write_text(
        results_path.read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="\n",
    )
    analysis = {
        "schema_version": "jinn_beast_construct_prime_eval_analysis_v1",
        "status": "complete",
        "evaluation_id": args.evaluation_id,
        "viewer_url": evaluation_viewer_url(args.evaluation_id),
        "metadata": metadata,
        "summary": summary,
        "artifacts": {
            "metadata": {
                "path": display_path(raw_metadata_path),
                "sha256": sha256_file(raw_metadata_path),
                "bytes": raw_metadata_path.stat().st_size,
            },
            "results": {
                "path": display_path(raw_results_path),
                "sha256": sha256_file(raw_results_path),
                "bytes": raw_results_path.stat().st_size,
                "rows": len(rows),
            },
        },
        "claim_boundary": (
            "Development-only evaluation evidence. It measures task-interface and "
            "policy behavior; an individual run does not establish a training effect "
            "without its matched comparison."
        ),
    }
    analysis_path.write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "analysis": display_path(analysis_path),
                "evaluation_id": args.evaluation_id,
                "summary": summary,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
