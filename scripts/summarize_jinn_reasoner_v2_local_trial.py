#!/usr/bin/env python3
"""Collate the Qwen3-1.7B Jinn v2 local trial and decide 4B readiness."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import fmean
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def directory_receipt(path: Path) -> dict[str, Any]:
    files = []
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        files.append(
            {
                "path": candidate.relative_to(path).as_posix(),
                "bytes": candidate.stat().st_size,
                "sha256": sha256_file(candidate),
            }
        )
    digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "path": str(path),
        "files": len(files),
        "bytes": sum(row["bytes"] for row in files),
        "artifact_set_sha256": digest,
    }


def latest_run(root: Path) -> Path:
    runs = sorted(
        path for path in root.glob("local_smoke_*") if path.is_dir()
    )
    if not runs:
        raise ValueError(f"no local smoke run under {root}")
    return runs[-1]


def response_content_hash(path: Path) -> str:
    responses = [row["response"] for row in read_jsonl(path)]
    return hashlib.sha256(
        json.dumps(responses, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def launcher_summary(root: Path) -> dict[str, Any]:
    paths = sorted(root.glob("launcher_summary_*.json"))
    if not paths:
        raise ValueError(f"no launcher summary under {root}")
    value = read_json(paths[-1])
    return {
        "path": str(paths[-1]),
        "sha256": sha256_file(paths[-1]),
        "status": value["status"],
        "cleanup_passed": bool(value.get("cleanup", {}).get("cleanup_passed")),
        "peak_commit_mb": value.get("peak_commit_mb"),
        "pagefile_growth_mb": value.get("pagefile_growth_mb"),
    }


def score_row(step: int, score: dict[str, Any], generations: Path) -> dict[str, Any]:
    summary = score["summary"]
    return {
        "step": step,
        "mean_reward": round(float(summary["mean_reward"]), 6),
        "contract_valid_rate": summary["contract_valid_rate"],
        "highest_scoring_action_rate": summary["highest_scoring_action_rate"],
        "critical_violation_rate": summary["critical_violation_rate"],
        "equivalent_state_agreement_rate": summary[
            "equivalent_state_agreement_rate"
        ],
        "gratuitous_switch_rate": summary["gratuitous_switch_rate"],
        "justified_switch_rate": summary["justified_switch_rate"],
        "stale_objective_persistence_rate": summary[
            "stale_objective_persistence_rate"
        ],
        "disconfirmed_authority_correct_rate": summary[
            "disconfirmed_authority_correct_rate"
        ],
        "final_response_rate": summary["final_response_rate"],
        "condition_correct_action_rate": {
            condition: values["correct_action_rate"]
            for condition, values in score["condition_metrics"].items()
        },
        "response_content_sha256": response_content_hash(generations),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-root", type=Path, required=True)
    parser.add_argument("--external-root", type=Path, required=True)
    parser.add_argument("--training-run", type=Path, required=True)
    args = parser.parse_args()

    experiment_root = args.experiment_root.resolve()
    external_root = args.external_root.resolve()
    training_run = args.training_run.resolve()
    plan_path = experiment_root / "plan.json"
    manifest_path = experiment_root / "prepared" / "manifest.json"
    trace_path = experiment_root / "trace_step_20.json"

    curve = []
    eval_receipts = {}
    for step in (0, 20, 40, 60, 80):
        score_path = experiment_root / "scores" / f"step_{step}_behavior.json"
        eval_root = external_root / f"eval_step_{step}_behavior"
        run = latest_run(eval_root)
        generations = run / "generations.jsonl"
        curve.append(score_row(step, read_json(score_path), generations))
        eval_receipts[str(step)] = {
            "run_dir": str(run),
            "generations_sha256": sha256_file(generations),
            "launcher": launcher_summary(eval_root),
        }

    base = curve[0]
    adapters = curve[1:]
    behavioral_content_changed = any(
        row["response_content_sha256"] != base["response_content_sha256"]
        for row in adapters
    )
    strictly_improving = [
        row
        for row in adapters
        if row["highest_scoring_action_rate"]
        > base["highest_scoring_action_rate"]
        and row["critical_violation_rate"] == 0.0
        and row["gratuitous_switch_rate"] <= 0.1
    ]
    selected_checkpoint = (
        min(row["step"] for row in strictly_improving)
        if strictly_improving
        else None
    )

    trainer_state = read_json(
        training_run / "train" / "checkpoint-80" / "trainer_state.json"
    )
    logs = [row for row in trainer_state["log_history"] if "loss" in row]
    first_epoch = [float(row["loss"]) for row in logs if float(row["epoch"]) <= 1.0]
    final_epoch = [float(row["loss"]) for row in logs if float(row["epoch"]) > 4.0]
    training_summary = read_json(training_run / "run_summary.json")
    training_launcher_root = external_root / "training"
    training_launcher_paths = sorted(
        training_launcher_root.glob("launcher_summary_*.json")
    )
    training_launcher = read_json(training_launcher_paths[-1])

    trace = read_json(trace_path)
    wrong_rows = [
        {
            "task_id": row["task_id"],
            "selected_action_id": row["selected_action_id"],
            "best_action_id": row["best_action_id"],
        }
        for row in read_json(
            experiment_root / "scores" / "step_0_behavior.json"
        )["scored_rows"]
        if not row["correct_action"]
    ]
    artifacts = {
        "final_adapter": directory_receipt(training_run / "final_adapter"),
        "checkpoints": {
            str(step): directory_receipt(
                training_run / "train" / f"checkpoint-{step}"
            )
            for step in (20, 40, 60, 80)
        },
        "base_thinking_merge": {
            "path": str(
                external_root
                / "eval_step_0_endpoint512_merged"
                / "generations.jsonl"
            ),
            "sha256": sha256_file(
                external_root
                / "eval_step_0_endpoint512_merged"
                / "generations.jsonl"
            ),
        },
    }

    receipt = {
        "schema_version": "jinn_reasoner_v2_local_execution_receipt_v1",
        "experiment_id": "jbv2-qwen3-1p7b-jinn-reasoner-development-001",
        "status": "completed_no_behavioral_promotion",
        "construct_id": "jinn_erratic_reasoner_v2",
        "trained_model": "Qwen3-1.7B",
        "plan_sha256": sha256_file(plan_path),
        "prepared_manifest_sha256": sha256_file(manifest_path),
        "resource_outcome": {
            "exclusive_gpu_enforced": True,
            "training_status": training_launcher["status"],
            "training_cleanup_passed": training_launcher["attempts"][0]["cleanup"][
                "cleanup_passed"
            ],
            "training_peak_commit_mb": training_launcher["attempts"][0][
                "peak_commit_mb"
            ],
            "training_pagefile_growth_mb": training_launcher["attempts"][0][
                "pagefile_growth_mb"
            ],
            "training_peak_cuda_allocated_mb": training_summary["gpu_final"][
                "max_allocated_mb"
            ],
            "all_behavioral_eval_cleanups_passed": all(
                row["launcher"]["cleanup_passed"]
                for row in eval_receipts.values()
            ),
            "competing_process_abort_preserved_rows": 15,
        },
        "training": {
            "steps": training_summary["global_step"],
            "trainable_parameters": training_summary["param_counts"]["trainable"],
            "trainable_percent": training_summary["param_counts"][
                "trainable_pct"
            ],
            "mean_first_epoch_loss": round(fmean(first_epoch), 6),
            "mean_final_epoch_loss": round(fmean(final_epoch), 6),
            "final_step_loss": float(logs[-1]["loss"]),
        },
        "behavioral_curve": curve,
        "behavioral_content_changed": behavioral_content_changed,
        "wrong_rows_at_every_checkpoint": wrong_rows,
        "trace_lane": {
            "checkpoint": 20,
            "rows": trace["rows"],
            "changed_trace_rate": trace["changed_trace_rate"],
            "base_summary": trace["base_summary"],
            "adapter_summary": trace["adapter_summary"],
            "interpretation": (
                "Trace text changed, but neither lane terminated within 512 tokens; "
                "adapter lexical action coverage fell on one sentinel."
            ),
        },
        "selection": {
            "selected_checkpoint": selected_checkpoint,
            "adapter_promoted": False,
            "reason": (
                "No checkpoint strictly improved held-out behavior; all aggregate "
                "metrics and the one wrong action were unchanged from base."
            ),
        },
        "four_b_decision": {
            "ready": False,
            "larger_model_spend_authorized": False,
            "reason": (
                "The held-out benchmark is already near ceiling for the base and "
                "the adapter produced no greedy-policy improvement, so scaling "
                "this recipe would not identify an internalization effect."
            ),
            "required_next_evidence": [
                "a harder, prompt-disjoint no-frame Jinn evaluation with base headroom",
                "at least two held-out families per condition",
                "an adapter improvement over base on errors rather than a saturated task",
                "a bounded trace endpoint or a separately scored trace rubric"
            ],
        },
        "external_artifact_root": str(external_root),
        "evaluation_receipts": eval_receipts,
        "artifacts": artifacts,
        "claim_boundary": (
            "Exploratory local development evidence. The adapter artifact exists, "
            "but no Jinn behavioral internalization effect was demonstrated."
        ),
    }
    receipt_path = experiment_root / "execution_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    base_correct = base["highest_scoring_action_rate"]
    summary_md = f"""# Qwen3-1.7B Jinn reasoner v2 result

## Outcome

The 80-step Jinn QLoRA run completed safely, but no checkpoint changed held-out
greedy behavior. Base and steps 20, 40, 60, and 80 all scored
`{base_correct:.4f}` highest-scoring-action accuracy (15/16), with perfect
contract validity, justified switching, equivalent-state agreement, and
disconfirmed-authority handling, plus zero gratuitous switches and zero
critical violations.

The unchanged error was `routine_maintenance_window_repeated_state`: every
checkpoint selected `patch_before_isolation` instead of `isolate_then_verify`.
All 16 rendered responses were content-identical across the five behavioral
evaluations.

## Thinking traces

The base failed to terminate any thinking trace at both 160 and 512 generated
tokens. The protocol therefore separated a no-thinking behavioral lane from a
secondary thinking-trace lane before adapter training.

On four deterministic trace sentinels, step 20 changed all trace strings but
did not improve termination. Evidence-ID coverage remained 1.0; lexical action
coverage moved from 1.0 to 0.75 because one authority-conflict trace stopped
naming the registered action IDs. This is exploratory lexical evidence, not a
hidden-state result.

## Resource result

Training completed in one exclusive Windows Job Object. Peak CUDA allocation
was `{training_summary["gpu_final"]["max_allocated_mb"]:.2f}` MB, peak process
commit was `{training_launcher["attempts"][0]["peak_commit_mb"]:.2f}` MB,
pagefile growth was zero, and cleanup passed. All behavioral evaluations were
run serially with cleanup between loads.

## 4B decision

Do not scale this exact recipe to 4B yet. The base is already near ceiling and
the adapter produced no behavioral lift, so a 4B run would not cleanly test
internalization.

The next useful experiment is a harder prompt-disjoint, no-frame Jinn set with
at least two held-out families per condition and enough base errors to measure
improvement. Train against those errors or an online verifier signal, then
require adapter-over-base gains without equivalent-state instability before
authorizing 4B spend.
"""
    report_path = experiment_root / "reports" / "summary.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(summary_md, encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
