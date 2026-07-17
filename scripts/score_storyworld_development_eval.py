#!/usr/bin/env python3
"""Score one adapter checkpoint on the frozen storyworld development suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.storyworld_evaluation import score_development_evaluation
from alignment_harness.storyworlds import read_json, sha256_file, write_json
from alignment_harness.trajectory_curriculum import read_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--arm", choices=("neutral", "constitutional", "jinn", "beast"), required=True)
    parser.add_argument("--checkpoint-tokens", type=int, choices=(1000000, 3000000, 6000000, 10000000), required=True)
    parser.add_argument("--checkpoint-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-provisional", action="store_true")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != "storyworld_development_eval_manifest_v1":
        raise ValueError("unexpected development evaluation manifest")
    if manifest["release_status"] != "review_approved" and not args.allow_provisional:
        raise ValueError("development evaluation remains provisional")
    public_path = manifest_path.parent / manifest["public_items"]["path"]
    key_path = manifest_path.parent / manifest["private_keys"]["path"]
    if sha256_file(public_path) != manifest["public_items"]["sha256"]:
        raise ValueError("development public item hash mismatch")
    if sha256_file(key_path) != manifest["private_keys"]["sha256"]:
        raise ValueError("development private key hash mismatch")
    predictions_path = args.predictions.resolve()
    checkpoint_path = args.checkpoint_receipt.resolve()
    checkpoint_manifest = read_json(checkpoint_path)
    if checkpoint_manifest.get("schema_version") != "storyworld_packed_curriculum_manifest_v1":
        raise ValueError("checkpoint receipt must be a packed curriculum manifest")
    if checkpoint_manifest.get("release_status") != "review_approved" and not args.allow_provisional:
        raise ValueError("checkpoint curriculum remains provisional")
    if args.arm not in checkpoint_manifest.get("arms", {}):
        raise ValueError("checkpoint manifest does not contain the requested arm")
    checkpoint_matches = [
        item
        for item in checkpoint_manifest["arms"][args.arm]["checkpoints"]
        if int(item["target_tokens"]) == args.checkpoint_tokens
    ]
    if len(checkpoint_matches) != 1:
        raise ValueError("checkpoint token boundary is absent or duplicated")
    tokenizer = checkpoint_manifest.get("tokenizer", {})
    if tokenizer.get("backend") != "huggingface_local" and not args.allow_provisional:
        raise ValueError("development selection requires the exact frozen Hugging Face tokenizer")
    score = score_development_evaluation(
        read_jsonl(public_path),
        read_jsonl(key_path),
        read_jsonl(predictions_path),
    )
    receipt = {
        **score,
        "suite_id": manifest["suite_id"],
        "development_manifest_sha256": sha256_file(manifest_path),
        "predictions_sha256": sha256_file(predictions_path),
        "arm": args.arm,
        "checkpoint_tokens": args.checkpoint_tokens,
        "checkpoint_receipt_sha256": sha256_file(checkpoint_path),
        "checkpoint_prefix_sha256": checkpoint_matches[0]["prefix_sha256"],
        "tokenizer_artifact_set_sha256": tokenizer.get(
            "tokenizer_artifact_set_sha256"
        ),
        "selection_use": "recipe_and_checkpoint_selection_only",
    }
    write_json(args.output.resolve(), receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
