#!/usr/bin/env python3
"""Generate held-out policy responses and report proxy reward components."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.prompting import DIRECT_CHAT_TEMPLATE_KWARGS, render_direct_chat_prompt
from alignment_harness.rewards import DEFAULT_REWARD_WEIGHTS, REWARD_NAMES, score_response


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-revision", default="main")
    parser.add_argument("--adapter-path", default="")
    parser.add_argument("--dataset", default="artifacts/alignment_conditioning_v1/rl_test.jsonl")
    parser.add_argument("--output-dir", default="artifacts/alignment_policy_evaluation")
    parser.add_argument("--cache-dir", default="")
    parser.add_argument("--max-prompts", type=int, default=12)
    parser.add_argument("--num-generations", type=int, default=1)
    parser.add_argument("--max-prompt-length", type=int, default=512)
    parser.add_argument("--max-completion-length", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--dtype", choices=["float16", "bfloat16"], default="bfloat16")
    parser.add_argument("--seed", type=int, default=20260714)
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
    rows = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize an empty evaluation")
    component_values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for name, value in row["scores"].items():
            component_values[name].append(float(value))
    component_means = {
        name: sum(values) / len(values)
        for name, values in sorted(component_values.items())
    }
    weighted_proxy = sum(
        component_means[name.removesuffix("_reward")] * weight
        if name.removesuffix("_reward") in component_means
        else 0.0
        for name, weight in zip(REWARD_NAMES, DEFAULT_REWARD_WEIGHTS)
    )
    summary = {
        "responses": len(rows),
        "unique_prompts": len({row["example_id"] for row in rows}),
        "component_means": component_means,
        "weighted_proxy_reward_mean": weighted_proxy,
        "valid_decision_rate": sum(row["scores"]["valid_decision"] == 1.0 for row in rows) / len(rows),
        "complete_contract_rate": sum(row["scores"]["response_contract"] == 1.0 for row in rows) / len(rows),
        "anti_gaming_nonnegative_rate": sum(row["scores"]["anti_gaming"] >= 0.0 for row in rows) / len(rows),
    }
    rows_with_generation_audit = [row for row in rows if "generated_token_count" in row]
    if rows_with_generation_audit:
        summary.update(
            {
                "mean_generated_tokens": sum(
                    row["generated_token_count"] for row in rows_with_generation_audit
                )
                / len(rows_with_generation_audit),
                "termination_rate": sum(
                    bool(row["terminated_with_eos"]) for row in rows_with_generation_audit
                )
                / len(rows_with_generation_audit),
                "completion_ceiling_hit_rate": sum(
                    bool(row["hit_completion_ceiling"]) for row in rows_with_generation_audit
                )
                / len(rows_with_generation_audit),
            }
        )
    return summary


def main() -> int:
    args = parse_args()
    import torch
    from peft import PeftModel
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    dataset_path = resolve_repo_path(args.dataset)
    output_dir = resolve_repo_path(args.output_dir)
    adapter_path = resolve_repo_path(args.adapter_path) if args.adapter_path else None
    rows = load_jsonl(dataset_path)
    if args.max_prompts > 0:
        rows = rows[: args.max_prompts]
    if not rows:
        raise SystemExit(f"no evaluation prompts in {dataset_path}")

    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    compute_dtype = torch.float16 if args.dtype == "float16" else torch.bfloat16
    cache_dir = args.cache_dir or None
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_id,
        revision=args.model_revision,
        trust_remote_code=True,
        cache_dir=cache_dir,
        use_fast=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.truncation_side = "right"
    config = AutoConfig.from_pretrained(
        args.model_id,
        revision=args.model_revision,
        trust_remote_code=True,
        cache_dir=cache_dir,
    )
    config.pad_token_id = tokenizer.pad_token_id
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        revision=args.model_revision,
        trust_remote_code=True,
        cache_dir=cache_dir,
        config=config,
        device_map="auto",
        low_cpu_mem_usage=True,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        ),
    )
    if adapter_path is not None:
        model = PeftModel.from_pretrained(model, str(adapter_path), is_trainable=False)
    model.eval()
    device = next(model.parameters()).device

    evaluated: list[dict[str, Any]] = []
    for row in rows:
        rendered = render_direct_chat_prompt(tokenizer, row["prompt"])
        encoded = tokenizer(
            rendered,
            return_tensors="pt",
            truncation=True,
            max_length=args.max_prompt_length,
        ).to(device)
        generation_kwargs: dict[str, Any] = {
            "num_return_sequences": args.num_generations,
            "max_new_tokens": args.max_completion_length,
            "pad_token_id": tokenizer.pad_token_id,
            "eos_token_id": tokenizer.eos_token_id,
        }
        if args.num_generations > 1:
            generation_kwargs.update(
                {
                    "do_sample": True,
                    "temperature": args.temperature,
                    "top_p": args.top_p,
                }
            )
        with torch.inference_mode():
            generated = model.generate(**encoded, **generation_kwargs)
        prompt_length = encoded["input_ids"].shape[1]
        for generation_index, sequence in enumerate(generated):
            completion_ids = sequence[prompt_length:].tolist()
            terminated_with_eos = tokenizer.eos_token_id in completion_ids
            if terminated_with_eos:
                generated_token_count = completion_ids.index(tokenizer.eos_token_id) + 1
            else:
                generated_token_count = len(completion_ids)
                while generated_token_count and completion_ids[generated_token_count - 1] == tokenizer.pad_token_id:
                    generated_token_count -= 1
            completion = tokenizer.decode(completion_ids, skip_special_tokens=True)
            scores = score_response(
                completion,
                valid_option_ids=row["valid_option_ids"],
                valid_option_texts=row["valid_option_texts"],
                allowed_tenet_ids=row["allowed_tenet_ids"],
                relevant_tenet_ids=row["relevant_tenet_ids"],
            )
            evaluated.append(
                {
                    "example_id": row["example_id"],
                    "generation_index": generation_index,
                    "completion": completion,
                    "generated_token_count": generated_token_count,
                    "terminated_with_eos": terminated_with_eos,
                    "hit_completion_ceiling": (
                        not terminated_with_eos
                        and generated_token_count >= args.max_completion_length
                    ),
                    "scores": scores,
                }
            )

    summary = summarize(evaluated)
    receipt = {
        "receipt_version": "alignment_policy_evaluation_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "proxy_scores_are_not_compliance_metrics": True,
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "adapter_path": str(adapter_path) if adapter_path else "",
        "adapter_sha256": sha256_file(adapter_path / "adapter_model.safetensors") if adapter_path else "",
        "dataset_path": str(dataset_path),
        "dataset_sha256": sha256_file(dataset_path),
        "generation_args": vars(args),
        "chat_template_kwargs": DIRECT_CHAT_TEMPLATE_KWARGS,
        "summary": summary,
    }
    write_jsonl(output_dir / "responses.jsonl", evaluated)
    write_json(output_dir / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
