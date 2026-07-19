#!/usr/bin/env python3
"""Validate the prospective direct prompt-versus-SFT analysis contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT = (
    REPO_ROOT
    / "experiments/frame_internalization_sft_v1/prompt_sft_contrast_v1.json"
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def binding(root: Path, item: dict[str, Any], label: str, failures: list[str]) -> dict[str, Any]:
    path = resolve(root, str(item.get("path", "")))
    observed = sha256_file(path) if path.is_file() else None
    expected = item.get("sha256")
    if observed != expected:
        failures.append(f"stale or missing binding: {label}")
    return {
        "path": str(item.get("path", "")),
        "expected_sha256": expected,
        "observed_sha256": observed,
        "valid": observed == expected,
    }


def frame_text(root: Path, source: dict[str, Any]) -> str:
    path = resolve(root, source["path"])
    if source["kind"] == "text":
        return path.read_text(encoding="utf-8").strip()
    if source["kind"] == "json_prompt_text":
        return str(read_object(path)["prompt_text"]).strip()
    raise ValueError(f"unsupported frame source kind: {source['kind']}")


def validate_contract(root: Path, contract_path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    root = root.resolve()
    contract_path = contract_path.resolve()
    contract = read_object(contract_path)
    failures: list[str] = []
    bindings: dict[str, dict[str, Any]] = {}

    schema_version = contract.get("schema_version")
    if schema_version not in {
        "frame_internalization_prompt_sft_contrast.v1",
        "frame_internalization_prompt_sft_contrast.v2",
    }:
        failures.append("unexpected schema_version")
    if contract.get("status") != "frozen_execution_pending":
        failures.append("contract is not frozen in execution-pending state")
    timing = contract.get("timing_attestation", {})
    if any(value is not False for value in timing.values()) or set(timing) != {
        "adapter_training_started_before_freeze",
        "adapter_outcomes_seen_before_freeze",
        "evaluation_outcomes_seen_before_freeze",
    }:
        failures.append("timing attestation is incomplete or not prospective")

    inherited = contract.get("inherits", {})
    bindings["inherited_amendment"] = binding(root, inherited, "inherited amendment", failures)
    if schema_version == "frame_internalization_prompt_sft_contrast.v2":
        bindings["universe_amendment"] = binding(
            root,
            contract.get("universe_amendment", {}),
            "licensed universe amendment",
            failures,
        )

    model = contract.get("model", {})
    bindings["model_inventory"] = binding(
        root, model.get("inventory", {}), "model inventory", failures
    )
    inventory_path = resolve(root, model.get("inventory", {}).get("path", ""))
    if inventory_path.is_file():
        inventory = read_object(inventory_path)
        if inventory.get("repository") != model.get("repository"):
            failures.append("model repository differs from inventory")
        if inventory.get("revision") != model.get("revision"):
            failures.append("model revision differs from inventory")
    if model.get("same_frozen_base_required_for_prompt_and_sft") is not True:
        failures.append("prompt and SFT cells are not bound to the same frozen base")

    evaluation = contract.get("evaluation", {})
    universe = evaluation.get("universe", {})
    bindings["harmful_universe"] = binding(root, universe, "harmful universe", failures)
    bindings["evaluation_manifest"] = binding(
        root, universe.get("manifest", {}), "evaluation manifest", failures
    )
    manifest_path = resolve(root, universe.get("manifest", {}).get("path", ""))
    if schema_version == "frame_internalization_prompt_sft_contrast.v2" and manifest_path.is_file():
        manifest = read_object(manifest_path)
        if manifest.get("schema_version") != "frame_internalization_evaluation_universes.v2":
            failures.append("v2 contract does not bind the v2 evaluation-universe manifest")
        if manifest.get("passed") is not True or manifest.get("license_gate", {}).get("passed") is not True:
            failures.append("v2 evaluation-universe or license gate has not passed")
        compatibility = manifest.get("historical_reanchor_compatibility", {})
        if compatibility.get("recovered_f0_interval_is_confirmatory_target") is not False:
            failures.append("v2 manifest does not retire the historical F0 pass/fail target")
    universe_path = resolve(root, universe.get("path", ""))
    if universe_path.is_file():
        row_count = sum(1 for line in universe_path.read_text(encoding="utf-8").splitlines() if line.strip())
        if row_count != universe.get("row_count") or row_count != 200:
            failures.append("harmful universe does not contain exactly 200 rows")

    for tier in ("free", "paid"):
        bindings[f"tier_{tier}"] = binding(
            root,
            evaluation.get("tier_templates", {}).get(tier, {}),
            f"{tier} tier template",
            failures,
        )
    decoding = evaluation.get("decoding", {})
    expected_decoding = {
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": 6000,
        "think_mode": True,
        "maximum_attempts": 4,
        "retry_settings_must_be_identical": True,
    }
    if decoding != expected_decoding:
        failures.append("decoding contract drift")
    if evaluation.get("samples_per_prompt_tier_arm") != 1 or evaluation.get("sample_id") != 0:
        failures.append("direct contrast must use one matched sample with sample_id zero")
    if evaluation.get("join_keys") != ["prompt_id", "tier", "sample_id"]:
        failures.append("join-key contract drift")
    if evaluation.get("expected_rows_per_arm") != 400:
        failures.append("expected rows per arm must be 400")
    seed_schedule = evaluation.get("seed_schedule", {})
    if seed_schedule.get("identical_seed_for_every_arm_at_a_prompt_tier") is not True:
        failures.append("seed schedule is not paired across arms")
    if seed_schedule.get("engine_seed_support_must_be_verified_before_generation") is not True:
        failures.append("engine seed support is not gated")

    prompt_contract = contract.get("system_prompt_construction", {})
    base_item = prompt_contract.get("base", {})
    bindings["base_system_prompt"] = binding(root, base_item, "base system prompt", failures)
    base_path = resolve(root, base_item.get("path", ""))
    base_text = base_path.read_text(encoding="utf-8") if base_path.is_file() else ""
    prompts: dict[str, Any] = prompt_contract.get("prompts", {})
    if set(prompts) != {"F0", "F1", "F3", "F3_concrete"}:
        failures.append("prompt set must be exactly F0, F1, F3, and F3_concrete")
    rendered_prompts: dict[str, dict[str, Any]] = {}
    for frame_id in ("F0", "F1", "F3", "F3_concrete"):
        item = prompts.get(frame_id, {})
        source = item.get("frame_source")
        if frame_id == "F0":
            rendered = base_text
            if source is not None:
                failures.append("F0 must not have a frame source")
        else:
            if not isinstance(source, dict):
                failures.append(f"{frame_id} lacks a frame source")
                rendered = base_text
            else:
                bindings[f"frame_{frame_id}"] = binding(
                    root, source, f"{frame_id} frame source", failures
                )
                rendered = base_text + "\n\n" + frame_text(root, source)
        raw = rendered.encode("utf-8")
        observed_hash = sha256_bytes(raw)
        if len(raw) != item.get("bytes"):
            failures.append(f"{frame_id} composed prompt byte count drift")
        if observed_hash != item.get("sha256"):
            failures.append(f"{frame_id} composed prompt hash drift")
        rendered_prompts[frame_id] = {"bytes": len(raw), "sha256": observed_hash}

    contrasts = contract.get("contrasts", {})
    confirmatory = contrasts.get("confirmatory_family", [])
    secondary = contrasts.get("secondary_family", [])
    expected_confirmatory = {
        ("F1", "reflection", "F1_reflection"),
        ("F3", "reflection", "F3_reflection"),
    }
    expected_secondary = {
        ("F1", "demonstration", "F1_demonstration"),
        ("F3", "demonstration", "F3_demonstration"),
        ("F3_concrete", "reflection", "F3_concrete_reflection"),
    }
    observed_confirmatory = {
        (item.get("frame"), item.get("curriculum"), item.get("sft_arm"))
        for item in confirmatory
    }
    observed_secondary = {
        (item.get("frame"), item.get("curriculum"), item.get("sft_arm"))
        for item in secondary
    }
    if observed_confirmatory != expected_confirmatory:
        failures.append("confirmatory contrast family drift")
    if observed_secondary != expected_secondary:
        failures.append("secondary contrast family drift")
    if contrasts.get("neutral_sft_arm") != "neutral_reflection":
        failures.append("neutral SFT comparator drift")
    if contrasts.get("sft_inference_system_prompt") != "F0":
        failures.append("SFT inference is not frame-free F0")

    bootstrap = contract.get("bootstrap", {})
    if bootstrap.get("method") != "paired prompt-cluster bootstrap":
        failures.append("bootstrap method drift")
    if bootstrap.get("draws") != 10000 or bootstrap.get("seed") != 42:
        failures.append("bootstrap draw count or seed drift")
    if bootstrap.get("confidence_level") != 0.95 or bootstrap.get("families_separate") is not True:
        failures.append("bootstrap interval family drift")

    for name, item in contract.get("frozen_scoring_inputs", {}).items():
        bindings[f"scoring_{name}"] = binding(root, item, f"scoring input {name}", failures)

    gate = contract.get("analysis_gate", {})
    required_true = {
        "all_expected_rows_required",
        "one_to_one_join_required",
        "judge_and_classifier_agreement_gate_required",
        "probe_freeze_required_before_adapter_outcomes",
        "benign_over_refusal_guard_required",
        "capability_guard_required",
        "no_prompt_or_judge_tuning_after_outcomes",
    }
    required_true.add(
        "base_reanchor_required"
        if schema_version == "frame_internalization_prompt_sft_contrast.v1"
        else "prospective_v2_base_baseline_required"
    )
    if any(gate.get(key) is not True for key in required_true):
        failures.append("one or more analysis gates are not fail-closed")
    if schema_version == "frame_internalization_prompt_sft_contrast.v2":
        if gate.get("historical_v1_interval_as_v2_pass_fail_forbidden") is not True:
            failures.append("v2 contract does not forbid the historical interval as a pass/fail target")
        baseline = evaluation.get("prospective_v2_baseline", {})
        if baseline.get("required_before_adapter_outcomes") is not True:
            failures.append("v2 prospective base baseline is not required before adapter outcomes")
        if baseline.get("magnitude_acceptance_interval", "missing") is not None:
            failures.append("v2 baseline improperly carries a magnitude acceptance interval")

    return {
        "schema_version": "frame_internalization_prompt_sft_contrast_validation.v1",
        "passed": not failures,
        "contract_path": display_path(root, contract_path),
        "contract_sha256": sha256_file(contract_path),
        "validator_sha256": sha256_file(Path(__file__)),
        "bindings": bindings,
        "rendered_prompts": rendered_prompts,
        "confirmatory_contrast_count": len(confirmatory) * 3,
        "secondary_contrast_count": len(secondary) * 3,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contract = args.contract if args.contract.is_absolute() else args.root / args.contract
    report = validate_contract(args.root, contract)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else args.root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
