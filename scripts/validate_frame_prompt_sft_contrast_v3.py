#!/usr/bin/env python3
"""Validate the Qwen3-1.7B model substitution and prompt-versus-SFT contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments/frame_internalization_sft_v1"
DEFAULT_CONTRACT = PACKAGE / "prompt_sft_contrast_v3_qwen3_1p7b.json"
EXPECTED_MODEL = "Qwen/Qwen3-1.7B"
EXPECTED_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
ARMS = {
    "neutral_reflection",
    "F1_reflection",
    "F1_demonstration",
    "F3_reflection",
    "F3_demonstration",
    "F3_concrete_reflection",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def bound_document(binding: dict[str, Any], failures: list[str], label: str) -> dict[str, Any]:
    path = REPO_ROOT / str(binding.get("path", ""))
    if not path.is_file():
        failures.append(f"{label}_missing")
        return {}
    if sha256_file(path) != binding.get("sha256"):
        failures.append(f"{label}_hash")
    return read_json(path)


def validate(contract_path: Path) -> dict[str, Any]:
    contract_path = contract_path.resolve()
    contract = read_json(contract_path)
    failures: list[str] = []
    checks: dict[str, bool] = {}

    def check(name: str, passed: bool) -> None:
        checks[name] = bool(passed)
        if not passed:
            failures.append(name)

    check(
        "contract_identity",
        contract.get("schema_version") == "frame_internalization_prompt_sft_contrast.v3"
        and contract.get("contract_id") == "frame_internalization_direct_prompt_sft_v3_qwen3_1p7b"
        and contract.get("status") == "frozen_qwen_execution_pending",
    )
    timing = contract.get("timing_attestation", {})
    check(
        "prospective_timing",
        timing.get("qwen_adapter_training_started_before_freeze") is False
        and timing.get("qwen_adapter_outcomes_seen_before_freeze") is False
        and timing.get("registered_qwen_evaluation_outcomes_seen_before_freeze") is False
        and timing.get("registered_qwen_curriculum_outputs_seen_before_freeze") is False
        and timing.get("fixed_format_infrastructure_smokes_existed_before_freeze") is True,
    )
    source = bound_document(contract.get("inherits", {}), failures, "v2_source")
    substitution = bound_document(
        {
            "path": contract.get("resource_substitution", {}).get("path"),
            "sha256": contract.get("resource_substitution", {}).get("sha256"),
        },
        failures,
        "substitution",
    )
    compute_plan = bound_document(
        {
            "path": contract.get("resource_substitution", {}).get("compute_plan_path"),
            "sha256": contract.get("resource_substitution", {}).get("compute_plan_sha256"),
        },
        failures,
        "compute_plan",
    )
    inventory = bound_document(contract.get("model", {}).get("inventory", {}), failures, "inventory")
    reanchor = bound_document(
        contract.get("frozen_scoring_inputs", {}).get("reanchor_progress", {}),
        failures,
        "qwen_reanchor",
    )
    freezer = contract.get("freezer", {})
    freezer_path = REPO_ROOT / str(freezer.get("path", ""))
    check(
        "freezer_hash",
        freezer_path.is_file() and sha256_file(freezer_path) == freezer.get("sha256"),
    )

    model = contract.get("model", {})
    check(
        "model_identity",
        model.get("repository") == EXPECTED_MODEL
        and model.get("revision") == EXPECTED_REVISION
        and model.get("license") == "apache-2.0"
        and model.get("same_frozen_base_required_for_prompt_and_sft") is True
        and model.get("historical_intellect_3_equivalence_claimed") is False,
    )
    check(
        "inventory_identity",
        inventory.get("repository") == EXPECTED_MODEL
        and inventory.get("revision") == EXPECTED_REVISION
        and inventory.get("artifact_count") == 12
        and inventory.get("weight_shard_count") == 2
        and inventory.get("immutable_revisions") is True,
    )
    check(
        "chat_template_binding",
        model.get("official_chat_template_sha256")
        == inventory.get("chat_template", {}).get("sha256")
        == contract.get("system_prompt_construction", {}).get("chat_template", {}).get("sha256")
        and contract.get("evaluation", {}).get("decoding", {}).get("chat_template_mode")
        == "official_qwen3_enable_thinking_true"
        and contract.get("evaluation", {}).get("decoding", {}).get("think_mode") is True,
    )
    check(
        "substitution_identity",
        substitution.get("schema_version") == "frame_internalization_model_substitution.v1"
        and substitution.get("status") == "frozen_before_registered_qwen_outcomes"
        and substitution.get("authorization", {}).get("registered_evaluation_prompts_run_before_freeze")
        == 0
        and substitution.get("authorization", {}).get("curriculum_requests_run_before_freeze") == 0
        and substitution.get("authorization", {}).get("adapter_training_steps_before_freeze") == 0,
    )
    request_manifest = bound_document(
        substitution.get("replacement_curriculum_requests", {}), failures, "qwen_request_manifest"
    )
    request_path = REPO_ROOT / str(
        substitution.get("replacement_curriculum_requests", {}).get("requests_path", "")
    )
    check(
        "qwen_request_pack",
        request_manifest.get("request_count") == 22400
        and request_manifest.get("source_frame_count") == 4
        and request_manifest.get("registered_training_arm_count") == 6
        and request_manifest.get("generation", {}).get("model_repository") == EXPECTED_MODEL
        and request_manifest.get("generation", {}).get("model_revision") == EXPECTED_REVISION
        and request_path.is_file()
        and sha256_file(request_path)
        == substitution.get("replacement_curriculum_requests", {}).get("requests_sha256"),
    )
    check(
        "compute_topology",
        compute_plan.get("schema_version") == "frame_internalization_compute_stage_plan.v2"
        and set(compute_plan.get("scope", {}).get("registered_training_arms", [])) == ARMS
        and compute_plan.get("scope", {}).get("sequence_length_preserved") == 4096
        and compute_plan.get("execution_lanes", {}).get("primelab", {}).get(
            "minimum_cuda_vram_gib"
        )
        >= 24
        and compute_plan.get("training", {}).get("sequence_length") == 4096
        and compute_plan.get("training", {}).get("epochs") == 2
        and compute_plan.get("training", {}).get("gradient_accumulation_steps") == 64
        and compute_plan.get("training", {}).get("lora", {}).get("rank") == 32,
    )
    check(
        "qwen_reanchor",
        reanchor.get("schema_version") == "frame_internalization_qwen_base_reanchor_plan.v1"
        and reanchor.get("status") == "frozen_execution_pending"
        and reanchor.get("evaluation", {}).get("expected_total_rows") == 1600
        and reanchor.get("representation_probe", {}).get("model_layer_index_zero_based") == 27
        and reanchor.get("representation_probe", {}).get("historical_intellect_probe_reused")
        is False,
    )
    preserved_fields = [
        "endpoint",
        "contrasts",
        "bootstrap",
        "universe_amendment",
    ]
    check(
        "scientific_fields_preserved",
        bool(source)
        and all(contract.get(field) == source.get(field) for field in preserved_fields)
        and contract.get("evaluation", {}).get("universe")
        == source.get("evaluation", {}).get("universe")
        and contract.get("evaluation", {}).get("tier_templates")
        == source.get("evaluation", {}).get("tier_templates")
        and contract.get("evaluation", {}).get("seed_schedule")
        == source.get("evaluation", {}).get("seed_schedule")
        and contract.get("evaluation", {}).get("join_keys")
        == source.get("evaluation", {}).get("join_keys")
        and contract.get("system_prompt_construction", {}).get("prompts")
        == source.get("system_prompt_construction", {}).get("prompts"),
    )
    check(
        "claim_boundary",
        "does not reproduce INTELLECT-3" in str(contract.get("interpretation_boundary"))
        and substitution.get("claim_boundary", {}).get("not_supported"),
    )

    return {
        "schema_version": "frame_internalization_prompt_sft_contrast_validation.v2",
        "contract_path": contract_path.relative_to(REPO_ROOT).as_posix(),
        "contract_sha256": sha256_file(contract_path),
        "validator_path": Path(__file__).resolve().relative_to(REPO_ROOT).as_posix(),
        "validator_sha256": sha256_file(Path(__file__).resolve()),
        "checks": checks,
        "passed": not failures and all(checks.values()),
        "failures": sorted(set(failures)),
    }


def main() -> int:
    args = parse_args()
    receipt = validate(args.contract)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0 if receipt["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
