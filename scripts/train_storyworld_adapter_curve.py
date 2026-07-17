#!/usr/bin/env python3
"""Train one ordered four-dose QLoRA arm from a reviewed packed curriculum."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.adapter_training import (
    audit_packed_curriculum_for_training,
    render_assistant_only_example,
    verify_local_model_fingerprint,
)
from alignment_harness.storyworlds import read_json, sha256_file, sha256_json, write_json
from alignment_harness.trajectory_curriculum import HuggingFaceTokenCounter, read_jsonl


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _directory_manifest(path: Path) -> dict[str, Any]:
    files = []
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        files.append(
            {
                "path": candidate.relative_to(path).as_posix(),
                "bytes": candidate.stat().st_size,
                "sha256": sha256_file(candidate),
            }
        )
    if not files:
        raise ValueError(f"adapter checkpoint contains no files: {path}")
    return {
        "artifact_set_sha256": sha256_json(files),
        "files": files,
        "total_bytes": sum(int(item["bytes"]) for item in files),
    }


def validate_training_authorization(
    authorization: dict[str, Any],
    *,
    authorization_path: Path,
    training_recipe_path: Path,
    token_recipe_path: Path,
    packing_manifest_path: Path,
    base_freeze_path: Path,
    output_root: Path,
    arm: str,
    authorize_spend: bool,
) -> None:
    if authorization.get("schema_version") != "storyworld_adapter_training_authorization_v1":
        raise ValueError("unexpected adapter training authorization schema")
    if authorization.get("status") != "authorized" or not authorization.get("passed"):
        raise ValueError("adapter training authorization is not active")
    expected_hashes = {
        "training_recipe_sha256": sha256_file(training_recipe_path),
        "token_recipe_sha256": sha256_file(token_recipe_path),
        "packing_manifest_sha256": sha256_file(packing_manifest_path),
        "base_freeze_sha256": sha256_file(base_freeze_path),
        "trainer_sha256": sha256_file(Path(__file__).resolve()),
    }
    for key, expected in expected_hashes.items():
        if authorization.get(key) != expected:
            raise ValueError(f"adapter training authorization hash mismatch: {key}")
    if Path(str(authorization.get("authorized_output_root", ""))).resolve() != output_root:
        raise ValueError("adapter output root differs from its authorization")
    if arm not in authorization.get("authorized_arms", []):
        raise ValueError("adapter arm is outside the training authorization")
    if (
        float(authorization.get("max_total_gpu_hours", 0)) <= 0
        or float(authorization.get("max_gpu_hours_per_arm", 0)) <= 0
        or authorization.get("gpu_hour_allocation_policy")
        != "equal_nontransferable_ceiling_per_matched_arm"
    ):
        raise ValueError("adapter authorization lacks valid total/per-arm GPU ceilings")
    if not authorization_path.is_file():
        raise ValueError("adapter authorization file is missing")
    if not authorize_spend:
        raise ValueError("adapter training requires explicit --authorize-adapter-training-spend")


def _optimizer_steps(row_count: int, flush_rows: set[int], accumulation: int) -> int:
    steps = 0
    pending = 0
    for index in range(1, row_count + 1):
        pending += 1
        if pending >= accumulation or index in flush_rows or index == row_count:
            steps += 1
            pending = 0
    return steps


def _audit_tokenized_arm(
    tokenizer: Any,
    rows: list[dict[str, Any]],
    *,
    max_sequence_tokens: int,
    minimum_supervised_tokens: int,
    minimum_supervised_tokens_by_slice: dict[str, int],
) -> dict[str, Any]:
    supervised = 0
    packed = 0
    maximum = 0
    maximum_record_id = None
    supervised_by_slice: dict[str, int] = {}
    for row in rows:
        encoded = render_assistant_only_example(tokenizer, row["messages"])
        expected = int(row["token_counts"]["packed"])
        expected_supervised = int(
            row["token_counts"]["loss_bearing_assistant"]
        )
        if encoded["packed_tokens"] != expected:
            raise ValueError(
                f"training tokenizer count drift for {row['record_id']}: "
                f"{encoded['packed_tokens']} != {expected}"
            )
        if encoded["supervised_tokens"] != expected_supervised:
            raise ValueError(
                f"training assistant-mask count drift for {row['record_id']}: "
                f"{encoded['supervised_tokens']} != {expected_supervised}"
            )
        if encoded["packed_tokens"] > max_sequence_tokens:
            raise ValueError(
                f"frozen row {row['record_id']} exceeds max_sequence_tokens; "
                "truncation is forbidden"
            )
        packed += int(encoded["packed_tokens"])
        supervised += int(encoded["supervised_tokens"])
        slice_id = str(row["slice"])
        supervised_by_slice[slice_id] = supervised_by_slice.get(slice_id, 0) + int(
            encoded["supervised_tokens"]
        )
        if encoded["packed_tokens"] > maximum:
            maximum = int(encoded["packed_tokens"])
            maximum_record_id = str(row["record_id"])
    if supervised < minimum_supervised_tokens:
        raise ValueError(
            "actual assistant-only labels miss the frozen per-arm assistant-token minimum"
        )
    for slice_id, minimum in minimum_supervised_tokens_by_slice.items():
        if supervised_by_slice.get(slice_id, 0) < int(minimum):
            raise ValueError(
                f"actual assistant-only labels miss the frozen {slice_id} minimum"
            )
    return {
        "rows": len(rows),
        "packed_tokens": packed,
        "actual_supervised_tokens": supervised,
        "minimum_supervised_tokens": minimum_supervised_tokens,
        "supervised_tokens_by_slice": supervised_by_slice,
        "maximum_sequence_tokens": maximum,
        "maximum_sequence_record_id": maximum_record_id,
        "truncated_rows": 0,
        "nonassistant_loss_tokens": 0,
        "passed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-recipe", type=Path, required=True)
    parser.add_argument("--token-recipe", type=Path, required=True)
    parser.add_argument("--packing-manifest", type=Path, required=True)
    parser.add_argument("--base-freeze", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument(
        "--arm", choices=("neutral", "constitutional", "jinn", "beast"), required=True
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--authorize-adapter-training-spend", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    training_recipe_path = args.training_recipe.resolve()
    token_recipe_path = args.token_recipe.resolve()
    packing_manifest_path = args.packing_manifest.resolve()
    base_freeze_path = args.base_freeze.resolve()
    authorization_path = args.authorization.resolve()
    output_root = args.output_root.resolve()
    authorization = read_json(authorization_path)
    validate_training_authorization(
        authorization,
        authorization_path=authorization_path,
        training_recipe_path=training_recipe_path,
        token_recipe_path=token_recipe_path,
        packing_manifest_path=packing_manifest_path,
        base_freeze_path=base_freeze_path,
        output_root=output_root,
        arm=args.arm,
        authorize_spend=args.authorize_adapter_training_spend,
    )
    training_recipe = read_json(training_recipe_path)
    token_recipe = read_json(token_recipe_path)
    packing_manifest = read_json(packing_manifest_path)
    base_freeze = read_json(base_freeze_path)
    audit = audit_packed_curriculum_for_training(
        packing_manifest_path, training_recipe, token_recipe
    )
    if base_freeze.get("base_freeze_id") != authorization.get("base_freeze_id"):
        raise ValueError("adapter authorization belongs to a different base freeze")
    model_dir = Path(str(base_freeze["model_dir"])).resolve()
    tokenizer_dir = Path(str(base_freeze["tokenizer_dir"])).resolve()
    verify_local_model_fingerprint(model_dir, base_freeze)
    counter = HuggingFaceTokenCounter(str(tokenizer_dir))
    if counter.description.get("tokenizer_artifact_set_sha256") != authorization.get(
        "tokenizer_artifact_set_sha256"
    ):
        raise ValueError("frozen tokenizer bytes drifted after authorization")
    if counter.description.get("tokenizer_artifact_set_sha256") != audit[
        "tokenizer"
    ].get("tokenizer_artifact_set_sha256"):
        raise ValueError("training tokenizer differs from packed curriculum tokenizer")

    arm_manifest = packing_manifest["arms"][args.arm]
    arm_path = (packing_manifest_path.parent / str(arm_manifest["path"])).resolve()
    rows = read_jsonl(arm_path)
    final_checkpoint = arm_manifest["checkpoints"][-1]
    final_row = int(final_checkpoint["reached_after_row"])
    if final_row != len(rows):
        raise ValueError("final adapter dose must consume the complete quota-satisfying stream")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        str(tokenizer_dir), local_files_only=True, trust_remote_code=False, use_fast=True
    )
    input_audit = _audit_tokenized_arm(
        tokenizer,
        rows,
        max_sequence_tokens=int(training_recipe["max_sequence_tokens"]),
        minimum_supervised_tokens=int(token_recipe["minimum_assistant_tokens_per_arm"]),
        minimum_supervised_tokens_by_slice={
            str(key): int(value)
            for key, value in token_recipe[
                "minimum_assistant_tokens_by_slice"
            ].items()
        },
    )
    checkpoints_by_row = {
        int(item["reached_after_row"]): item for item in arm_manifest["checkpoints"]
    }
    flush_rows = set(checkpoints_by_row)
    accumulation = int(training_recipe["optimizer"]["gradient_accumulation_rows"])
    optimizer_steps = _optimizer_steps(len(rows), flush_rows, accumulation)

    run_dir = output_root / args.arm
    claim_path = run_dir / "RUN_CLAIM.json"
    receipt_path = run_dir / "TRAINING_RECEIPT.json"
    run_identity = {
        "authorization_sha256": sha256_file(authorization_path),
        "authorization_id": authorization["authorization_id"],
        "arm": args.arm,
        "arm_file_sha256": sha256_file(arm_path),
        "base_freeze_sha256": sha256_file(base_freeze_path),
        "training_recipe_sha256": sha256_file(training_recipe_path),
        "trainer_sha256": sha256_file(Path(__file__).resolve()),
    }
    run_sha256 = sha256_json(run_identity)
    if receipt_path.is_file():
        receipt = read_json(receipt_path)
        if receipt.get("run_sha256") != run_sha256:
            raise ValueError("existing adapter receipt belongs to a different run")
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
        return 0
    if claim_path.is_file():
        claim = read_json(claim_path)
        if claim.get("run_sha256") != run_sha256:
            raise ValueError("existing adapter claim belongs to a different run")
        raise ValueError(
            "incomplete adapter training claim exists; inspect checkpoints and compute state "
            "before issuing a new explicit authorization"
        )
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(
        run_dir / "INPUT_AUDIT.json",
        {
            "schema_version": "storyworld_adapter_training_input_audit_v1",
            "run_sha256": run_sha256,
            "arm": args.arm,
            "packed_curriculum_audit": audit["arms"][args.arm],
            "tokenization": input_audit,
            "optimizer_steps": optimizer_steps,
            "checkpoint_rows": sorted(flush_rows),
            "passed": True,
        },
    )
    write_json(
        claim_path,
        {
            "schema_version": "storyworld_adapter_training_claim_v1",
            "run_sha256": run_sha256,
            **run_identity,
            "hostname": socket.gethostname(),
            "process_id": os.getpid(),
            "created_at": utc_now(),
            "max_total_gpu_hours": authorization["max_total_gpu_hours"],
            "max_gpu_hours_per_arm": authorization["max_gpu_hours_per_arm"],
            "status": "claimed_before_model_load",
            "claim_boundary": (
                "An absent TRAINING_RECEIPT.json after this claim is ambiguous compute. "
                "Do not silently rerun under the same authorization."
            ),
        },
    )

    import torch
    import torch.nn.functional as functional
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoConfig,
        AutoModelForCausalLM,
        BitsAndBytesConfig,
        get_cosine_schedule_with_warmup,
    )

    if not torch.cuda.is_available():
        raise RuntimeError("authorized QLoRA training requires one CUDA device")
    if int(os.environ.get("WORLD_SIZE", "1")) != 1:
        raise RuntimeError("v1 exact-dose trainer is single-process; WORLD_SIZE must equal 1")
    seed = int(training_recipe["runtime"]["seed"])
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    compute_dtype = (
        torch.bfloat16
        if training_recipe["quantization"]["compute_dtype"] == "bfloat16"
        and torch.cuda.is_bf16_supported()
        else torch.float16
    )
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=bool(
            training_recipe["quantization"]["double_quantization"]
        ),
        bnb_4bit_compute_dtype=compute_dtype,
    )
    config = AutoConfig.from_pretrained(
        str(model_dir), local_files_only=True, trust_remote_code=False
    )
    if getattr(config, "pad_token_id", None) is None:
        config.pad_token_id = tokenizer.pad_token_id or tokenizer.eos_token_id
    model = AutoModelForCausalLM.from_pretrained(
        str(model_dir),
        config=config,
        local_files_only=True,
        trust_remote_code=False,
        quantization_config=quantization,
        device_map={"": 0},
        low_cpu_mem_usage=True,
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    lora = training_recipe["lora"]
    target_suffixes = list(map(str, lora["target_module_suffixes"]))
    matched_modules = sorted(
        name
        for name, _ in model.named_modules()
        if any(name.endswith(suffix) for suffix in target_suffixes)
    )
    if not matched_modules:
        raise RuntimeError("no frozen LoRA target module suffix matched the base model")
    model = get_peft_model(
        model,
        LoraConfig(
            r=int(lora["rank"]),
            lora_alpha=int(lora["alpha"]),
            lora_dropout=float(lora["dropout"]),
            bias=str(lora["bias"]),
            task_type="CAUSAL_LM",
            target_modules=target_suffixes,
        ),
    )
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    trainable_params = sum(parameter.numel() for parameter in trainable)
    if trainable_params <= 0:
        raise RuntimeError("adapter construction produced no trainable parameters")
    optimizer_config = training_recipe["optimizer"]
    optimizer = torch.optim.AdamW(
        trainable,
        lr=float(optimizer_config["learning_rate"]),
        weight_decay=float(optimizer_config["weight_decay"]),
    )
    warmup_steps = math.floor(optimizer_steps * float(optimizer_config["warmup_ratio"]))
    scheduler = get_cosine_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=optimizer_steps
    )
    optimizer.zero_grad(set_to_none=True)
    device = next(parameter for parameter in model.parameters() if parameter.device.type == "cuda").device
    pending_rows = 0
    pending_supervised = 0
    cumulative_packed = 0
    cumulative_supervised = 0
    global_step = 0
    checkpoint_receipts = []
    started = time.monotonic()
    model.train()
    for row_index, row in enumerate(rows, start=1):
        elapsed_hours = (time.monotonic() - started) / 3600
        if elapsed_hours >= float(authorization["max_gpu_hours_per_arm"]):
            raise RuntimeError("adapter run reached its authorized GPU-hour ceiling")
        encoded = render_assistant_only_example(tokenizer, row["messages"])
        input_ids = torch.tensor([encoded["input_ids"]], dtype=torch.long, device=device)
        labels = torch.tensor([encoded["labels"]], dtype=torch.long, device=device)
        attention_mask = torch.ones_like(input_ids)
        outputs = model(input_ids=input_ids, attention_mask=attention_mask, use_cache=False)
        shift_logits = outputs.logits[:, :-1, :].float().contiguous()
        shift_labels = labels[:, 1:].contiguous()
        supervised_this_row = int((shift_labels != -100).sum().item())
        if supervised_this_row <= 0:
            raise RuntimeError(f"row has no shifted supervised tokens: {row['record_id']}")
        loss_sum = functional.cross_entropy(
            shift_logits.view(-1, shift_logits.size(-1)),
            shift_labels.view(-1),
            ignore_index=-100,
            reduction="sum",
        )
        loss_sum.backward()
        elapsed_hours = (time.monotonic() - started) / 3600
        if elapsed_hours > float(authorization["max_gpu_hours_per_arm"]):
            raise RuntimeError(
                "adapter run exceeded its authorized GPU-hour ceiling during a row"
            )
        pending_rows += 1
        pending_supervised += supervised_this_row
        cumulative_packed += int(encoded["packed_tokens"])
        cumulative_supervised += supervised_this_row
        should_step = (
            pending_rows >= accumulation
            or row_index in flush_rows
            or row_index == len(rows)
        )
        if should_step:
            for parameter in trainable:
                if parameter.grad is not None:
                    parameter.grad.div_(pending_supervised)
            torch.nn.utils.clip_grad_norm_(
                trainable, float(optimizer_config["max_gradient_norm"])
            )
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            global_step += 1
            pending_rows = 0
            pending_supervised = 0
        if row_index in checkpoints_by_row:
            checkpoint = checkpoints_by_row[row_index]
            target = int(checkpoint["target_tokens"])
            if cumulative_packed != int(
                checkpoint["actual_cumulative_tokens"]
            ) or cumulative_supervised != int(
                checkpoint["actual_cumulative_assistant_tokens"]
            ):
                raise RuntimeError(
                    "observed packed/supervised checkpoint totals drifted from the frozen prefix"
                )
            checkpoint_dir = run_dir / f"checkpoint_{target:08d}_tokens"
            adapter_dir = checkpoint_dir / "adapter"
            model.save_pretrained(adapter_dir, safe_serialization=True)
            tokenizer.save_pretrained(adapter_dir)
            artifact = _directory_manifest(adapter_dir)
            checkpoint_receipt = {
                "schema_version": "storyworld_adapter_checkpoint_receipt_v1",
                "run_sha256": run_sha256,
                "arm": args.arm,
                "target_tokens": target,
                "reached_after_row": row_index,
                "packed_prefix_sha256": checkpoint["prefix_sha256"],
                "manifest_cumulative_tokens": int(
                    checkpoint["actual_cumulative_tokens"]
                ),
                "observed_cumulative_tokens": cumulative_packed,
                "observed_supervised_tokens": cumulative_supervised,
                "global_step": global_step,
                "adapter_path": "adapter",
                "adapter_artifact": artifact,
                "base_freeze_id": base_freeze["base_freeze_id"],
                "training_recipe_sha256": sha256_file(training_recipe_path),
                "development_evaluated": False,
                "sealed_evaluation_opened": False,
                "passed": True,
            }
            write_json(checkpoint_dir / "CHECKPOINT_RECEIPT.json", checkpoint_receipt)
            checkpoint_receipts.append(
                {
                    "target_tokens": target,
                    "path": checkpoint_dir.name,
                    "receipt_sha256": sha256_file(
                        checkpoint_dir / "CHECKPOINT_RECEIPT.json"
                    ),
                    "adapter_artifact_set_sha256": artifact["artifact_set_sha256"],
                }
            )
        del outputs, shift_logits, shift_labels, loss_sum, input_ids, labels, attention_mask

    if global_step != optimizer_steps or len(checkpoint_receipts) != len(
        training_recipe["checkpoint_tokens"]
    ):
        raise RuntimeError("adapter optimizer/checkpoint completion count drifted")
    elapsed_hours = (time.monotonic() - started) / 3600
    if elapsed_hours > float(authorization["max_gpu_hours_per_arm"]):
        raise RuntimeError("adapter run exceeded its authorized GPU-hour ceiling")
    receipt = {
        "schema_version": "storyworld_adapter_training_receipt_v1",
        "run_sha256": run_sha256,
        "authorization_id": authorization["authorization_id"],
        "authorization_sha256": sha256_file(authorization_path),
        "arm": args.arm,
        "status": "completed",
        "finished_at": utc_now(),
        "base_freeze_id": base_freeze["base_freeze_id"],
        "packing_manifest_sha256": sha256_file(packing_manifest_path),
        "arm_file_sha256": sha256_file(arm_path),
        "training_recipe_sha256": sha256_file(training_recipe_path),
        "trainer_sha256": sha256_file(Path(__file__).resolve()),
        "input_audit_sha256": sha256_file(run_dir / "INPUT_AUDIT.json"),
        "target_module_suffixes": target_suffixes,
        "matched_module_count": len(matched_modules),
        "matched_module_names_sha256": sha256_json(matched_modules),
        "trainable_parameters": trainable_params,
        "optimizer_steps": global_step,
        "elapsed_gpu_hours_upper_bound": elapsed_hours,
        "authorized_max_total_gpu_hours": authorization["max_total_gpu_hours"],
        "authorized_max_gpu_hours_per_arm": authorization[
            "max_gpu_hours_per_arm"
        ],
        "checkpoints": checkpoint_receipts,
        "development_evaluations": 0,
        "sealed_evaluation_opened": False,
        "passed": True,
    }
    write_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
