#!/usr/bin/env python3
"""Evaluate one local adapter checkpoint on a public development shard in one load."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.adapter_training import verify_local_model_fingerprint
from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json, write_jsonl
from alignment_harness.trajectory_curriculum import read_jsonl


def _directory_hash(path: Path) -> str:
    files = [
        {
            "path": candidate.relative_to(path).as_posix(),
            "bytes": candidate.stat().st_size,
            "sha256": sha256_file(candidate),
        }
        for candidate in sorted(item for item in path.rglob("*") if item.is_file())
    ]
    if not files:
        raise ValueError("adapter directory contains no files")
    return sha256_json(files)


def _extract_response(text: str) -> dict[str, Any] | str:
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return text.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--packing-manifest", type=Path, required=True)
    parser.add_argument("--base-freeze", type=Path, required=True)
    parser.add_argument("--training-receipt", type=Path, required=True)
    parser.add_argument("--adapter-checkpoint-receipt", type=Path, required=True)
    parser.add_argument(
        "--arm", choices=("neutral", "constitutional", "jinn", "beast"), required=True
    )
    parser.add_argument(
        "--checkpoint-tokens",
        type=int,
        choices=(1000000, 3000000, 6000000, 10000000),
        required=True,
    )
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--authorize-evaluation-spend", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.authorize_evaluation_spend:
        raise ValueError("local adapter evaluation requires --authorize-evaluation-spend")
    if not 0 <= args.shard_index < args.shard_count:
        raise ValueError("development shard index is outside the declared shard count")
    if int(os.environ.get("WORLD_SIZE", "1")) != 1:
        raise ValueError("local adapter evaluator is one process per shard")
    development_manifest_path = args.development_manifest.resolve()
    packing_manifest_path = args.packing_manifest.resolve()
    base_freeze_path = args.base_freeze.resolve()
    training_receipt_path = args.training_receipt.resolve()
    checkpoint_receipt_path = args.adapter_checkpoint_receipt.resolve()
    development = read_json(development_manifest_path)
    packing = read_json(packing_manifest_path)
    base_freeze = read_json(base_freeze_path)
    training = read_json(training_receipt_path)
    checkpoint = read_json(checkpoint_receipt_path)
    if development.get("schema_version") != "storyworld_development_eval_manifest_v1":
        raise ValueError("unexpected development evaluation manifest schema")
    if development.get("release_status") != "review_approved":
        raise ValueError("local adapter evaluation requires reviewed development worlds")
    if packing.get("schema_version") != "storyworld_packed_curriculum_manifest_v1" or packing.get(
        "release_status"
    ) != "review_approved":
        raise ValueError("local adapter evaluation requires a reviewed packed curriculum")
    if training.get("schema_version") != "storyworld_adapter_training_receipt_v1" or not training.get(
        "passed"
    ):
        raise ValueError("adapter training receipt is incomplete")
    if checkpoint.get("schema_version") != "storyworld_adapter_checkpoint_receipt_v1" or not checkpoint.get(
        "passed"
    ):
        raise ValueError("adapter checkpoint receipt is incomplete")
    if training.get("arm") != args.arm or checkpoint.get("arm") != args.arm:
        raise ValueError("adapter receipts belong to another arm")
    if int(checkpoint.get("target_tokens", 0)) != args.checkpoint_tokens:
        raise ValueError("adapter checkpoint receipt belongs to another token dose")
    if training.get("base_freeze_id") != base_freeze.get("base_freeze_id") or checkpoint.get(
        "base_freeze_id"
    ) != base_freeze.get("base_freeze_id"):
        raise ValueError("adapter receipts belong to another frozen base")
    if training.get("packing_manifest_sha256") != sha256_file(packing_manifest_path):
        raise ValueError("adapter was trained from another packed curriculum")
    packed_matches = [
        item
        for item in packing["arms"][args.arm]["checkpoints"]
        if int(item["target_tokens"]) == args.checkpoint_tokens
    ]
    if len(packed_matches) != 1 or checkpoint.get("packed_prefix_sha256") != packed_matches[0].get(
        "prefix_sha256"
    ):
        raise ValueError("adapter checkpoint does not bind the packed dose prefix")
    adapter_dir = checkpoint_receipt_path.parent / str(checkpoint["adapter_path"])
    if _directory_hash(adapter_dir) != checkpoint["adapter_artifact"][
        "artifact_set_sha256"
    ]:
        raise ValueError("adapter checkpoint artifacts drifted after training")
    verify_local_model_fingerprint(Path(base_freeze["model_dir"]), base_freeze)
    public_path = development_manifest_path.parent / development["public_items"]["path"]
    if sha256_file(public_path) != development["public_items"]["sha256"]:
        raise ValueError("development public items drifted")
    all_items = read_jsonl(public_path)
    items = [
        item
        for index, item in enumerate(all_items)
        if index % args.shard_count == args.shard_index
    ]
    if not items:
        raise ValueError("selected local development shard is empty")

    output_dir = args.output_dir.resolve()
    shard_name = f"{args.arm}_{args.checkpoint_tokens:08d}_shard_{args.shard_index:04d}_of_{args.shard_count:04d}"
    predictions_path = output_dir / f"{shard_name}.jsonl"
    claim_path = output_dir / f"{shard_name}.claim.json"
    receipt_path = output_dir / f"{shard_name}.receipt.json"
    run_identity = {
        "development_manifest_sha256": sha256_file(development_manifest_path),
        "public_items_sha256": sha256_file(public_path),
        "packing_manifest_sha256": sha256_file(packing_manifest_path),
        "base_freeze_sha256": sha256_file(base_freeze_path),
        "training_receipt_sha256": sha256_file(training_receipt_path),
        "checkpoint_receipt_sha256": sha256_file(checkpoint_receipt_path),
        "adapter_artifact_set_sha256": checkpoint["adapter_artifact"][
            "artifact_set_sha256"
        ],
        "arm": args.arm,
        "checkpoint_tokens": args.checkpoint_tokens,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "max_new_tokens": args.max_new_tokens,
        "runner_sha256": sha256_file(Path(__file__).resolve()),
    }
    run_sha256 = sha256_json(run_identity)
    if receipt_path.is_file():
        receipt = read_json(receipt_path)
        if receipt.get("run_sha256") != run_sha256:
            raise ValueError("existing local development receipt belongs to another run")
        if not predictions_path.is_file() or receipt.get("predictions_sha256") != sha256_file(
            predictions_path
        ):
            raise ValueError("existing local development predictions drifted")
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
        return 0
    if claim_path.is_file():
        claim = read_json(claim_path)
        if claim.get("run_sha256") != run_sha256:
            raise ValueError("existing local development claim belongs to another run")
        raise ValueError("incomplete local development claim exists; inspect it before retrying")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        claim_path,
        {
            "schema_version": "storyworld_local_adapter_development_claim_v1",
            "run_sha256": run_sha256,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "items": len(items),
            "status": "claimed_before_model_load",
            "private_key_opened": False,
            "sealed_evaluation_opened": False,
        },
    )

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise RuntimeError("local adapter development evaluation requires CUDA")
    random.seed(20260716)
    torch.manual_seed(20260716)
    tokenizer = AutoTokenizer.from_pretrained(
        str(base_freeze["tokenizer_dir"]),
        local_files_only=True,
        trust_remote_code=False,
        use_fast=True,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    base = AutoModelForCausalLM.from_pretrained(
        str(base_freeze["model_dir"]),
        local_files_only=True,
        trust_remote_code=False,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        ),
        device_map={"": 0},
        low_cpu_mem_usage=True,
    )
    model = PeftModel.from_pretrained(base, str(adapter_dir), is_trainable=False)
    model.eval()
    predictions = []
    invalid_json = 0
    device = next(parameter for parameter in model.parameters() if parameter.device.type == "cuda").device
    for item in items:
        messages = [
            *item["messages"],
            {
                "role": "user",
                "content": (
                    "Return only one JSON object satisfying this contract: "
                    + json.dumps(item["response_contract"], ensure_ascii=False, sort_keys=True)
                ),
            },
        ]
        rendered = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        encoded = tokenizer(rendered, return_tensors="pt", add_special_tokens=False)
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.inference_mode():
            generated = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        completion_ids = generated[0, encoded["input_ids"].shape[1] :]
        completion = tokenizer.decode(completion_ids, skip_special_tokens=True)
        response = _extract_response(completion)
        if not isinstance(response, dict):
            invalid_json += 1
        predictions.append(
            {
                "schema_version": "storyworld_development_eval_prediction_v1",
                "item_id": item["item_id"],
                "response": response,
                "request_sha256": sha256_json(
                    {
                        "arm": args.arm,
                        "checkpoint_tokens": args.checkpoint_tokens,
                        "packed_prefix_sha256": checkpoint["packed_prefix_sha256"],
                        "item": item,
                    }
                ),
                "response_sha256": sha256_json(response),
            }
        )
    write_jsonl(predictions_path, predictions)
    receipt = {
        "schema_version": "storyworld_local_adapter_development_run_receipt_v1",
        "run_sha256": run_sha256,
        "arm": args.arm,
        "checkpoint_tokens": args.checkpoint_tokens,
        "packed_prefix_sha256": checkpoint["packed_prefix_sha256"],
        "adapter_artifact_set_sha256": checkpoint["adapter_artifact"][
            "artifact_set_sha256"
        ],
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "items": len(predictions),
        "invalid_json_outputs": invalid_json,
        "predictions_path": predictions_path.name,
        "predictions_sha256": sha256_file(predictions_path),
        "base_loaded_once": True,
        "private_key_opened": False,
        "training_rows_emitted": 0,
        "sealed_evaluation_opened": False,
        "passed": True,
    }
    write_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
