from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.generate_qwen3_frame_curriculum_transcripts import (
    PairedStatelessSampler,
    select_top_p_indices,
    stateless_uniform,
    visible_answer,
)
from scripts.build_primelab_f06_optimization_plan import build_plan
from scripts.hash_git_blobs import (
    build_receipt,
    git_blob_sha256,
    resolve_commit,
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


def test_single_softmax_top_p_matches_reference_selection() -> None:
    import torch

    scores = torch.tensor(
        [
            [2.1, 0.4, -0.5, 1.2, 0.0],
            [-1.0, 0.5, 2.5, 1.0, 0.25],
        ],
        dtype=torch.float32,
    )
    uniforms = torch.tensor([[0.25], [0.75]], dtype=torch.float32)
    temperature = 0.7
    top_p = 0.8

    logits = scores / temperature
    sorted_logits, sorted_indices = torch.sort(logits, descending=True, dim=-1)
    probabilities = torch.softmax(sorted_logits, dim=-1)
    cumulative = torch.cumsum(probabilities, dim=-1)
    remove = cumulative > top_p
    remove[..., 1:] = remove[..., :-1].clone()
    remove[..., 0] = False
    reference_probabilities = torch.softmax(
        sorted_logits.masked_fill(remove, -torch.inf),
        dim=-1,
    )
    reference_positions = torch.searchsorted(
        torch.cumsum(reference_probabilities, dim=-1),
        uniforms,
    ).clamp_max(scores.shape[-1] - 1)
    reference = sorted_indices.gather(1, reference_positions).squeeze(1)

    actual = select_top_p_indices(scores, uniforms, temperature, top_p)
    assert torch.equal(actual, reference)


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
    result = json.loads(
        (
            PACKAGE / "primelab_f06/f06_throughput_smoke_result_v1.json"
        ).read_text(encoding="utf-8")
    )
    source_commit = result["source_commit"]
    assert resolve_commit(source_commit) == source_commit
    assert plan["authorization"]["billing_authorized"] is True
    assert plan["hard_caps"]["maximum_billable_seconds"] == 1800
    assert plan["hard_caps"]["maximum_compute_cost_usd"] == 0.65
    assert plan["hard_caps"]["maximum_inference_wall_clock_seconds"] == 1200
    assert plan["workload"]["maximum_transcripts"] == 16
    assert plan["scope_boundary"]["closes_f06"] is False
    assert plan["scope_boundary"]["authorizes_adapter_training"] is False
    for name, binding in plan["frozen_inputs"].items():
        if name == "f04_receipt":
            continue
        path = REPO_ROOT / binding["path"]
        assert git_blob_sha256(path, source_commit) == binding["sha256"]
    for binding in plan["executables"]:
        path = REPO_ROOT / binding["path"]
        assert git_blob_sha256(path, source_commit) == binding["sha256"]


def test_canonical_git_blob_receipt_is_revision_bound() -> None:
    result = json.loads(
        (
            PACKAGE / "primelab_f06/f06_throughput_smoke_result_v1.json"
        ).read_text(encoding="utf-8")
    )
    source_commit = result["source_commit"]
    generator = REPO_ROOT / "scripts/generate_qwen3_frame_curriculum_transcripts.py"
    receipt = build_receipt([generator], source_commit)

    assert receipt["source_commit"] == source_commit
    assert receipt["byte_source"] == "git_cat_file_blob"
    assert receipt["bindings"] == [
        {
            "path": "scripts/generate_qwen3_frame_curriculum_transcripts.py",
            "sha256": "bd1e930480487082c199672d9abe4c69fe66c78971bf7ef526132cac7ab4c1e2",
        }
    ]


def test_f06_optimization_builder_is_no_spend_and_preserves_science() -> None:
    plan = build_plan("HEAD", frozen_at_utc="2026-07-23T00:00:00Z")

    assert plan["status"] == "prepared_not_authorized"
    assert plan["authorization"]["billing_authorized"] is False
    assert plan["authorization"]["pod_creation_authorized"] is False
    assert plan["candidate"]["single_change_under_test"] == (
        "increase inference batch size from 8 to 32"
    )
    assert plan["candidate"]["batch_size"] == 32
    assert plan["scientific_invariants"]["quantization"] == (
        "bitsandbytes NF4 with double quantization"
    )
    assert plan["scientific_invariants"]["chat_template_mode"] == (
        "official_qwen3_enable_thinking_true"
    )
    assert plan["scientific_invariants"]["max_tokens_per_turn"] == 2500
    assert plan["promotion_criteria"]["minimum_generated_tokens_per_second"] == 240
    assert plan["scope_boundary"]["closes_f06"] is False
    assert plan["scope_boundary"]["authorizes_adapter_training"] is False


def test_f06_optimization_plan_matches_its_source_bound_builder() -> None:
    path = PACKAGE / "primelab_f06/f06_throughput_optimization_plan_v1.json"
    frozen = json.loads(path.read_text(encoding="utf-8"))
    rebuilt = build_plan(
        frozen["source_commit"],
        frozen_at_utc=frozen["frozen_at_utc"],
    )

    assert frozen == rebuilt
    assert frozen["canonical_git_bindings"]["byte_source"] == "git_cat_file_blob"
    for group in ("frozen_inputs", "development_executables"):
        for binding in frozen["canonical_git_bindings"][group].values():
            assert (
                git_blob_sha256(
                    REPO_ROOT / binding["path"],
                    frozen["source_commit"],
                )
                == binding["sha256"]
            )


def test_f06_result_fails_closed_on_host_line_ending_binding() -> None:
    plan = json.loads(
        (
            PACKAGE / "primelab_f06/f06_throughput_smoke_plan_v1.json"
        ).read_text(encoding="utf-8")
    )
    result = json.loads(
        (
            PACKAGE / "primelab_f06/f06_throughput_smoke_result_v1.json"
        ).read_text(encoding="utf-8")
    )
    f04_path = REPO_ROOT / plan["frozen_inputs"]["f04_receipt"]["path"]
    canonical_hash = git_blob_sha256(f04_path, result["source_commit"])

    assert canonical_hash != plan["frozen_inputs"]["f04_receipt"]["sha256"]
    assert result["passed"] is False
    assert result["operational_checks"]["wrapper_reported_passed"] is True
    assert result["contract_checks"]["passed"] is False
    assert result["contract_checks"][
        "f04_receipt_hash_on_remote_and_in_generation_receipts"
    ] == canonical_hash
    assert result["runtime"]["generated_tokens"] == 34651
    assert result["factor_and_claim_boundary"]["f06_remains_pending"] is True
    assert result["factor_and_claim_boundary"]["behavioral_or_scientific_result"] is False
