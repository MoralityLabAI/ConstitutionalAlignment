#!/usr/bin/env python3
"""Registered six-arm QLoRA trainer for the frame-internalization study.

Recipe frozen in compute_stage_plan_qwen3_1p7b_v1.json: NF4 + double quant,
float16 compute, rank-32/alpha-64 LoRA on q/k/v/o, 4,096-token packed
sequences, microbatch 1, gradient accumulation 64, paged 8-bit AdamW, cosine
schedule with 3% warmup, lr 1e-4, seed 42, assistant-only loss, rows over
4,096 tokens rejected (never truncated). No arm-specific option exists.

Modes
  train      one arm: ``--max-steps 50`` is the F18 smoke, omit it for two epochs.
  aggregate  join six per-arm smoke receipts into
             frame_internalization_training_smoke_receipt.v2.

The model-loading function is separate from ``run_training`` so the loop can be
exercised on CPU with a tiny random model (tests/test_frame_sft_trainer.py).
No GPU validation has been done for this file: the first GPU run is the smoke.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import frame_sft_data as fsd  # noqa: E402

SEQUENCE_LENGTH = 4096
MICRO_BATCHES_PER_STEP = 64
EPOCHS = 2
SEED = 42
LEARNING_RATE = 1e-4
WARMUP_RATIO = 0.03
LORA = {"r": 32, "lora_alpha": 64, "lora_dropout": 0.0, "bias": "none",
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"]}
ARMS = ("neutral_reflection", "F1_reflection", "F1_demonstration",
        "F3_reflection", "F3_demonstration", "F3_concrete_reflection")
SMOKE_STEPS = 50


class StopGate(RuntimeError):
    """A registered abort rule fired; the run stops and is reported."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def block_causal_mask(segment_ids: Any):
    """Boolean [1,1,L,L], True = may attend: causal and same document only."""
    import torch

    seg = segment_ids.view(-1)
    length = seg.numel()
    causal = torch.tril(torch.ones(length, length, dtype=torch.bool, device=seg.device))
    return (causal & (seg[:, None] == seg[None, :]))[None, None]


def pack_to_tensors(pack: fsd.Pack, device: str):
    import torch

    return {
        "input_ids": torch.tensor([pack.input_ids], dtype=torch.long, device=device),
        "labels": torch.tensor([pack.labels], dtype=torch.long, device=device),
        "position_ids": torch.tensor([pack.position_ids], dtype=torch.long, device=device),
        "segment_ids": torch.tensor([pack.segment_ids], dtype=torch.long, device=device),
    }


def packed_loss_sum(model: Any, batch: dict[str, Any]):
    """Sum of next-token cross-entropy over assistant label positions."""
    import torch
    import torch.nn.functional as F

    out = model(
        input_ids=batch["input_ids"],
        attention_mask=block_causal_mask(batch["segment_ids"]),
        position_ids=batch["position_ids"],
        use_cache=False,
    )
    logits = out.logits[0, :-1]
    target = batch["labels"][0, 1:]
    keep = target != fsd.IGNORE_INDEX
    if not bool(keep.any()):
        return logits.sum() * 0.0, 0
    loss = F.cross_entropy(logits[keep].float(), target[keep], reduction="sum")
    return loss, int(keep.sum())


def lora_names_and_counts(model: Any) -> dict[str, Any]:
    names = [n for n, p in model.named_parameters() if p.requires_grad]
    bad = [n for n in names if "lora_" not in n]
    frozen_router = [n for n, p in model.named_parameters() if "router" in n and p.requires_grad]
    return {
        "trainable_parameter_count": sum(p.numel() for n, p in model.named_parameters() if p.requires_grad),
        "trainable_tensor_count": len(names),
        "non_lora_trainable": bad,
        "router_trainable": frozen_router,
    }


def run_training(model: Any, tokenizer: Any, examples: list[fsd.Example], *, device: str,
                 sequence_length: int, micro_batches: int, epochs: int, max_steps: int | None,
                 seed: int, learning_rate: float, optimizer_factory: Any, use_scaler: bool,
                 log: Any = print) -> dict[str, Any]:
    import torch
    from transformers import get_cosine_schedule_with_warmup

    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    steps = fsd.plan_steps(examples, sequence_length, pad_id, micro_batches, seed, epochs, max_steps)
    if not steps:
        raise StopGate("no complete optimizer step can be formed from the data")
    first = pack_to_tensors(steps[0][0], device)
    if tuple(first["input_ids"].shape) != (1, sequence_length):
        raise StopGate(f"first batch shape {tuple(first['input_ids'].shape)} != (1, {sequence_length})")

    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = optimizer_factory(params, lr=learning_rate)
    scheduler = get_cosine_schedule_with_warmup(
        optimizer, max(1, math.ceil(WARMUP_RATIO * len(steps))), len(steps)
    )
    scaler = torch.amp.GradScaler("cuda", enabled=use_scaler) if use_scaler else None
    model.train()
    losses: list[float] = []
    grad_norms: list[float] = []
    consecutive_high = 0
    started = time.time()
    warmup = math.ceil(WARMUP_RATIO * len(steps))
    for step_index, step in enumerate(steps):
        optimizer.zero_grad(set_to_none=True)
        label_tokens = sum(sum(1 for t in pack.labels[1:] if t != fsd.IGNORE_INDEX) for pack in step)
        if label_tokens == 0:
            raise StopGate(f"step {step_index} has no assistant label tokens")
        total = 0.0
        for pack in step:
            batch = pack_to_tensors(pack, device)
            ctx = torch.autocast(device_type="cuda", dtype=torch.float16) if use_scaler else _null()
            with ctx:
                loss_sum, _ = packed_loss_sum(model, batch)
                scaled = loss_sum / label_tokens
            (scaler.scale(scaled) if scaler else scaled).backward()
            total += float(loss_sum.detach())
        if scaler:
            scaler.unscale_(optimizer)
        norm = float(torch.nn.utils.clip_grad_norm_(params, 1.0))
        mean_loss = total / label_tokens
        if not math.isfinite(mean_loss) or not math.isfinite(norm):
            raise StopGate(f"non-finite loss or gradient at step {step_index}")
        if scaler:
            scaler.step(optimizer)
            scaler.update()
        else:
            optimizer.step()
        scheduler.step()
        losses.append(mean_loss)
        grad_norms.append(norm)
        if len(losses) >= 10 and step_index >= warmup:
            baseline = statistics.median(losses[:10])
            consecutive_high = consecutive_high + 1 if mean_loss > 2 * baseline else 0
            if consecutive_high >= 3:
                raise StopGate("loss above twice the first ten-step median for three consecutive steps")
        log(f"step {step_index + 1}/{len(steps)} loss {mean_loss:.4f} gradnorm {norm:.3f}")
    return {
        "steps_completed": len(steps),
        "losses": losses,
        "grad_norms": grad_norms,
        "first_batch_shape": [1, sequence_length],
        "elapsed_seconds": time.time() - started,
        "tokens_per_step_padded": micro_batches * sequence_length,
    }


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def adapter_round_trip(model: Any, base_loader: Any, tokenizer: Any, out_dir: Path, probe: dict[str, Any],
                       device: str, generation_prompts: list[list[dict[str, str]]], max_new_tokens: int) -> dict[str, Any]:
    """Save the adapter, reload it onto a fresh base, compare logits, generate."""
    import torch
    from peft import PeftModel

    model.save_pretrained(str(out_dir))
    model.eval()
    with torch.no_grad():
        before = model(input_ids=probe["input_ids"],
                       attention_mask=block_causal_mask(probe["segment_ids"]),
                       position_ids=probe["position_ids"], use_cache=False).logits.float().cpu()
    fresh = base_loader()
    reloaded = PeftModel.from_pretrained(fresh, str(out_dir))
    reloaded.eval()
    with torch.no_grad():
        after = reloaded(input_ids=probe["input_ids"],
                         attention_mask=block_causal_mask(probe["segment_ids"]),
                         position_ids=probe["position_ids"], use_cache=False).logits.float().cpu()
    max_diff = float((before - after).abs().max())
    valid = 0
    for messages in generation_prompts:
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        enc = tokenizer(text, return_tensors="pt", add_special_tokens=False).to(device)
        with torch.no_grad():
            gen = reloaded.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False)
        decoded = tokenizer.decode(gen[0, enc["input_ids"].shape[1]:], skip_special_tokens=True)
        valid += int(isinstance(decoded, str) and len(decoded.strip()) > 0)
    del reloaded, fresh
    return {"max_abs_logit_diff": max_diff, "logits_match": max_diff < 1e-2,
            "generations_attempted": len(generation_prompts), "generations_nonempty": valid}


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_quantized_base(model_dir: Path):
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                               bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)
    return AutoModelForCausalLM.from_pretrained(str(model_dir), quantization_config=quant,
                                                device_map={"": 0}, local_files_only=True,
                                                attn_implementation="sdpa")


def train_main(args: argparse.Namespace) -> int:
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoTokenizer
    import bitsandbytes as bnb

    if args.arm not in ARMS:
        raise SystemExit(f"unknown arm {args.arm}")
    out_dir = Path(args.output_dir) / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)
    rows = load_rows(Path(args.train_jsonl))
    examples, rejected = fsd.build_examples(tokenizer, rows, SEQUENCE_LENGTH)
    model = prepare_model_for_kbit_training(load_quantized_base(args.model_dir), use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(task_type="CAUSAL_LM", **LORA))
    census = lora_names_and_counts(model)
    if census["non_lora_trainable"] or census["router_trainable"]:
        raise StopGate(f"unexpected trainable parameters: {census}")
    result = run_training(
        model, tokenizer, examples, device="cuda", sequence_length=SEQUENCE_LENGTH,
        micro_batches=MICRO_BATCHES_PER_STEP, epochs=EPOCHS, max_steps=args.max_steps, seed=SEED,
        learning_rate=LEARNING_RATE, optimizer_factory=lambda p, lr: bnb.optim.PagedAdamW8bit(p, lr=lr),
        use_scaler=True)
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    probe_pack = fsd.pack_examples(examples, [0], SEQUENCE_LENGTH, pad_id)[0]
    prompts = [[{"role": "user", "content": rows[i]["messages"][0]["content"]}] for i in range(10)]
    trip = adapter_round_trip(model, lambda: load_quantized_base(args.model_dir), tokenizer,
                              out_dir / "adapter", pack_to_tensors(probe_pack, "cuda"), "cuda", prompts, 48)
    adapter_hashes = {p.name: sha256_file(p) for p in sorted((out_dir / "adapter").glob("*.safetensors"))}
    receipt = {
        "schema_version": "frame_internalization_arm_smoke_receipt.v1",
        "arm": args.arm,
        "max_steps": args.max_steps,
        "train_jsonl_sha256": sha256_file(Path(args.train_jsonl)),
        "trainer_sha256": sha256_file(Path(__file__)),
        "sequence_length": SEQUENCE_LENGTH,
        "micro_batches_per_step": MICRO_BATCHES_PER_STEP,
        "examples": len(examples),
        "rejected_oversize": rejected,
        "census": census,
        "training": result,
        "peak_cuda_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "round_trip": trip,
        "adapter_sha256": adapter_hashes,
        "wraps_into_extra_epochs": bool(args.max_steps and args.max_steps > 0),
    }
    (out_dir / "arm_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"arm": args.arm, "steps": result["steps_completed"], "round_trip": trip}))
    return 0 if trip["logits_match"] and trip["generations_nonempty"] == trip["generations_attempted"] else 2


def aggregate_main(args: argparse.Namespace) -> int:
    receipts = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.arm_receipt]
    by_arm = {r["arm"]: r for r in receipts}
    arms_ok = sorted(by_arm) == sorted(ARMS)
    all_ok = arms_ok and all(
        r["training"]["steps_completed"] == SMOKE_STEPS
        and r["sequence_length"] == SEQUENCE_LENGTH
        and r["round_trip"]["logits_match"]
        and r["round_trip"]["generations_nonempty"] >= 10
        and not r["rejected_oversize"] for r in by_arm.values())
    doc = {
        "schema_version": "frame_internalization_training_smoke_receipt.v2",
        "passed": bool(all_ok and args.cleanup_passed and args.gpu_hours <= 2),
        "gpu_count": 1,
        "sequence_length": SEQUENCE_LENGTH,
        "arms_completed": len(by_arm),
        "steps_per_arm": SMOKE_STEPS,
        "checkpoint_round_trip_all_arms": bool(arms_ok and all(r["round_trip"]["logits_match"] for r in by_arm.values())),
        "cleanup_passed": bool(args.cleanup_passed),
        "gpu_hours": float(args.gpu_hours),
        "note": "cleanup_passed and gpu_hours must be copied from the capped wrapper receipt, not asserted by hand",
        "arm_receipts": {a: sha256_file(Path(p)) for a, p in zip((r["arm"] for r in receipts), args.arm_receipt)},
    }
    Path(args.output).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": doc["passed"]}))
    return 0 if doc["passed"] else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    t = sub.add_parser("train")
    t.add_argument("--arm", required=True, choices=ARMS)
    t.add_argument("--train-jsonl", required=True)
    t.add_argument("--model-dir", type=Path, required=True)
    t.add_argument("--output-dir", required=True)
    t.add_argument("--max-steps", type=int, default=None)
    a = sub.add_parser("aggregate")
    a.add_argument("--arm-receipt", action="append", required=True)
    a.add_argument("--cleanup-passed", action="store_true")
    a.add_argument("--gpu-hours", type=float, required=True)
    a.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        return train_main(args) if args.command == "train" else aggregate_main(args)
    except StopGate as error:
        print(f"STOP GATE: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
