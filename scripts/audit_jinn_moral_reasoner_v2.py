"""Fail-closed local signal and scheduling gate for the Jinn moral-reasoner lane."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_ROOT = REPO_ROOT / "environments/jinn_beast_metta"
if str(ENV_ROOT) not in sys.path:
    sys.path.insert(0, str(ENV_ROOT))

from jinn_beast_metta.core import score_construct_response

DATA_PATH = (
    ENV_ROOT / "jinn_beast_metta/data/jinn_moral_reasoner_tasks.jsonl"
)
MANIFEST_PATH = (
    ENV_ROOT / "jinn_beast_metta/data/jinn_moral_reasoner_manifest.json"
)
WORLD_ROOT = REPO_ROOT / "jinn_bench/constructs_v2/jinn_moral_reasoner/storyworlds"
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "experiments/jinn_beast_metta_rl_v1/moral_reasoner_v2/"
    "local_signal_gate_20260725.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected a JSON object")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path}: expected non-empty JSONL objects")
    return rows


def _completion(task: dict[str, Any], action_id: str) -> str:
    return json.dumps(
        {
            "decision": action_id,
            "evidence_ids": task["visible_fact_ids"],
            "uncertainty": task["expected_uncertainty"],
            "review_required": task["expected_review_required"],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _validate_worlds(validator: Path) -> dict[str, Any]:
    if not validator.is_file():
        raise FileNotFoundError(f"storyworld validator not found: {validator}")
    worlds = sorted(WORLD_ROOT.rglob("*.json"))
    failures = []
    for world in worlds:
        result = subprocess.run(
            [sys.executable, str(validator), "validate", str(world)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            failures.append(
                {
                    "path": world.relative_to(REPO_ROOT).as_posix(),
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )
    return {
        "validator_path": validator.as_posix(),
        "worlds": len(worlds),
        "failures": failures,
        "passed": len(worlds) == 32 and not failures,
    }


def audit(validator: Path) -> dict[str, Any]:
    tasks = _load_jsonl(DATA_PATH)
    manifest = _load_json(MANIFEST_PATH)
    task_scores = []
    for task in tasks:
        scores = {}
        for action_id in task["action_scores"]:
            scores[action_id] = score_construct_response(
                _completion(task, action_id),
                task,
            )
        best = scores[task["target_action_id"]]
        alternatives = [
            receipt
            for action_id, receipt in scores.items()
            if action_id != task["target_action_id"]
        ]
        critical = [
            receipt for receipt in scores.values() if receipt["critical_violation"]
        ]
        task_scores.append(
            {
                "task_id": task["task_id"],
                "split": task["split"],
                "family_id": task["family_id"],
                "target_action_id": task["target_action_id"],
                "best_final_score": best["final_score"],
                "runner_up_final_score": max(
                    receipt["final_score"] for receipt in alternatives
                ),
                "best_to_runner_up_gap": round(
                    best["final_score"]
                    - max(receipt["final_score"] for receipt in alternatives),
                    6,
                ),
                "critical_action_count": len(critical),
                "maximum_critical_final_score": max(
                    receipt["final_score"] for receipt in critical
                ),
                "minimum_best_to_critical_gap": round(
                    min(
                        best["final_score"] - receipt["final_score"]
                        for receipt in critical
                    ),
                    6,
                ),
            }
        )

    equivalence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    change: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        equivalence[task["equivalence_pair_id"]].append(task)
        change[task["change_pair_id"]].append(task)
    pair_gate = {
        "equivalence_pairs": len(equivalence),
        "equivalence_targets_invariant": all(
            len(rows) == 2
            and len({row["target_action_id"] for row in rows}) == 1
            for rows in equivalence.values()
        ),
        "material_change_families": len(change),
        "material_change_targets_change": all(
            {
                row["target_action_id"]
                for row in rows
                if row["state_role"] == "baseline"
            }
            != {
                row["target_action_id"]
                for row in rows
                if row["state_role"] == "material_change"
            }
            for rows in change.values()
        ),
    }
    world_validation = _validate_worlds(validator)
    split_rows = manifest["split_counts"]
    scheduling = {
        "candidate_tasks": split_rows["candidate_train"],
        "batch_size": 64,
        "rollouts_per_example": 4,
        "max_inflight_rollouts": 4,
        "rollouts_per_complete_task_epoch": (
            split_rows["candidate_train"] * 4
        ),
        "complete_task_epochs_per_batch": (
            64 / (split_rows["candidate_train"] * 4)
        ),
        "exact_batch_balance": (
            split_rows["candidate_train"] * 4 == 64
        ),
    }
    aggregate = {
        "tasks": len(task_scores),
        "mean_target_final_score": round(
            fmean(row["best_final_score"] for row in task_scores),
            6,
        ),
        "minimum_target_final_score": min(
            row["best_final_score"] for row in task_scores
        ),
        "minimum_best_to_runner_up_gap": min(
            row["best_to_runner_up_gap"] for row in task_scores
        ),
        "maximum_critical_final_score": max(
            row["maximum_critical_final_score"] for row in task_scores
        ),
        "minimum_best_to_critical_gap": min(
            row["minimum_best_to_critical_gap"] for row in task_scores
        ),
    }
    gates = {
        "storyworld_validation": world_validation["passed"],
        "task_count": len(tasks) == 32,
        "balanced_splits": split_rows == {
            "candidate_train": 16,
            "development": 16,
        },
        "disjoint_families": manifest["split_family_counts"]
        == {"candidate_train": 4, "development": 4},
        "equivalence_target_invariance": pair_gate[
            "equivalence_targets_invariant"
        ],
        "material_change_target_sensitivity": pair_gate[
            "material_change_targets_change"
        ],
        "action_reward_weight": (
            manifest["reward_profile"]["weights"]["action"] == 0.75
        ),
        "critical_cap": aggregate["maximum_critical_final_score"] <= 0.2,
        "minimum_target_reward": aggregate["minimum_target_final_score"] >= 0.85,
        "minimum_best_to_critical_gap": (
            aggregate["minimum_best_to_critical_gap"] >= 0.65
        ),
        "exact_batch_balance": scheduling["exact_batch_balance"],
        "candidate_release_remains_fail_closed": not manifest[
            "candidate_training_ready"
        ],
        "exact_village_excluded_from_training": (
            manifest["exact_village_rows_used_for_training"] == 0
        ),
    }
    return {
        "schema_version": "jinn_moral_reasoner_local_signal_gate_v2",
        "status": "passed" if all(gates.values()) else "failed",
        "environment_version": manifest["environment_version"],
        "scorer_id": manifest["scorer_id"],
        "gates": gates,
        "aggregate": aggregate,
        "pair_gate": pair_gate,
        "scheduling": scheduling,
        "storyworld_validation": world_validation,
        "task_scores": task_scores,
        "claim_boundary": (
            "Deterministic environment and scheduling evidence only; no model "
            "behavior or training effect is measured by this receipt."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    receipt = audit(args.validator.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if receipt["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
