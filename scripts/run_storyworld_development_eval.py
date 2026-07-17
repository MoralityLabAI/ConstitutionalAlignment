#!/usr/bin/env python3
"""Run one hash-bound public development-evaluation shard through a model command."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json, write_jsonl
from alignment_harness.trajectory_curriculum import read_jsonl


def _checkpoint(
    path: Path,
    arm: str,
    checkpoint_tokens: int,
    *,
    allow_provisional: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = read_json(path)
    if manifest.get("schema_version") != "storyworld_packed_curriculum_manifest_v1":
        raise ValueError("checkpoint receipt must be a packed curriculum manifest")
    if manifest.get("release_status") != "review_approved" and not allow_provisional:
        raise ValueError("checkpoint curriculum remains provisional")
    if arm not in manifest.get("arms", {}):
        raise ValueError("checkpoint manifest does not contain the requested arm")
    matches = [
        item
        for item in manifest["arms"][arm]["checkpoints"]
        if int(item["target_tokens"]) == checkpoint_tokens
    ]
    if len(matches) != 1:
        raise ValueError("checkpoint token boundary is absent or duplicated")
    if manifest.get("tokenizer", {}).get("backend") != "huggingface_local" and not allow_provisional:
        raise ValueError("development evaluation requires the exact frozen tokenizer")
    return manifest, matches[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--agent-command", required=True)
    parser.add_argument("--arm", choices=("neutral", "constitutional", "jinn", "beast"), required=True)
    parser.add_argument(
        "--checkpoint-tokens",
        type=int,
        choices=(1000000, 3000000, 6000000, 10000000),
        required=True,
    )
    parser.add_argument("--checkpoint-receipt", type=Path, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--allow-provisional", action="store_true")
    parser.add_argument("--authorize-evaluation-spend", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0 <= args.shard_index < args.shard_count:
        raise ValueError("shard index must be within the declared shard count")
    if not args.authorize_evaluation_spend:
        raise ValueError("model invocation requires --authorize-evaluation-spend")
    manifest_path = args.manifest.resolve()
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != "storyworld_development_eval_manifest_v1":
        raise ValueError("unexpected development evaluation manifest")
    if manifest["release_status"] != "review_approved" and not args.allow_provisional:
        raise ValueError("development evaluation remains provisional")
    public_path = manifest_path.parent / manifest["public_items"]["path"]
    if sha256_file(public_path) != manifest["public_items"]["sha256"]:
        raise ValueError("development public item hash mismatch")
    checkpoint_path = args.checkpoint_receipt.resolve()
    checkpoint_manifest, checkpoint = _checkpoint(
        checkpoint_path,
        args.arm,
        args.checkpoint_tokens,
        allow_provisional=args.allow_provisional,
    )
    all_items = read_jsonl(public_path)
    items = [
        item for index, item in enumerate(all_items) if index % args.shard_count == args.shard_index
    ]
    if not items:
        raise ValueError("selected development shard contains no items")

    output_dir = args.output_dir.resolve()
    shard_name = f"shard_{args.shard_index:04d}_of_{args.shard_count:04d}"
    predictions_path = output_dir / f"{shard_name}.jsonl"
    receipt_path = output_dir / f"{shard_name}.receipt.json"
    claim_path = output_dir / f"{shard_name}.claim.json"
    run_identity = {
        "development_manifest_sha256": sha256_file(manifest_path),
        "public_items_sha256": sha256_file(public_path),
        "checkpoint_manifest_sha256": sha256_file(checkpoint_path),
        "checkpoint_prefix_sha256": checkpoint["prefix_sha256"],
        "arm": args.arm,
        "checkpoint_tokens": args.checkpoint_tokens,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "agent_command": shlex.split(args.agent_command),
    }
    run_sha256 = sha256_json(run_identity)
    if receipt_path.is_file():
        receipt = read_json(receipt_path)
        if receipt.get("run_sha256") != run_sha256:
            raise ValueError("existing development receipt belongs to a different run")
        if not predictions_path.is_file() or sha256_file(predictions_path) != receipt.get(
            "predictions_sha256"
        ):
            raise ValueError("existing development predictions are missing or drifted")
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
        return 0
    if claim_path.is_file():
        claim = read_json(claim_path)
        if claim.get("run_sha256") != run_sha256:
            raise ValueError("existing development claim belongs to a different run")
        raise ValueError("incomplete development run claim exists; inspect it before retrying")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        claim_path,
        {
            "schema_version": "storyworld_development_eval_claim_v1",
            "run_sha256": run_sha256,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "items": len(items),
            "claim_boundary": "An absent completion receipt is ambiguous; do not silently replay paid inference.",
        },
    )

    command = shlex.split(args.agent_command)
    predictions = []
    provider_receipts = []
    for item in items:
        request = {
            "schema_version": "storyworld_development_eval_request_v1",
            "suite_id": manifest["suite_id"],
            "arm": args.arm,
            "checkpoint_tokens": args.checkpoint_tokens,
            "checkpoint_prefix_sha256": checkpoint["prefix_sha256"],
            "item": item,
        }
        process = subprocess.run(
            command,
            input=json.dumps(request, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=args.timeout_seconds,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(
                f"development command exited {process.returncode}: {process.stderr.strip()[:1000]}"
            )
        try:
            value = json.loads(process.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ValueError("development command must return one JSON object") from exc
        if not isinstance(value, dict):
            raise ValueError("development command response must be a JSON object")
        if set(value) == {"response", "provider_receipt"}:
            response = value["response"]
            provider_receipt = value["provider_receipt"]
            if not isinstance(response, dict) or not isinstance(provider_receipt, dict):
                raise ValueError("development command envelope values must be objects")
            provider_receipts.append(
                {"item_id": item["item_id"], "provider_receipt": provider_receipt}
            )
        else:
            response = value
        predictions.append(
            {
                "schema_version": "storyworld_development_eval_prediction_v1",
                "item_id": item["item_id"],
                "response": response,
                "request_sha256": sha256_json(request),
                "response_sha256": sha256_json(response),
            }
        )
    write_jsonl(predictions_path, predictions)
    receipt = {
        "schema_version": "storyworld_development_eval_run_receipt_v1",
        "run_sha256": run_sha256,
        "suite_id": manifest["suite_id"],
        "arm": args.arm,
        "checkpoint_tokens": args.checkpoint_tokens,
        "checkpoint_prefix_sha256": checkpoint["prefix_sha256"],
        "tokenizer_artifact_set_sha256": checkpoint_manifest["tokenizer"].get(
            "tokenizer_artifact_set_sha256"
        ),
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "items": len(predictions),
        "predictions_path": predictions_path.name,
        "predictions_sha256": sha256_file(predictions_path),
        "provider_receipts_sha256": sha256_json(provider_receipts),
        "private_key_opened": False,
        "training_rows_emitted": 0,
        "sealed_evaluation_content_opened": False,
        "passed": True,
    }
    write_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
