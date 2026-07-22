#!/usr/bin/env python3
"""Validate pre-spend gates F01-F05 for the constitutional 200M HRM lane."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitutional_metta import (  # noqa: E402
    HrmArchitecture,
    audit_hrm_architecture,
    compile_constitution_to_metta,
    render_prompt_bundle,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def curriculum_audit(path: Path, expected_target_slots: int) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    slices = payload["train_slices"]
    example_sum = sum(int(item["examples"]) for item in slices)
    share_sum = sum(float(item["share"]) for item in slices)
    train_families = {str(item["id"]) for item in slices}
    heldout = {str(item) for item in payload["heldout_structural_families"]}
    checks = {
        "example_sum_matches": example_sum == int(payload["train_base_examples"]),
        "share_sum_is_one": abs(share_sum - 1.0) < 1e-9,
        "families_are_disjoint": train_families.isdisjoint(heldout),
        "split_before_augmentation": bool(
            payload["augmentation"]["group_split_before_augmentation"]
        ),
        "target_slot_count_matches": int(payload["supervised_target_slot_count"])
        == expected_target_slots,
        "has_contrast_focus": any(
            item["id"] == "prohibition_vs_gain" and float(item["share"]) >= 0.30
            for item in slices
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "train_base_examples": payload["train_base_examples"],
        "target_slot_count": payload["supervised_target_slot_count"],
        "sha256": sha256_file(path),
    }


def hyperon_audit(executable: Path, metta_text: str) -> dict[str, Any]:
    if not executable.is_file():
        return {"passed": False, "reason": "hyperon_executable_missing", "path": str(executable)}
    version = subprocess.run(
        [str(executable), "--version"], capture_output=True, text=True, check=False
    )
    with tempfile.TemporaryDirectory() as temporary:
        kernel = Path(temporary) / "constitution_kernel_v2.metta"
        kernel.write_text(metta_text, encoding="utf-8", newline="\n")
        loaded = subprocess.run(
            [str(executable), str(kernel)], capture_output=True, text=True, check=False
        )
    return {
        "passed": version.returncode == 0 and loaded.returncode == 0,
        "path": str(executable),
        "version": version.stdout.strip(),
        "version_exit_code": version.returncode,
        "load_exit_code": loaded.returncode,
        "load_stdout": loaded.stdout.strip(),
        "load_stderr": loaded.stderr.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--constitution", type=Path, default=Path("constitution.md"))
    parser.add_argument(
        "--package",
        type=Path,
        default=Path("experiments/constitutional_hrm_200m_v2"),
    )
    parser.add_argument(
        "--hyperon-exe",
        type=Path,
        default=Path("D:/Research_Engine/venvs/hyperon-metta/Scripts/metta.exe"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    model_path = args.package / "model_config.json"
    curriculum_path = args.package / "curriculum_plan.json"
    plan_path = args.package / "experiment_plan.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    experiment_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    expected_gate_ids = {f"F{index:02d}_{suffix}" for index, suffix in (
        (1, "CONSTITUTION_COMPILE"),
        (2, "HYPERON_LOAD"),
        (3, "PROMPT_FREEZE"),
        (4, "PARAMETER_AUDIT"),
        (5, "CURRICULUM_AUDIT"),
        (6, "TOKENIZER_FREEZE"),
        (7, "OFFICIAL_CODE_ADAPTER"),
        (8, "CLUSTER_CAPS_AND_CLEANUP"),
        (9, "TWO_HOUR_AUTHORIZATION"),
    )}
    actual_gate_ids = {str(item["id"]) for item in experiment_plan["gates"]}
    if actual_gate_ids != expected_gate_ids:
        raise ValueError(
            f"experiment plan gate IDs differ: {sorted(actual_gate_ids ^ expected_gate_ids)}"
        )
    architecture = audit_hrm_architecture(
        HrmArchitecture.from_mapping(model["architecture"])
    )
    compilation = compile_constitution_to_metta(args.constitution)
    prompts = render_prompt_bundle(args.constitution)
    prompt_checks = {
        "three_conditions": set(prompts["prompts"])
        == {
            "constitution_metta_full",
            "constitution_hash_only",
            "constitution_removed",
        },
        "full_prompt_within_budget": prompts["prompts"]["constitution_metta_full"][
            "whitespace_tokens"
        ]
        <= int(model["input_contract"]["prompt_tokens_max"]),
        "unique_prompt_hashes": len(
            {item["sha256"] for item in prompts["prompts"].values()}
        )
        == 3,
    }
    curriculum = curriculum_audit(
        curriculum_path, int(model["input_contract"]["target_slots"])
    )
    hyperon = hyperon_audit(args.hyperon_exe, compilation["metta_text"])
    gates = {
        "F01_CONSTITUTION_COMPILE": {
            "status": "passed",
            "constitution_sha256": compilation["constitution_sha256"],
            "metta_sha256": compilation["metta_sha256"],
            "fact_count": compilation["fact_count"],
        },
        "F02_HYPERON_LOAD": {"status": "passed" if hyperon["passed"] else "failed", **hyperon},
        "F03_PROMPT_FREEZE": {
            "status": "passed" if all(prompt_checks.values()) else "failed",
            "checks": prompt_checks,
            "prompt_hashes": {
                key: value["sha256"] for key, value in prompts["prompts"].items()
            },
            "prompt_whitespace_tokens": {
                key: value["whitespace_tokens"]
                for key, value in prompts["prompts"].items()
            },
        },
        "F04_PARAMETER_AUDIT": {
            "status": "passed" if architecture["passed"] else "failed",
            **architecture,
        },
        "F05_CURRICULUM_AUDIT": {
            "status": "passed" if curriculum["passed"] else "failed",
            **curriculum,
        },
        "F06_TOKENIZER_FREEZE": {"status": "pending"},
        "F07_OFFICIAL_CODE_ADAPTER": {"status": "pending"},
        "F08_CLUSTER_CAPS_AND_CLEANUP": {"status": "pending"},
        "F09_TWO_HOUR_AUTHORIZATION": {"status": "pending"},
    }
    passed_pre_spend = all(
        gates[gate_id]["status"] == "passed"
        for gate_id in (
            "F01_CONSTITUTION_COMPILE",
            "F02_HYPERON_LOAD",
            "F03_PROMPT_FREEZE",
            "F04_PARAMETER_AUDIT",
            "F05_CURRICULUM_AUDIT",
        )
    )
    receipt = {
        "schema_version": "constitutional_hrm_200m_readiness_v2",
        "experiment_id": "constitutional_hrm_200m_v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pre_spend_passed_next_F06" if passed_pre_spend else "pre_spend_failed",
        "source_sha256": {
            "constitution.md": compilation["constitution_sha256"],
            "model_config.json": sha256_file(model_path),
            "curriculum_plan.json": sha256_file(curriculum_path),
            "experiment_plan.json": sha256_file(plan_path),
        },
        "gates": gates,
        "optimizer_launch_authorized": False,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if passed_pre_spend else 1


if __name__ == "__main__":
    raise SystemExit(main())
