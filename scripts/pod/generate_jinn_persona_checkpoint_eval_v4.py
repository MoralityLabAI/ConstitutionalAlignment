#!/usr/bin/env python3
"""Generate expanded base/checkpoint persona responses with resumable row saves."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
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


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


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
    if not path.exists():
        return values
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
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        )
        handle.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--model-revision", default="main")
    parser.add_argument("--arm-config", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def render_prompt(
    tokenizer: Any,
    *,
    system_prompt: str,
    user_prompt: str,
) -> str:
    return tokenizer.apply_chat_template(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
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
    arm_config_path = args.arm_config.resolve()
    output_dir = args.output_dir.resolve()
    cache_dir = args.cache_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    event_path = output_dir / "events.jsonl"
    receipt_path = output_dir / "generation_receipt.json"
    partial_path = output_dir / "partial_responses.jsonl"
    final_path = output_dir / "responses.jsonl"

    protocol = load_json(protocol_path)
    if protocol.get("status") != "prospective_frozen_before_v4_outputs":
        raise ValueError("expanded protocol is not prospectively frozen")
    prompts = load_jsonl(prompts_path)
    expected_prompts = int(protocol["sample_design"]["independent_families"])
    if len(prompts) != expected_prompts:
        raise ValueError(
            f"expected {expected_prompts} prompts, found {len(prompts)}"
        )
    family_ids = [str(row["family_id"]) for row in prompts]
    if len(set(family_ids)) != len(family_ids):
        raise ValueError("family IDs are not unique")
    arms = list(load_json(arm_config_path)["arms"])
    arm_ids = [str(arm["arm_id"]) for arm in arms]
    if arm_ids != list(protocol["arms"]["ordered_arm_ids"]):
        raise ValueError("arm order differs from frozen protocol")
    if arm_ids[0] != "base" or arms[0].get("adapter_path") is not None:
        raise ValueError("the first arm must be the unadapted base")
    for arm in arms[1:]:
        adapter_path = Path(str(arm["adapter_path"])).resolve()
        if not adapter_path.is_dir():
            raise FileNotFoundError(adapter_path)
    expected_rows = len(prompts) * len(arms)
    if final_path.exists():
        raise FileExistsError(f"final output already exists: {final_path}")
    if partial_path.exists() and not args.resume:
        raise FileExistsError(
            f"partial output exists without --resume: {partial_path}"
        )

    existing_rows = load_jsonl(partial_path) if args.resume else []
    completed_keys = {
        (str(row["arm"]), str(row["family_id"])) for row in existing_rows
    }
    if len(completed_keys) != len(existing_rows):
        raise ValueError("partial output contains duplicate arm/family rows")
    valid_keys = {
        (arm_id, family_id)
        for arm_id in arm_ids
        for family_id in family_ids
    }
    if not completed_keys <= valid_keys:
        raise ValueError("partial output contains rows outside the frozen universe")

    receipt: dict[str, Any] = {
        "schema_version": "jinn_persona_expanded_generation_receipt_v4",
        "status": "validated" if args.dry_run else "initializing",
        "started_at_utc": utc_now(),
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "protocol_sha256": sha256_file(protocol_path),
        "prompts_sha256": sha256_file(prompts_path),
        "arm_config_sha256": sha256_file(arm_config_path),
        "arm_ids": arm_ids,
        "prompt_count": len(prompts),
        "expected_rows": expected_rows,
        "resumed_rows": len(existing_rows),
        "checkpoint_interval_rows": int(
            protocol["resource_contract"]["checkpoint_interval_rows"]
        ),
        "dry_run": bool(args.dry_run),
    }
    write_json(receipt_path, receipt)
    append_jsonl(
        event_path,
        {
            "ts": utc_now(),
            "event": "validated",
            "rows_complete": len(existing_rows),
            "expected_rows": expected_rows,
        },
    )
    if args.dry_run:
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0

    generation = dict(protocol["generation"])
    tokenizer: Any = None
    model: Any = None
    base_model: Any = None
    try:
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
        base_model = AutoModelForCausalLM.from_pretrained(
            args.model_id,
            revision=args.model_revision,
            trust_remote_code=True,
            cache_dir=str(cache_dir),
            config=config,
            quantization_config=quantization,
            device_map="auto",
            low_cpu_mem_usage=True,
        )
        base_model.eval()
        base_model.config.use_cache = True
        torch.cuda.reset_peak_memory_stats()
        receipt["status"] = "generating"
        write_json(receipt_path, receipt)

        row_count = len(existing_rows)
        for prompt in prompts:
            key = ("base", str(prompt["family_id"]))
            if key in completed_keys:
                continue
            rendered = render_prompt(
                tokenizer,
                system_prompt=str(generation["system_prompt"]),
                user_prompt=str(prompt["prompt"]),
            )
            text, tokens, seconds = generate(
                base_model,
                tokenizer,
                rendered,
                max_new_tokens=int(generation["max_new_tokens"]),
                repetition_penalty=float(generation["repetition_penalty"]),
            )
            append_jsonl(
                partial_path,
                {
                    **prompt,
                    "arm": "base",
                    "completion": text,
                    "output_tokens": tokens,
                    "generation_seconds": round(seconds, 6),
                },
            )
            row_count += 1
            if row_count % receipt["checkpoint_interval_rows"] == 0:
                append_jsonl(
                    event_path,
                    {
                        "ts": utc_now(),
                        "event": "row_checkpoint",
                        "rows_complete": row_count,
                        "arm": "base",
                    },
                )

        first_adapter = arms[1]
        model = PeftModel.from_pretrained(
            base_model,
            str(Path(str(first_adapter["adapter_path"])).resolve()),
            adapter_name=str(first_adapter["arm_id"]),
            is_trainable=False,
        )
        for arm in arms[2:]:
            model.load_adapter(
                str(Path(str(arm["adapter_path"])).resolve()),
                adapter_name=str(arm["arm_id"]),
                is_trainable=False,
            )
        model.eval()
        for arm in arms[1:]:
            arm_id = str(arm["arm_id"])
            model.set_adapter(arm_id)
            for prompt in prompts:
                key = (arm_id, str(prompt["family_id"]))
                if key in completed_keys:
                    continue
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
                append_jsonl(
                    partial_path,
                    {
                        **prompt,
                        "arm": arm_id,
                        "completion": text,
                        "output_tokens": tokens,
                        "generation_seconds": round(seconds, 6),
                    },
                )
                row_count += 1
                if row_count % receipt["checkpoint_interval_rows"] == 0:
                    append_jsonl(
                        event_path,
                        {
                            "ts": utc_now(),
                            "event": "row_checkpoint",
                            "rows_complete": row_count,
                            "arm": arm_id,
                        },
                    )

        rows = load_jsonl(partial_path)
        keys = {(str(row["arm"]), str(row["family_id"])) for row in rows}
        if len(rows) != expected_rows or keys != valid_keys:
            raise ValueError(
                f"output join failed: rows={len(rows)} "
                f"keys={len(keys)} expected={expected_rows}"
            )
        arm_order = {arm_id: index for index, arm_id in enumerate(arm_ids)}
        rows.sort(
            key=lambda row: (
                arm_order[str(row["arm"])],
                str(row["family_id"]),
            )
        )
        write_jsonl(final_path, rows)
        receipt.update(
            {
                "status": "completed",
                "completed_at_utc": utc_now(),
                "result_rows": len(rows),
                "result_sha256": sha256_file(final_path),
                "partial_sha256": sha256_file(partial_path),
                "generation": generation,
                "torch_version": torch.__version__,
                "cuda_version": torch.version.cuda,
                "peak_gpu_memory_mib": round(
                    torch.cuda.max_memory_allocated() / (1024 * 1024), 3
                ),
            }
        )
        append_jsonl(
            event_path,
            {
                "ts": utc_now(),
                "event": "generation_completed",
                "rows_complete": len(rows),
                "result_sha256": receipt["result_sha256"],
            },
        )
    except BaseException as exc:
        receipt.update(
            {
                "status": "aborted",
                "aborted_at_utc": utc_now(),
                "error": f"{type(exc).__name__}: {exc}",
                "rows_preserved": len(load_jsonl(partial_path)),
            }
        )
        append_jsonl(
            event_path,
            {
                "ts": utc_now(),
                "event": "abort",
                "error": receipt["error"],
                "rows_preserved": receipt["rows_preserved"],
            },
        )
        raise
    finally:
        model = None
        base_model = None
        tokenizer = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
        receipt["process_cleanup_attempted"] = True
        write_json(receipt_path, receipt)
        append_jsonl(
            event_path,
            {
                "ts": utc_now(),
                "event": "process_cleanup_attempted",
                "status": receipt["status"],
            },
        )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
