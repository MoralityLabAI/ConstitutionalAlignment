#!/usr/bin/env python3
"""Freeze a local base model and tokenizer for the adapter-spend experiment."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.adapter_training import fingerprint_local_model_dir
from alignment_harness.storyworlds import sha256_json, write_json
from alignment_harness.trajectory_curriculum import HuggingFaceTokenCounter


def build_base_freeze(
    model_dir: Path,
    tokenizer_dir: Path,
    *,
    model_id: str,
    model_revision: str,
    license_review_reference: str,
    reviewed_by: str,
) -> dict:
    model_dir = model_dir.resolve()
    tokenizer_dir = tokenizer_dir.resolve()
    if not model_id.strip() or not model_revision.strip() or model_revision.strip() == "main":
        raise ValueError("base freeze requires a stable model ID and non-main revision")
    if not license_review_reference.strip() or not reviewed_by.strip():
        raise ValueError("base freeze requires license-review attribution and reference")
    model_fingerprint = fingerprint_local_model_dir(model_dir)
    tokenizer = HuggingFaceTokenCounter(str(tokenizer_dir)).description
    body = {
        "schema_version": "storyworld_adapter_base_freeze_v1",
        "status": "frozen_not_training_authorization",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model_id,
        "model_revision": model_revision,
        "model_dir": str(model_dir),
        **model_fingerprint,
        "tokenizer_dir": str(tokenizer_dir),
        "tokenizer": tokenizer,
        "license_reviewed_by": reviewed_by,
        "license_review_reference": license_review_reference,
        "local_files_only": True,
        "training_authorized": False,
        "claim_boundary": (
            "This freezes local base and tokenizer bytes plus a license-review reference. "
            "It does not authorize adapter training or establish model suitability."
        ),
        "passed": True,
    }
    return {**body, "base_freeze_id": f"adapter-base-{sha256_json(body)[:24]}"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--tokenizer-dir", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--license-review-reference", required=True)
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = build_base_freeze(
        args.model_dir,
        args.tokenizer_dir,
        model_id=args.model_id,
        model_revision=args.model_revision,
        license_review_reference=args.license_review_reference,
        reviewed_by=args.reviewed_by,
    )
    write_json(args.output.resolve(), receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
