#!/usr/bin/env python3
"""Train a constitutional adapter with conservative defaults."""

from __future__ import annotations

import argparse
import inspect
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from model_family import (
    default_cache_dir,
    default_runs_root,
    patch_transformers_for_model_family,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-revision", default="main")
    parser.add_argument("--dataset-dir", required=True, help="Directory containing train.jsonl and val.jsonl.")
    parser.add_argument("--constitution-id", required=True)
    parser.add_argument("--output-root", default=str(default_runs_root()))
    parser.add_argument("--run-name", default="")
    parser.add_argument("--cache-dir", default=str(default_cache_dir()))
    parser.add_argument("--max-seq-length", type=int, default=1024)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--per-device-eval-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--num-train-epochs", type=float, default=1.0)
    parser.add_argument("--max-steps", type=int, default=0)
    parser.add_argument("--warmup-ratio", type=float, default=0.05)
    parser.add_argument("--logging-steps", type=int, default=5)
    parser.add_argument("--save-steps", type=int, default=50)
    parser.add_argument("--eval-steps", type=int, default=50)
    parser.add_argument("--save-total-limit", type=int, default=2)
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument(
        "--target-modules",
        default="q_proj,k_proj,v_proj,o_proj",
        help="Comma-separated module suffixes to target with LoRA.",
    )
    parser.add_argument("--quantization", choices=["qlora", "lora"], default="qlora")
    parser.add_argument("--dtype", choices=["auto", "float16", "bfloat16"], default="bfloat16")
    parser.add_argument("--init-adapter-path", default="", help="Optional existing adapter directory to continue training from.")
    parser.add_argument("--resume-from-checkpoint", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def set_cache_env(cache_dir: str) -> None:
    cache = str(Path(cache_dir).resolve())
    os.environ.setdefault("HF_HOME", cache)
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", cache)
    os.environ.setdefault("TRANSFORMERS_CACHE", cache)
    os.environ.setdefault("TRITON_CACHE_DIR", str(Path(cache) / "triton"))


def load_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} line {line_no}: {exc}") from exc
    return rows


def filter_rows(rows: Iterable[dict], constitution_id: str) -> List[dict]:
    return [row for row in rows if row.get("constitution_id") == constitution_id]


def build_run_dir(args: argparse.Namespace) -> Path:
    name = args.run_name.strip() or f"{args.constitution_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    return Path(args.output_root).resolve() / name


def get_dtype(torch_mod: Any, dtype_name: str) -> Any:
    if dtype_name == "float16":
        return torch_mod.float16
    if dtype_name == "bfloat16":
        return torch_mod.bfloat16
    return "auto"
def materialize_text_dataset(rows: List[dict], tokenizer: Any) -> List[dict]:
    out = []
    for row in rows:
        rendered = tokenizer.apply_chat_template(
            row["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )
        out.append({"text": rendered, "example_id": row["example_id"]})
    return out


def inspect_model_skeleton(model_id: str, revision: str, cache_dir: str, target_suffixes: List[str]) -> dict:
    from accelerate import init_empty_weights
    from transformers import AutoConfig, AutoModelForCausalLM

    patch_info = patch_transformers_for_model_family(model_id, revision, cache_dir)
    config = AutoConfig.from_pretrained(
        model_id,
        revision=revision,
        trust_remote_code=True,
        cache_dir=cache_dir,
    )
    if getattr(config, "pad_token_id", None) is None:
        config.pad_token_id = getattr(config, "eos_token_id", 0)
    try:
        with init_empty_weights():
            model = AutoModelForCausalLM.from_config(config, trust_remote_code=True)

        target_modules = []
        for name, _module in model.named_modules():
            if any(name.endswith(suffix) for suffix in target_suffixes):
                target_modules.append(name)
        return {
            "architectures": list(getattr(config, "architectures", []) or []),
            "model_type": str(getattr(config, "model_type", "") or ""),
            "target_module_count": len(target_modules),
            "target_module_examples": target_modules[:64],
            "layer_count": int(getattr(config, "num_hidden_layers", 0) or 0),
            "hidden_size": int(getattr(config, "hidden_size", 0) or 0),
            "afmoe_patch": patch_info,
        }
    except Exception as exc:
        return {
            "architectures": list(getattr(config, "architectures", []) or []),
            "model_type": str(getattr(config, "model_type", "") or ""),
            "target_module_count": 0,
            "target_module_examples": [],
            "layer_count": int(getattr(config, "num_hidden_layers", 0) or 0),
            "hidden_size": int(getattr(config, "hidden_size", 0) or 0),
            "afmoe_patch": patch_info,
            "inspection_error": f"{type(exc).__name__}: {exc}",
        }


def count_trainable_params(model: Any) -> Dict[str, int]:
    trainable = 0
    total = 0
    for param in model.parameters():
        total += param.numel()
        if param.requires_grad:
            trainable += param.numel()
    return {"trainable_params": int(trainable), "total_params": int(total)}


def compatibility_hint(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if "ROPE_INIT_FUNCTIONS" in text or "KeyError: 'default'" in text:
        return (
            "An AFMoE-style remote-code model is incompatible with the current transformers runtime in this env. "
            "Patch in a default RoPE initializer before model construction or use a model-specific env with a known-good transformers snapshot."
        )
    if "compute_default_rope_parameters" in text:
        return (
            "The model's AFMoE rotary embedding remote code is missing the default RoPE helper expected by this transformers runtime. "
            "Import and patch AfmoeRotaryEmbedding before model load."
        )
    if "pad_token_id" in text:
        return (
            "The model config is missing pad_token_id in this runtime path. "
            "The loader needs config normalization before model construction."
        )
    if "Some modules are dispatched on the CPU or the disk" in text:
        return (
            "The selected 4-bit model does not fit cleanly on this GPU with the current auto placement. "
            "Limited inference may still work with custom offload, but adapter training is not a reliable default on this hardware."
        )
    return ""


def main() -> int:
    args = parse_args()
    set_cache_env(args.cache_dir)
    run_dir = build_run_dir(args)
    ensure_dir(run_dir)
    receipt_path = run_dir / "receipt.json"

    target_suffixes = [item.strip() for item in args.target_modules.split(",") if item.strip()]
    train_path = Path(args.dataset_dir).resolve() / "train.jsonl"
    val_path = Path(args.dataset_dir).resolve() / "val.jsonl"
    if not train_path.exists():
        raise SystemExit(f"Missing train split: {train_path}")
    if not val_path.exists():
        raise SystemExit(f"Missing val split: {val_path}")

    train_rows = filter_rows(load_jsonl(train_path), args.constitution_id)
    val_rows = filter_rows(load_jsonl(val_path), args.constitution_id)
    if not train_rows:
        raise SystemExit(f"No training rows found for constitution_id={args.constitution_id}")

    receipt: Dict[str, Any] = {
        "status": "initializing",
        "started_at_utc": utc_now(),
        "hostname": socket.gethostname(),
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "dataset_dir": str(Path(args.dataset_dir).resolve()),
        "constitution_id": args.constitution_id,
        "train_examples": len(train_rows),
        "val_examples": len(val_rows),
        "quantization": args.quantization,
        "target_module_suffixes": target_suffixes,
        "dry_run": bool(args.dry_run),
        "cache_dir": str(Path(args.cache_dir).resolve()),
        "run_dir": str(run_dir),
        "init_adapter_path": str(Path(args.init_adapter_path).resolve()) if args.init_adapter_path else "",
    }

    skeleton = inspect_model_skeleton(args.model_id, args.model_revision, args.cache_dir, target_suffixes)
    receipt["model_skeleton"] = skeleton
    receipt["model_family"] = skeleton.get("afmoe_patch", {}).get("family", "generic")
    if skeleton.get("inspection_error"):
        receipt["compatibility_hint"] = compatibility_hint(Exception(skeleton["inspection_error"]))
    write_json(receipt_path, receipt)

    if args.dry_run:
        receipt["status"] = "dry_run_completed"
        receipt["finished_at_utc"] = utc_now()
        write_json(receipt_path, receipt)
        print(json.dumps(receipt, indent=2))
        return 0

    import torch
    from datasets import Dataset
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    patch_info = patch_transformers_for_model_family(args.model_id, args.model_revision, args.cache_dir)
    receipt["afmoe_patch"] = patch_info
    receipt["model_family"] = patch_info.get("family", receipt.get("model_family", "generic"))
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_id,
        revision=args.model_revision,
        trust_remote_code=True,
        cache_dir=args.cache_dir,
        use_fast=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    text_train = materialize_text_dataset(train_rows, tokenizer)
    text_val = materialize_text_dataset(val_rows, tokenizer)
    train_dataset = Dataset.from_list(text_train)
    eval_dataset = Dataset.from_list(text_val) if text_val else None

    model_kwargs: Dict[str, Any] = {
        "revision": args.model_revision,
        "trust_remote_code": True,
        "cache_dir": args.cache_dir,
        "device_map": "auto",
        "low_cpu_mem_usage": True,
    }
    if args.quantization == "qlora":
        compute_dtype = torch.float16 if args.dtype == "float16" else torch.bfloat16
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        )
    else:
        model_kwargs["torch_dtype"] = get_dtype(torch, args.dtype)

    if "trust_remote_code" in model_kwargs:
        config = None
        from transformers import AutoConfig

        config = AutoConfig.from_pretrained(
            args.model_id,
            revision=args.model_revision,
            trust_remote_code=True,
            cache_dir=args.cache_dir,
        )
        if getattr(config, "pad_token_id", None) is None:
            config.pad_token_id = tokenizer.pad_token_id
        model_kwargs["config"] = config

    try:
        model = AutoModelForCausalLM.from_pretrained(args.model_id, **model_kwargs)
    except Exception as exc:
        receipt["status"] = "failed_model_load"
        receipt["finished_at_utc"] = utc_now()
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        receipt["compatibility_hint"] = compatibility_hint(exc)
        write_json(receipt_path, receipt)
        raise
    model.config.use_cache = False

    if args.quantization == "qlora":
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    else:
        model.gradient_checkpointing_enable()

    if args.init_adapter_path:
        init_adapter_path = Path(args.init_adapter_path).resolve()
        if not init_adapter_path.exists():
            raise SystemExit(f"init adapter path not found: {init_adapter_path}")
        model = PeftModel.from_pretrained(model, str(init_adapter_path), is_trainable=True)
        receipt["init_adapter_path"] = str(init_adapter_path)
    else:
        lora_config = LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=target_suffixes,
        )
        model = get_peft_model(model, lora_config)
    param_counts = count_trainable_params(model)
    receipt["param_counts"] = param_counts
    write_json(receipt_path, receipt)

    warmup_kwargs: Dict[str, float | int]
    if "warmup_ratio" in inspect.signature(SFTConfig).parameters:
        warmup_kwargs = {"warmup_ratio": args.warmup_ratio}
    elif args.max_steps > 0:
        warmup_kwargs = {
            "warmup_steps": max(0, int(round(args.max_steps * args.warmup_ratio)))
        }
    else:
        raise RuntimeError(
            "This SFTConfig runtime has no warmup_ratio and max_steps is not "
            "set, so the requested warmup schedule cannot be preserved."
        )
    receipt["warmup_schedule"] = warmup_kwargs
    write_json(receipt_path, receipt)

    train_config = SFTConfig(
        output_dir=str(run_dir / "train"),
        max_length=args.max_seq_length,
        per_device_train_batch_size=args.per_device_train_batch_size,
        per_device_eval_batch_size=args.per_device_eval_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        num_train_epochs=args.num_train_epochs,
        max_steps=args.max_steps if args.max_steps > 0 else -1,
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        eval_steps=args.eval_steps,
        save_total_limit=args.save_total_limit,
        bf16=(args.quantization == "lora" and args.dtype == "bfloat16"),
        fp16=(args.quantization == "lora" and args.dtype == "float16"),
        gradient_checkpointing=True,
        dataset_text_field="text",
        packing=False,
        report_to=[],
        logging_dir=str(run_dir / "logs"),
        eval_strategy="steps" if eval_dataset is not None else "no",
        save_strategy="steps",
        **warmup_kwargs,
    )

    trainer = SFTTrainer(
        model=model,
        args=train_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
    )

    receipt["status"] = "training"
    write_json(receipt_path, receipt)
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint or None)
    final_adapter_dir = run_dir / "final_adapter"
    trainer.model.save_pretrained(final_adapter_dir)
    tokenizer.save_pretrained(final_adapter_dir)

    metrics = trainer.state.log_history
    write_json(run_dir / "train_metrics.json", {"log_history": metrics})

    receipt["status"] = "completed"
    receipt["finished_at_utc"] = utc_now()
    receipt["final_adapter_dir"] = str(final_adapter_dir)
    write_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
