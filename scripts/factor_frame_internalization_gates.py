#!/usr/bin/env python3
"""Factor the active Qwen frame-internalization gates into a dependency DAG."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments/frame_internalization_sft_v1"
READINESS = PACKAGE / "readiness"
FREEZE = PACKAGE / "rerun_freeze"
QWEN_FREEZE = FREEZE / "qwen3_1p7b_v1"

ACTIVE_PATHS = {
    "contract_validation": READINESS / "prompt_sft_contrast_validation_v3_qwen3_1p7b.json",
    "compute_plan": PACKAGE / "compute_stage_plan_qwen3_1p7b_v1.json",
    "substitution": PACKAGE / "model_substitution_qwen3_1p7b_v1.json",
    "split": READINESS / "split_freeze_v1.json",
    "evaluation_manifest": FREEZE / "evaluation_universes_v2.json",
    "evaluation_seal": READINESS / "evaluation_seal_v2.json",
    "local_model_freeze": READINESS / "qwen3_1p7b_local_model_tokenizer_freeze_v2.json",
    "request_manifest": QWEN_FREEZE / "curriculum_generation_v1/request_manifest.json",
    "source_nonleakage": FREEZE / "nonleakage_source_prompts_v2.json",
    "judge_inputs": FREEZE / "judge_classifier_inputs_v2.json",
    "base_reanchor_plan": QWEN_FREEZE / "base_reanchor_plan_v1.json",
}

REGISTERED_ARMS = {
    "neutral_reflection",
    "F1_reflection",
    "F1_demonstration",
    "F3_reflection",
    "F3_demonstration",
    "F3_concrete_reflection",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--primelab-environment", type=Path)
    parser.add_argument("--generation-receipt", type=Path, action="append", default=[])
    parser.add_argument("--curriculum-manifest", type=Path)
    parser.add_argument("--nonleakage-audit", type=Path)
    parser.add_argument("--judge-freeze", type=Path)
    parser.add_argument("--judge-predictions", type=Path)
    parser.add_argument("--human-validation", type=Path)
    parser.add_argument("--base-generation", type=Path)
    parser.add_argument("--probe-freeze", type=Path)
    parser.add_argument("--base-reanchor", type=Path)
    parser.add_argument("--training-smoke", type=Path)
    parser.add_argument("--pilot-authorization", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-ready-for-pilot", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def binding(root: Path, path: Path) -> dict[str, Any]:
    resolved = resolve(root, path)
    return {
        "path": display_path(root, resolved),
        "sha256": sha256_file(resolved) if resolved.is_file() else None,
    }


def bound_file_valid(root: Path, item: dict[str, Any]) -> bool:
    path = resolve(root, Path(str(item.get("path", ""))))
    expected = item.get("sha256") or item.get("file_sha256")
    return path.is_file() and sha256_file(path) == expected


def fixed_status(
    root: Path,
    paths: list[Path],
    predicate: Callable[[list[dict[str, Any]]], bool],
) -> tuple[str, list[dict[str, Any]], str | None]:
    resolved = [resolve(root, path) for path in paths]
    evidence = [binding(root, path) for path in resolved]
    if not all(path.is_file() for path in resolved):
        return "failed", evidence, "required_repository_evidence_missing"
    try:
        documents = [read_json(path) for path in resolved]
        passed = bool(predicate(documents))
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return "failed", evidence, f"{type(exc).__name__}: {exc}"
    return ("passed", evidence, None) if passed else (
        "failed",
        evidence,
        "repository_evidence_predicate_failed",
    )


def optional_status(
    root: Path,
    path: Path | None,
    predicate: Callable[[dict[str, Any]], bool],
) -> tuple[str, list[dict[str, Any]], str | None]:
    if path is None:
        return "pending", [], None
    resolved = resolve(root, path)
    evidence = [binding(root, resolved)]
    if not resolved.is_file():
        return "failed", evidence, "supplied_receipt_missing"
    try:
        document = read_json(resolved)
        passed = bool(predicate(document))
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return "failed", evidence, f"{type(exc).__name__}: {exc}"
    return ("passed", evidence, None) if passed else (
        "failed",
        evidence,
        "supplied_receipt_predicate_failed",
    )


def factor(
    factor_id: str,
    label: str,
    lane: str,
    owner: str,
    depends_on: list[str],
    result: tuple[str, list[dict[str, Any]], str | None],
    next_action: str,
    receipt_interface: dict[str, Any] | None = None,
    resource_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status, evidence, error = result
    return {
        "factor_id": factor_id,
        "label": label,
        "lane": lane,
        "owner": owner,
        "evidence_status": status,
        "depends_on": depends_on,
        "evidence": evidence,
        "error": error,
        "next_action": "none" if status == "passed" else next_action,
        "receipt_interface": receipt_interface,
        "resource_contract": resource_contract,
    }


def build_factors(args: argparse.Namespace) -> list[dict[str, Any]]:
    root = args.root.resolve()
    path = {name: resolve(root, value) for name, value in ACTIVE_PATHS.items()}

    protocol = fixed_status(
        root,
        [path["contract_validation"], path["compute_plan"], path["substitution"]],
        lambda docs: docs[0].get("passed") is True
        and docs[1].get("schema_version") == "frame_internalization_compute_stage_plan.v2"
        and docs[1].get("status") == "frozen_execution_pending"
        and set(docs[1].get("scope", {}).get("registered_training_arms", [])) == REGISTERED_ARMS
        and docs[2].get("schema_version") == "frame_internalization_model_substitution.v1"
        and docs[2].get("status") == "frozen_before_registered_qwen_outcomes",
    )
    split = fixed_status(
        root,
        [path["split"]],
        lambda docs: docs[0].get("passed") is True
        and docs[0].get("scenario_count") == 5600
        and docs[0].get("train_count") == 5320
        and docs[0].get("validation_count") == 280
        and docs[0].get("cluster_overlap_count") == 0,
    )
    evaluation = fixed_status(
        root,
        [path["evaluation_manifest"], path["evaluation_seal"]],
        lambda docs: docs[0].get("schema_version") == "frame_internalization_evaluation_universes.v2"
        and docs[0].get("passed") is True
        and docs[0].get("status") == "frozen_licensed_prospective_substitution"
        and all(bound_file_valid(root, item) for item in docs[0].get("universes", {}).values())
        and docs[1].get("schema_version") == "frame_internalization_evaluation_seal.v2"
        and docs[1].get("sealed") is True
        and docs[1].get("opened") is False,
    )
    local_model = fixed_status(
        root,
        [path["local_model_freeze"]],
        lambda docs: docs[0].get("schema_version") == "frame_internalization_base_freeze.v1"
        and docs[0].get("passed") is True
        and docs[0].get("immutable_revisions") is True
        and docs[0].get("repository") == "Qwen/Qwen3-1.7B"
        and docs[0].get("revision") == "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
        and all(item.get("passed") is True for item in docs[0].get("artifact_checks", []))
        and len(docs[0].get("artifact_checks", [])) == 12
        and docs[0].get("engine", {}).get("passed") is True,
    )
    requests = fixed_status(
        root,
        [path["request_manifest"]],
        lambda docs: docs[0].get("schema_version")
        == "frame_internalization_curriculum_request_freeze.v1"
        and docs[0].get("request_count") == 22400
        and docs[0].get("source_frame_count") == 4
        and docs[0].get("registered_training_arm_count") == 6
        and docs[0].get("dilemma_count") == 5600
        and docs[0].get("generation", {}).get("model_revision")
        == "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
        and bound_file_valid(root, docs[0]["requests"])
        and bound_file_valid(root, docs[0]["dilemmas"])
        and bound_file_valid(root, docs[0]["model_inventory"])
        and all(bound_file_valid(root, item) for item in docs[0].get("frames", {}).values()),
    )
    source_nonleakage = fixed_status(
        root,
        [path["source_nonleakage"]],
        lambda docs: docs[0].get("schema_version")
        == "frame_internalization_nonleakage_precursor.v1"
        and docs[0].get("passed") is True
        and docs[0].get("gate_satisfying") is False
        and docs[0].get("exact_overlap_count") == 0
        and docs[0].get("normalized_overlap_count") == 0
        and docs[0].get("ngram_overlap_count") == 0,
    )
    judge_inputs = fixed_status(
        root,
        [path["judge_inputs"]],
        lambda docs: docs[0].get("schema_version")
        == "frame_internalization_judge_classifier_inputs.v2"
        and docs[0].get("validation_queue", {}).get("row_count") == 400
        and docs[0].get("validation_queue", {}).get("compliance_rows") == 200
        and docs[0].get("validation_queue", {}).get("strict_af_rows") == 200
        and docs[0].get("agreement_gate", {}).get("minimum_cohens_kappa_each_task") == 0.7
        and bound_file_valid(root, docs[0]["evaluation_universe"])
        and bound_file_valid(root, docs[0]["validation_queue"])
        and bound_file_valid(root, docs[0]["request_builder"])
        and all(bound_file_valid(root, item) for item in docs[0].get("rubrics", {}).values()),
    )
    base_plan = fixed_status(
        root,
        [path["base_reanchor_plan"]],
        lambda docs: docs[0].get("schema_version")
        == "frame_internalization_qwen_base_reanchor_plan.v1"
        and docs[0].get("status") == "frozen_execution_pending"
        and docs[0].get("evaluation", {}).get("expected_total_rows") == 1600
        and docs[0].get("representation_probe", {}).get("model_layer_index_zero_based") == 27,
    )

    generation_result: tuple[str, list[dict[str, Any]], str | None]
    if not args.generation_receipt:
        generation_result = ("pending", [], None)
    else:
        evidence: list[dict[str, Any]] = []
        documents: list[dict[str, Any]] = []
        error: str | None = None
        for item in args.generation_receipt:
            resolved = resolve(root, item)
            evidence.append(binding(root, resolved))
            if not resolved.is_file():
                error = "supplied_generation_receipt_missing"
                break
            documents.append(read_json(resolved))
        frames = {doc.get("source_frame") for doc in documents}
        generation_passed = bool(
            error is None
            and frames == {"neutral", "F1", "F3", "F3_concrete"}
            and all(
                doc.get("schema_version")
                == "frame_internalization_curriculum_generation_receipt.v1"
                and doc.get("complete") is True
                and doc.get("requested") == 5600
                and doc.get("completed") == 5600
                and not doc.get("failed")
                for doc in documents
            )
        )
        generation_result = (
            ("passed", evidence, None)
            if generation_passed
            else ("failed", evidence, error or "four_complete_generation_receipts_required")
        )

    curriculum_join = optional_status(
        root,
        args.curriculum_manifest,
        lambda doc: doc.get("schema_version") == "frame_internalization_curriculum_manifest.v1"
        and set(doc.get("arms", {})) == REGISTERED_ARMS
        and all(item.get("scenario_count") == 5600 for item in doc.get("arms", {}).values())
        and all(item.get("train_count") == 5320 for item in doc.get("arms", {}).values())
        and all(item.get("validation_count") == 280 for item in doc.get("arms", {}).values())
        and len({item.get("scenario_ids_sha256") for item in doc.get("arms", {}).values()}) == 1
        and all(int(item.get("total_train_tokens", 0)) > 0 for item in doc.get("arms", {}).values()),
    )
    token_parity = optional_status(
        root,
        args.curriculum_manifest,
        lambda doc: doc.get("schema_version") == "frame_internalization_curriculum_manifest.v1"
        and float(doc.get("f3_pair_total_token_spread", 1.0)) <= 0.02
        and int(doc.get("sequence_length", 0)) == 4096,
    )
    final_nonleakage = optional_status(
        root,
        args.nonleakage_audit,
        lambda doc: doc.get("schema_version") == "frame_internalization_nonleakage_audit.v1"
        and doc.get("passed") is True
        and doc.get("gate_satisfying") is True
        and doc.get("exact_overlap_count") == 0
        and doc.get("normalized_overlap_count") == 0
        and doc.get("ngram_overlap_count") == 0,
    )
    primelab = optional_status(
        root,
        args.primelab_environment,
        lambda doc: doc.get("schema_version")
        == "frame_internalization_primelab_environment_freeze.v1"
        and doc.get("passed") is True
        and doc.get("gpu_count") == 1
        and float(doc.get("gpu_vram_gib", 0)) >= 24
        and bool(doc.get("environment_lock_sha256"))
        and doc.get("model_artifact_inventory_sha256")
        == "26dbf683e31beebd0282217ea79a1b53f7a8fed6f4961978d7881c5a556e1959"
        and all(float(doc.get("inference_caps", {}).get(key, 0)) > 0 for key in (
            "maximum_wall_clock_seconds",
            "maximum_gpu_hours",
            "maximum_output_bytes",
            "checkpoint_every_requests",
        ))
        and doc.get("cleanup_required") is True,
    )
    judge_freeze = optional_status(
        root,
        args.judge_freeze,
        lambda doc: doc.get("schema_version")
        == "frame_internalization_judge_configuration_freeze.v1"
        and doc.get("passed") is True
        and doc.get("immutable_revisions") is True
        and bool(doc.get("judge_revision"))
        and bool(doc.get("classifier_revision"))
        and bool(doc.get("decoding_settings_sha256")),
    )
    judge_predictions = optional_status(
        root,
        args.judge_predictions,
        lambda doc: doc.get("schema_version")
        == "frame_internalization_judge_predictions.v1"
        and doc.get("passed") is True
        and doc.get("prediction_rows_complete") is True
        and doc.get("predictions_frozen_before_human_agreement") is True
        and doc.get("all_missing_rows_retained") is True,
    )
    human_validation = optional_status(
        root,
        args.human_validation,
        lambda doc: doc.get("schema_version") == "frame_internalization_human_validation.v1"
        and doc.get("passed") is True
        and int(doc.get("compliance_completed_labels", 0)) >= 200
        and int(doc.get("strict_af_completed_labels", 0)) >= 200
        and float(doc.get("compliance_cohens_kappa", -1)) >= 0.7
        and float(doc.get("strict_af_cohens_kappa", -1)) >= 0.7
        and doc.get("blinded_to_judge_outputs") is True,
    )
    base_generation = optional_status(
        root,
        args.base_generation,
        lambda doc: doc.get("schema_version") == "frame_internalization_qwen_base_generation.v1"
        and doc.get("passed") is True
        and doc.get("expected_rows") == 1600
        and doc.get("observed_rows") == 1600
        and doc.get("complete_join_keys") is True,
    )
    probe_freeze = optional_status(
        root,
        args.probe_freeze,
        lambda doc: doc.get("schema_version") == "frame_internalization_qwen_probe_freeze.v1"
        and doc.get("passed") is True
        and doc.get("layer_index_zero_based") == 27
        and doc.get("prompt_disjoint") is True
        and doc.get("random_label_control_passed") is True
        and doc.get("random_projection_control_passed") is True
        and doc.get("frozen_before_adapter_outcomes") is True,
    )
    base_reanchor = optional_status(
        root,
        args.base_reanchor,
        lambda doc: doc.get("schema_version") == "frame_internalization_qwen_base_reanchor.v1"
        and doc.get("passed") is True
        and doc.get("joined_rows") == 1600
        and doc.get("bootstrap_draws") == 10000
        and doc.get("bootstrap_seed") == 42
        and doc.get("all_invalid_and_missing_outputs_reported") is True,
    )
    training_smoke = optional_status(
        root,
        args.training_smoke,
        lambda doc: doc.get("schema_version") == "frame_internalization_training_smoke_receipt.v2"
        and doc.get("passed") is True
        and doc.get("gpu_count") == 1
        and doc.get("sequence_length") == 4096
        and doc.get("arms_completed") == 6
        and doc.get("steps_per_arm") == 50
        and doc.get("checkpoint_round_trip_all_arms") is True
        and doc.get("cleanup_passed") is True
        and float(doc.get("gpu_hours", 999)) <= 2,
    )
    authorization = optional_status(
        root,
        args.pilot_authorization,
        lambda doc: doc.get("schema_version") == "frame_internalization_compute_authorization.v2"
        and doc.get("authorized") is True
        and doc.get("stage") == "pilot"
        and doc.get("all_required_gates_passed") is True,
    )

    return [
        factor("F00", "protocol and Qwen execution contract", "repository", "repository", [], protocol, "repair the active contract, substitution, or compute-plan binding"),
        factor("F01", "cluster-disjoint source split", "repository", "repository", ["F00"], split, "repair or refreeze the 5,600-row split"),
        factor("F02", "licensed evaluation universe and seal", "repository", "repository", ["F00"], evaluation, "repair the licensed universe or unopened seal"),
        factor("F03", "Qwen local checkpoint and runtime", "local", "repository", ["F00"], local_model, "rerun exact local artifact and NF4 runtime verification"),
        factor(
            "F04",
            "PrimeLab hardware, environment, model, and inference caps",
            "primelab_setup",
            "researcher",
            ["F00", "F03"],
            primelab,
            "freeze the exact PrimeLab GPU, environment lock, model hashes, bounded inference caps, and cleanup contract",
            {
                "schema_version": "frame_internalization_primelab_environment_freeze.v1",
                "required": ["one GPU with at least 24 GiB VRAM", "environment lock SHA-256", "matching model inventory", "positive inference caps", "cleanup_required=true"],
            },
        ),
        factor("F05", "Qwen-bound 22,400-request curriculum pack", "repository", "repository", ["F00", "F01", "F03"], requests, "repair or refreeze the Qwen request pack"),
        factor(
            "F06",
            "complete four-frame transcript generation",
            "primelab_inference",
            "primelab",
            ["F04", "F05"],
            generation_result,
            "run the four resumable generation jobs under the F04 caps and return four complete receipts",
            {"schema_version": "frame_internalization_curriculum_generation_receipt.v1", "required_receipts": 4},
        ),
        factor(
            "F07",
            "exact six-arm render and 4,096-token accounting",
            "primelab_data",
            "primelab",
            ["F03", "F06"],
            curriculum_join,
            "render all six arms with exact joins and the frozen Qwen tokenizer",
            {"schema_version": "frame_internalization_curriculum_manifest.v1"},
        ),
        factor("F08", "F3 versus F3-concrete token parity", "primelab_data", "primelab", ["F07"], token_parity, "satisfy the frozen total-token spread threshold of at most 0.02"),
        factor("F09", "source-prompt nonleakage", "repository", "repository", ["F01", "F02"], source_nonleakage, "repair the source-prompt leakage audit"),
        factor(
            "F10",
            "generated-text nonleakage",
            "primelab_data",
            "primelab",
            ["F02", "F07", "F09"],
            final_nonleakage,
            "audit every rendered message against every sealed evaluation universe",
            {"schema_version": "frame_internalization_nonleakage_audit.v1"},
        ),
        factor("F11", "judge rubrics, request builder, and validation queue", "repository", "repository", ["F02"], judge_inputs, "repair the v2 judge input freeze"),
        factor(
            "F12",
            "immutable judge revisions and decoding configuration",
            "judge_setup",
            "researcher",
            ["F02", "F11"],
            judge_freeze,
            "select immutable judge and classifier revisions and freeze their decoding configuration",
            {"schema_version": "frame_internalization_judge_configuration_freeze.v1"},
        ),
        factor(
            "F13",
            "complete prospective Qwen base generation",
            "primelab_inference",
            "primelab",
            ["F02", "F03", "F04", "F11"],
            base_generation,
            "generate and retain all 1,600 registered Qwen base rows under the F04 caps",
            {"schema_version": "frame_internalization_qwen_base_generation.v1", "expected_rows": 1600},
        ),
        factor(
            "F14",
            "complete frozen judge predictions",
            "judge_inference",
            "researcher",
            ["F12", "F13"],
            judge_predictions,
            "run the frozen judge configuration over the validation rows and retain every missing result",
            {"schema_version": "frame_internalization_judge_predictions.v1"},
        ),
        factor(
            "F15",
            "blinded human agreement",
            "human_validation",
            "human_annotators",
            ["F14"],
            human_validation,
            "complete 200 blinded labels per task and pass Cohen's kappa >= 0.70 for each",
            {"schema_version": "frame_internalization_human_validation.v1"},
        ),
        factor(
            "F16",
            "Qwen layer-27 probe and controls",
            "primelab_analysis",
            "primelab",
            ["F13"],
            probe_freeze,
            "fit and freeze the prompt-disjoint layer-27 probe and both controls before adapter outcomes",
            {"schema_version": "frame_internalization_qwen_probe_freeze.v1"},
        ),
        factor(
            "F17",
            "prospective Qwen base analysis",
            "analysis",
            "repository",
            ["F13", "F14", "F15", "F16"],
            base_reanchor,
            "join, score, bootstrap, and freeze the Qwen base result with all missingness retained",
            {"schema_version": "frame_internalization_qwen_base_reanchor.v1"},
        ),
        factor(
            "F18",
            "single-GPU six-arm 4,096-token smoke",
            "primelab_training",
            "primelab",
            ["F04", "F07", "F08", "F10"],
            training_smoke,
            "run the exact six-arm 50-step smoke inside the capped wrapper and complete cleanup",
            {"schema_version": "frame_internalization_training_smoke_receipt.v2"},
            {
                "gpu_count": 1,
                "minimum_vram_gib": 24,
                "maximum_wall_clock_seconds": 7200,
                "maximum_gpu_hours": 2,
                "steps_per_arm": 50,
                "sequence_length": 4096,
                "checkpoint_every_steps_maximum": 200,
                "checkpoint_every_minutes_maximum": 20,
                "cleanup_required": True,
            },
        ),
        factor(
            "F19",
            "signed pilot authorization",
            "authorization",
            "researcher",
            [f"F{index:02d}" for index in range(20) if index != 19],
            authorization,
            "bind every passed factor and the exact capped pilot command in a signed authorization",
            {"schema_version": "frame_internalization_compute_authorization.v2"},
        ),
    ]


def finalize_factors(factors: list[dict[str, Any]]) -> None:
    by_id = {item["factor_id"]: item for item in factors}
    if len(by_id) != len(factors):
        raise ValueError("duplicate factor ID")
    for item in factors:
        unknown = sorted(set(item["depends_on"]) - set(by_id))
        if unknown:
            raise ValueError(f"unknown dependencies for {item['factor_id']}: {unknown}")
        blocked_by = [
            dependency
            for dependency in item["depends_on"]
            if by_id[dependency]["evidence_status"] != "passed"
        ]
        item["blocked_by"] = blocked_by
        if item["evidence_status"] == "passed":
            item["execution_state"] = "satisfied"
        elif item["evidence_status"] == "failed":
            item["execution_state"] = "failed"
        elif blocked_by:
            item["execution_state"] = "blocked"
        else:
            item["execution_state"] = "ready"
    for item in factors:
        item["unlocks"] = [
            candidate["factor_id"]
            for candidate in factors
            if item["factor_id"] in candidate["depends_on"]
        ]


def execution_waves(factors: list[dict[str, Any]]) -> list[list[str]]:
    satisfied = {
        item["factor_id"] for item in factors if item["evidence_status"] == "passed"
    }
    remaining = {
        item["factor_id"] for item in factors if item["evidence_status"] != "passed"
    }
    dependencies = {item["factor_id"]: set(item["depends_on"]) for item in factors}
    waves: list[list[str]] = []
    while remaining:
        wave = sorted(item for item in remaining if dependencies[item] <= satisfied)
        if not wave:
            raise ValueError(f"factor dependency cycle or unresolved dependency: {sorted(remaining)}")
        waves.append(wave)
        satisfied.update(wave)
        remaining.difference_update(wave)
    return waves


def build_gates(factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item["factor_id"]: item for item in factors}
    specifications = [
        ("G01", "qwen_model_tokenizer_local_freeze", ["F03"]),
        ("G02", "primelab_environment_and_hardware_freeze", ["F04"]),
        ("G03", "complete_matched_qwen_curricula", ["F01", "F05", "F06", "F07"]),
        ("G04", "curriculum_token_parity", ["F07", "F08"]),
        ("G05", "generated_text_nonleakage", ["F02", "F09", "F10"]),
        ("G06", "evaluation_seal", ["F02"]),
        ("G07", "judge_and_human_validation_freeze", ["F11", "F12", "F14", "F15"]),
        (
            "G08",
            "prospective_qwen_base_baseline_and_layer_27_probe_freeze",
            ["F02", "F03", "F11", "F12", "F13", "F14", "F15", "F16", "F17"],
        ),
        ("G09", "single_gpu_4096_training_smoke", ["F03", "F04", "F07", "F08", "F10", "F18"]),
        ("G10", "human_pilot_authorization", [f"F{index:02d}" for index in range(20)]),
    ]
    gates: list[dict[str, Any]] = []
    for gate_id, label, factor_ids in specifications:
        statuses = [by_id[item]["evidence_status"] for item in factor_ids]
        status = "failed" if "failed" in statuses else (
            "passed" if all(item == "passed" for item in statuses) else "pending"
        )
        gates.append(
            {
                "gate_id": gate_id,
                "label": label,
                "status": status,
                "required_factors": factor_ids,
                "unsatisfied_factors": [
                    item for item in factor_ids if by_id[item]["evidence_status"] != "passed"
                ],
                "blocks_pilot": status != "passed",
            }
        )
    return gates


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    factors = build_factors(args)
    finalize_factors(factors)
    gates = build_gates(factors)
    pilot_ready = all(item["status"] == "passed" for item in gates)
    return {
        "schema_version": "frame_internalization_gate_factorization.v1",
        "as_of_date": args.as_of_date,
        "active_execution": "qwen3_1p7b_single_gpu_v1",
        "classification": "operational_factorization_without_gate_weakening",
        "pilot_ready": pilot_ready,
        "invariants": {
            "parent_gate_pass_requires_every_required_factor": True,
            "shared_factor_is_evaluated_once": True,
            "factorization_does_not_authorize_compute": True,
            "historical_intellect_receipts_do_not_satisfy_active_qwen_factors": True,
        },
        "summary": {
            "factor_count": len(factors),
            "passed_factor_count": sum(item["evidence_status"] == "passed" for item in factors),
            "pending_factor_count": sum(item["evidence_status"] == "pending" for item in factors),
            "failed_factor_count": sum(item["evidence_status"] == "failed" for item in factors),
            "parent_gate_count": len(gates),
            "passed_parent_gate_count": sum(item["status"] == "passed" for item in gates),
            "blocking_parent_gate_count": sum(item["blocks_pilot"] for item in gates),
        },
        "current_frontier": [
            item["factor_id"] for item in factors if item["execution_state"] == "ready"
        ],
        "projected_execution_waves": execution_waves(factors),
        "factors": factors,
        "parent_gates": gates,
        "generator": {
            "path": Path(__file__).resolve().relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
    }


def main() -> int:
    args = parse_args()
    report = build_report(args)
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = resolve(args.root.resolve(), args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    if args.require_ready_for_pilot and not report["pilot_ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
