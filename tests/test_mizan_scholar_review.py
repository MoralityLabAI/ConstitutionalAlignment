import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.prepare_mizan_scholar_review_handoff import (
    build_queue,
    receipt_template,
    validate_completed_review,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BINDINGS = {
    "source_commit": "0" * 40,
    "conditions_sha256": "1" * 64,
    "queue_sha256": "2" * 64,
    "packet_sha256": "3" * 64,
    "receipt_schema_sha256": "4" * 64,
}


def test_queue_covers_full_cue_universe_without_source_labels_or_results():
    queue, private = build_queue(ROOT)
    assert len(queue) == 5
    assert sum(len(row["cues"]) for row in queue) == 15
    assert len(private) == 5
    public_text = str(queue)
    for prohibited in (
        "condition_id",
        "model_output",
        "action_selection",
        "switch_rate",
        "proxy_delta",
    ):
        assert prohibited not in public_text
    assert {cue["stage"] for row in queue for cue in row["cues"]} == {
        "initial",
        "evidence",
        "continuity",
    }
    assert all(len(row["sha256"]) == 64 for row in queue)


def test_untouched_scholar_template_fails_closed():
    queue, _ = build_queue(ROOT)
    template = receipt_template(queue, SOURCE_BINDINGS)
    with pytest.raises(ValueError, match="incomplete reviewer_id"):
        validate_completed_review(queue, template, SOURCE_BINDINGS)


def test_completed_scholar_receipt_passes_exact_validator_and_json_schema():
    queue, _ = build_queue(ROOT)
    receipt = receipt_template(queue, SOURCE_BINDINGS)
    receipt["reviewer"] = {
        "reviewer_id": "qualified-scholar-001",
        "role": "qualified_muslim_scholar",
        "external_to_author_team": True,
        "qualification_summary": "Independent scholar qualification recorded in the audit file.",
        "audit_identity_record_location": "private-governance-record-001",
        "conflicts_disclosed": True,
        "conflict_details": "No conflicts declared.",
    }
    receipt["review_timing_acknowledgments"] = {
        key: True for key in receipt["review_timing_acknowledgments"]
    }
    for family in receipt["family_reviews"]:
        family["inferred_construct"] = "Reviewer-provided construct description."
        for cue in family["cue_reviews"]:
            for result in cue["criterion_results"]:
                result["finding"] = "no_material_concern"
                result["comment"] = "No material concern identified for this criterion."
        for result in family["family_criterion_results"]:
            result["finding"] = "not_applicable"
            result["comment"] = "Not applicable to this family as interpreted."
        family["overall_finding"] = "no_material_concern"
        family["summary"] = "No material concern identified in this family."
    receipt["overall_assessment"] = "no_material_concern_for_limited_descriptive_use"
    receipt["overall_comment"] = "Limited descriptive use only; no broader claim is implied."
    receipt["reviewed_at"] = "2026-07-20T12:00:00-04:00"

    validate_completed_review(queue, receipt, SOURCE_BINDINGS)
    schema = json.loads(
        (ROOT / "schemas/mizan_scholar_review_receipt_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(receipt)
