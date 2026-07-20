#!/usr/bin/env python3
"""Prepare a hash-bound, full-cue Mizan scholar-review handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
NAMESPACE = "mizan-scholar-review-v1"
PLACEHOLDER = "REPLACE_ME"
PLACEHOLDER_TIME = "REPLACE_WITH_ISO_8601_TIMEZONE_TIMESTAMP"
ATTESTATION = (
    "I reviewed every cue in the exact hash-bound packet, without consulting model outputs "
    "or result statistics, and understand that this post-result review cannot make the "
    "exploratory run confirmatory."
)
CUE_CRITERIA = [
    "theological_accuracy_and_tone",
    "intended_construct_fit",
    "confound_or_misuse_risk",
]
FAMILY_CRITERIA = [
    "semantic_continuity_across_stages",
    "comparator_distinctness",
    "final_accountability_operationalization",
    "unreliable_authority_control_coherence",
]
FINDINGS = {
    "no_material_concern",
    "material_concern",
    "revision_recommended_for_future_use",
    "not_applicable",
    "unable_to_assess",
}
OVERALL_ASSESSMENTS = {
    "no_material_concern_for_limited_descriptive_use",
    "material_concerns_require_disclosure",
    "unsuitable_for_theological_interpretation",
    "unable_to_assess",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def opaque_id(kind: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join((NAMESPACE, kind, *parts)).encode("utf-8")).hexdigest()
    return f"MZS-{kind.upper()}-{digest[:12]}"


def git_head(repo_root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()


def git_tracked_clean(repo_root: Path) -> bool:
    return not subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo_root, text=True
    ).strip()


def build_queue(repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conditions_path = repo_root / "experiments/mizan_rooms_v1/conditions.json"
    source = read_json(conditions_path)
    conditions = source.get("conditions")
    if source.get("schema_version") != "mizan_conditions_v1" or not isinstance(conditions, list):
        raise ValueError("unexpected Mizan conditions schema")
    if len(conditions) != 5 or len({str(item.get("id")) for item in conditions}) != 5:
        raise ValueError("expected five unique cue families")

    stages = [("initial", "initial_cue"), ("evidence", "evidence_cue"), ("continuity", "continuity_cue")]
    queue_rows: list[dict[str, Any]] = []
    private_rows: list[dict[str, Any]] = []
    for condition in conditions:
        condition_id = str(condition["id"])
        family_id = opaque_id("family", condition_id)
        public_cues = []
        private_cues = []
        for stage, key in stages:
            text = condition.get(key)
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"{condition_id}: missing {key}")
            cue_id = opaque_id("cue", condition_id, stage)
            public_cues.append(
                {
                    "review_cue_id": cue_id,
                    "stage": stage,
                    "text": text,
                }
            )
            private_cues.append(
                {
                    "review_cue_id": cue_id,
                    "source_field": key,
                }
            )
        payload = {
            "schema_version": "mizan_cue_review_family_v1",
            "review_family_id": family_id,
            "register": str(condition.get("register", "")),
            "cues": public_cues,
        }
        queue_rows.append({**payload, "sha256": sha256_json(payload)})
        private_rows.append(
            {
                "review_family_id": family_id,
                "condition_id": condition_id,
                "source_path": "experiments/mizan_rooms_v1/conditions.json",
                "cues": private_cues,
            }
        )
    queue_rows.sort(key=lambda item: str(item["review_family_id"]))
    private_rows.sort(key=lambda item: str(item["review_family_id"]))
    if sum(len(row["cues"]) for row in queue_rows) != 15:
        raise ValueError("full 15-cell cue universe is incomplete")
    return queue_rows, private_rows


def criterion_templates(criterion_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "criterion_id": criterion_id,
            "finding": None,
            "comment": PLACEHOLDER,
        }
        for criterion_id in criterion_ids
    ]


def receipt_template(
    queue_rows: list[dict[str, Any]], source_bindings: dict[str, str]
) -> dict[str, Any]:
    return {
        "schema_version": "mizan_scholar_review_receipt.v1",
        "review_contract_id": "mizan_cue_scholar_review_v1",
        "source_bindings": source_bindings,
        "reviewer": {
            "reviewer_id": PLACEHOLDER,
            "role": "qualified_muslim_scholar",
            "external_to_author_team": False,
            "qualification_summary": PLACEHOLDER,
            "audit_identity_record_location": PLACEHOLDER,
            "conflicts_disclosed": None,
            "conflict_details": PLACEHOLDER,
        },
        "review_timing_acknowledgments": {
            "model_outcomes_preexisted_this_review": True,
            "model_outputs_not_consulted": False,
            "result_statistics_not_consulted": False,
            "historical_fielded_cues_will_not_be_silently_edited": False,
            "all_findings_will_be_reported": False,
        },
        "family_reviews": [
            {
                "review_family_id": row["review_family_id"],
                "queue_row_sha256": row["sha256"],
                "inferred_construct": PLACEHOLDER,
                "cue_reviews": [
                    {
                        "review_cue_id": cue["review_cue_id"],
                        "criterion_results": criterion_templates(CUE_CRITERIA),
                    }
                    for cue in row["cues"]
                ],
                "family_criterion_results": criterion_templates(FAMILY_CRITERIA),
                "overall_finding": None,
                "summary": PLACEHOLDER,
                "recommended_future_changes": [],
            }
            for row in queue_rows
        ],
        "overall_assessment": None,
        "overall_comment": PLACEHOLDER,
        "reviewed_at": PLACEHOLDER_TIME,
        "attestation": ATTESTATION,
    }


def require_completed_text(value: Any, field: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum or value.startswith("REPLACE"):
        raise ValueError(f"incomplete {field}")
    return value


def validate_criterion_results(
    results: Any, expected_ids: list[str], field: str
) -> None:
    if not isinstance(results, list) or len(results) != len(expected_ids):
        raise ValueError(f"{field}: criterion count drifted")
    ids = [str(item.get("criterion_id")) for item in results]
    if len(set(ids)) != len(ids) or set(ids) != set(expected_ids):
        raise ValueError(f"{field}: criterion universe drifted")
    for result in results:
        if result.get("finding") not in FINDINGS:
            raise ValueError(f"{field}: invalid or incomplete finding")
        require_completed_text(result.get("comment"), f"{field} comment")


def validate_completed_review(
    queue_rows: list[dict[str, Any]], receipt: dict[str, Any], source_bindings: dict[str, str]
) -> None:
    if receipt.get("schema_version") != "mizan_scholar_review_receipt.v1":
        raise ValueError("receipt schema drifted")
    if receipt.get("review_contract_id") != "mizan_cue_scholar_review_v1":
        raise ValueError("review contract drifted")
    if receipt.get("source_bindings") != source_bindings:
        raise ValueError("source bindings drifted")

    reviewer = receipt.get("reviewer")
    if not isinstance(reviewer, dict):
        raise ValueError("reviewer record missing")
    require_completed_text(reviewer.get("reviewer_id"), "reviewer_id")
    if reviewer.get("role") != "qualified_muslim_scholar":
        raise ValueError("reviewer role drifted")
    if reviewer.get("external_to_author_team") is not True:
        raise ValueError("reviewer must attest that they are external to the author team")
    require_completed_text(reviewer.get("qualification_summary"), "qualification_summary", 20)
    require_completed_text(reviewer.get("audit_identity_record_location"), "audit_identity_record_location")
    if reviewer.get("conflicts_disclosed") is not True:
        raise ValueError("conflicts disclosure must be attested")
    require_completed_text(reviewer.get("conflict_details"), "conflict_details")

    acknowledgments = receipt.get("review_timing_acknowledgments")
    required_acknowledgments = {
        "model_outcomes_preexisted_this_review",
        "model_outputs_not_consulted",
        "result_statistics_not_consulted",
        "historical_fielded_cues_will_not_be_silently_edited",
        "all_findings_will_be_reported",
    }
    if not isinstance(acknowledgments, dict) or set(acknowledgments) != required_acknowledgments:
        raise ValueError("review timing acknowledgment universe drifted")
    if any(value is not True for value in acknowledgments.values()):
        raise ValueError("every review timing acknowledgment must be true")

    queue = {str(row["review_family_id"]): row for row in queue_rows}
    family_reviews = receipt.get("family_reviews")
    if not isinstance(family_reviews, list) or len(family_reviews) != len(queue):
        raise ValueError("family review count drifted")
    received_ids = [str(row.get("review_family_id")) for row in family_reviews]
    if len(set(received_ids)) != len(received_ids) or set(received_ids) != set(queue):
        raise ValueError("family review universe drifted")
    for family_review in family_reviews:
        family_id = str(family_review["review_family_id"])
        source = queue[family_id]
        if family_review.get("queue_row_sha256") != source["sha256"]:
            raise ValueError(f"{family_id}: queue-row hash drifted")
        require_completed_text(family_review.get("inferred_construct"), f"{family_id} inferred_construct")
        cue_source = {str(cue["review_cue_id"]): cue for cue in source["cues"]}
        cue_reviews = family_review.get("cue_reviews")
        if not isinstance(cue_reviews, list) or len(cue_reviews) != len(cue_source):
            raise ValueError(f"{family_id}: cue review count drifted")
        cue_ids = [str(cue.get("review_cue_id")) for cue in cue_reviews]
        if len(set(cue_ids)) != len(cue_ids) or set(cue_ids) != set(cue_source):
            raise ValueError(f"{family_id}: cue review universe drifted")
        for cue_review in cue_reviews:
            cue_id = str(cue_review["review_cue_id"])
            validate_criterion_results(
                cue_review.get("criterion_results"), CUE_CRITERIA, f"{family_id}/{cue_id}"
            )
        validate_criterion_results(
            family_review.get("family_criterion_results"), FAMILY_CRITERIA, family_id
        )
        if family_review.get("overall_finding") not in FINDINGS:
            raise ValueError(f"{family_id}: invalid or incomplete overall_finding")
        require_completed_text(family_review.get("summary"), f"{family_id} summary")
        changes = family_review.get("recommended_future_changes")
        if not isinstance(changes, list) or any(
            not isinstance(item, str) or not item.strip() for item in changes
        ):
            raise ValueError(f"{family_id}: invalid recommended_future_changes")

    if receipt.get("overall_assessment") not in OVERALL_ASSESSMENTS:
        raise ValueError("invalid or incomplete overall_assessment")
    require_completed_text(receipt.get("overall_comment"), "overall_comment")
    reviewed_at = require_completed_text(receipt.get("reviewed_at"), "reviewed_at")
    try:
        parsed_reviewed_at = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("reviewed_at must be an ISO-8601 timestamp") from exc
    if parsed_reviewed_at.tzinfo is None:
        raise ValueError("reviewed_at must include a timezone")
    if receipt.get("attestation") != ATTESTATION:
        raise ValueError("attestation drifted")


def review_packet(queue_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Mīzān cue scholar-review packet v1",
        "",
        "Status: post-result review of exact fielded wording; scholar findings are not yet present.",
        "",
        "Please review every cue family and every cue below before consulting the source repository, model outputs, action selections, or result statistics. Model outcomes existed before this packet was frozen. The packet contains all 15 fielded cue cells, with no outcome-based selection.",
        "",
        "The opaque IDs withhold source condition labels, but the wording necessarily reveals much of its semantic intent. Semantic blinding is therefore impossible and is not claimed. Record the construct you infer rather than trying to guess a hidden label.",
        "",
        "For each cue, assess:",
        "",
        "- `theological_accuracy_and_tone`: material accuracy, respect, proportion, and appropriateness of any theological or spiritual characterization; use `not_applicable` only when appropriate.",
        "- `intended_construct_fit`: whether the wording coherently operationalizes the construct you infer.",
        "- `confound_or_misuse_risk`: conceptual overlap or misleading implications involving observation, omniscience, authority, recording, judgment, or other salient concepts.",
        "",
        "For each three-cue family, also assess semantic continuity, comparator distinctness, final-accountability operationalization when applicable, and unreliable-authority-control coherence when applicable.",
        "",
        "Allowed findings are `no_material_concern`, `material_concern`, `revision_recommended_for_future_use`, `not_applicable`, and `unable_to_assess`. Explain every finding. There is no numeric pass threshold. All concerns and recommended changes will be disclosed, while exact fielded wording remains immutable historical evidence.",
        "",
        "A completed receipt supports only a factual report of this scholar's findings. It cannot make the exploratory run confirmatory or establish normative improvement, eschatological specificity, theological truth, or frame internalization.",
        "",
    ]
    for index, row in enumerate(queue_rows, start=1):
        lines.extend(
            [
                f"## Family {index}: `{row['review_family_id']}`",
                "",
                f"Queue-row SHA-256: `{row['sha256']}`",
                "",
            ]
        )
        for cue in row["cues"]:
            lines.extend(
                [
                    f"### `{cue['review_cue_id']}` — {cue['stage']}",
                    "",
                    str(cue["text"]),
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def prepare_handoff(
    repo_root: Path,
    output_dir: Path,
    private_dir: Path,
    expected_source_commit: str,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    private_dir = private_dir.resolve()
    if output_dir.exists() or private_dir.exists():
        raise ValueError("output and private directories must not already exist")
    head = git_head(repo_root)
    if head != expected_source_commit:
        raise ValueError(f"source commit mismatch: expected {expected_source_commit}, found {head}")
    if not git_tracked_clean(repo_root):
        raise ValueError("tracked worktree must be clean before handoff generation")

    conditions_path = repo_root / "experiments/mizan_rooms_v1/conditions.json"
    suite_path = repo_root / "experiments/mizan_rooms_v1/suite.json"
    schema_path = repo_root / "schemas/mizan_scholar_review_receipt_v1.schema.json"
    queue_rows, private_rows = build_queue(repo_root)
    output_dir.mkdir(parents=True)
    private_dir.mkdir(parents=True)
    queue_path = output_dir / "CUE_REVIEW_QUEUE.jsonl"
    packet_path = output_dir / "SCHOLAR_REVIEW_PACKET.md"
    copied_schema_path = output_dir / "RECEIPT_SCHEMA.json"
    template_path = output_dir / "SCHOLAR_REVIEW_TEMPLATE.json"
    private_map_path = private_dir / "cue_condition_blinding_map.jsonl"
    write_jsonl(queue_path, queue_rows)
    packet_path.write_text(review_packet(queue_rows), encoding="utf-8", newline="\n")
    shutil.copyfile(schema_path, copied_schema_path)
    write_jsonl(private_map_path, private_rows)

    source_bindings = {
        "source_commit": head,
        "conditions_sha256": sha256_file(conditions_path),
        "queue_sha256": sha256_file(queue_path),
        "packet_sha256": sha256_file(packet_path),
        "receipt_schema_sha256": sha256_file(copied_schema_path),
    }
    template = receipt_template(queue_rows, source_bindings)
    try:
        validate_completed_review(queue_rows, template, source_bindings)
    except ValueError as exc:
        template_rejection = f"{type(exc).__name__}: {exc}"
    else:
        raise ValueError("untouched scholar template unexpectedly passed validation")
    write_json(template_path, template)

    public_files = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in (queue_path, packet_path, copied_schema_path, template_path)
    }
    body = {
        "schema_version": "mizan_scholar_review_handoff_v1",
        "status": "template_incomplete_external_scholar_review_required",
        "classification": "post_result_full_cue_universe_scholar_review",
        "source_commit": head,
        "timing_attestation": {
            "model_outcomes_existed_before_handoff_freeze": True,
            "cue_cells_selected_using_model_outputs_or_results": False,
            "all_fielded_cue_cells_included": True,
            "model_outputs_or_action_selections_in_packet": False,
            "result_statistics_in_packet": False,
            "source_condition_labels_in_packet": False,
            "semantic_blinding_claimed": False,
        },
        "source_files": {
            "experiments/mizan_rooms_v1/conditions.json": sha256_file(conditions_path),
            "experiments/mizan_rooms_v1/suite.json": sha256_file(suite_path),
            "schemas/mizan_scholar_review_receipt_v1.schema.json": sha256_file(schema_path),
        },
        "counts": {
            "cue_families": len(queue_rows),
            "cue_cells": sum(len(row["cues"]) for row in queue_rows),
            "qualified_external_scholars_required": 1,
            "cue_criterion_findings_required": 45,
            "family_criterion_findings_required": 20,
        },
        "public_files": public_files,
        "private_condition_map": {
            "tracked_in_git": False,
            "path": str(private_map_path),
            "rows": len(private_rows),
            "sha256": sha256_file(private_map_path),
        },
        "untouched_template_rejected": True,
        "template_rejection": template_rejection,
        "interpretation_rules": [
            "Report every finding and recommended change; do not add a post-result numeric pass threshold.",
            "A receipt supports only a factual statement of the exact review and its findings.",
            "The exact fielded cues remain immutable; revisions create prospective versions.",
            "Scholar review cannot make this exploratory run confirmatory.",
            "Scholar review alone cannot establish normative improvement, eschatological specificity, theological truth, or frame internalization.",
        ],
        "scholar_review_complete": False,
        "normative_claims_allowed": False,
        "handoff_structural_validation_passed": True,
    }
    manifest = {**body, "handoff_content_sha256": sha256_json(body)}
    write_json(output_dir / "HANDOFF_MANIFEST.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = prepare_handoff(
        args.repo_root, args.output_dir, args.private_dir, args.source_commit
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
