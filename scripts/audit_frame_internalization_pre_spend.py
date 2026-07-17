#!/usr/bin/env python3
"""Audit v2 governance and all evidence required before the eight-A100 pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path("experiments/frame_internalization_sft_v1")
AMENDMENT = PACKAGE / "protocol_amendment_v2.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--base-freeze", type=Path)
    parser.add_argument("--curriculum-manifest", type=Path)
    parser.add_argument("--split-freeze", type=Path)
    parser.add_argument("--nonleakage-audit", type=Path)
    parser.add_argument("--evaluation-seal", type=Path)
    parser.add_argument("--judge-dry-run", type=Path)
    parser.add_argument("--predecessor-reanchor", type=Path)
    parser.add_argument("--training-smoke", type=Path)
    parser.add_argument("--pilot-authorization", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-pilot-ready", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def schema_errors(instance: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
    ]


def gate(gate_id: str, status: str, evidence: dict[str, Any], next_action: str) -> dict[str, Any]:
    if status not in {"passed", "pending", "failed", "pending_nonblocking"}:
        raise ValueError(f"invalid status for {gate_id}: {status}")
    return {
        "gate_id": gate_id,
        "status": status,
        "blocks_pilot": status in {"pending", "failed"},
        "evidence": evidence,
        "next_action": "none" if status in {"passed", "pending_nonblocking"} else next_action,
    }


def optional_evidence(
    root: Path,
    value: Path | None,
    gate_id: str,
    schema_version: str,
    pass_predicate: Any,
    next_action: str,
) -> dict[str, Any]:
    if value is None:
        return gate(gate_id, "pending", {"path": None, "sha256": None}, next_action)
    path = value if value.is_absolute() else root / value
    path = path.resolve()
    if not path.is_file():
        return gate(
            gate_id,
            "pending",
            {"path": str(path), "sha256": None, "error": "file_not_found"},
            next_action,
        )
    try:
        document = read_json(path)
        passed = document.get("schema_version") == schema_version and bool(pass_predicate(document))
        error = None if passed else "receipt_schema_or_pass_condition_failed"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        document = {}
        passed = False
        error = f"{type(exc).__name__}: {exc}"
    return gate(
        gate_id,
        "passed" if passed else "failed",
        {"path": str(path), "sha256": sha256_file(path), "error": error},
        next_action,
    )


def governance_audit(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    failures: list[str] = []
    amendment_path = root / AMENDMENT
    amendment = read_json(amendment_path)
    if amendment.get("schema_version") != "frame_internalization_protocol_amendment.v2":
        failures.append("unexpected v2 amendment schema_version")
    timing = amendment.get("timing_attestation", {})
    if any(timing.get(key) is not False for key in timing):
        failures.append("v2 amendment must remain prospective to all outcomes")
    if amendment.get("compute_authorization", {}).get("scholar_receipt_required") is not False:
        failures.append("v2 amendment did not separate the scholar and compute gates")
    if amendment.get("compute_authorization", {}).get("current_state") != (
        "not_authorized_pre_spend_gates_pending"
    ):
        failures.append("v2 amendment must not claim current compute authorization")

    bindings: dict[str, dict[str, Any]] = {}
    for binding_id, binding in amendment.get("frozen_inputs", {}).items():
        if not isinstance(binding, dict) or "path" not in binding or "sha256" not in binding:
            continue
        path = root / str(binding.get("path", ""))
        observed = sha256_file(path) if path.is_file() else None
        expected = binding.get("sha256")
        bindings[binding_id] = {
            "path": str(binding.get("path", "")),
            "expected_sha256": expected,
            "observed_sha256": observed,
            "valid": observed == expected,
        }
        if observed != expected:
            failures.append(f"stale or missing frozen input: {binding_id}")

    schema_path = root / amendment["frozen_inputs"]["frame_card_schema"]["path"]
    card_schema = read_json(schema_path)
    contract = read_json(root / amendment["frozen_inputs"]["scholar_review_contract"]["path"])
    cards: dict[str, dict[str, Any]] = {}
    try:
        import tiktoken  # type: ignore

        encoding = tiktoken.get_encoding("cl100k_base")
    except ImportError:
        encoding = None
        failures.append("missing required validation dependency: tiktoken")

    for card_binding in amendment["frozen_inputs"]["frame_cards"]:
        path = root / card_binding["path"]
        card = read_json(path)
        errors = schema_errors(card, card_schema)
        if errors:
            failures.extend(f"{card_binding['frame_id']} schema: {error}" for error in errors)
        observed_card_hash = sha256_file(path)
        prompt_hash = sha256_text(str(card.get("prompt_text", "")))
        token_count = len(encoding.encode(card["prompt_text"])) if encoding else None
        if observed_card_hash != card_binding["sha256"]:
            failures.append(f"{card_binding['frame_id']} card hash drift")
        if prompt_hash != card_binding["prompt_text_sha256"]:
            failures.append(f"{card_binding['frame_id']} prompt hash drift")
        if token_count != card_binding["reference_tokens"]:
            failures.append(f"{card_binding['frame_id']} token count drift")
        v1_path = path.with_name(path.name.replace("_v2.json", "_v1.json"))
        v1 = read_json(v1_path)
        prompt_preserved = card.get("prompt_text") == v1.get("prompt_text")
        if not prompt_preserved:
            failures.append(f"{card_binding['frame_id']} v2 prompt_text differs from v1")
        cards[card_binding["frame_id"]] = {
            "path": card_binding["path"],
            "sha256": observed_card_hash,
            "prompt_text_sha256": prompt_hash,
            "reference_tokens": token_count,
            "v1_prompt_text_preserved": prompt_preserved,
        }

    counts = [cards[key]["reference_tokens"] for key in ("F3", "F3_concrete")]
    spread = (max(counts) - min(counts)) / min(counts) if all(counts) else None
    if spread is None or spread > 0.1:
        failures.append("frame-card token spread exceeds 10 percent")

    if contract.get("status") != "active_review_pending_nonblocking_for_compute":
        failures.append("v2 scholar contract is not active in its pending nonblocking state")
    if contract.get("approval_logic", {}).get("pending_receipts_do_not_block_compute") is not True:
        failures.append("v2 scholar contract still blocks compute")
    contract_cards = {item.get("frame_id"): item for item in contract.get("required_artifacts", [])}
    for frame_id, card in cards.items():
        expected = contract_cards.get(frame_id, {})
        if expected.get("sha256") != card["sha256"]:
            failures.append(f"scholar contract has stale {frame_id} card hash")
        if expected.get("prompt_text_sha256") != card["prompt_text_sha256"]:
            failures.append(f"scholar contract has stale {frame_id} prompt hash")

    stage_plan = read_json(root / amendment["frozen_inputs"]["compute_stage_plan"]["path"])
    resource = stage_plan.get("hard_resource_caps", {})
    if resource.get("gpus") != 8 or resource.get("gpu_type") != "NVIDIA A100":
        failures.append("stage plan must require exactly eight NVIDIA A100 GPUs")
    if resource.get("pilot", {}).get("wall_clock_seconds") != 7200:
        failures.append("pilot wall-clock cap must be two hours")
    if resource.get("pilot", {}).get("maximum_gpu_hours") != 16:
        failures.append("pilot GPU-hour cap must be 16")
    if resource.get("overnight", {}).get("wall_clock_seconds") != 43200:
        failures.append("overnight wall-clock cap must be 12 hours")
    if resource.get("overnight", {}).get("maximum_gpu_hours") != 96:
        failures.append("overnight GPU-hour cap must be 96")
    if resource.get("sequence_length") != 4096:
        failures.append("stage plan sequence length must be 4096")
    if stage_plan.get("status") != "frozen":
        failures.append("stage plan status must remain frozen")
    arms = stage_plan.get("scope", {}).get("registered_training_arms", [])
    if len(arms) != 6 or len(set(arms)) != 6:
        failures.append("stage plan must contain six unique training arms")

    event_schema = read_json(root / amendment["frozen_inputs"]["stage_event_schema"]["path"])
    example_path = root / PACKAGE / "examples" / "stage_events_example.jsonl"
    for line_number, line in enumerate(example_path.read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(line)
        errors = schema_errors(row, event_schema)
        if errors:
            failures.extend(f"example event line {line_number}: {error}" for error in errors)
        if row.get("example") is not True:
            failures.append(f"example event line {line_number} is not marked example")

    launcher = root / amendment["frozen_inputs"]["guard_launcher"]["path"]
    dry_run = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "--stage",
            "pilot",
            "--training-task-id",
            "audit-dry-run",
            "--authorization",
            str(root / ".audit-dry-run-authorization-not-read.json"),
            "--run-dir",
            str(root / ".audit-dry-run-not-created"),
            "--checkpoint-root",
            str(root / ".audit-dry-run-not-created" / "checkpoints"),
            "--checkpoint-every-steps",
            "200",
            "--checkpoint-every-minutes",
            "20",
            "--dry-run",
            "--",
            sys.executable,
            "-c",
            "print('not executed')",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if dry_run.returncode != 0:
        failures.append(f"guard launcher dry-run failed: {dry_run.stderr.strip()}")

    report = {
        "passed": not failures,
        "amendment_path": str(AMENDMENT).replace("\\", "/"),
        "amendment_sha256": sha256_file(amendment_path),
        "bindings": bindings,
        "cards": cards,
        "observed_card_token_spread": spread,
        "guard_launcher_dry_run_passed": dry_run.returncode == 0,
        "failures": failures,
    }
    return report, stage_plan


def audit(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    governance, stage_plan = governance_audit(root)
    gates = [
        gate(
            "governance_v2_integrity",
            "passed" if governance["passed"] else "failed",
            governance,
            "repair the v2 hash, schema, card, contract, plan, event, or launcher failure",
        ),
        gate(
            "scholar_review_claim_gate",
            "pending_nonblocking",
            {
                "review_state": "pending",
                "compute_blocked_by_review": False,
                "paper_disclosure_required": True,
            },
            "none",
        ),
    ]

    gates.append(
        optional_evidence(
            root,
            args.base_freeze,
            "base_model_tokenizer_freeze",
            "frame_internalization_base_freeze.v1",
            lambda doc: doc.get("passed") is True and doc.get("immutable_revisions") is True,
            "freeze immutable model/tokenizer revisions, chat template, license, and artifact hashes",
        )
    )

    if args.curriculum_manifest is None:
        gates.append(
            gate(
                "matched_curriculum_and_token_parity",
                "pending",
                {"path": None, "required_f3_pair_total_token_spread_max": 0.02},
                "generate and freeze all six matched curricula with exact scenario and token receipts",
            )
        )
    else:
        path = args.curriculum_manifest if args.curriculum_manifest.is_absolute() else root / args.curriculum_manifest
        path = path.resolve()
        error: str | None = None
        spread: float | None = None
        passed = False
        try:
            doc = read_json(path)
            arms = doc.get("arms", {})
            f3 = arms.get("F3_reflection", {})
            concrete = arms.get("F3_concrete_reflection", {})
            counts = [int(f3.get("total_train_tokens", 0)), int(concrete.get("total_train_tokens", 0))]
            spread = (max(counts) - min(counts)) / min(counts) if min(counts) > 0 else None
            passed = bool(
                doc.get("schema_version") == "frame_internalization_curriculum_manifest.v1"
                and doc.get("passed") is True
                and set(arms) == set(stage_plan["scope"]["registered_training_arms"])
                and f3.get("scenario_ids_sha256") == concrete.get("scenario_ids_sha256")
                and f3.get("scenario_count") == concrete.get("scenario_count")
                and spread is not None
                and spread <= 0.02
            )
            if not passed:
                error = "curriculum manifest, arm set, scenario match, or 2 percent parity gate failed"
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        gates.append(
            gate(
                "matched_curriculum_and_token_parity",
                "passed" if passed else "failed",
                {
                    "path": str(path),
                    "sha256": sha256_file(path) if path.is_file() else None,
                    "observed_f3_pair_total_token_spread": spread,
                    "error": error,
                },
                "regenerate and refreeze all six matched curricula",
            )
        )

    gates.extend(
        [
            optional_evidence(
                root,
                args.split_freeze,
                "split_freeze",
                "frame_internalization_split_freeze.v1",
                lambda doc: doc.get("passed") is True and doc.get("cluster_overlap_count") == 0,
                "freeze a cluster-disjoint train/validation assignment",
            ),
            optional_evidence(
                root,
                args.nonleakage_audit,
                "nonleakage_audit",
                "frame_internalization_nonleakage_audit.v1",
                lambda doc: doc.get("passed") is True
                and doc.get("exact_overlap_count") == 0
                and doc.get("normalized_overlap_count") == 0
                and doc.get("ngram_overlap_count") == 0,
                "run exact, normalized, and registered n-gram audits against every eval universe",
            ),
            optional_evidence(
                root,
                args.evaluation_seal,
                "evaluation_seal",
                "frame_internalization_evaluation_seal.v1",
                lambda doc: doc.get("sealed") is True and doc.get("opened") is False,
                "freeze evaluation hashes and close content access before adapter outputs",
            ),
            optional_evidence(
                root,
                args.judge_dry_run,
                "blinded_judge_synthetic_dry_run",
                "frame_internalization_judge_dry_run.v1",
                lambda doc: doc.get("passed") is True
                and doc.get("expected_parse_rate") == 1.0
                and int(doc.get("rows_per_suite", 0)) >= 3,
                "exercise the actual blinded judge CLI on synthetic pass, fail, and malformed rows per suite",
            ),
            optional_evidence(
                root,
                args.predecessor_reanchor,
                "predecessor_reanchor",
                "frame_internalization_predecessor_reanchor_receipt.v1",
                lambda doc: doc.get("passed") is True
                and doc.get("probe_frozen_before_adapter_outcomes") is True,
                "complete the existing reanchoring plan and freeze the base endpoint and probe",
            ),
            optional_evidence(
                root,
                args.training_smoke,
                "distributed_4096_training_smoke",
                "frame_internalization_training_smoke_receipt.v1",
                lambda doc: doc.get("passed") is True
                and doc.get("gpus") == 8
                and doc.get("sequence_length") == 4096
                and int(doc.get("steps", 0)) >= 50
                and doc.get("checkpoint_round_trip") is True,
                "run the capped 50-step full-topology smoke with checkpoint reload and ten generations",
            ),
            optional_evidence(
                root,
                args.pilot_authorization,
                "pilot_human_authorization",
                "frame_internalization_compute_authorization.v1",
                lambda doc: doc.get("authorized") is True
                and doc.get("stage") == "pilot"
                and doc.get("all_required_gates_passed") is True
                and doc.get("compute_stage_plan_sha256")
                == sha256_file(root / PACKAGE / "compute_stage_plan_v1.json")
                and doc.get("protocol_amendment_sha256")
                == sha256_file(root / PACKAGE / "protocol_amendment_v2.json"),
                "sign an authorization binding all passed receipts and the exact capped command",
            ),
        ]
    )

    blocking = [item["gate_id"] for item in gates if item["blocks_pilot"]]
    failed = [item["gate_id"] for item in gates if item["status"] == "failed"]
    status = "pilot_ready" if not blocking else ("failed" if failed else "gates_pending")
    return {
        "schema_version": "frame_internalization_pre_spend_readiness.v1",
        "audit_date": "2026-07-17",
        "status": status,
        "pilot_ready": not blocking,
        "scholar_review_blocks_compute": False,
        "blocking_gates": blocking,
        "failed_gates": failed,
        "passed_gate_count": sum(item["status"] == "passed" for item in gates),
        "blocking_gate_count": len(blocking),
        "gates": gates,
    }


def main() -> int:
    args = parse_args()
    try:
        report = audit(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 1
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else args.root.resolve() / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    if args.require_pilot_ready and not report["pilot_ready"]:
        return 2
    return 0 if not report["failed_gates"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
