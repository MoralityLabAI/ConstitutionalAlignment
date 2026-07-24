#!/usr/bin/env python3
"""VRAM-guarded tiny Jinn/Mutazili adapter training.

This trainer is intentionally fail-closed for low-VRAM local runs:

- local files only by default
- 4-bit QLoRA only
- explicit CUDA placement, never ``device_map="auto"``
- aborts if any loaded tensor or HF device-map entry lands on CPU or disk
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import socket
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET_DIR = REPO_ROOT / "data" / "jinn_tiny_mutazili_v1"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "constitution_pipeline" / "runs" / "jinn_tiny_mutazili_v1"
DEFAULT_CACHE_DIR = REPO_ROOT / ".cache" / "huggingface"
DEFAULT_MODEL_ID = r"D:\Research_Engine\models\Qwen3.5\Qwen2.5-3B"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def release_cuda_memory(summary: dict | None = None, log: "RunLog | None" = None) -> None:
    record: dict[str, Any] = {"status": "started"}
    try:
        gc.collect()
        import torch

        record["torch_imported"] = True
        record["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
            record["allocated_mb_after"] = round(torch.cuda.memory_allocated() / 1_000_000, 3)
            record["reserved_mb_after"] = round(torch.cuda.memory_reserved() / 1_000_000, 3)
        record["status"] = "completed"
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
    if summary is not None:
        summary["python_cuda_cleanup"] = record
    if log is not None:
        try:
            log.event("python_cuda_cleanup", **record)
        except Exception:
            pass


class RunLog:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.event_path = run_dir / "events.jsonl"
        self.summary_path = run_dir / "run_summary.json"
        ensure_dir(run_dir)

    def event(self, event_type: str, **payload: Any) -> None:
        record = {"ts_utc": utc_now(), "event": event_type}
        record.update(payload)
        with self.event_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def summary(self, payload: dict) -> None:
        write_json(self.summary_path, payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR))
    parser.add_argument("--train-split", choices=("train", "fresh_train"), default="train")
    parser.add_argument("--constitution-id", default="jinn_tiny_mutazili_v1")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-name", default="")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--max-steps", type=int, default=3)
    parser.add_argument("--max-seq-length", type=int, default=192)
    parser.add_argument("--vram-limit-mb", type=int, default=3900)
    parser.add_argument("--vram-reserve-mb", type=int, default=192)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=1)
    parser.add_argument("--lora-r", type=int, default=4)
    parser.add_argument("--lora-alpha", type=int, default=8)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--init-adapter-path", default="")
    parser.add_argument("--logging-steps", type=int, default=1)
    parser.add_argument("--save-steps", type=int, default=1)
    parser.add_argument("--save-total-limit", type=int, default=2)
    parser.add_argument("--target-modules", default="q_proj,k_proj,v_proj,o_proj")
    parser.add_argument("--seed", type=int, default=713)
    parser.add_argument("--dry-run-load-only", action="store_true")
    parser.add_argument("--skip-cuda-allocator-warmup", action="store_true")
    parser.add_argument("--local-files-only", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    if args.gradient_accumulation_steps < 1:
        parser.error("--gradient-accumulation-steps must be positive")
    return args


def run_name(args: argparse.Namespace) -> str:
    if args.run_name.strip():
        return args.run_name.strip()
    model_leaf = Path(str(args.model_id)).name.replace(".", "p")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{args.constitution_id}_{model_leaf}_vram_guarded_{stamp}"


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
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


def filter_rows(rows: Iterable[dict], constitution_id: str) -> list[dict]:
    return [row for row in rows if row.get("constitution_id") == constitution_id]


def missing_weight_files(model_id: str) -> list[str]:
    model_path = Path(model_id)
    if not model_path.exists() or not model_path.is_dir():
        return []
    if list(model_path.glob("*.gguf")) and not (model_path / "config.json").exists():
        return ["unsupported_gguf_only_checkpoint"]
    index_path = model_path / "model.safetensors.index.json"
    if not index_path.exists():
        has_single_file = any(model_path.glob("*.safetensors")) or any(model_path.glob("*.bin"))
        return [] if has_single_file else ["no_weight_file_found"]
    with index_path.open("r", encoding="utf-8") as handle:
        index = json.load(handle)
    needed = sorted(set(index.get("weight_map", {}).values()))
    return [item for item in needed if not (model_path / item).exists()]


def nvidia_smi_snapshot() -> dict:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        line = proc.stdout.strip().splitlines()[0]
        name, total, used, free = [item.strip() for item in line.split(",")]
        return {
            "name": name,
            "total_mb": int(total),
            "used_mb": int(used),
            "free_mb": int(free),
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def cuda_mem_snapshot(torch_mod: Any) -> dict:
    if not torch_mod.cuda.is_available():
        return {"cuda_available": False}
    free_bytes, total_bytes = torch_mod.cuda.mem_get_info()
    return {
        "cuda_available": True,
        "device_name": torch_mod.cuda.get_device_name(0),
        "total_mb": round(total_bytes / 1024 / 1024, 2),
        "free_mb": round(free_bytes / 1024 / 1024, 2),
        "allocated_mb": round(torch_mod.cuda.memory_allocated(0) / 1024 / 1024, 2),
        "reserved_mb": round(torch_mod.cuda.memory_reserved(0) / 1024 / 1024, 2),
        "max_allocated_mb": round(torch_mod.cuda.max_memory_allocated(0) / 1024 / 1024, 2),
    }


def assert_peak_vram_under_limit(torch_mod: Any, limit_mb: int, stage: str) -> dict:
    snap = cuda_mem_snapshot(torch_mod)
    peak = float(snap.get("max_allocated_mb", 0.0) or 0.0)
    if peak > float(limit_mb):
        raise RuntimeError(f"Peak CUDA allocation {peak:.2f} MB exceeded limit {limit_mb} MB at {stage}.")
    return snap


def assert_gpu_budget(torch_mod: Any, args: argparse.Namespace) -> dict:
    if not torch_mod.cuda.is_available():
        raise RuntimeError("CUDA is not available; refusing to train without the GPU.")
    snap = cuda_mem_snapshot(torch_mod)
    total = float(snap["total_mb"])
    free = float(snap["free_mb"])
    if total > args.vram_limit_mb + 256:
        raise RuntimeError(
            f"GPU total VRAM {total:.0f} MB exceeds configured low-VRAM lane {args.vram_limit_mb} MB."
        )
    if free < args.vram_reserve_mb:
        raise RuntimeError(f"Only {free:.0f} MB free VRAM before load; reserve is {args.vram_reserve_mb} MB.")
    return snap


def format_device(device: Any) -> str:
    text = str(device)
    if text == "0":
        return "cuda:0"
    return text


def assert_no_offload(model: Any, stage: str) -> dict:
    hf_map = getattr(model, "hf_device_map", None)
    bad_map: list[dict] = []
    if isinstance(hf_map, dict):
        for name, device in hf_map.items():
            formatted = format_device(device).lower()
            if "cpu" in formatted or "disk" in formatted:
                bad_map.append({"module": name, "device": format_device(device)})
    offenders: list[dict] = []
    for tensor_kind, iterator in (("parameter", model.named_parameters()), ("buffer", model.named_buffers())):
        for name, tensor in iterator:
            device_type = getattr(tensor.device, "type", str(tensor.device))
            if device_type != "cuda":
                offenders.append({"kind": tensor_kind, "name": name, "device": str(tensor.device)})
                if len(offenders) >= 32:
                    break
        if len(offenders) >= 32:
            break
    if bad_map or offenders:
        raise RuntimeError(
            f"Offload detected at {stage}: hf_device_map={bad_map[:8]} tensor_offenders={offenders[:8]}"
        )
    return {
        "stage": stage,
        "hf_device_map": {k: format_device(v) for k, v in hf_map.items()} if isinstance(hf_map, dict) else {},
        "checked": True,
    }


def render_chat(
    tokenizer: Any, messages: list[dict], *, add_generation_prompt: bool
) -> str:
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=add_generation_prompt,
        enable_thinking=False,
    )


def materialize_prompt_completion_dataset(
    rows: list[dict], tokenizer: Any
) -> list[dict]:
    materialized: list[dict] = []
    for row in rows:
        messages = row["messages"]
        if len(messages) < 2 or messages[-1].get("role") != "assistant":
            raise ValueError(
                f"{row.get('example_id', '<unknown>')}: final message must be assistant"
            )
        prompt = render_chat(
            tokenizer, messages[:-1], add_generation_prompt=True
        )
        full = render_chat(tokenizer, messages, add_generation_prompt=False)
        if not full.startswith(prompt):
            raise ValueError(
                f"{row.get('example_id', '<unknown>')}: rendered prompt is not a full-sequence prefix"
            )
        completion = full[len(prompt) :]
        if not completion.strip():
            raise ValueError(
                f"{row.get('example_id', '<unknown>')}: rendered completion is empty"
            )
        materialized.append(
            {
                "prompt": prompt,
                "completion": completion,
                "example_id": row["example_id"],
            }
        )
    return materialized


def count_trainable_params(model: Any) -> dict:
    trainable = 0
    total = 0
    for param in model.parameters():
        total += param.numel()
        if param.requires_grad:
            trainable += param.numel()
    pct = (trainable / total * 100.0) if total else 0.0
    return {"trainable": int(trainable), "total": int(total), "trainable_pct": round(pct, 6)}


def configure_environment(args: argparse.Namespace) -> None:
    cache = str(Path(args.cache_dir).resolve())
    os.environ.setdefault("HF_HOME", cache)
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", cache)
    os.environ.setdefault("TRANSFORMERS_CACHE", cache)
    os.environ.setdefault("TRITON_CACHE_DIR", str(Path(cache) / "triton"))
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("ACCELERATE_DISABLE_RICH", "1")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True,max_split_size_mb:64")
    if args.local_files_only:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def run_training(args: argparse.Namespace, log: RunLog, summary: dict) -> int:
    missing = missing_weight_files(args.model_id)
    if missing:
        raise RuntimeError(f"Local checkpoint is incomplete or unsupported; missing={missing[:8]}")

    import torch
    from datasets import Dataset
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    if args.skip_cuda_allocator_warmup:
        import transformers.modeling_utils as transformers_modeling_utils

        def skip_cuda_allocator_warmup(*_args: Any, **_kwargs: Any) -> None:
            return None

        transformers_modeling_utils.caching_allocator_warmup = skip_cuda_allocator_warmup
        summary["cuda_allocator_warmup"] = "skipped"
        log.event("cuda_allocator_warmup_skipped")
    else:
        summary["cuda_allocator_warmup"] = "enabled"

    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    first_gpu = assert_gpu_budget(torch, args)
    summary["gpu_initial"] = first_gpu
    summary["nvidia_smi_initial"] = nvidia_smi_snapshot()
    log.event("gpu_check", torch_cuda=first_gpu, nvidia_smi=summary["nvidia_smi_initial"])

    dataset_dir = Path(args.dataset_dir).resolve()
    train_path = dataset_dir / f"{args.train_split}.jsonl"
    val_path = dataset_dir / "val.jsonl"
    if not train_path.exists() or not val_path.exists():
        raise RuntimeError(f"Missing dataset split under {dataset_dir}")
    train_rows = filter_rows(load_jsonl(train_path), args.constitution_id)
    val_rows = filter_rows(load_jsonl(val_path), args.constitution_id)
    if not train_rows:
        raise RuntimeError(f"No rows found for constitution_id={args.constitution_id}")
    summary["train_examples"] = len(train_rows)
    summary["val_examples"] = len(val_rows)
    summary["train_split"] = args.train_split
    log.event(
        "dataset_loaded",
        train_examples=len(train_rows),
        train_split=args.train_split,
        val_examples=len(val_rows),
    )

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_id,
        cache_dir=args.cache_dir,
        trust_remote_code=True,
        use_fast=True,
        local_files_only=args.local_files_only,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    config = AutoConfig.from_pretrained(
        args.model_id,
        cache_dir=args.cache_dir,
        trust_remote_code=True,
        local_files_only=args.local_files_only,
    )
    if getattr(config, "pad_token_id", None) is None:
        config.pad_token_id = tokenizer.pad_token_id

    train_dataset = Dataset.from_list(
        materialize_prompt_completion_dataset(train_rows, tokenizer)
    )

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    log.event("model_load_start", model_id=args.model_id, quantization="nf4_4bit", device_map={"": 0})
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        config=config,
        cache_dir=args.cache_dir,
        trust_remote_code=True,
        local_files_only=args.local_files_only,
        quantization_config=quant_config,
        device_map={"": 0},
        low_cpu_mem_usage=True,
    )
    model.config.use_cache = False
    summary["gpu_after_model_load"] = assert_peak_vram_under_limit(torch, args.vram_limit_mb, "after_model_load")
    summary["nvidia_smi_after_model_load"] = nvidia_smi_snapshot()
    summary["placement_after_model_load"] = assert_no_offload(model, "after_model_load")
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    summary["gpu_after_model_cache_trim"] = cuda_mem_snapshot(torch)
    log.event(
        "model_loaded",
        torch_cuda=summary["gpu_after_model_load"],
        nvidia_smi=summary["nvidia_smi_after_model_load"],
        placement=summary["placement_after_model_load"],
    )

    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    target_modules = [item.strip() for item in args.target_modules.split(",") if item.strip()]
    if args.init_adapter_path:
        init_adapter_path = Path(args.init_adapter_path).resolve()
        if not (init_adapter_path / "adapter_config.json").exists():
            raise RuntimeError(f"init adapter path is missing adapter_config.json: {init_adapter_path}")
        model = PeftModel.from_pretrained(model, str(init_adapter_path), is_trainable=True)
        summary["init_adapter_path"] = str(init_adapter_path)
        log.event("init_adapter_loaded", init_adapter_path=str(init_adapter_path))
    else:
        lora_config = LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=target_modules,
        )
        model = get_peft_model(model, lora_config)
    summary["gpu_after_lora"] = assert_peak_vram_under_limit(torch, args.vram_limit_mb, "after_lora")
    summary["placement_after_lora"] = assert_no_offload(model, "after_lora")
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    summary["gpu_after_lora_cache_trim"] = cuda_mem_snapshot(torch)
    summary["param_counts"] = count_trainable_params(model)
    log.event(
        "lora_ready",
        torch_cuda=summary["gpu_after_lora"],
        placement=summary["placement_after_lora"],
        param_counts=summary["param_counts"],
    )

    if args.dry_run_load_only:
        summary["status"] = "dry_run_load_completed"
        summary["finished_at_utc"] = utc_now()
        summary["gpu_final"] = cuda_mem_snapshot(torch)
        log.summary(summary)
        log.event("dry_run_load_completed", torch_cuda=summary["gpu_final"])
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    train_config = SFTConfig(
        output_dir=str(log.run_dir / "train"),
        max_length=args.max_seq_length,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        max_steps=args.max_steps,
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        save_total_limit=args.save_total_limit,
        fp16=False,
        bf16=False,
        gradient_checkpointing=True,
        completion_only_loss=True,
        seed=args.seed,
        data_seed=args.seed,
        packing=False,
        report_to=[],
        logging_dir=str(log.run_dir / "logs"),
        eval_strategy="no",
        save_strategy="steps",
        optim="adamw_torch",
        dataloader_pin_memory=False,
    )
    trainer = SFTTrainer(
        model=model,
        args=train_config,
        train_dataset=train_dataset,
        processing_class=tokenizer,
    )

    summary["status"] = "training"
    summary["training_contract"] = {
        "loss_scope": "completion_only",
        "seed": args.seed,
        "data_seed": args.seed,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "planned_micro_batches": args.max_steps * args.gradient_accumulation_steps,
    }
    log.summary(summary)
    log.event(
        "train_start",
        data_seed=args.seed,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        loss_scope="completion_only",
        max_steps=args.max_steps,
        max_seq_length=args.max_seq_length,
        planned_micro_batches=args.max_steps * args.gradient_accumulation_steps,
        seed=args.seed,
    )
    trainer.train()
    final_adapter_dir = log.run_dir / "final_adapter"
    trainer.model.save_pretrained(final_adapter_dir)
    tokenizer.save_pretrained(final_adapter_dir)
    write_json(log.run_dir / "train_metrics.json", {"log_history": trainer.state.log_history})

    summary["status"] = "completed"
    summary["finished_at_utc"] = utc_now()
    summary["final_adapter_dir"] = str(final_adapter_dir)
    summary["global_step"] = int(trainer.state.global_step)
    summary["gpu_final"] = assert_peak_vram_under_limit(torch, args.vram_limit_mb, "after_train")
    summary["nvidia_smi_final"] = nvidia_smi_snapshot()
    log.summary(summary)
    log.event("completed", global_step=summary["global_step"], torch_cuda=summary["gpu_final"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def main() -> int:
    args = parse_args()
    configure_environment(args)
    selected_run_name = run_name(args)
    run_dir = Path(args.output_root).resolve() / selected_run_name
    log = RunLog(run_dir)
    summary: dict[str, Any] = {
        "status": "initializing",
        "started_at_utc": utc_now(),
        "hostname": socket.gethostname(),
        "repo_root": str(REPO_ROOT),
        "run_dir": str(run_dir),
        "event_log": str(log.event_path),
        "summary_path": str(log.summary_path),
        "model_id": args.model_id,
        "dataset_dir": str(Path(args.dataset_dir).resolve()),
        "train_split": args.train_split,
        "constitution_id": args.constitution_id,
        "local_files_only": bool(args.local_files_only),
        "skip_cuda_allocator_warmup": bool(args.skip_cuda_allocator_warmup),
        "max_steps": args.max_steps,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "seed": args.seed,
        "max_seq_length": args.max_seq_length,
        "vram_limit_mb": args.vram_limit_mb,
        "vram_reserve_mb": args.vram_reserve_mb,
        "lora": {"r": args.lora_r, "alpha": args.lora_alpha, "dropout": args.lora_dropout},
        "target_modules": [
            item.strip() for item in args.target_modules.split(",") if item.strip()
        ],
        "init_adapter_path": str(Path(args.init_adapter_path).resolve()) if args.init_adapter_path else "",
        "safety_contract": {
            "identity_is_metaphor": True,
            "literal_supernatural_claims_allowed": False,
            "cpu_or_disk_model_offload_allowed": False,
            "device_map_auto_allowed": False,
        },
    }
    log.summary(summary)
    log.event("start", model_id=args.model_id, run_dir=str(run_dir))
    exit_code = 0
    try:
        exit_code = run_training(args, log, summary)
    except Exception as exc:
        summary["status"] = "aborted"
        summary["finished_at_utc"] = utc_now()
        summary["abort_reason"] = f"{type(exc).__name__}: {exc}"
        summary["traceback"] = traceback.format_exc(limit=12)
        log.summary(summary)
        log.event("aborted", abort_reason=summary["abort_reason"])
        print(json.dumps(summary, indent=2, sort_keys=True), file=sys.stderr)
        exit_code = 2
    finally:
        release_cuda_memory(summary, log)
        log.summary(summary)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
