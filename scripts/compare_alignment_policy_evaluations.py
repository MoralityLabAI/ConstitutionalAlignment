#!/usr/bin/env python3
"""Compare paired base/policy proxy evaluations with prompt-cluster bootstrap CIs."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


WEIGHTS = {
    "response_contract": 1.0,
    "valid_decision": 1.5,
    "tenet_grounding": 1.25,
    "reflective_defense": 1.25,
    "action_defense_consistency": 1.25,
    "anti_gaming": 1.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--policy-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260714)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bootstrap_mean_ci(
    values: list[float],
    *,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    if not values:
        raise ValueError("bootstrap requires at least one paired prompt")
    if samples < 100:
        raise ValueError("bootstrap_samples must be at least 100")
    rng = random.Random(seed)
    size = len(values)
    draws = sorted(
        sum(values[rng.randrange(size)] for _ in range(size)) / size
        for _ in range(samples)
    )
    lower = draws[int(0.025 * (samples - 1))]
    upper = draws[int(0.975 * (samples - 1))]
    return {
        "estimate": sum(values) / size,
        "ci_95_percentile": [lower, upper],
        "paired_prompt_differences": values,
    }


def weighted_proxy(row: dict[str, Any]) -> float:
    return sum(float(row["scores"][name]) * weight for name, weight in WEIGHTS.items())


def prompt_means(
    rows: list[dict[str, Any]],
    metric: Callable[[dict[str, Any]], float],
) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        values[row["example_id"]].append(float(metric(row)))
    return {
        example_id: sum(samples) / len(samples)
        for example_id, samples in values.items()
    }


def paired_differences(
    base_rows: list[dict[str, Any]],
    policy_rows: list[dict[str, Any]],
    metric: Callable[[dict[str, Any]], float],
) -> tuple[list[str], list[float]]:
    base = prompt_means(base_rows, metric)
    policy = prompt_means(policy_rows, metric)
    if set(base) != set(policy):
        raise ValueError("base and policy evaluations contain different prompt IDs")
    prompt_ids = sorted(base)
    return prompt_ids, [policy[prompt_id] - base[prompt_id] for prompt_id in prompt_ids]


def compare(
    base_dir: Path,
    policy_dir: Path,
    *,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    base_receipt_path = base_dir / "receipt.json"
    policy_receipt_path = policy_dir / "receipt.json"
    base_response_path = base_dir / "responses.jsonl"
    policy_response_path = policy_dir / "responses.jsonl"
    base_receipt = load_json(base_receipt_path)
    policy_receipt = load_json(policy_receipt_path)
    for field in ("model_id", "model_revision", "dataset_sha256"):
        if base_receipt.get(field) != policy_receipt.get(field):
            raise ValueError(f"evaluation receipt mismatch for {field}")
    if base_receipt.get("adapter_sha256"):
        raise ValueError("base evaluation unexpectedly contains an adapter")
    if not policy_receipt.get("adapter_sha256"):
        raise ValueError("policy evaluation does not contain an adapter hash")
    if base_receipt.get("chat_template_kwargs") != policy_receipt.get("chat_template_kwargs"):
        raise ValueError("chat-template settings differ between evaluations")
    comparable_args = ("seed", "max_prompts", "num_generations", "max_completion_length")
    for field in comparable_args:
        base_value = base_receipt["generation_args"].get(field)
        policy_value = policy_receipt["generation_args"].get(field)
        if base_value != policy_value:
            raise ValueError(f"generation argument mismatch for {field}")

    base_rows = load_jsonl(base_response_path)
    policy_rows = load_jsonl(policy_response_path)
    base_response_keys = {
        (row["example_id"], row["generation_index"]) for row in base_rows
    }
    policy_response_keys = {
        (row["example_id"], row["generation_index"]) for row in policy_rows
    }
    if base_response_keys != policy_response_keys:
        raise ValueError("base and policy response cells do not match")

    metrics: dict[str, Callable[[dict[str, Any]], float]] = {
        "weighted_proxy_reward": weighted_proxy,
        **{
            name: lambda row, component=name: float(row["scores"][component])
            for name in WEIGHTS
        },
        "valid_decision_rate": lambda row: float(row["scores"]["valid_decision"] == 1.0),
        "complete_contract_rate": lambda row: float(row["scores"]["response_contract"] == 1.0),
        "termination_rate": lambda row: float(row["terminated_with_eos"]),
    }
    deltas: dict[str, Any] = {}
    prompt_ids: list[str] = []
    for index, (name, metric) in enumerate(metrics.items()):
        prompt_ids, differences = paired_differences(base_rows, policy_rows, metric)
        deltas[name] = bootstrap_mean_ci(
            differences,
            samples=bootstrap_samples,
            seed=seed + index,
        )

    return {
        "comparison_version": "alignment_policy_paired_comparison_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "proxy_scores_are_not_compliance_metrics": True,
        "model_id": base_receipt["model_id"],
        "model_revision": base_receipt["model_revision"],
        "dataset_sha256": base_receipt["dataset_sha256"],
        "base_adapter": "",
        "policy_adapter_sha256": policy_receipt["adapter_sha256"],
        "paired_prompt_clusters": len(prompt_ids),
        "generations_per_prompt": base_receipt["generation_args"]["num_generations"],
        "bootstrap": {
            "method": "paired prompt-cluster percentile bootstrap",
            "samples": bootstrap_samples,
            "seed": seed,
        },
        "source_receipt_sha256": {
            "base": sha256_file(base_receipt_path),
            "policy": sha256_file(policy_receipt_path),
        },
        "source_responses_sha256": {
            "base": sha256_file(base_response_path),
            "policy": sha256_file(policy_response_path),
        },
        "policy_minus_base": deltas,
    }


def main() -> int:
    args = parse_args()
    report = compare(
        Path(args.base_dir).resolve(),
        Path(args.policy_dir).resolve(),
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
