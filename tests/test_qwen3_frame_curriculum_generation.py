from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path

from scripts.generate_qwen3_frame_curriculum_transcripts import (
    PairedStatelessSampler,
    stateless_uniform,
    visible_answer,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "generate_qwen3_frame_curriculum_transcripts.py"
PACKAGE = REPO_ROOT / "experiments" / "frame_internalization_sft_v1"


def test_stateless_sampler_is_stable_and_seed_sensitive() -> None:
    assert stateless_uniform(42, 0, 0) == 0.8436906260802506
    assert stateless_uniform(42, 1, 0) == 0.036806554520679435
    assert stateless_uniform(43, 0, 0) == 0.14527104831951582
    assert 0 < stateless_uniform(42, 0, 0) < 1


def test_paired_sampler_uses_common_random_numbers() -> None:
    left = PairedStatelessSampler([420042], 0, 8, 0.7, 0.8)
    right = PairedStatelessSampler([420042], 0, 8, 0.7, 0.8)
    changed = PairedStatelessSampler([420043], 0, 8, 0.7, 0.8)
    assert left._uniform_rows == right._uniform_rows
    assert left._uniform_rows != changed._uniform_rows


def test_visible_answer_requires_closed_thinking_block() -> None:
    assert visible_answer("<think>hidden</think>Visible<|im_end|>") == "Visible"
    assert visible_answer("<think>unclosed") == ""
    assert visible_answer("Direct answer<|endoftext|>") == "Direct answer"


def test_active_request_freeze_has_four_paired_frame_sets() -> None:
    freeze_path = (
        PACKAGE
        / "rerun_freeze/qwen3_1p7b_v1/curriculum_generation_v1/"
        "request_manifest.json"
    )
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    request_path = REPO_ROOT / freeze["requests"]["path"]
    rows = [json.loads(line) for line in request_path.read_text(encoding="utf-8").splitlines()]
    paired: dict[str, dict[str, int]] = {}
    for row in rows:
        paired.setdefault(row["source_frame"], {})[row["scenario_id"]] = row[
            "generation_seed"
        ]
    assert set(paired) == {"neutral", "F1", "F3", "F3_concrete"}
    assert all(values == paired["neutral"] for values in paired.values())


def test_generator_help_does_not_load_the_model_runtime() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--limit-per-frame" in result.stdout


def test_f06_smoke_plan_binds_caps_inputs_and_executables() -> None:
    plan = json.loads(
        (
            PACKAGE / "primelab_f06/f06_throughput_smoke_plan_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert plan["authorization"]["billing_authorized"] is True
    assert plan["hard_caps"]["maximum_billable_seconds"] == 1800
    assert plan["hard_caps"]["maximum_compute_cost_usd"] == 0.65
    assert plan["hard_caps"]["maximum_inference_wall_clock_seconds"] == 1200
    assert plan["workload"]["maximum_transcripts"] == 16
    assert plan["scope_boundary"]["closes_f06"] is False
    assert plan["scope_boundary"]["authorizes_adapter_training"] is False
    for binding in [*plan["frozen_inputs"].values(), *plan["executables"]]:
        path = REPO_ROOT / binding["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]
