#!/usr/bin/env python3
"""Generate paired persona-free base and adapter responses on one GPU."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import (
    AutoConfig,
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected a JSON object")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number}: expected an object")
            values.append(value)
    return values


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
        newline="\n",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--model-revision", default="main")
    parser.add_argument("--adapter-dir", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    return parser.parse_args()


def render_prompt(
    tokenizer: Any,
    *,
    system_prompt: str,
    user_prompt: str,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )


def generate(
    model: Any,
    tokenizer: Any,
    rendered: str,
    *,
    max_new_tokens: int,
    repetition_penalty: float,
) -> tuple[str, int, float]:
    inputs = tokenizer(rendered, return_tensors="pt").to(model.device)
    started = time.monotonic()
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            do_sample=False,
            max_new_tokens=max_new_tokens,
            repetition_penalty=repetition_penalty,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    elapsed = time.monotonic() - started
    generated = output[0, inputs["input_ids"].shape[1] :]
    return tokenizer.decode(generated, skip_special_tokens=True).strip(), int(
        generated.shape[0]
    ), elapsed


def main() -> int:
    args = parse_args()
    protocol_path = args.protocol.resolve()
    prompts_path = args.prompts.resolve()
    adapter_dir = args.adapter_dir.resolve()
    output_dir = args.output_dir.resolve()
    cache_dir = args.cache_dir.resolve()
    protocol = load_json(protocol_path)
    if protocol.get("status") != "prospective_frozen_before_adapter_outputs":
        raise ValueError("behavior protocol is not prospectively frozen")
    prompts = load_jsonl(prompts_path)
    if len(prompts) != 18:
        raise ValueError(f"expected 18 prompts, found {len(prompts)}")
    probe_ids = [str(row["probe_id"]) for row in prompts]
    if len(set(probe_ids)) != len(probe_ids):
        raise ValueError("probe IDs are not unique")
    if not adapter_dir.is_dir():
        raise FileNotFoundError(adapter_dir)

    generation = dict(protocol["generation"])
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_id,
        revision=args.model_revision,
        trust_remote_code=True,
        cache_dir=str(cache_dir),
        use_fast=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    config = AutoConfig.from_pretrained(
        args.model_id,
        revision=args.model_revision,
        trust_remote_code=True,
        cache_dir=str(cache_dir),
    )
    if getattr(config, "pad_token_id", None) is None:
        config.pad_token_id = tokenizer.pad_token_id
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        revision=args.model_revision,
        trust_remote_code=True,
        cache_dir=str(cache_dir),
        config=config,
        quantization_config=quantization,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    model.eval()
    rows: list[dict[str, Any]] = []
    for prompt in prompts:
        rendered = render_prompt(
            tokenizer,
            system_prompt=str(generation["system_prompt"]),
            user_prompt=str(prompt["prompt"]),
        )
        text, tokens, seconds = generate(
            model,
            tokenizer,
            rendered,
            max_new_tokens=int(generation["max_new_tokens"]),
            repetition_penalty=float(generation["repetition_penalty"]),
        )
        rows.append(
            {
                **prompt,
                "arm": "base",
                "completion": text,
                "output_tokens": tokens,
                "generation_seconds": round(seconds, 6),
            }
        )

    model = PeftModel.from_pretrained(model, str(adapter_dir), is_trainable=False)
    model.eval()
    for prompt in prompts:
        rendered = render_prompt(
            tokenizer,
            system_prompt=str(generation["system_prompt"]),
            user_prompt=str(prompt["prompt"]),
        )
        text, tokens, seconds = generate(
            model,
            tokenizer,
            rendered,
            max_new_tokens=int(generation["max_new_tokens"]),
            repetition_penalty=float(generation["repetition_penalty"]),
        )
        rows.append(
            {
                **prompt,
                "arm": "jinn_persona_adapter",
                "completion": text,
                "output_tokens": tokens,
                "generation_seconds": round(seconds, 6),
            }
        )

    result_path = output_dir / "paired_responses.jsonl"
    write_jsonl(result_path, rows)
    metadata = {
        "schema_version": "jinn_persona_paired_generation_receipt_v1",
        "status": "completed",
        "completed_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "adapter_dir": str(adapter_dir),
        "protocol_sha256": sha256_file(protocol_path),
        "prompts_sha256": sha256_file(prompts_path),
        "prompt_count": len(prompts),
        "result_rows": len(rows),
        "result_sha256": sha256_file(result_path),
        "generation": generation,
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "peak_gpu_memory_mib": round(
            torch.cuda.max_memory_allocated() / (1024 * 1024), 3
        ),
    }
    write_json(output_dir / "generation_receipt.json", metadata)
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
