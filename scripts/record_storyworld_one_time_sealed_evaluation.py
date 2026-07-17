#!/usr/bin/env python3
"""Record the externally executed sealed evaluation exactly once."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json


def record_sealed_evaluation(
    authorization_path: Path, external_results_path: Path
) -> dict:
    authorization_path = authorization_path.resolve()
    external_results_path = external_results_path.resolve()
    authorization = read_json(authorization_path)
    results = read_json(external_results_path)
    if authorization.get("schema_version") != "storyworld_one_time_unseal_authorization_v1" or not authorization.get(
        "passed"
    ):
        raise ValueError("invalid one-time unseal authorization")
    if authorization.get("status") != "authorized_not_yet_opened" or authorization.get(
        "sealed_content_opened"
    ) is not False:
        raise ValueError("one-time unseal authorization was not closed at issue time")
    if results.get("schema_version") != "storyworld_external_sealed_evaluation_result_v1":
        raise ValueError("unexpected external sealed result schema")
    if results.get("protocol_id") != authorization["protocol_id"]:
        raise ValueError("external sealed result belongs to another protocol")
    if results.get("unseal_authorization_id") != authorization[
        "unseal_authorization_id"
    ] or results.get("unseal_authorization_sha256") != sha256_file(authorization_path):
        raise ValueError("external result does not bind the exact unseal authorization")
    if int(results.get("evaluation_families", 0)) != int(
        authorization["evaluation_families"]
    ):
        raise ValueError("external result covers the wrong sealed family count")
    if results.get("training_rows_emitted") != 0:
        raise ValueError("sealed evaluation cannot emit training rows")
    if results.get("metric_or_contrast_changes_after_unseal") is not False:
        raise ValueError("external sealed analysis changed after unseal")
    expected_adapters = {
        (item["arm"], item["adapter_artifact_set_sha256"])
        for item in authorization["adapter_checkpoints"]
    }
    observed_adapters = {
        (item["arm"], item["adapter_artifact_set_sha256"])
        for item in results.get("adapter_checkpoints", [])
    }
    if observed_adapters != expected_adapters:
        raise ValueError("external sealed result evaluated different adapters")
    signed_at = datetime.fromisoformat(str(results.get("signed_at", "")).replace("Z", "+00:00"))
    if signed_at.tzinfo is None or signed_at.utcoffset() is None:
        raise ValueError("external sealed result timestamp must include a timezone")
    if not str(results.get("signature_or_external_receipt", "")).strip() or not results.get(
        "passed"
    ):
        raise ValueError("external sealed result lacks signature or completion status")
    body = {
        "schema_version": "storyworld_one_time_sealed_evaluation_receipt_v1",
        "protocol_id": authorization["protocol_id"],
        "unseal_authorization_id": authorization["unseal_authorization_id"],
        "unseal_authorization_sha256": sha256_file(authorization_path),
        "external_results_sha256": sha256_file(external_results_path),
        "external_results_content_sha256": sha256_json(results),
        "selected_checkpoint_tokens": authorization["selected_checkpoint_tokens"],
        "adapter_checkpoints": authorization["adapter_checkpoints"],
        "evaluation_families": authorization["evaluation_families"],
        "one_time_unseal": True,
        "sealed_content_opened": True,
        "training_rows_emitted": 0,
        "metric_or_contrast_changes_after_unseal": False,
        "result_summary": results.get("result_summary"),
        "additional_unseal_allowed": False,
        "claim_boundary": (
            "This records the sole sealed opening and the exact externally signed result. "
            "It cannot authorize another opening or retroactive analysis changes."
        ),
        "passed": True,
    }
    return {**body, "sealed_evaluation_id": f"sealed-eval-{sha256_json(body)[:24]}"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unseal-authorization", type=Path, required=True)
    parser.add_argument("--external-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record-one-time-sealed-evaluation", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.record_one_time_sealed_evaluation:
        raise ValueError(
            "writing the final receipt requires --record-one-time-sealed-evaluation"
        )
    output_path = args.output.resolve()
    if output_path.exists():
        raise ValueError("one-time sealed evaluation receipt already exists")
    receipt = record_sealed_evaluation(args.unseal_authorization, args.external_results)
    write_json(output_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
