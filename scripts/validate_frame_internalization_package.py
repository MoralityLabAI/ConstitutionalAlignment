#!/usr/bin/env python3
"""Validate frozen F3 cards, hash bindings, and scholar-review readiness."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path("experiments/frame_internalization_sft_v1")
AMENDMENT = PACKAGE / "protocol_amendment_f3_concrete_v1.json"
CONTRACT = PACKAGE / "scholar_review_contract_v1.json"
RECOVERY_MANIFEST = PACKAGE / "recovery_manifest.json"
PREDECESSOR_DEPENDENCIES = PACKAGE / "predecessor_dependency_manifest_v1.json"
PROMPT_RECONSTRUCTION = PACKAGE / "predecessor_prompt_reconstruction_v1.json"
REANCHORING_PLAN = PACKAGE / "predecessor_reanchoring_plan_v1.json"
CARD_SCHEMA = Path("schemas/frame_internalization_frame_card_v1.schema.json")
RECEIPT_SCHEMA = Path("schemas/frame_internalization_scholar_review_receipt_v1.schema.json")
RESEARCH_NOTES = Path("constitutional-harness/RESEARCH_NOTES.md")
EXPECTED_FRAMES = {"F3", "F3_concrete"}
EXPECTED_CRITERIA = {
    "theological_accuracy",
    "eschatological_mechanics",
    "non_literal_model_status",
    "non_authority_boundary",
    "terminology_and_tone",
    "research_use_and_claims",
}
EXPECTED_ENDPOINTS = {
    "frame_removal_persistence",
    "generic_override_resistance",
    "registered_representation_movement",
}
EXPECTED_REANCHOR_GATES = {
    "prompt_text_reconstruction",
    "immutable_model_tokenizer_freeze",
    "evaluation_universe_freeze",
    "judge_classifier_freeze",
    "base_f0_layer27_probe_freeze",
    "base_model_reanchor",
    "row_level_receipt_contract",
}
EXPECTED_PENDING_REANCHOR_GATES = {
    "immutable_model_tokenizer_freeze",
    "evaluation_universe_freeze",
    "judge_classifier_freeze",
    "base_f0_layer27_probe_freeze",
    "base_model_reanchor",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (defaults to the root containing this script).",
    )
    parser.add_argument(
        "--review-receipt",
        type=Path,
        action="append",
        default=[],
        help="Hash-bound scholar receipt; repeat once per receipt.",
    )
    parser.add_argument(
        "--require-fielding-ready",
        action="store_true",
        help="Return exit 2 while any frame lacks an approving receipt.",
    )
    parser.add_argument(
        "--require-predecessor-ready",
        action="store_true",
        help="Return exit 3 while any predecessor dependency freeze gate is pending.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON readiness report path.")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema_errors(instance: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    ]


def extract_recovered_f3(notes: str) -> str:
    match = re.search(
        r"<!-- phase3-arm:eschatological:start -->\s*(.*?)\s*"
        r"<!-- phase3-arm:eschatological:end -->",
        notes,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Could not locate phase3-arm:eschatological in RESEARCH_NOTES.md")
    return match.group(1)


def validate_package(root: Path, receipt_paths: list[Path]) -> dict[str, Any]:
    root = root.resolve()
    failures: list[str] = []

    def resolve(relative: str | Path) -> Path:
        path = Path(relative)
        return path.resolve() if path.is_absolute() else (root / path).resolve()

    amendment_path = resolve(AMENDMENT)
    contract_path = resolve(CONTRACT)
    card_schema_path = resolve(CARD_SCHEMA)
    receipt_schema_path = resolve(RECEIPT_SCHEMA)
    notes_path = resolve(RESEARCH_NOTES)
    recovery_manifest_path = resolve(RECOVERY_MANIFEST)
    predecessor_path = resolve(PREDECESSOR_DEPENDENCIES)
    prompt_reconstruction_path = resolve(PROMPT_RECONSTRUCTION)
    reanchoring_plan_path = resolve(REANCHORING_PLAN)
    amendment = read_json(amendment_path)
    contract = read_json(contract_path)
    card_schema = read_json(card_schema_path)
    receipt_schema = read_json(receipt_schema_path)
    recovery_manifest = read_json(recovery_manifest_path)
    predecessor = read_json(predecessor_path)
    prompt_reconstruction = read_json(prompt_reconstruction_path)
    reanchoring_plan = read_json(reanchoring_plan_path)

    if amendment.get("schema_version") != "frame_internalization_protocol_amendment.v1":
        failures.append("unexpected amendment schema_version")
    if amendment.get("historical_boundary", {}).get("changes_recovered_facts") is not False:
        failures.append("amendment must preserve recovered facts")
    if amendment.get("historical_boundary", {}).get("outcomes_seen_before_freeze") is not False:
        failures.append("amendment must state that no outcomes were seen before freeze")
    if contract.get("schema_version") != "frame_internalization_scholar_review_contract.v1":
        failures.append("unexpected scholar review contract schema_version")
    if contract.get("status") != "pending_receipts":
        failures.append("frozen contract must remain pending_receipts; approval lives in receipts")
    contract_criteria = [item.get("criterion_id") for item in contract.get("criteria", [])]
    if len(contract_criteria) != len(EXPECTED_CRITERIA) or set(contract_criteria) != EXPECTED_CRITERIA:
        failures.append("review contract must define each required criterion exactly once")
    if any(item.get("review_state") != "pending" for item in contract.get("artifacts", [])):
        failures.append("frozen contract cannot record approval; approval lives in external receipts")

    claim_gate = amendment.get("operational_internalization_claim_gate", {})
    endpoint_ids = [item.get("endpoint_id") for item in claim_gate.get("endpoints", [])]
    if len(endpoint_ids) != len(EXPECTED_ENDPOINTS) or set(endpoint_ids) != EXPECTED_ENDPOINTS:
        failures.append("amendment must define each internalization endpoint exactly once")
    if claim_gate.get("logic") != "all_three_endpoints_and_all_regression_guards":
        failures.append("amendment cannot weaken the conjunction claim gate")
    if amendment.get("arm_amendment", {}).get("add_arm") != "F3_concrete_reflection":
        failures.append("unexpected prospective arm amendment")

    prospective = recovery_manifest.get("prospective_rerun_amendments", [])
    amendment_bindings = [
        item for item in prospective if item.get("id") == amendment.get("amendment_id")
    ]
    if len(amendment_bindings) != 1 or amendment_bindings[0].get("sha256") != sha256_file(
        amendment_path
    ):
        failures.append("recovery manifest has a stale or missing amendment binding")
    predecessor_binding = recovery_manifest.get("predecessor_dependency_recovery", {})
    if (
        predecessor_binding.get("path") != str(PREDECESSOR_DEPENDENCIES).replace("\\", "/")
        or predecessor_binding.get("sha256") != sha256_file(predecessor_path)
    ):
        failures.append("recovery manifest has a stale predecessor dependency binding")
    for key, path, label in (
        ("prompt_text_reconstruction", prompt_reconstruction_path, "prompt reconstruction"),
        ("prospective_reanchoring_plan", reanchoring_plan_path, "reanchoring plan"),
    ):
        binding = predecessor_binding.get(key, {})
        if binding.get("sha256") != sha256_file(path):
            failures.append(f"recovery manifest has a stale or missing {label} binding")

    if (
        prompt_reconstruction.get("schema_version")
        != "frame_internalization_predecessor_prompt_reconstruction.v1"
    ):
        failures.append("unexpected predecessor prompt-reconstruction schema_version")
    if prompt_reconstruction.get("classification") != (
        "deterministic_reconstruction_from_session_embedded_inputs"
    ):
        failures.append("prompt reconstruction must retain its recovered/reconstructed boundary")
    if prompt_reconstruction.get("status") != (
        "prompt_text_reconstructable_canonical_bundle_missing"
    ):
        failures.append("prompt reconstruction must not claim canonical bundle recovery")

    construction = prompt_reconstruction.get("construction", {})
    prompt_bindings = [
        (construction.get("recorded_recipe", {}), "recorded arm-construction recipe"),
        (construction.get("base", {}), "recovered prompt base"),
        (prompt_reconstruction.get("target_chat_template", {}), "target chat template"),
        (
            prompt_reconstruction.get("recorded_token_receipts", {}).get("arm_manifest", {}),
            "arm token receipt",
        ),
        (
            prompt_reconstruction.get("recorded_token_receipts", {}).get("frame_counts", {}),
            "frame token-count receipt",
        ),
    ]
    for frame_id, binding in sorted(construction.get("frames", {}).items()):
        prompt_bindings.append((binding, f"{frame_id} predecessor frame"))
    for binding, label in prompt_bindings:
        path_value = binding.get("path")
        if not path_value:
            failures.append(f"missing path for {label}")
            continue
        observed = sha256_file(resolve(path_value))
        if binding.get("sha256") != observed:
            failures.append(f"stale SHA-256 for {label}")

    if construction.get("base", {}).get("path"):
        base_text = resolve(construction["base"]["path"]).read_text(encoding="utf-8")
        reconstructed = prompt_reconstruction.get("reconstructed_system_prompts", {})
        for arm in ("F0", "F1", "F2", "F3"):
            text = base_text
            if arm != "F0":
                frame_binding = construction.get("frames", {}).get(arm, {})
                frame_path = frame_binding.get("path")
                if not frame_path:
                    failures.append(f"missing {arm} frame for prompt reconstruction")
                    continue
                text += "\n\n" + resolve(frame_path).read_text(encoding="utf-8").strip()
            payload = text.encode("utf-8")
            expected = reconstructed.get(arm, {})
            if expected.get("bytes") != len(payload):
                failures.append(f"stale reconstructed byte count: {arm}")
            if expected.get("sha256") != hashlib.sha256(payload).hexdigest():
                failures.append(f"stale reconstructed prompt SHA-256: {arm}")

    if (
        reanchoring_plan.get("schema_version")
        != "frame_internalization_predecessor_reanchoring_plan.v1"
    ):
        failures.append("unexpected predecessor reanchoring-plan schema_version")
    if reanchoring_plan.get("classification") != "prospective_protocol_not_recovered_history":
        failures.append("reanchoring plan must remain prospective rather than recovered history")
    if reanchoring_plan.get("status") != "frozen_gates_pending":
        failures.append("reanchoring plan must remain frozen with gates pending")
    reanchor_prompt_binding = reanchoring_plan.get("bound_prompt_reconstruction", {})
    if (
        reanchor_prompt_binding.get("path") != str(PROMPT_RECONSTRUCTION).replace("\\", "/")
        or reanchor_prompt_binding.get("sha256") != sha256_file(prompt_reconstruction_path)
    ):
        failures.append("reanchoring plan has a stale prompt-reconstruction binding")
    reanchor_gates = reanchoring_plan.get("freeze_sequence", [])
    reanchor_gate_ids = [str(item.get("gate_id")) for item in reanchor_gates]
    if len(reanchor_gate_ids) != len(set(reanchor_gate_ids)):
        failures.append("reanchoring gate IDs must be unique")
    if set(reanchor_gate_ids) != EXPECTED_REANCHOR_GATES:
        failures.append("reanchoring plan gate set changed")
    observed_pending_reanchor = {
        str(item.get("gate_id")) for item in reanchor_gates if item.get("status") == "pending"
    }
    if observed_pending_reanchor != EXPECTED_PENDING_REANCHOR_GATES:
        failures.append("reanchoring pending-gate set changed or was prematurely passed")
    invalid_reanchor_statuses = [
        str(item.get("gate_id"))
        for item in reanchor_gates
        if item.get("status") not in {"passed", "pending"}
    ]
    if invalid_reanchor_statuses:
        failures.append(f"invalid reanchoring gate statuses: {invalid_reanchor_statuses}")
    budget_decision = reanchoring_plan.get("budget_decision", {})
    if budget_decision.get("cap_usd") != 98:
        failures.append("reanchoring budget cap must remain 98 USD")
    if budget_decision.get("status") != "reserved_not_authorized":
        failures.append("reanchoring budget must remain reserved and unauthorized while gates are pending")
    if budget_decision.get("allocation") != "experiment_1_F0_headline_table_reanchor":
        failures.append("reanchoring budget allocation changed")
    if "adapter training" not in budget_decision.get("excluded_scope", []):
        failures.append("reanchoring budget must exclude adapter training")
    if predecessor.get("schema_version") != "frame_internalization_predecessor_dependency_manifest.v1":
        failures.append("unexpected predecessor dependency schema_version")
    if predecessor.get("status") != "partial_recovery_not_freeze_ready":
        failures.append("predecessor manifest must not claim readiness while required payloads are missing")
    extraction = predecessor.get("extraction", {})
    for path_key, hash_key, label in (
        ("spec_path", "spec_sha256", "predecessor recovery spec"),
        ("manifest_path", "manifest_sha256", "predecessor extraction manifest"),
    ):
        value = extraction.get(path_key)
        if not value:
            failures.append(f"missing {label} path")
            continue
        observed = sha256_file(resolve(value))
        if extraction.get(hash_key) != observed:
            failures.append(f"stale {label} SHA-256")
    for dependency in predecessor.get("recovered_dependencies", []):
        path_value = dependency.get("path")
        if dependency.get("status") != "passed" or not path_value:
            failures.append(f"invalid recovered dependency entry: {dependency.get('dependency_id')}")
            continue
        if dependency.get("sha256") != sha256_file(resolve(path_value)):
            failures.append(f"stale recovered dependency SHA-256: {dependency.get('dependency_id')}")

    predecessor_gates = predecessor.get("freeze_gates", [])
    gate_ids = [str(item.get("gate_id")) for item in predecessor_gates]
    if len(gate_ids) != len(set(gate_ids)):
        failures.append("predecessor freeze gate IDs must be unique")
    invalid_gate_statuses = [
        gate_id
        for gate_id, item in zip(gate_ids, predecessor_gates)
        if item.get("status") not in {"passed", "pending"}
    ]
    if invalid_gate_statuses:
        failures.append(f"invalid predecessor freeze gate statuses: {invalid_gate_statuses}")
    pending_predecessor_gates = sorted(
        str(item.get("gate_id")) for item in predecessor_gates if item.get("status") != "passed"
    )

    frozen_inputs = amendment.get("frozen_inputs", {})
    hash_bindings = [
        (frozen_inputs.get("frame_card_schema", {}), card_schema_path, "frame-card schema"),
        (
            frozen_inputs.get("scholar_review_contract", {}),
            contract_path,
            "scholar-review contract",
        ),
        (contract.get("receipt_schema", {}), receipt_schema_path, "receipt schema"),
    ]
    for binding, path, label in hash_bindings:
        observed = sha256_file(path)
        if binding.get("sha256") != observed:
            failures.append(f"stale {label} SHA-256: expected {binding.get('sha256')}, observed {observed}")

    amendment_cards = {
        item.get("frame_id"): item for item in frozen_inputs.get("frame_cards", [])
    }
    contract_cards = {item.get("frame_id"): item for item in contract.get("artifacts", [])}
    if set(amendment_cards) != EXPECTED_FRAMES:
        failures.append(f"amendment frame set must be {sorted(EXPECTED_FRAMES)}")
    if set(contract_cards) != EXPECTED_FRAMES:
        failures.append(f"review contract frame set must be {sorted(EXPECTED_FRAMES)}")

    cards: dict[str, dict[str, Any]] = {}
    card_receipts: dict[str, dict[str, Any]] = {}
    for frame_id in sorted(EXPECTED_FRAMES):
        binding = amendment_cards.get(frame_id, {})
        path_value = binding.get("path")
        if not path_value:
            failures.append(f"missing card path for {frame_id}")
            continue
        path = resolve(path_value)
        card = read_json(path)
        cards[frame_id] = card
        observed_hash = sha256_file(path)
        card_receipts[frame_id] = {
            "path": str(path.relative_to(root)),
            "sha256": observed_hash,
            "reference_tokens": card.get("tokenization", {}).get("recorded_tokens"),
        }
        for error in schema_errors(card, card_schema):
            failures.append(f"{frame_id} schema: {error}")
        if card.get("frame_id") != frame_id:
            failures.append(f"card frame_id mismatch for {frame_id}")
        if binding.get("sha256") != observed_hash:
            failures.append(f"stale amendment card SHA-256 for {frame_id}")
        if binding.get("reference_tokens") != card.get("tokenization", {}).get(
            "recorded_tokens"
        ):
            failures.append(f"stale amendment token count for {frame_id}")
        contract_binding = contract_cards.get(frame_id, {})
        if contract_binding.get("path") != path_value or contract_binding.get("sha256") != observed_hash:
            failures.append(f"stale review-contract binding for {frame_id}")

    if "F3" in cards:
        recovered_text = extract_recovered_f3(notes_path.read_text(encoding="utf-8"))
        if cards["F3"].get("prompt_text") != recovered_text:
            failures.append("F3 prompt_text is not exact recovered phase3 eschatological wording")
    if "F3_concrete" in cards:
        concrete = str(cards["F3_concrete"].get("prompt_text", "")).lower()
        for marker in ("recorded", "witnessed", "weighed"):
            if marker not in concrete:
                failures.append(f"F3_concrete prompt is missing required mechanic: {marker}")

    actual_tokens: dict[str, int] = {}
    try:
        import tiktoken  # type: ignore

        encoding = tiktoken.get_encoding("cl100k_base")
        actual_tokens = {
            frame_id: len(encoding.encode(str(card["prompt_text"])))
            for frame_id, card in cards.items()
        }
        for frame_id, actual in actual_tokens.items():
            if actual != cards[frame_id]["tokenization"]["recorded_tokens"]:
                failures.append(
                    f"stale recorded token count for {frame_id}: "
                    f"expected {cards[frame_id]['tokenization']['recorded_tokens']}, observed {actual}"
                )
    except ImportError:
        failures.append("missing required validation dependency: tiktoken")

    observed_spread: float | None = None
    if len(actual_tokens) == 2:
        observed_spread = max(actual_tokens.values()) / min(actual_tokens.values()) - 1
        maximum = float(frozen_inputs.get("maximum_pair_token_spread", 0.0))
        if observed_spread > maximum:
            failures.append(f"frame pair token spread {observed_spread:.6f} exceeds {maximum:.6f}")
        if abs(observed_spread - float(frozen_inputs.get("observed_pair_token_spread", -1))) > 1e-12:
            failures.append("stale observed_pair_token_spread in amendment")

    approvals = {frame_id: 0 for frame_id in EXPECTED_FRAMES}
    receipt_results: list[dict[str, Any]] = []
    for raw_path in receipt_paths:
        path = raw_path.resolve()
        receipt = read_json(path)
        errors = schema_errors(receipt, receipt_schema)
        frame_id = str(receipt.get("frame_id", ""))
        result = {
            "path": str(path),
            "frame_id": frame_id,
            "sha256": sha256_file(path),
            "decision": receipt.get("decision"),
            "valid": not errors,
            "errors": errors,
        }
        if frame_id not in EXPECTED_FRAMES:
            errors.append("receipt names an unknown frame_id")
        elif receipt.get("frame_card_sha256") != card_receipts.get(frame_id, {}).get("sha256"):
            errors.append("receipt is stale for the current frame-card SHA-256")
        criterion_ids = [item.get("criterion_id") for item in receipt.get("criterion_results", [])]
        if len(criterion_ids) != len(EXPECTED_CRITERIA) or set(criterion_ids) != EXPECTED_CRITERIA:
            errors.append("receipt must decide each required criterion exactly once")
        if receipt.get("decision") == "approve" and receipt.get("reviewer", {}).get(
            "conflicts_disclosed"
        ) is not True:
            errors.append("an approval must affirm that conflicts were disclosed")
        result["valid"] = not errors
        if errors:
            failures.extend(f"receipt {path.name}: {error}" for error in errors)
        elif receipt.get("decision") == "approve":
            approvals[frame_id] += 1
        receipt_results.append(result)

    minimum = int(contract.get("reviewer_requirement", {}).get("minimum_approvals_per_artifact", 1))
    pending_frames = sorted(frame_id for frame_id, count in approvals.items() if count < minimum)
    structurally_valid = not failures
    frame_use_ready = structurally_valid and not pending_frames
    predecessor_freeze_ready = structurally_valid and not pending_predecessor_gates
    reanchoring_freeze_ready = structurally_valid and not observed_pending_reanchor
    if failures:
        status = "failed"
    elif pending_frames or pending_predecessor_gates:
        status = "structurally_valid_gates_pending"
    else:
        status = "frame_and_predecessor_gates_passed"

    gates = [
        {
            "gate_id": "frozen_card_integrity",
            "status": "passed" if structurally_valid else "failed",
        },
        {
            "gate_id": "qualified_scholar_review",
            "status": "passed" if frame_use_ready else ("failed" if failures else "pending"),
            "pending_frames": pending_frames,
        },
        {
            "gate_id": "predecessor_dependency_freeze",
            "status": "passed"
            if predecessor_freeze_ready
            else ("failed" if failures else "pending"),
            "pending_gates": pending_predecessor_gates,
        },
        {
            "gate_id": "prospective_reanchoring_freeze",
            "status": "passed"
            if reanchoring_freeze_ready
            else ("failed" if failures else "pending"),
            "pending_gates": sorted(observed_pending_reanchor),
        },
        {
            "gate_id": "experiment_launch",
            "status": "pending",
            "reason": "Experiment-level source, smoke, base-reproduction, evaluator-freeze, and budget gates are outside this frame-package validator.",
        },
    ]
    return {
        "schema_version": "frame_internalization_package_readiness.v1",
        "status": status,
        "structurally_valid": structurally_valid,
        "frame_use_ready": frame_use_ready,
        "predecessor_freeze_ready": predecessor_freeze_ready,
        "reanchoring_freeze_ready": reanchoring_freeze_ready,
        "experiment_launch_ready": False,
        "amendment_sha256": sha256_file(amendment_path),
        "contract_sha256": sha256_file(contract_path),
        "cards": card_receipts,
        "actual_reference_tokens": actual_tokens,
        "observed_pair_token_spread": observed_spread,
        "approvals_by_frame": dict(sorted(approvals.items())),
        "pending_frames": pending_frames,
        "pending_predecessor_gates": pending_predecessor_gates,
        "pending_reanchoring_gates": sorted(observed_pending_reanchor),
        "review_receipts": receipt_results,
        "gates": gates,
        "failures": failures,
    }


def main() -> int:
    args = parse_args()
    try:
        report = validate_package(args.root, args.review_receipt)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 1
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not report["structurally_valid"]:
        return 1
    if args.require_fielding_ready and not report["frame_use_ready"]:
        return 2
    if args.require_predecessor_ready and not report["predecessor_freeze_ready"]:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
