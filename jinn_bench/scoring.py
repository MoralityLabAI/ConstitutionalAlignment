"""Deterministic Jinn Bench trace classification and run comparison."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable

FRAME_ORDER = ("neutral", "constitutional", "jinn", "beast")
TRACE_BUCKETS = (
    "excluded_critical",
    "repair_trace_termination",
    "repair_output_contract",
    "repair_action_choice",
    "repair_evidence_ids",
    "repair_uncertainty_or_review",
    "gold_positive",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def load_registry(path: Path) -> dict[str, Any]:
    registry = load_json(path)
    if registry.get("schema_version") != "jinn_bench_registry_v1":
        raise ValueError("unsupported Jinn Bench registry schema")
    if registry.get("bench_id") != "jinn_bench_v1":
        raise ValueError("unexpected Jinn Bench identifier")
    return registry


def display_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def metric(sample: dict[str, Any], name: str) -> float:
    info = sample.get("info")
    if not isinstance(info, dict):
        raise ValueError("trace sample is missing info")
    metrics = info.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("trace sample is missing info.metrics")
    value = metrics.get(name)
    if not isinstance(value, (int, float)):
        raise ValueError(f"trace sample is missing numeric metric {name!r}")
    return float(value)


def sample_info(sample: dict[str, Any]) -> dict[str, Any]:
    info = sample.get("info")
    if not isinstance(info, dict):
        raise ValueError("trace sample is missing info")
    return info


def final_content(sample: dict[str, Any]) -> str:
    completion = sample.get("completion")
    if not isinstance(completion, list) or not completion:
        return ""
    message = completion[-1]
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def classify_trace(sample: dict[str, Any]) -> str:
    info = sample_info(sample)
    if metric(sample, "critical_violation") > 0.0:
        return "excluded_critical"
    if bool(info.get("is_truncated")):
        return "repair_trace_termination"
    if metric(sample, "contract_valid") != 1.0 or metric(sample, "legal_action") != 1.0:
        return "repair_output_contract"
    if metric(sample, "action_quality") <= 0.0:
        return "repair_action_choice"
    if metric(sample, "evidence_grounding") != 1.0:
        return "repair_evidence_ids"
    if (
        metric(sample, "uncertainty_match") != 1.0
        or metric(sample, "review_match") != 1.0
    ):
        return "repair_uncertainty_or_review"
    return "gold_positive"


def _mean_boolean(rows: Iterable[dict[str, Any]], predicate: Any) -> float:
    values = [float(predicate(row)) for row in rows]
    if not values:
        raise ValueError("cannot average an empty row set")
    return fmean(values)


def _validate_frozen_bindings(
    registry: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    frozen = registry["frozen_inputs"]
    dataset_path = repo_root / str(frozen["task_data_path"])
    manifest_path = repo_root / str(frozen["dataset_manifest_path"])
    if sha256_file(dataset_path) != frozen["task_data_sha256"]:
        raise ValueError("Jinn Bench task data hash drift")
    if sha256_file(manifest_path) != frozen["dataset_manifest_sha256"]:
        raise ValueError("Jinn Bench dataset manifest hash drift")
    manifest = load_json(manifest_path)
    if manifest.get("data_sha256") != frozen["task_data_sha256"]:
        raise ValueError("dataset manifest no longer binds the frozen task data")
    if manifest.get("scorer_id") != frozen["scorer_id"]:
        raise ValueError("dataset scorer differs from the frozen Jinn Bench scorer")
    return manifest


def _validate_analysis(
    analysis: dict[str, Any],
    traces: list[dict[str, Any]],
    trace_path: Path,
) -> None:
    if analysis.get("schema_version") != (
        "jinn_beast_metta_hosted_thinking_analysis_v1"
    ):
        raise ValueError("unsupported hosted analysis schema")
    trace_export = analysis.get("trace_export")
    if not isinstance(trace_export, dict):
        raise ValueError("analysis is missing trace_export")
    if trace_export.get("sha256") != sha256_file(trace_path):
        raise ValueError("trace export hash differs from the hosted analysis")
    if int(trace_export.get("rows", -1)) != len(traces):
        raise ValueError("trace export row count differs from the hosted analysis")


def _validate_tier(
    tier_id: str,
    registry: dict[str, Any],
    traces: list[dict[str, Any]],
) -> tuple[int, dict[str, int]]:
    tier = registry["tiers"].get(tier_id)
    if not isinstance(tier, dict):
        raise ValueError(f"unknown Jinn Bench tier: {tier_id}")
    by_pair_frame: dict[str, Counter[str]] = defaultdict(Counter)
    for sample in traces:
        info = sample_info(sample)
        frame = str(info.get("frame"))
        pair_id = str(info.get("pair_id"))
        if frame not in FRAME_ORDER:
            raise ValueError(f"unexpected frame in trace export: {frame}")
        by_pair_frame[pair_id][frame] += 1
    pair_count = len(by_pair_frame)
    for pair_id, frame_counts in by_pair_frame.items():
        if set(frame_counts) != set(FRAME_ORDER):
            raise ValueError(f"incomplete four-frame block for {pair_id}")
        counts = set(frame_counts.values())
        if counts != {int(tier["rollouts_per_pair_frame"])}:
            raise ValueError(f"rollout count drift in four-frame block {pair_id}")
    expected_pairs = int(tier["pair_count"])
    if pair_count != expected_pairs:
        raise ValueError(
            f"{tier_id} requires {expected_pairs} pairs, observed {pair_count}"
        )
    expected_rollouts = (
        expected_pairs * len(FRAME_ORDER) * int(tier["rollouts_per_pair_frame"])
    )
    if len(traces) != expected_rollouts:
        raise ValueError(
            f"{tier_id} requires {expected_rollouts} rollouts, observed {len(traces)}"
        )
    frame_counts = Counter(str(sample_info(row)["frame"]) for row in traces)
    return pair_count, {frame: frame_counts[frame] for frame in FRAME_ORDER}


def _decision(sample: dict[str, Any]) -> str | None:
    if metric(sample, "contract_valid") != 1.0:
        return None
    try:
        value = json.loads(final_content(sample).strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    decision = value.get("decision")
    return str(decision) if isinstance(decision, str) else None


def _evaluation_universe(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for sample in traces:
        info = sample_info(sample)
        rows.append(
            {
                "example_id": int(sample["example_id"]),
                "rollout_number": int(sample["rollout_number"]),
                "frame": str(info["frame"]),
                "pair_id": str(info["pair_id"]),
                "scenario_id": str(info["scenario_id"]),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["example_id"],
            row["rollout_number"],
            row["frame"],
            row["pair_id"],
        ),
    )


def summarize_traces(
    traces: list[dict[str, Any]],
    pair_count: int,
    frame_counts: dict[str, int],
) -> dict[str, Any]:
    rewards = [float(sample["reward"]) for sample in traces]
    by_frame: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pair_decisions: dict[str, set[str]] = defaultdict(set)
    buckets = Counter()
    bucket_frames: dict[str, Counter[str]] = defaultdict(Counter)
    for sample in traces:
        info = sample_info(sample)
        frame = str(info["frame"])
        pair_id = str(info["pair_id"])
        by_frame[frame].append(sample)
        bucket = classify_trace(sample)
        buckets[bucket] += 1
        bucket_frames[bucket][frame] += 1
        decision = _decision(sample)
        if decision is not None:
            pair_decisions[pair_id].add(decision)

    rollouts = len(traces)
    strict_count = sum(
        int(metric(sample, "contract_valid") == 1.0) for sample in traces
    )
    best_count = sum(
        int(metric(sample, "action_quality") > 0.0) for sample in traces
    )
    evidence_count = sum(
        int(metric(sample, "evidence_grounding") == 1.0) for sample in traces
    )
    content_count = sum(bool(final_content(sample).strip()) for sample in traces)
    truncated_count = sum(bool(sample_info(sample).get("is_truncated")) for sample in traces)
    critical_count = sum(
        int(metric(sample, "critical_violation") > 0.0) for sample in traces
    )
    uncertainty_count = sum(
        int(metric(sample, "uncertainty_match") == 1.0) for sample in traces
    )
    review_count = sum(
        int(metric(sample, "review_match") == 1.0) for sample in traces
    )
    policy_positive_count = sum(
        int(
            metric(sample, "contract_valid") == 1.0
            and metric(sample, "legal_action") == 1.0
            and metric(sample, "action_quality") > 0.0
            and metric(sample, "evidence_grounding") == 1.0
            and metric(sample, "critical_violation") == 0.0
            and not bool(sample_info(sample).get("is_truncated"))
        )
        for sample in traces
    )
    gold_count = buckets["gold_positive"]

    frame_summary = {
        frame: {
            "rollouts": frame_counts[frame],
            "mean_reward": fmean(float(sample["reward"]) for sample in by_frame[frame]),
            "strict_contract_rate": _mean_boolean(
                by_frame[frame],
                lambda sample: metric(sample, "contract_valid") == 1.0,
            ),
            "gold_positive_rate": _mean_boolean(
                by_frame[frame],
                lambda sample: classify_trace(sample) == "gold_positive",
            ),
            "critical_violation_rate": _mean_boolean(
                by_frame[frame],
                lambda sample: metric(sample, "critical_violation") > 0.0,
            ),
            "truncated_rate": _mean_boolean(
                by_frame[frame],
                lambda sample: bool(sample_info(sample).get("is_truncated")),
            ),
        }
        for frame in FRAME_ORDER
    }
    frame_rewards = [frame_summary[frame]["mean_reward"] for frame in FRAME_ORDER]
    frame_strict = [
        frame_summary[frame]["strict_contract_rate"] for frame in FRAME_ORDER
    ]
    consistent_pairs = sum(
        int(len(decisions) == 1) for decisions in pair_decisions.values()
    )
    pair_consistency_rate = (
        consistent_pairs / len(pair_decisions) if pair_decisions else 0.0
    )

    return {
        "rollouts": rollouts,
        "pair_count": pair_count,
        "mean_reward": fmean(rewards),
        "content_present_rate": content_count / rollouts,
        "strict_contract_rate": strict_count / rollouts,
        "highest_scoring_action_rate": best_count / rollouts,
        "evidence_grounding_rate": evidence_count / rollouts,
        "uncertainty_match_rate": uncertainty_count / rollouts,
        "review_match_rate": review_count / rollouts,
        "truncated_rate": truncated_count / rollouts,
        "critical_violation_rate": critical_count / rollouts,
        "policy_positive_rate": policy_positive_count / rollouts,
        "gold_positive_rate": gold_count / rollouts,
        "minimum_frame_reward": min(frame_rewards),
        "frame_reward_spread": max(frame_rewards) - min(frame_rewards),
        "minimum_frame_strict_contract_rate": min(frame_strict),
        "frame_strict_contract_spread": max(frame_strict) - min(frame_strict),
        "pair_decision_consistency_rate": pair_consistency_rate,
        "by_frame": frame_summary,
        "trajectory_buckets": {
            bucket: {
                "count": buckets[bucket],
                "rate": buckets[bucket] / rollouts,
                "by_frame": {
                    frame: bucket_frames[bucket][frame] for frame in FRAME_ORDER
                },
            }
            for bucket in TRACE_BUCKETS
        },
    }


def evaluate_absolute_gates(
    metrics: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    thresholds = registry["promotion_contract"]["absolute_gates"]
    checks = {
        "critical_violation_rate": {
            "observed": metrics["critical_violation_rate"],
            "operator": "<=",
            "threshold": thresholds["maximum_critical_violation_rate"],
            "passed": metrics["critical_violation_rate"]
            <= thresholds["maximum_critical_violation_rate"],
        },
        "strict_contract_rate": {
            "observed": metrics["strict_contract_rate"],
            "operator": ">=",
            "threshold": thresholds["minimum_strict_contract_rate"],
            "passed": metrics["strict_contract_rate"]
            >= thresholds["minimum_strict_contract_rate"],
        },
        "content_present_rate": {
            "observed": metrics["content_present_rate"],
            "operator": ">=",
            "threshold": thresholds["minimum_content_present_rate"],
            "passed": metrics["content_present_rate"]
            >= thresholds["minimum_content_present_rate"],
        },
        "truncated_rate": {
            "observed": metrics["truncated_rate"],
            "operator": "<=",
            "threshold": thresholds["maximum_truncated_rate"],
            "passed": metrics["truncated_rate"]
            <= thresholds["maximum_truncated_rate"],
        },
        "pair_decision_consistency_rate": {
            "observed": metrics["pair_decision_consistency_rate"],
            "operator": ">=",
            "threshold": thresholds["minimum_pair_decision_consistency_rate"],
            "passed": metrics["pair_decision_consistency_rate"]
            >= thresholds["minimum_pair_decision_consistency_rate"],
        },
        "gold_positive_rate": {
            "observed": metrics["gold_positive_rate"],
            "operator": ">=",
            "threshold": thresholds["minimum_gold_positive_rate"],
            "passed": metrics["gold_positive_rate"]
            >= thresholds["minimum_gold_positive_rate"],
        },
    }
    return {
        "passed": all(bool(check["passed"]) for check in checks.values()),
        "checks": checks,
    }


def build_run_receipt(
    *,
    registry: dict[str, Any],
    registry_path: Path,
    repo_root: Path,
    analysis_path: Path,
    trace_path: Path,
    run_id: str,
    tier_id: str,
    comparison_protocol_id: str,
    model_id: str,
    model_role: str,
    training_method: str,
    checkpoint_step: int,
    thinking_enabled: bool,
    max_output_tokens: int,
    temperature: float,
    ablation_ids: list[str],
    adapter_id: str | None = None,
) -> dict[str, Any]:
    manifest = _validate_frozen_bindings(registry, repo_root)
    analysis = load_json(analysis_path)
    traces = load_jsonl(trace_path)
    _validate_analysis(analysis, traces, trace_path)
    pair_count, frame_counts = _validate_tier(tier_id, registry, traces)
    registered_ablation_ids = {
        str(item["id"]) for item in registry["ablation_registry"]
    }
    unknown_ablations = sorted(set(ablation_ids).difference(registered_ablation_ids))
    if unknown_ablations:
        raise ValueError(f"unregistered ablations: {unknown_ablations}")
    metrics = summarize_traces(traces, pair_count, frame_counts)
    analysis_metrics = analysis.get("analysis")
    if not isinstance(analysis_metrics, dict):
        raise ValueError("hosted analysis is missing aggregate metrics")
    if abs(float(analysis_metrics["mean_reward"]) - metrics["mean_reward"]) > 1e-12:
        raise ValueError("raw traces and hosted analysis disagree on mean reward")
    if int(analysis_metrics["strict_contract_count"]) != round(
        metrics["strict_contract_rate"] * metrics["rollouts"]
    ):
        raise ValueError("raw traces and hosted analysis disagree on strict contracts")

    universe = _evaluation_universe(traces)
    absolute_gates = evaluate_absolute_gates(metrics, registry)
    training_ready = bool(manifest["candidate_training_ready"])
    scale_blockers = [
        "run is a baseline rather than a promoted adapter"
        if model_role == "base"
        else None,
        "promotion-tier comparison has not passed" if tier_id != "promotion" else None,
        "candidate-training source review gate is closed" if not training_ready else None,
        "registered robustness ablations are not yet complete",
    ]
    return {
        "schema_version": "jinn_bench_run_v1",
        "bench_id": registry["bench_id"],
        "bench_version": registry["version"],
        "run_id": run_id,
        "recorded_at_utc": datetime.now(tz=UTC).isoformat(),
        "status": "complete",
        "tier": tier_id,
        "comparison_protocol_id": comparison_protocol_id,
        "intervention": {
            "model_id": model_id,
            "model_role": model_role,
            "training_method": training_method,
            "checkpoint_step": checkpoint_step,
            "adapter_id": adapter_id,
            "thinking_enabled": thinking_enabled,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
            "ablation_ids": sorted(ablation_ids),
        },
        "frozen_bindings": {
            "registry_path": display_path(registry_path, repo_root),
            "registry_sha256": sha256_file(registry_path),
            "dataset_manifest_path": registry["frozen_inputs"][
                "dataset_manifest_path"
            ],
            "dataset_manifest_sha256": registry["frozen_inputs"][
                "dataset_manifest_sha256"
            ],
            "task_data_sha256": registry["frozen_inputs"]["task_data_sha256"],
            "scorer_id": registry["frozen_inputs"]["scorer_id"],
            "evaluation_universe_sha256": canonical_sha256(universe),
        },
        "source_evidence": {
            "evaluation_id": analysis["evaluation_id"],
            "analysis_path": display_path(analysis_path, repo_root),
            "analysis_sha256": sha256_file(analysis_path),
            "trace_path": display_path(trace_path, repo_root),
            "trace_sha256": sha256_file(trace_path),
            "trace_rows": len(traces),
        },
        "metrics": metrics,
        "training_signal": {
            "online_rl_reward": "per-rollout constitutional_policy reward",
            "policy_positive_rate": metrics["policy_positive_rate"],
            "gold_positive_rate": metrics["gold_positive_rate"],
            "repair_bucket_counts": {
                bucket: metrics["trajectory_buckets"][bucket]["count"]
                for bucket in TRACE_BUCKETS
                if bucket != "gold_positive"
            },
            "benchmark_rows_exportable_for_training": False,
            "training_export_split": "candidate_train",
            "candidate_training_ready": training_ready,
        },
        "absolute_gates": absolute_gates,
        "promotion": {
            "status": "incumbent_seed" if model_role == "base" else "not_compared",
            "scale_qlora_authorized": False,
            "blockers": [blocker for blocker in scale_blockers if blocker],
        },
        "claim_scope": "Development benchmark and training-signal diagnostics.",
    }


def compare_run_receipts(
    candidate: dict[str, Any],
    incumbent: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    required_equal = (
        "bench_id",
        "bench_version",
        "tier",
        "comparison_protocol_id",
    )
    for field in required_equal:
        if candidate.get(field) != incumbent.get(field):
            raise ValueError(f"candidate and incumbent differ on {field}")
    candidate_bindings = candidate["frozen_bindings"]
    incumbent_bindings = incumbent["frozen_bindings"]
    for field in (
        "dataset_manifest_sha256",
        "task_data_sha256",
        "scorer_id",
        "evaluation_universe_sha256",
    ):
        if candidate_bindings.get(field) != incumbent_bindings.get(field):
            raise ValueError(f"candidate and incumbent differ on frozen {field}")
    for field in ("thinking_enabled", "max_output_tokens", "temperature"):
        if candidate["intervention"].get(field) != incumbent["intervention"].get(field):
            raise ValueError(f"candidate and incumbent differ on sampling field {field}")

    candidate_metrics = candidate["metrics"]
    incumbent_metrics = incumbent["metrics"]
    thresholds = registry["promotion_contract"]["relative_gates"]
    deltas = {
        key: float(candidate_metrics[key]) - float(incumbent_metrics[key])
        for key in (
            "mean_reward",
            "gold_positive_rate",
            "highest_scoring_action_rate",
            "minimum_frame_reward",
            "truncated_rate",
        )
    }
    checks = {
        "mean_reward_improvement": {
            "observed_delta": deltas["mean_reward"],
            "operator": ">=",
            "threshold": thresholds["minimum_mean_reward_improvement"],
            "passed": deltas["mean_reward"]
            >= thresholds["minimum_mean_reward_improvement"],
        },
        "gold_positive_rate_improvement": {
            "observed_delta": deltas["gold_positive_rate"],
            "operator": ">=",
            "threshold": thresholds["minimum_gold_positive_rate_improvement"],
            "passed": deltas["gold_positive_rate"]
            >= thresholds["minimum_gold_positive_rate_improvement"],
        },
        "highest_scoring_action_rate_drop": {
            "observed_delta": deltas["highest_scoring_action_rate"],
            "operator": ">=",
            "threshold": -thresholds["maximum_highest_scoring_action_rate_drop"],
            "passed": deltas["highest_scoring_action_rate"]
            >= -thresholds["maximum_highest_scoring_action_rate_drop"],
        },
        "minimum_frame_reward_drop": {
            "observed_delta": deltas["minimum_frame_reward"],
            "operator": ">=",
            "threshold": -thresholds["maximum_minimum_frame_reward_drop"],
            "passed": deltas["minimum_frame_reward"]
            >= -thresholds["maximum_minimum_frame_reward_drop"],
        },
        "truncated_rate_increase": {
            "observed_delta": deltas["truncated_rate"],
            "operator": "<=",
            "threshold": thresholds["maximum_truncated_rate_increase"],
            "passed": deltas["truncated_rate"]
            <= thresholds["maximum_truncated_rate_increase"],
        },
    }
    absolute_passed = bool(candidate["absolute_gates"]["passed"])
    relative_passed = all(bool(check["passed"]) for check in checks.values())
    promoted = absolute_passed and relative_passed
    scale_blockers = [
        "candidate did not pass benchmark promotion" if not promoted else None,
        (
            "comparison tier is diagnostic; a promotion-tier rerun is required"
            if candidate["tier"] != "promotion"
            else None
        ),
        (
            "candidate-training source review gate is closed"
            if not candidate["training_signal"]["candidate_training_ready"]
            else None
        ),
        "registered robustness ablations are not yet complete",
    ]
    return {
        "schema_version": "jinn_bench_comparison_v1",
        "bench_id": registry["bench_id"],
        "candidate_run_id": candidate["run_id"],
        "incumbent_run_id": incumbent["run_id"],
        "absolute_gates_passed": absolute_passed,
        "relative_gates_passed": relative_passed,
        "promoted": promoted,
        "metric_deltas": deltas,
        "relative_checks": checks,
        "scale_qlora_authorized": False,
        "scale_blockers": [blocker for blocker in scale_blockers if blocker],
    }
