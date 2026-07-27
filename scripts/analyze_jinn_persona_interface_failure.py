#!/usr/bin/env python3
"""Diagnose first-turn tool-interface failures without counterfactual rollout replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

from scripts.analyze_jinn_persona_control_mesh_2x2 import (
    CELLS,
    bootstrap_samples,
    contrast_ci,
    load_jsonl,
    validate_surface,
)
from scripts.pod.run_jinn_persona_control_mesh_cell import (
    dispatch,
    load_frozen_controller_class,
    parse_tool_call,
)

OPEN_TOOL_FRAGMENT_RE = re.compile(r"\A<tool_call>\s*(\{.*\})\s*\Z", re.S)
ARGUMENT_SIGNATURES = {
    frozenset({"action_id", "evidence_ids"}): "inspect_action",
    frozenset({"action_ids", "objective_id"}): "prune_actions",
    frozenset(
        {
            "action_id",
            "evidence_ids",
            "update_basis",
            "uncertainty",
            "review_required",
        }
    ): "commit_decision",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recover_first_call(
    raw: str,
) -> tuple[str, dict[str, Any], str] | None:
    """Recover only an exact unterminated tool fragment with a known signature."""
    try:
        tool, arguments, normalization = parse_tool_call(raw)
        return tool, arguments, f"strict:{normalization}"
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    match = OPEN_TOOL_FRAGMENT_RE.fullmatch(raw.strip())
    if not match:
        return None
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    if set(value) == {"tool", "arguments"}:
        try:
            tool, arguments, _ = parse_tool_call(
                json.dumps(value, separators=(",", ":"))
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        return tool, arguments, "missing_closing_tag_only"
    tool = ARGUMENT_SIGNATURES.get(frozenset(value))
    if tool is None:
        return None
    return tool, value, "missing_tool_envelope_and_closing_tag"


def rate(count: int, denominator: int) -> float:
    return count / denominator if denominator else 0.0


def diagnose_cell(
    rows: list[dict[str, Any]],
    *,
    tasks: dict[str, dict[str, Any]],
    weight: str,
    frame: str,
    controller_class: type[Any],
) -> dict[str, Any]:
    validate_surface(rows, weight=weight, frame=frame)
    counts: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    unique_outputs: list[int] = []
    commit_count = 0
    commit_target_count = 0
    commit_safe_count = 0
    commit_critical_count = 0
    for row in rows:
        task_id = str(row["info"]["task_id"])
        task = tasks[task_id]
        turns = row.get("turns")
        if not isinstance(turns, list) or not turns:
            raise ValueError(f"{task_id}: missing turns")
        raw_outputs = [str(turn["raw_assistant"]) for turn in turns]
        unique_outputs.append(len(set(raw_outputs)))
        if len(set(raw_outputs)) == 1:
            counts["identical_all_turns"] += 1
        raw = raw_outputs[0]
        try:
            parse_tool_call(raw)
            counts["strict_protocol"] += 1
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        recovered = recover_first_call(raw)
        if recovered is None:
            counts["unrecoverable"] += 1
            continue
        tool, arguments, mode = recovered
        modes[mode] += 1
        tools[tool] += 1
        if mode != "strict:raw_json" and not mode.startswith("strict:"):
            counts["shim_required"] += 1
        result = dispatch(controller_class(task), tool, arguments)
        if bool(result.get("accepted")):
            counts["executable_after_shim"] += 1
        action_id = arguments.get("action_id")
        if isinstance(action_id, str):
            counts["action_id_present"] += 1
            if action_id in task["action_scores"]:
                counts["action_id_valid"] += 1
            evidence_ids = arguments.get("evidence_ids")
            if isinstance(evidence_ids, list) and set(evidence_ids) <= set(
                task["visible_fact_ids"]
            ):
                counts["evidence_ids_visible"] += 1
        if tool == "commit_decision" and isinstance(action_id, str):
            commit_count += 1
            commit_target_count += int(action_id == task["target_action_id"])
            commit_safe_count += int(action_id in task["safe_action_ids"])
            commit_critical_count += int(action_id == task["critical_action_id"])
    total = len(rows)
    return {
        "rollouts": total,
        "strict_first_turn_protocol_rate": rate(counts["strict_protocol"], total),
        "first_turn_shim_required_rate": rate(counts["shim_required"], total),
        "first_turn_unrecoverable_rate": rate(counts["unrecoverable"], total),
        "first_turn_executable_after_shim_rate": rate(
            counts["executable_after_shim"], total
        ),
        "first_turn_action_id_present_rate": rate(
            counts["action_id_present"], total
        ),
        "first_turn_action_id_valid_rate": rate(counts["action_id_valid"], total),
        "first_turn_evidence_ids_visible_rate": rate(
            counts["evidence_ids_visible"], total
        ),
        "identical_output_on_every_turn_rate": rate(
            counts["identical_all_turns"], total
        ),
        "mean_unique_outputs_per_rollout": fmean(unique_outputs),
        "recovery_mode_counts": dict(sorted(modes.items())),
        "inferred_tool_counts": dict(sorted(tools.items())),
        "commit_candidates": {
            "count": commit_count,
            "target_rate_given_commit": rate(commit_target_count, commit_count),
            "safe_rate_given_commit": rate(commit_safe_count, commit_count),
            "critical_rate_given_commit": rate(commit_critical_count, commit_count),
        },
    }


def exploratory_family_contrasts(
    surfaces: dict[tuple[str, str], list[dict[str, Any]]],
    *,
    tasks: dict[str, dict[str, Any]],
    controller_class: type[Any],
) -> dict[str, Any]:
    metrics = (
        "strict_first_turn_protocol",
        "recognized_first_turn_call",
        "executable_first_turn_after_shim",
    )
    family_values: dict[
        str, dict[tuple[str, str], dict[str, float]]
    ] = {metric_id: {} for metric_id in metrics}
    for cell, rows in surfaces.items():
        grouped: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for row in rows:
            task = tasks[str(row["info"]["task_id"])]
            raw = str(row["turns"][0]["raw_assistant"])
            try:
                parse_tool_call(raw)
                strict = 1.0
            except (json.JSONDecodeError, TypeError, ValueError):
                strict = 0.0
            recovered = recover_first_call(raw)
            recognized = float(recovered is not None)
            executable = 0.0
            if recovered is not None:
                tool, arguments, _ = recovered
                result = dispatch(controller_class(task), tool, arguments)
                executable = float(bool(result.get("accepted")))
            family_id = str(row["info"]["family_id"])
            grouped[family_id]["strict_first_turn_protocol"].append(strict)
            grouped[family_id]["recognized_first_turn_call"].append(recognized)
            grouped[family_id]["executable_first_turn_after_shim"].append(
                executable
            )
        for metric_id in metrics:
            family_values[metric_id][cell] = {
                family_id: fmean(values[metric_id])
                for family_id, values in grouped.items()
            }
    family_ids = sorted(
        family_values["strict_first_turn_protocol"][("base", "jinn")]
    )
    samples = bootstrap_samples(family_ids)
    terms = {
        "membrane_effect_under_base": {
            ("base", "jinn"): 1.0,
            ("base", "beast"): -1.0,
        },
        "membrane_effect_under_adapter": {
            ("checkpoint_100", "jinn"): 1.0,
            ("checkpoint_100", "beast"): -1.0,
        },
        "adapter_effect_under_jinn": {
            ("checkpoint_100", "jinn"): 1.0,
            ("base", "jinn"): -1.0,
        },
        "adapter_effect_under_beast": {
            ("checkpoint_100", "beast"): 1.0,
            ("base", "beast"): -1.0,
        },
        "interaction": {
            ("checkpoint_100", "jinn"): 1.0,
            ("checkpoint_100", "beast"): -1.0,
            ("base", "jinn"): -1.0,
            ("base", "beast"): 1.0,
        },
    }
    return {
        metric_id: {
            contrast_id: contrast_ci(
                family_values[metric_id],
                samples,
                coefficients,
            )
            for contrast_id, coefficients in terms.items()
        }
        for metric_id in metrics
    }


def diagnose(
    surfaces: dict[tuple[str, str], list[dict[str, Any]]],
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    task_map = {str(task["task_id"]): task for task in tasks}
    if len(task_map) != 288:
        raise ValueError("expected 288 unique frozen tasks")
    controller_class = load_frozen_controller_class()
    surfaces_summary = {
        f"{weight}_{frame}": diagnose_cell(
            surfaces[(weight, frame)],
            tasks=task_map,
            weight=weight,
            frame=frame,
            controller_class=controller_class,
        )
        for weight, frame in CELLS
    }
    return {
        "schema_version": "jinn_persona_interface_failure_diagnostic_v1",
        "status": "completed_post_hoc",
        "surfaces": surfaces_summary,
        "exploratory_family_bootstrap_contrasts": exploratory_family_contrasts(
            surfaces,
            tasks=task_map,
            controller_class=controller_class,
        ),
        "interpretation_boundary": (
            "The shim diagnoses first-turn serialization recoverability only. "
            "Later recorded turns were conditioned on strict-parser rejection, "
            "so they are not replayed as counterfactual accepted trajectories. "
            "This diagnostic does not rescue the confirmatory outcome."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for weight, frame in CELLS:
        parser.add_argument(
            f"--{weight.replace('_', '-')}-{frame}",
            dest=f"{weight}_{frame}",
            type=Path,
            required=True,
        )
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        (weight, frame): getattr(args, f"{weight}_{frame}").resolve()
        for weight, frame in CELLS
    }
    tasks_path = args.tasks.resolve()
    result = diagnose(
        {cell: load_jsonl(path) for cell, path in paths.items()},
        load_jsonl(tasks_path),
    )
    result["inputs"] = {
        **{
            f"{weight}_{frame}": {
                "path": path.as_posix(),
                "sha256": sha256_file(path),
            }
            for (weight, frame), path in paths.items()
        },
        "tasks": {
            "path": tasks_path.as_posix(),
            "sha256": sha256_file(tasks_path),
        },
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                name: {
                    "strict_first_turn_protocol_rate": surface[
                        "strict_first_turn_protocol_rate"
                    ],
                    "first_turn_executable_after_shim_rate": surface[
                        "first_turn_executable_after_shim_rate"
                    ],
                    "first_turn_unrecoverable_rate": surface[
                        "first_turn_unrecoverable_rate"
                    ],
                }
                for name, surface in result["surfaces"].items()
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
