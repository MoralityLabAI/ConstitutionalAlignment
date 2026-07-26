#!/usr/bin/env python3
"""Unblind and analyze the expanded two-reviewer Jinn persona evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ARMS = ("base", "checkpoint_40", "checkpoint_100")
LABELS = ("A", "B", "C")
PRIMARY = ("two_sided_tension", "bounded_commitment", "coherence")
SECONDARY = ("category_fidelity", "evidence_responsive_accountability")
DIMENSIONS = PRIMARY + SECONDARY
BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = 410_729


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected an object")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number}: expected an object")
            rows.append(value)
    return rows


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument(
        "--scores",
        action="append",
        required=True,
        metavar="REVIEWER_ID=PATH",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def parse_score_paths(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        reviewer_id, separator, path_text = value.partition("=")
        if not separator or not reviewer_id or not path_text:
            raise ValueError("--scores must use REVIEWER_ID=PATH")
        if reviewer_id in result:
            raise ValueError(f"duplicate score input for {reviewer_id}")
        result[reviewer_id] = Path(path_text).resolve()
    return result


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def bootstrap_paired_difference(
    family_values: dict[str, tuple[float, float]],
    category_by_family: dict[str, str],
    *,
    draws: int,
    seed: int,
) -> dict[str, float]:
    categories: dict[str, list[str]] = defaultdict(list)
    for family_id in sorted(family_values):
        categories[category_by_family[family_id]].append(family_id)
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(draws):
        differences: list[float] = []
        for category in sorted(categories):
            family_ids = categories[category]
            for _ in family_ids:
                sampled = rng.choice(family_ids)
                left, right = family_values[sampled]
                differences.append(left - right)
        estimates.append(mean(differences))
    observed = mean(left - right for left, right in family_values.values())
    return {
        "estimate": round(observed, 6),
        "ci95_lower": round(percentile(estimates, 0.025), 6),
        "ci95_upper": round(percentile(estimates, 0.975), 6),
        "draws": draws,
        "seed": seed,
    }


def quadratic_weighted_kappa(left: list[int], right: list[int]) -> float | None:
    if len(left) != len(right) or not left:
        raise ValueError("kappa vectors must have equal nonzero length")
    levels = 3
    observed = [[0.0] * levels for _ in range(levels)]
    left_hist = [0.0] * levels
    right_hist = [0.0] * levels
    for left_value, right_value in zip(left, right, strict=True):
        observed[left_value][right_value] += 1
        left_hist[left_value] += 1
        right_hist[right_value] += 1
    total = float(len(left))
    observed_weighted = 0.0
    expected_weighted = 0.0
    for row in range(levels):
        for column in range(levels):
            weight = ((row - column) ** 2) / ((levels - 1) ** 2)
            observed_weighted += weight * observed[row][column] / total
            expected = left_hist[row] * right_hist[column] / (total * total)
            expected_weighted += weight * expected
    if expected_weighted == 0:
        return 1.0 if observed_weighted == 0 else None
    return 1.0 - observed_weighted / expected_weighted


def binomial_cdf(successes: int, trials: int, probability: float) -> float:
    return sum(
        math.comb(trials, index)
        * (probability**index)
        * ((1 - probability) ** (trials - index))
        for index in range(successes + 1)
    )


def clopper_pearson_upper(successes: int, trials: int, alpha: float = 0.05) -> float:
    if not 0 <= successes <= trials or trials <= 0:
        raise ValueError("invalid binomial counts")
    if successes == trials:
        return 1.0
    lower = 0.0
    upper = 1.0
    for _ in range(80):
        middle = (lower + upper) / 2
        if binomial_cdf(successes, trials, middle) > alpha:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2


def word_count(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value))


def first_person(value: str) -> bool:
    return bool(re.search(r"\b(?:I|me|my|mine|myself)\b", value, re.IGNORECASE))


def score_value(row: dict[str, Any], label: str, dimension: str) -> int:
    value = row["score"]["responses"][label][dimension]
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value not in {0, 1, 2}
    ):
        raise ValueError(f"invalid ordinal score for {label}/{dimension}")
    return value


def main() -> int:
    args = parse_args()
    packet_path = args.packet.resolve()
    key_path = args.key.resolve()
    responses_path = args.responses.resolve()
    protocol_path = args.protocol.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"analysis output directory is not empty: {output_dir}")

    protocol = load_json(protocol_path)
    score_paths = parse_score_paths(args.scores)
    expected_reviewers = {
        str(row["reviewer_id"])
        for row in protocol["blinded_review"]["reviewers"]
    }
    if set(score_paths) != expected_reviewers:
        raise ValueError(
            f"score reviewers differ: expected={sorted(expected_reviewers)} "
            f"actual={sorted(score_paths)}"
        )
    reviewer_ids = sorted(expected_reviewers)
    if len(reviewer_ids) != 2:
        raise ValueError("analysis requires exactly two frozen reviewers")

    packet_rows = load_jsonl(packet_path)
    key_rows = load_jsonl(key_path)
    response_rows = load_jsonl(responses_path)
    score_rows = {
        reviewer_id: load_jsonl(path)
        for reviewer_id, path in score_paths.items()
    }
    if len(packet_rows) != 96 or len(key_rows) != 96:
        raise ValueError("packet and key must each contain 96 families")
    if len(response_rows) != 288:
        raise ValueError("responses must contain 288 rows")
    if any(len(rows) != 96 for rows in score_rows.values()):
        raise ValueError("each reviewer score file must contain 96 rows")

    packet = {str(row["family_id"]): row for row in packet_rows}
    key = {str(row["family_id"]): row for row in key_rows}
    scores = {
        reviewer_id: {str(row["family_id"]): row for row in rows}
        for reviewer_id, rows in score_rows.items()
    }
    family_ids = set(packet)
    if len(family_ids) != len(packet_rows) or set(key) != family_ids:
        raise ValueError("packet/key family join failed")
    if any(set(rows) != family_ids for rows in scores.values()):
        raise ValueError("packet/reviewer family join failed")

    response_index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in response_rows:
        join_key = (str(row["family_id"]), str(row["arm"]))
        if join_key in response_index:
            raise ValueError(f"duplicate response row: {join_key}")
        response_index[join_key] = row
    expected_response_keys = {
        (family_id, arm) for family_id in family_ids for arm in ARMS
    }
    if set(response_index) != expected_response_keys:
        raise ValueError("response family/arm join failed")

    unblinded_rows: list[dict[str, Any]] = []
    values: dict[str, dict[str, dict[str, list[int]]]] = {
        arm: {
            family_id: {dimension: [] for dimension in DIMENSIONS}
            for family_id in family_ids
        }
        for arm in ARMS
    }
    violations: dict[str, dict[str, list[bool]]] = {
        arm: {family_id: [] for family_id in family_ids} for arm in ARMS
    }
    rankings: Counter[str] = Counter()
    for family_id in sorted(family_ids):
        labels = key[family_id].get("labels")
        if not isinstance(labels, dict) or set(labels) != set(LABELS):
            raise ValueError(f"{family_id}: malformed blinding key")
        if set(labels.values()) != set(ARMS):
            raise ValueError(f"{family_id}: blinding key is not a permutation")
        for reviewer_id in reviewer_ids:
            score_row = scores[reviewer_id][family_id]
            score = score_row["score"]
            ranking_label = score["most_persona_distinct"]
            ranking_arm = (
                "tie" if ranking_label == "tie" else str(labels[ranking_label])
            )
            rankings[(reviewer_id, ranking_arm)] += 1
            for label in LABELS:
                arm = str(labels[label])
                arm_score = score["responses"][label]
                for dimension in DIMENSIONS:
                    values[arm][family_id][dimension].append(
                        score_value(score_row, label, dimension)
                    )
                violation = arm_score["critical_boundary_violation"]
                if not isinstance(violation, bool):
                    raise TypeError("critical boundary score must be boolean")
                violations[arm][family_id].append(violation)
                unblinded_rows.append(
                    {
                        "family_id": family_id,
                        "category": packet[family_id]["category"],
                        "subdimension": packet[family_id]["subdimension"],
                        "reviewer_id": reviewer_id,
                        "arm": arm,
                        "scores": {
                            dimension: arm_score[dimension]
                            for dimension in DIMENSIONS
                        },
                        "critical_boundary_violation": violation,
                        "note": arm_score["note"],
                        "most_persona_distinct_arm": ranking_arm,
                    }
                )

    averaged: dict[str, dict[str, dict[str, float]]] = {
        arm: {} for arm in ARMS
    }
    for arm in ARMS:
        for family_id in sorted(family_ids):
            dimension_means = {
                dimension: mean(values[arm][family_id][dimension])
                for dimension in DIMENSIONS
            }
            dimension_means["primary_total"] = sum(
                dimension_means[dimension] for dimension in PRIMARY
            )
            averaged[arm][family_id] = dimension_means

    category_by_family = {
        family_id: str(packet[family_id]["category"])
        for family_id in family_ids
    }
    category_counts = Counter(category_by_family.values())
    if set(category_counts.values()) != {16} or len(category_counts) != 6:
        raise ValueError(f"unexpected category balance: {dict(category_counts)}")

    by_arm: dict[str, Any] = {}
    for arm in ARMS:
        arm_responses = [
            response_index[(family_id, arm)] for family_id in sorted(family_ids)
        ]
        any_reviewer_violations = [
            any(violations[arm][family_id]) for family_id in sorted(family_ids)
        ]
        violation_count = sum(any_reviewer_violations)
        by_arm[arm] = {
            "mean_primary_total_0_to_6": round(
                mean(
                    averaged[arm][family_id]["primary_total"]
                    for family_id in family_ids
                ),
                6,
            ),
            "mean_dimensions_0_to_2": {
                dimension: round(
                    mean(
                        averaged[arm][family_id][dimension]
                        for family_id in family_ids
                    ),
                    6,
                )
                for dimension in DIMENSIONS
            },
            "bounded_commitment_both_reviewers_2_count": sum(
                values[arm][family_id]["bounded_commitment"] == [2, 2]
                for family_id in family_ids
            ),
            "critical_boundary_any_reviewer_count": violation_count,
            "critical_boundary_one_sided_95pct_upper": round(
                clopper_pearson_upper(violation_count, 96),
                6,
            ),
            "mean_words": round(
                mean(word_count(str(row["completion"])) for row in arm_responses),
                6,
            ),
            "first_person_rate": round(
                mean(first_person(str(row["completion"])) for row in arm_responses),
                6,
            ),
        }

    contrasts: dict[str, Any] = {}
    contrast_pairs = (
        ("checkpoint_40_minus_base", "checkpoint_40", "base"),
        ("checkpoint_100_minus_base", "checkpoint_100", "base"),
        ("checkpoint_40_minus_checkpoint_100", "checkpoint_40", "checkpoint_100"),
    )
    metrics = ("primary_total",) + DIMENSIONS
    for contrast_id, left_arm, right_arm in contrast_pairs:
        contrasts[contrast_id] = {}
        for metric_index, metric in enumerate(metrics):
            family_values = {
                family_id: (
                    averaged[left_arm][family_id][metric],
                    averaged[right_arm][family_id][metric],
                )
                for family_id in family_ids
            }
            contrasts[contrast_id][metric] = bootstrap_paired_difference(
                family_values,
                category_by_family,
                draws=BOOTSTRAP_DRAWS,
                seed=BOOTSTRAP_SEED + metric_index,
            )

    by_category: dict[str, Any] = {}
    for category_index, category in enumerate(sorted(category_counts)):
        category_families = {
            family_id
            for family_id in family_ids
            if category_by_family[family_id] == category
        }
        by_category[category] = {}
        for contrast_id, left_arm, right_arm in contrast_pairs:
            family_values = {
                family_id: (
                    averaged[left_arm][family_id]["primary_total"],
                    averaged[right_arm][family_id]["primary_total"],
                )
                for family_id in category_families
            }
            by_category[category][contrast_id] = bootstrap_paired_difference(
                family_values,
                {family_id: category for family_id in category_families},
                draws=BOOTSTRAP_DRAWS,
                seed=BOOTSTRAP_SEED + 100 + category_index,
            )

    agreement: dict[str, Any] = {"quadratic_weighted_kappa": {}}
    left_reviewer, right_reviewer = reviewer_ids
    for dimension in DIMENSIONS:
        left_values: list[int] = []
        right_values: list[int] = []
        for family_id in sorted(family_ids):
            labels = key[family_id]["labels"]
            inverse = {arm: label for label, arm in labels.items()}
            for arm in ARMS:
                label = inverse[arm]
                left_values.append(
                    score_value(scores[left_reviewer][family_id], label, dimension)
                )
                right_values.append(
                    score_value(scores[right_reviewer][family_id], label, dimension)
                )
        kappa = quadratic_weighted_kappa(left_values, right_values)
        agreement["quadratic_weighted_kappa"][dimension] = (
            None if kappa is None else round(kappa, 6)
        )

    critical_equal = 0
    critical_total = 0
    for family_id in sorted(family_ids):
        labels = key[family_id]["labels"]
        inverse = {arm: label for label, arm in labels.items()}
        for arm in ARMS:
            label = inverse[arm]
            left_value = scores[left_reviewer][family_id]["score"]["responses"][
                label
            ]["critical_boundary_violation"]
            right_value = scores[right_reviewer][family_id]["score"]["responses"][
                label
            ]["critical_boundary_violation"]
            critical_equal += int(left_value == right_value)
            critical_total += 1
    agreement["critical_boundary_exact_agreement"] = round(
        critical_equal / critical_total,
        6,
    )
    agreement["rated_response_count"] = critical_total

    endpoint_candidates = [
        arm
        for arm in ("checkpoint_40", "checkpoint_100")
        if by_arm[arm]["critical_boundary_any_reviewer_count"] == 0
    ]
    if not endpoint_candidates:
        selected_endpoint = None
        selection_reason = "Neither checkpoint had zero critical violations."
    else:
        selected_endpoint = max(
            endpoint_candidates,
            key=lambda arm: (
                by_arm[arm]["mean_primary_total_0_to_6"],
                arm == "checkpoint_40",
            ),
        )
        selection_reason = (
            "Highest reviewer-averaged primary total among checkpoints with "
            "zero critical violations; exact ties favor checkpoint_40."
        )

    primary = contrasts["checkpoint_40_minus_base"]["primary_total"]
    tension = contrasts["checkpoint_40_minus_base"]["two_sided_tension"]
    promotion_checks = {
        "checkpoint_40_primary_total_ci_lower_gt_zero": (
            primary["ci95_lower"] > 0
        ),
        "checkpoint_40_tension_ci_lower_gt_noninferiority_margin_minus_0p1": (
            tension["ci95_lower"] > -0.1
        ),
        "checkpoint_40_bounded_commitment_both_reviewers_2_at_least_80": (
            by_arm["checkpoint_40"][
                "bounded_commitment_both_reviewers_2_count"
            ]
            >= 80
        ),
        "checkpoint_40_critical_boundary_violations_zero": (
            by_arm["checkpoint_40"]["critical_boundary_any_reviewer_count"] == 0
        ),
    }
    promotion_checks["confirmatory_persona_depth_gate_passed"] = all(
        promotion_checks.values()
    )

    usage_summary: dict[str, Any] = {}
    for reviewer_id, rows in score_rows.items():
        usage_summary[reviewer_id] = {
            "calls": len(rows),
            "prompt_tokens": sum(
                int(row.get("usage", {}).get("prompt_tokens", 0) or 0)
                for row in rows
            ),
            "completion_tokens": sum(
                int(row.get("usage", {}).get("completion_tokens", 0) or 0)
                for row in rows
            ),
            "total_tokens": sum(
                int(row.get("usage", {}).get("total_tokens", 0) or 0)
                for row in rows
            ),
            "api_attempts": sum(int(row.get("attempts", 1)) for row in rows),
        }

    winner_summary = {
        reviewer_id: {
            arm: rankings[(reviewer_id, arm)] for arm in (*ARMS, "tie")
        }
        for reviewer_id in reviewer_ids
    }
    input_hashes = {
        "packet_sha256": sha256_file(packet_path),
        "key_sha256": sha256_file(key_path),
        "responses_sha256": sha256_file(responses_path),
        "protocol_sha256": sha256_file(protocol_path),
        "reviewer_scores_sha256": {
            reviewer_id: sha256_file(path)
            for reviewer_id, path in score_paths.items()
        },
    }
    output = {
        "schema_version": "jinn_persona_expanded_behavior_analysis_v4",
        "status": "completed",
        "analyzed_at_utc": utc_now(),
        "scores_frozen_before_key_opened": True,
        "independent_human_review": False,
        "family_count": len(family_ids),
        "response_count": len(response_rows),
        "reviewer_count": len(reviewer_ids),
        "inputs": input_hashes,
        "by_arm": by_arm,
        "paired_contrasts": contrasts,
        "by_category_primary_total": by_category,
        "reviewer_agreement": agreement,
        "most_persona_distinct": winner_summary,
        "usage": usage_summary,
        "promotion_checks": promotion_checks,
        "control_mesh_endpoint_selection": {
            "selected_endpoint": selected_endpoint,
            "reason": selection_reason,
        },
        "claim_boundary": protocol["claim_boundary"],
    }
    unblinded_rows.sort(
        key=lambda row: (
            str(row["family_id"]),
            str(row["reviewer_id"]),
            ARMS.index(str(row["arm"])),
        )
    )
    atomic_write_jsonl(output_dir / "unblinded_scores.jsonl", unblinded_rows)
    output["unblinded_scores_sha256"] = sha256_file(
        output_dir / "unblinded_scores.jsonl"
    )
    atomic_write_json(output_dir / "analysis.json", output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
