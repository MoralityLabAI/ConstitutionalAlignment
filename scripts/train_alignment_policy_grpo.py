#!/usr/bin/env python3
"""Train a LoRA/QLoRA policy with constitutional-reflection GRPO rewards."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitution import load_constitution
from alignment_harness.prompting import DIRECT_CHAT_TEMPLATE_KWARGS
from alignment_harness.rewards import (
    DEFAULT_REWARD_WEIGHTS,
    REWARD_FUNCTIONS,
    REWARD_NAMES,
    score_response,
)


ACTIVE_RECEIPT: tuple[Path, dict[str, Any]] | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="", help="Base model ID or local path. Required for training.")
    parser.add_argument("--model-revision", default="main")
    parser.add_argument("--dataset-dir", default="artifacts/alignment_conditioning_v1")
    parser.add_argument("--constitution", default="constitution.md")
    parser.add_argument("--output-root", default="artifacts/alignment_policy_runs")
    parser.add_argument("--run-name", default="")
    parser.add_argument("--cache-dir", default=os.environ.get("HF_HOME", str(REPO_ROOT / ".cache" / "huggingface")))
    parser.add_argument("--init-adapter-path", default="")
    parser.add_argument("--resume-from-checkpoint", default="")
    parser.add_argument("--quantization", choices=["qlora", "lora"], default="qlora")
    parser.add_argument("--dtype", choices=["float16", "bfloat16"], default="float16")
    parser.add_argument("--max-prompts", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--num-generations", type=int, default=2)
    parser.add_argument("--max-prompt-length", type=int, default=1024)
    parser.add_argument("--max-completion-length", type=int, default=256)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=1e-6)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--logging-steps", type=int, default=1)
    parser.add_argument("--save-steps", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260714)
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--minimum-signal-step-fraction", type=float, default=0.25)
    parser.add_argument("--max-mean-clipped-ratio", type=float, default=0.5)
    parser.add_argument("--target-modules", default="q_proj,k_proj,v_proj,o_proj")
    parser.add_argument("--dry-run", action="store_true", help="Validate data and rewards without loading a model.")
    parser.add_argument("--preflight-only", action="store_true", help="Also import the local TRL stack, then exit.")
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Skip internal validation generation when using the external held-out evaluator.",
    )
    return parser.parse_args()


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL in {path}:{line_no}: {exc}") from exc
            rows.append(row)
    return rows


def validate_rl_rows(rows: list[dict[str, Any]], path: Path) -> None:
    required = {
        "example_id",
        "prompt",
        "valid_option_ids",
        "valid_option_texts",
        "allowed_tenet_ids",
        "relevant_tenet_ids",
        "near_duplicate_cluster_id",
    }
    if not rows:
        raise ValueError(f"RL dataset is empty: {path}")
    for index, row in enumerate(rows):
        missing = required - set(row)
        if missing:
            raise ValueError(f"{path}:{index + 1} missing columns: {sorted(missing)}")
        if len(row["valid_option_ids"]) < 2:
            raise ValueError(f"{path}:{index + 1} has fewer than two valid options")
        if not row["relevant_tenet_ids"]:
            raise ValueError(f"{path}:{index + 1} has no relevant tenet proxies")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def package_versions(names: list[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not_installed"
    return versions


def normalize_trainable_parameters(model: Any) -> dict[str, Any]:
    before: dict[str, int] = {}
    after: dict[str, int] = {}
    converted = 0
    for parameter in model.parameters():
        if not parameter.requires_grad:
            continue
        before[str(parameter.dtype)] = before.get(str(parameter.dtype), 0) + parameter.numel()
        if str(parameter.dtype) in {"torch.float16", "torch.bfloat16"}:
            parameter.data = parameter.data.float()
            converted += parameter.numel()
        after[str(parameter.dtype)] = after.get(str(parameter.dtype), 0) + parameter.numel()
    return {"before": before, "after": after, "converted_to_float32": converted}


def finite_training_audit(model: Any, log_history: list[dict[str, Any]]) -> dict[str, Any]:
    import torch

    nonfinite_metrics: list[dict[str, Any]] = []
    for index, entry in enumerate(log_history):
        for key in ("loss", "grad_norm", "train_loss"):
            if key not in entry:
                continue
            try:
                value = float(entry[key])
            except (TypeError, ValueError):
                nonfinite_metrics.append({"history_index": index, "key": key, "value": str(entry[key])})
                continue
            if not math.isfinite(value):
                nonfinite_metrics.append({"history_index": index, "key": key, "value": str(entry[key])})
    trainable_elements = 0
    nonfinite_parameters = 0
    for parameter in model.parameters():
        if not parameter.requires_grad:
            continue
        trainable_elements += parameter.numel()
        nonfinite_parameters += int((~torch.isfinite(parameter.detach())).sum().item())
    return {
        "trainable_elements": trainable_elements,
        "nonfinite_parameter_elements": nonfinite_parameters,
        "nonfinite_metrics": nonfinite_metrics,
        "passed": not nonfinite_metrics and nonfinite_parameters == 0,
    }


def optimization_signal_audit(
    log_history: list[dict[str, Any]],
    minimum_signal_fraction: float = 0.25,
    max_mean_clipped_ratio: float = 0.5,
) -> dict[str, Any]:
    signal_steps: list[dict[str, float]] = []
    optimization_steps = 0
    clipped_ratios: list[float] = []
    for entry in log_history:
        if "reward_std" not in entry or "grad_norm" not in entry:
            continue
        optimization_steps += 1
        reward_std = float(entry["reward_std"])
        grad_norm = float(entry["grad_norm"])
        if "completions/clipped_ratio" in entry:
            clipped_ratios.append(float(entry["completions/clipped_ratio"]))
        if math.isfinite(reward_std) and math.isfinite(grad_norm) and reward_std > 1e-8 and grad_norm > 1e-8:
            signal_steps.append(
                {
                    "step": float(entry.get("step", 0)),
                    "reward_std": reward_std,
                    "grad_norm": grad_norm,
                }
            )
    signal_fraction = len(signal_steps) / optimization_steps if optimization_steps else 0.0
    mean_clipped_ratio = sum(clipped_ratios) / len(clipped_ratios) if clipped_ratios else 1.0
    return {
        "optimization_steps": optimization_steps,
        "steps_with_reward_variance_and_nonzero_gradient": signal_steps,
        "signal_step_fraction": signal_fraction,
        "minimum_signal_step_fraction": minimum_signal_fraction,
        "mean_clipped_ratio": mean_clipped_ratio,
        "max_mean_clipped_ratio": max_mean_clipped_ratio,
        "passed": (
            signal_fraction >= minimum_signal_fraction
            and mean_clipped_ratio <= max_mean_clipped_ratio
        ),
    }


def import_training_stack() -> dict[str, Any]:
    import trl.import_utils as trl_import_utils

    compatibility_patches: list[str] = []
    weave_result = trl_import_utils.is_weave_available()
    if isinstance(weave_result, tuple):
        available = bool(weave_result[0])
        trl_import_utils.is_weave_available = lambda: available
        compatibility_patches.append("trl_is_weave_available_tuple_return")

    from datasets import Dataset
    from peft import LoraConfig, PeftModel, prepare_model_for_kbit_training
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import GRPOConfig, GRPOTrainer

    return {
        "Dataset": Dataset,
        "LoraConfig": LoraConfig,
        "PeftModel": PeftModel,
        "prepare_model_for_kbit_training": prepare_model_for_kbit_training,
        "AutoConfig": AutoConfig,
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "BitsAndBytesConfig": BitsAndBytesConfig,
        "GRPOConfig": GRPOConfig,
        "GRPOTrainer": GRPOTrainer,
        "compatibility_patches": compatibility_patches,
    }


def make_probe_completion(row: dict[str, Any]) -> str:
    tenets = list(row["relevant_tenet_ids"][:2])
    reflection = str(row.get("behavioral_reference_reflection", "") or "").strip()
    if len(reflection.split()) < 20:
        reflection = (
            f"The choice affects competing interests, so I would examine the likely harm, available evidence, "
            f"and responsibility attached to {row['valid_option_ids'][0]} before acting."
        )
    return "\n".join(
        [
            f"Decision: {row['valid_option_ids'][0]}",
            f"Reflection: {reflection}",
            f"Tenets defended: {', '.join(tenets)}",
            "Counterpressure: Another listed option could protect a competing interest under unresolved uncertainty.",
            "Constitutional defense: On balance, this action defends "
            f"{', '.join(tenets)} because it addresses the recorded stakes "
            "without hiding the tradeoff.",
        ]
    )


def run_dir_for(args: argparse.Namespace) -> Path:
    name = args.run_name.strip() or datetime.now(timezone.utc).strftime("grpo_%Y%m%dT%H%M%SZ")
    return resolve_repo_path(args.output_root) / name


def main() -> int:
    global ACTIVE_RECEIPT
    args = parse_args()
    dataset_dir = resolve_repo_path(args.dataset_dir)
    train_path = dataset_dir / "rl_train.jsonl"
    validation_path = dataset_dir / "rl_validation.jsonl"
    if not train_path.exists():
        raise SystemExit(f"missing RL training split: {train_path}")
    train_rows = load_jsonl(train_path)
    validation_rows = load_jsonl(validation_path) if validation_path.exists() else []
    validate_rl_rows(train_rows, train_path)
    if validation_rows:
        validate_rl_rows(validation_rows, validation_path)
    if args.max_prompts > 0:
        train_rows = train_rows[: args.max_prompts]
        validation_rows = validation_rows[: args.max_prompts]

    constitution = load_constitution(resolve_repo_path(args.constitution))
    run_dir = run_dir_for(args)
    run_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = run_dir / "receipt.json"
    receipt: dict[str, Any] = {
        "receipt_version": "alignment_policy_grpo_receipt_v1",
        "status": "validated",
        "started_at_utc": utc_now(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "research_only": True,
        "proxy_rewards_are_not_compliance_metrics": True,
        "promotion_blocked_on_scholar_review": constitution.needs_scholar_review,
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "constitution_id": constitution.constitution_id,
        "constitution_sha256": constitution.sha256,
        "dataset_dir": str(dataset_dir),
        "train_dataset_sha256": sha256_file(train_path),
        "train_prompts": len(train_rows),
        "validation_prompts": len(validation_rows),
        "reward_functions": list(REWARD_NAMES),
        "reward_weights": list(DEFAULT_REWARD_WEIGHTS),
        "chat_template_kwargs": DIRECT_CHAT_TEMPLATE_KWARGS,
        "training_args": vars(args),
        "package_versions": package_versions(
            ["torch", "transformers", "trl", "datasets", "peft", "accelerate", "bitsandbytes"]
        ),
    }
    probe = make_probe_completion(train_rows[0])
    receipt["reward_probe"] = {
        "example_id": train_rows[0]["example_id"],
        "component_scores": score_response(
            probe,
            valid_option_ids=train_rows[0]["valid_option_ids"],
            valid_option_texts=train_rows[0]["valid_option_texts"],
            allowed_tenet_ids=train_rows[0]["allowed_tenet_ids"],
            relevant_tenet_ids=train_rows[0]["relevant_tenet_ids"],
        ),
    }
    write_json(receipt_path, receipt)
    ACTIVE_RECEIPT = (receipt_path, receipt)

    stack: dict[str, Any] | None = None
    if args.preflight_only:
        stack = import_training_stack()
        receipt["compatibility_patches"] = stack["compatibility_patches"]
        receipt["status"] = "preflight_completed"
        receipt["finished_at_utc"] = utc_now()
        write_json(receipt_path, receipt)
        print(json.dumps(receipt, indent=2))
        return 0
    if args.dry_run:
        receipt["status"] = "dry_run_completed"
        receipt["finished_at_utc"] = utc_now()
        write_json(receipt_path, receipt)
        print(json.dumps(receipt, indent=2))
        return 0
    if not args.model_id:
        raise SystemExit("--model-id is required unless --dry-run is used")

    import torch

    stack = import_training_stack()
    receipt["compatibility_patches"] = stack["compatibility_patches"]
    tokenizer = stack["AutoTokenizer"].from_pretrained(
        args.model_id,
        revision=args.model_revision,
        trust_remote_code=True,
        cache_dir=args.cache_dir,
        use_fast=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    config = stack["AutoConfig"].from_pretrained(
        args.model_id,
        revision=args.model_revision,
        trust_remote_code=True,
        cache_dir=args.cache_dir,
    )
    if getattr(config, "pad_token_id", None) is None:
        config.pad_token_id = tokenizer.pad_token_id
    config.use_cache = False

    compute_dtype = torch.float16 if args.dtype == "float16" else torch.bfloat16
    model_kwargs: dict[str, Any] = {
        "revision": args.model_revision,
        "trust_remote_code": True,
        "cache_dir": args.cache_dir,
        "config": config,
        "device_map": "auto",
        "low_cpu_mem_usage": True,
    }
    if args.quantization == "qlora":
        model_kwargs["quantization_config"] = stack["BitsAndBytesConfig"](
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        )
    else:
        model_kwargs["torch_dtype"] = compute_dtype
    model = stack["AutoModelForCausalLM"].from_pretrained(args.model_id, **model_kwargs)
    model.config.use_cache = False
    if args.quantization == "qlora":
        model = stack["prepare_model_for_kbit_training"](model, use_gradient_checkpointing=True)
    else:
        model.gradient_checkpointing_enable()

    target_modules = [item.strip() for item in args.target_modules.split(",") if item.strip()]
    peft_config = None
    if args.init_adapter_path:
        init_path = resolve_repo_path(args.init_adapter_path)
        model = stack["PeftModel"].from_pretrained(model, str(init_path), is_trainable=True)
        receipt["init_adapter_path"] = str(init_path)
    else:
        peft_config = stack["LoraConfig"](
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=target_modules,
        )

    effective_batch = args.per_device_train_batch_size * args.gradient_accumulation_steps
    if effective_batch % args.num_generations != 0:
        raise ValueError(
            "per_device_train_batch_size * gradient_accumulation_steps must be divisible by num_generations"
        )
    train_dataset = stack["Dataset"].from_list(train_rows)
    validation_dataset = (
        stack["Dataset"].from_list(validation_rows)
        if validation_rows and not args.skip_eval
        else None
    )
    training_config = stack["GRPOConfig"](
        output_dir=str(run_dir / "trainer"),
        max_steps=args.max_steps,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.per_device_train_batch_size,
        per_device_eval_batch_size=args.num_generations,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        num_generations=args.num_generations,
        num_generations_eval=args.num_generations,
        max_prompt_length=args.max_prompt_length,
        max_completion_length=args.max_completion_length,
        temperature=args.temperature,
        top_p=args.top_p,
        beta=0.0,
        loss_type="dapo",
        scale_rewards="group",
        reward_weights=list(DEFAULT_REWARD_WEIGHTS),
        remove_unused_columns=False,
        chat_template_kwargs=DIRECT_CHAT_TEMPLATE_KWARGS,
        mask_truncated_completions=True,
        gradient_checkpointing=True,
        fp16=args.dtype == "float16",
        bf16=args.dtype == "bfloat16",
        optim="paged_adamw_8bit" if args.quantization == "qlora" else "adamw_torch",
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        save_total_limit=2,
        eval_strategy="steps" if validation_dataset is not None else "no",
        eval_steps=args.save_steps if validation_dataset is not None else None,
        report_to="none",
        seed=args.seed,
        data_seed=args.seed,
    )
    trainer = stack["GRPOTrainer"](
        model=model,
        reward_funcs=list(REWARD_FUNCTIONS),
        args=training_config,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        processing_class=tokenizer,
        peft_config=peft_config,
    )
    receipt["trainable_parameter_dtypes"] = normalize_trainable_parameters(trainer.model)
    receipt["status"] = "training"
    write_json(receipt_path, receipt)
    result = trainer.train(resume_from_checkpoint=args.resume_from_checkpoint or None)
    write_json(run_dir / "log_history.json", trainer.state.log_history)
    receipt["finite_training_audit"] = finite_training_audit(trainer.model, trainer.state.log_history)
    if not receipt["finite_training_audit"]["passed"]:
        raise RuntimeError(f"non-finite training audit failed: {receipt['finite_training_audit']}")
    receipt["optimization_signal_audit"] = optimization_signal_audit(
        trainer.state.log_history,
        minimum_signal_fraction=args.minimum_signal_step_fraction,
        max_mean_clipped_ratio=args.max_mean_clipped_ratio,
    )
    if not receipt["optimization_signal_audit"]["passed"]:
        raise RuntimeError(f"optimization signal audit failed: {receipt['optimization_signal_audit']}")
    final_adapter = run_dir / "final_adapter"
    trainer.model.save_pretrained(final_adapter)
    tokenizer.save_pretrained(final_adapter)
    write_json(run_dir / "train_metrics.json", dict(result.metrics))

    receipt["status"] = "completed_exploratory_policy"
    receipt["finished_at_utc"] = utc_now()
    receipt["final_adapter"] = str(final_adapter)
    receipt["train_metrics"] = dict(result.metrics)
    write_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        if ACTIVE_RECEIPT is not None:
            active_path, active_receipt = ACTIVE_RECEIPT
            active_receipt["status"] = "failed"
            active_receipt["finished_at_utc"] = utc_now()
            active_receipt["error"] = f"{type(exc).__name__}: {exc}"
            write_json(active_path, active_receipt)
        raise
