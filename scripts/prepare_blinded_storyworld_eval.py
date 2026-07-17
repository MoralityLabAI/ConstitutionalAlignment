#!/usr/bin/env python3
"""Emit family-level author briefs without resolving sealed evaluation content."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import (
    read_json,
    sha256_file,
    validate_blinded_eval_protocol,
    validate_curriculum_package,
    write_json,
)


DEFAULT_PACKAGE = REPO_ROOT / "experiments" / "storyworld_curriculum_v1" / "package.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the closed blinded-evaluation protocol and optionally emit "
            "sanitized family-level author briefs. This command never reads sealed content."
        )
    )
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_path = args.package.resolve()
    package = read_json(package_path)
    split_path = (REPO_ROOT / str(package["split_freeze"])).resolve()
    protocol_path = (REPO_ROOT / str(package["blinded_eval_protocol"])).resolve()
    split_freeze = read_json(split_path)
    protocol = read_json(protocol_path)
    protocol_receipt = validate_blinded_eval_protocol(split_freeze, protocol)
    package_receipt = validate_curriculum_package(REPO_ROOT, package_path)

    briefs = {
        "schema_version": "storyworld_blinded_author_briefs_v1",
        "protocol_id": protocol["protocol_id"],
        "status": "sealed_content_unavailable",
        "allowed_family_fields": protocol["author_visibility"]["allowed_family_fields"],
        "forbidden_material": protocol["author_visibility"]["forbidden_material"],
        "structural_contract": protocol["structural_contract"],
        "evaluation_families": protocol["evaluation_families"],
        "claim_boundary": (
            "These briefs expose frozen family-level constructs only. They contain no evaluation "
            "prompt, legal action, outcome, private fact, trace, target, or content hash."
        ),
    }
    closed_gate_receipt = {
        "schema_version": "storyworld_closed_eval_gate_receipt_v1",
        "protocol_id": protocol["protocol_id"],
        "gate_status": "closed",
        "one_time_unseal": True,
        "package_sha256": sha256_file(package_path),
        "split_freeze_sha256": sha256_file(split_path),
        "protocol_sha256": sha256_file(protocol_path),
        "evaluation_families": protocol_receipt["evaluation_families"],
        "resolved_nonsealed_worlds": len(package_receipt["worlds"]),
        "required_frozen_receipts": protocol["unseal_gate"]["required_frozen_receipts"],
        "authorization_flag": protocol["unseal_gate"]["authorization_flag"],
        "sealed_content_opened": False,
        "passed": True,
    }
    authoring_receipt_template = {
        "schema_version": "storyworld_sealed_authoring_completion_v1",
        "protocol_id": protocol["protocol_id"],
        "status": "pending_external_access_controlled_authoring",
        "family_ids": [
            item["family_id"] for item in protocol["evaluation_families"]
        ],
        "approved_families": 0,
        "family_review_receipts": [],
        "structural_validation_receipts": [],
        "train_or_development_content_visible_to_authors": False,
        "candidate_adapter_outputs_visible_to_authors": False,
        "sealed_content_location_reference": None,
        "signed_at": None,
        "signature_or_external_receipt": None,
        "claim_boundary": (
            "Complete this receipt only inside the external access-controlled authoring "
            "environment. Do not place sealed prompts, actions, outcomes, or keys here."
        ),
    }
    result = {
        "author_briefs": briefs,
        "closed_gate_receipt": closed_gate_receipt,
        "sealed_authoring_receipt_template": authoring_receipt_template,
    }
    if args.output_dir is not None:
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / "AUTHOR_BRIEFS.json", briefs)
        write_json(output_dir / "CLOSED_GATE_RECEIPT.json", closed_gate_receipt)
        write_json(
            output_dir / "SEALED_AUTHORING_RECEIPT_TEMPLATE.json",
            authoring_receipt_template,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
