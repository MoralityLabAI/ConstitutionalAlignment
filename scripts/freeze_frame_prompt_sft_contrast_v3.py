#!/usr/bin/env python3
"""Freeze the Qwen3-1.7B direct prompt-versus-SFT contract v3."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments/frame_internalization_sft_v1"
SOURCE = PACKAGE / "prompt_sft_contrast_v2.json"
SUBSTITUTION = PACKAGE / "model_substitution_qwen3_1p7b_v1.json"
INVENTORY = PACKAGE / "rerun_freeze/qwen3_1p7b_v1/model_tokenizer_remote_inventory_v1.json"
REANCHOR = PACKAGE / "rerun_freeze/qwen3_1p7b_v1/base_reanchor_plan_v1.json"
COMPUTE_PLAN = PACKAGE / "compute_stage_plan_qwen3_1p7b_v1.json"
OUTPUT = PACKAGE / "prompt_sft_contrast_v3_qwen3_1p7b.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def main() -> int:
    source = read_json(SOURCE)
    substitution = read_json(SUBSTITUTION)
    inventory = read_json(INVENTORY)
    reanchor = read_json(REANCHOR)
    compute_plan = read_json(COMPUTE_PLAN)
    if source.get("schema_version") != "frame_internalization_prompt_sft_contrast.v2":
        raise RuntimeError("unexpected v2 source contract")
    if substitution.get("status") != "frozen_before_registered_qwen_outcomes":
        raise RuntimeError("Qwen substitution is not prospectively frozen")
    if inventory.get("repository") != "Qwen/Qwen3-1.7B":
        raise RuntimeError("Qwen inventory identity drifted")
    if reanchor.get("status") != "frozen_execution_pending":
        raise RuntimeError("Qwen base reanchor is not frozen")
    if compute_plan.get("status") != "frozen_execution_pending":
        raise RuntimeError("Qwen compute plan is not frozen")

    contract = deepcopy(source)
    contract["schema_version"] = "frame_internalization_prompt_sft_contrast.v3"
    contract["contract_id"] = "frame_internalization_direct_prompt_sft_v3_qwen3_1p7b"
    contract["frozen_at"] = "2026-07-20"
    contract["status"] = "frozen_qwen_execution_pending"
    contract["classification"] = (
        "prospective_small_model_substitution_on_the_licensed_v2_evaluation_universe"
    )
    contract["timing_attestation"] = {
        "qwen_adapter_training_started_before_freeze": False,
        "qwen_adapter_outcomes_seen_before_freeze": False,
        "registered_qwen_evaluation_outcomes_seen_before_freeze": False,
        "registered_qwen_curriculum_outputs_seen_before_freeze": False,
        "fixed_format_infrastructure_smokes_existed_before_freeze": True,
    }
    contract["inherits"] = {
        "path": rel(SOURCE),
        "sha256": sha256_file(SOURCE),
        "changed_provision": (
            "Replaces only the unavailable INTELLECT-3 model/runtime and historical reanchor "
            "with a prospective Qwen3-1.7B baseline; preserves the six arms, estimands, "
            "evaluation universe, joins, bootstrap, and guards."
        ),
    }
    contract["resource_substitution"] = {
        "path": rel(SUBSTITUTION),
        "sha256": sha256_file(SUBSTITUTION),
        "compute_plan_path": rel(COMPUTE_PLAN),
        "compute_plan_sha256": sha256_file(COMPUTE_PLAN),
    }
    contract["model"] = {
        "repository": inventory["repository"],
        "revision": inventory["revision"],
        "license": inventory["license"],
        "inventory": {"path": rel(INVENTORY), "sha256": sha256_file(INVENTORY)},
        "official_chat_template_sha256": inventory["chat_template"]["sha256"],
        "loader": "Transformers BitsAndBytes NF4 double-quant with float16 compute",
        "same_frozen_base_required_for_prompt_and_sft": True,
        "historical_intellect_3_equivalence_claimed": False,
    }
    contract["evaluation"]["decoding"]["think_mode"] = True
    contract["evaluation"]["decoding"]["chat_template_mode"] = (
        "official_qwen3_enable_thinking_true"
    )
    contract["evaluation"]["historical_reanchor_separation"] = (
        "The recovered INTELLECT-3 results remain descriptive cross-model provenance only. "
        "They are not pooled with Qwen and are not a Qwen pass/fail target."
    )
    contract["evaluation"]["prospective_v2_baseline"] = {
        "required_before_qwen_adapter_outcomes": True,
        "same_200_prompt_ids_as_prompt_and_sft_cells": True,
        "magnitude_acceptance_interval": None,
        "report_complete_joined_qwen_F0_estimate": True,
    }
    contract["system_prompt_construction"]["chat_template"] = {
        "source": "official Qwen tokenizer_config.json at the frozen revision",
        "sha256": inventory["chat_template"]["sha256"],
        "thinking_mode": True,
        "system_prompt_text_rewritten_for_qwen": False,
    }
    contract["frozen_scoring_inputs"]["reanchor_progress"] = {
        "path": rel(REANCHOR),
        "sha256": sha256_file(REANCHOR),
        "qwen_probe_frozen_before_adapter_outcomes_must_be_true": True,
        "historical_intellect_probe_reused": False,
    }
    contract["analysis_gate"]["prospective_qwen_base_baseline_required"] = True
    contract["analysis_gate"]["historical_intellect_result_as_qwen_gate_forbidden"] = True
    contract["analysis_gate"]["exact_primelab_environment_freeze_required_before_training"] = True
    contract["interpretation_boundary"] = (
        "This is a prospective within-Qwen3-1.7B operational comparison of explicit prompting "
        "and matched QLoRA interventions. It does not reproduce INTELLECT-3 and does not support "
        "model-family-general, theological, or literal-internalization claims."
    )
    contract["freezer"] = {
        "path": rel(Path(__file__)),
        "sha256": sha256_file(Path(__file__)),
    }
    OUTPUT.write_text(
        json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"output": str(OUTPUT), "sha256": sha256_file(OUTPUT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
