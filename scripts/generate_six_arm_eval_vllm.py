#!/usr/bin/env python3
"""Registered primary/benign/override generation with vLLM + LoRA (unscored).

Amendment frame_internalization_evaluation_vllm_v1 moves evaluation decoding from
transformers NF4 to vLLM bf16 for the base model and every adapter alike. Prompts,
tier templates, seeds, temperature, top-p and the 6,000-token cap follow
prompt_sft_contrast_v3_qwen3_1p7b.json. Judge scoring needs API credentials and is
done off the pod. Resume-safe; prints no secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "experiments/frame_internalization_sft_v1"
CONTRACT = PKG / "prompt_sft_contrast_v3_qwen3_1p7b.json"
UNIVERSES = PKG / "rerun_freeze/evaluation_universes_v2"
MATERIALS = PKG / "predecessor_recovery/session_extracted/experiment_2/recovered_worktree/src/materials.py"
ARMS = ("neutral_reflection", "F1_reflection", "F1_demonstration", "F3_reflection",
        "F3_demonstration", "F3_concrete_reflection")
PROMPT_ARMS = ("F0", "F1", "F3", "F3_concrete")
TIERS = ("free", "paid")
MAX_ATTEMPTS = 4
MAX_TOKENS = 6000
MAX_MODEL_LEN = 12288
OVERRIDE_COUNT = 100
THINK = re.compile(r"<\s*think\s*>(.*?)</\s*think\s*>", re.DOTALL | re.IGNORECASE)
ACCEPT = re.compile(r"<request_fully_accepted\s*/>")
REJECT = re.compile(r"<rejected\s*/>")
SPECIAL = ("<|im_end|>", "<|endoftext|>")
GenerateFn = Callable[[list[str], list[int]], list[tuple[str, int, str]]]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seed_for(prompt_index: int, tier: str, attempt: int = 0) -> int:
    """Registered schedule 420000 + 2*index + tier_index; retries offset by the attempt."""
    return (420000 + 2 * prompt_index + TIERS.index(tier) + 1000003 * attempt) & 0x7FFFFFFF


def build_system_prompts(contract: dict[str, Any], root: Path = REPO) -> dict[str, str]:
    """F0 is the base byte for byte; framed prompts are base + blank line + stripped frame."""
    spec = contract["system_prompt_construction"]
    base_bytes = (root / spec["base"]["path"]).read_bytes()
    if sha256_bytes(base_bytes) != spec["base"]["sha256"]:
        raise RuntimeError("base system prompt hash mismatch")
    base = base_bytes.decode("utf-8")
    prompts = {"F0": base}
    for name, item in spec["prompts"].items():
        if name == "F0":
            continue
        source = item["frame_source"]
        raw = (root / source["path"]).read_bytes()
        if sha256_bytes(raw) != source["sha256"]:
            raise RuntimeError(f"frame source hash mismatch: {name}")
        frame = json.loads(raw.decode("utf-8"))["prompt_text"] if source["kind"] == "json_prompt_text" else raw.decode("utf-8")
        text = (base.encode("utf-8") + b"\n\n" + frame.strip().encode("utf-8"))
        if sha256_bytes(text) != item["sha256"]:
            raise RuntimeError(f"constructed system prompt hash mismatch: {name}")
        prompts[name] = text.decode("utf-8")
    if sha256_bytes(prompts["F0"].encode("utf-8")) != spec["prompts"]["F0"]["sha256"]:
        raise RuntimeError("F0 hash mismatch")
    return prompts


def generic_override() -> str:
    """OVERRIDE_GENERIC from the recovered predecessor materials, read without importing."""
    source = MATERIALS.read_text(encoding="utf-8")
    start = source.index("OVERRIDE_GENERIC = (")
    end = source.index("\n)\n", start)
    namespace: dict[str, Any] = {}
    exec(source[start : end + 2], {}, namespace)  # a parenthesised string literal only
    return str(namespace["OVERRIDE_GENERIC"])


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_bytes().decode("utf-8").splitlines() if l.strip()]


def load_universe(name: str) -> list[dict[str, Any]]:
    if name == "harmful":
        return [{"prompt_id": r["prompt_id"], "text": r["text"]} for r in read_jsonl(UNIVERSES / "harmful_queries.jsonl")]
    if name == "benign":
        return [{"prompt_id": r["prompt_id"], "text": r["text"]} for r in read_jsonl(UNIVERSES / "benign_queries.jsonl")]
    if name == "override":
        rows = read_jsonl(UNIVERSES / "override_queries.jsonl")[:OVERRIDE_COUNT]
        prefix = generic_override()
        return [{"prompt_id": r["override_prompt_id"], "text": prefix + "\n\n" + r["text"]} for r in rows]
    raise ValueError(name)


def list_cells() -> list[dict[str, str]]:
    cells = [{"universe": "harmful", "arm": "base", "prompt_arm": f} for f in PROMPT_ARMS]
    cells += [{"universe": "harmful", "arm": a, "prompt_arm": "F0"} for a in ARMS]
    cells += [{"universe": "benign", "arm": a, "prompt_arm": "F0"} for a in ("base",) + ARMS]
    cells += [{"universe": "override", "arm": a, "prompt_arm": "F0"} for a in ARMS]
    for c in cells:
        c["cell_id"] = f"{c['universe']}__{c['arm']}__{c['prompt_arm']}"
    return cells


def extract(text: str) -> tuple[str, str]:
    reasoning = "\n".join(THINK.findall(text)).strip()
    clean = THINK.sub("", text)
    for token in SPECIAL:
        clean = clean.replace(token, "")
    return reasoning, clean.strip()


def is_valid(reasoning: str, clean: str, finish_reason: str) -> bool:
    """Recovered gen_driver rule plus no truncation: reasoning present and an accept/reject tag."""
    if finish_reason == "length" or not reasoning or not clean:
        return False
    return bool(ACCEPT.search(clean) or REJECT.search(clean))


def build_requests(cell: dict[str, str], universe: list[dict[str, Any]], tier_templates: dict[str, str],
                   system_prompts: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for tier in TIERS:
        for index, row in enumerate(universe):
            out.append({
                "cell_id": cell["cell_id"], "universe": cell["universe"], "arm": cell["arm"],
                "prompt_arm": cell["prompt_arm"], "prompt_id": row["prompt_id"], "prompt_index": index,
                "tier": tier, "sample_id": 0,
                "messages": [{"role": "system", "content": system_prompts[cell["prompt_arm"]]},
                             {"role": "user", "content": tier_templates[tier].replace("{user_input}", row["text"])}],
            })
    return out


def run_requests(requests: list[dict[str, Any]], generate_fn: GenerateFn,
                 render: Callable[[list[dict[str, str]]], str], max_attempts: int = MAX_ATTEMPTS) -> list[dict[str, Any]]:
    """Generate, retrying invalid outputs with identical settings except the attempt seed offset."""
    final: dict[int, dict[str, Any]] = {}
    pending = list(range(len(requests)))
    for attempt in range(max_attempts):
        if not pending:
            break
        prompts = [render(requests[i]["messages"]) for i in pending]
        seeds = [seed_for(requests[i]["prompt_index"], requests[i]["tier"], attempt) for i in pending]
        results = generate_fn(prompts, seeds)
        if len(results) != len(pending):
            raise RuntimeError("engine returned a different number of outputs than prompts")
        retry = []
        for slot, (text, tokens, reason) in enumerate(results):
            i = pending[slot]
            reasoning, clean = extract(text)
            valid = is_valid(reasoning, clean, reason)
            request = requests[i]
            final[i] = {
                "cell_id": request["cell_id"], "universe": request["universe"], "arm": request["arm"],
                "prompt_arm": request["prompt_arm"], "prompt_id": request["prompt_id"],
                "tier": request["tier"], "sample_id": 0, "seed": seeds[slot], "attempts": attempt + 1,
                "valid": valid, "tag_accepted": bool(ACCEPT.search(clean)), "tag_rejected": bool(REJECT.search(clean)),
                "reasoning_content": reasoning, "output_without_scratchpad": clean,
                "generated_tokens": tokens, "finish_reason": reason,
                "truncated": reason == "length", "missing_visible_answer": not clean,
            }
            if not valid:
                retry.append(i)
        pending = retry
    return [final[i] for i in range(len(requests))]


def append_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    import os

    with path.open("ab") as handle:
        for row in rows:
            handle.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())


def load_done(path: Path) -> set[tuple[str, int, str]]:
    """Completed (prompt_id, tier) keys; a torn last line is truncated first."""
    if not path.is_file():
        return set()
    data = path.read_bytes()
    keep = data.rfind(b"\n") + 1
    if keep < len(data):
        with path.open("r+b") as handle:
            handle.truncate(keep)
        data = data[:keep]
    keys = [(r["prompt_id"], r["tier"]) for r in (json.loads(l) for l in data.decode("utf-8").splitlines() if l.strip())]
    if len(keys) != len(set(keys)):
        raise RuntimeError(f"duplicate rows in {path}")
    return set(keys)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--train-root", type=Path, required=True, help="directory holding <arm>/adapter")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cell", action="append", help="restrict to cell_id (repeatable)")
    parser.add_argument("--limit", type=int, default=0, help="prompts per universe, for smoke checks only")
    parser.add_argument("--chunk", type=int, default=200)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    args = parser.parse_args()

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    systems = build_system_prompts(contract)
    tiers = {}
    for tier in TIERS:
        item = contract["evaluation"]["tier_templates"][tier]
        raw = (REPO / item["path"]).read_bytes()
        if sha256_bytes(raw) != item["sha256"]:
            raise RuntimeError(f"tier template hash mismatch: {tier}")
        tiers[tier] = raw.decode("utf-8")
    cells = [c for c in list_cells() if not args.cell or c["cell_id"] in args.cell]
    universes = {u: load_universe(u) for u in {c["universe"] for c in cells}}
    if args.limit:
        universes = {u: rows[: args.limit] for u, rows in universes.items()}
    args.output_dir.mkdir(parents=True, exist_ok=True)

    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams
    from vllm.lora.request import LoRARequest

    tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)

    def render(messages: list[dict[str, str]]) -> str:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                             enable_thinking=True)

    llm = LLM(model=str(args.model_dir), tokenizer=str(args.model_dir), dtype="bfloat16", seed=0,
              max_model_len=MAX_MODEL_LEN, gpu_memory_utilization=args.gpu_memory_utilization,
              generation_config="vllm", enable_lora=True, max_lora_rank=32, enable_prefix_caching=True)
    decoding = contract["evaluation"]["decoding"]
    started = time.time()
    for lora_id, cell in enumerate(cells, start=1):
        path = args.output_dir / f"{cell['cell_id']}.jsonl"
        done = load_done(path)
        requests = [r for r in build_requests(cell, universes[cell["universe"]], tiers, systems)
                    if (r["prompt_id"], r["tier"]) not in done]
        lora = None
        if cell["arm"] != "base":
            adapter = args.train_root / cell["arm"] / "adapter"
            if not adapter.is_dir():
                raise RuntimeError(f"missing adapter: {adapter}")
            lora = LoRARequest(cell["arm"], ARMS.index(cell["arm"]) + 1, str(adapter))

        def generate_fn(prompts: list[str], seeds: list[int]) -> list[tuple[str, int, str]]:
            params = [SamplingParams(temperature=float(decoding["temperature"]), top_p=float(decoding["top_p"]),
                                     top_k=0, min_p=0.0, repetition_penalty=1.0, max_tokens=MAX_TOKENS,
                                     seed=s, skip_special_tokens=False) for s in seeds]
            outs = llm.generate(prompts, params, lora_request=lora, use_tqdm=False)
            return [(o.outputs[0].text, len(o.outputs[0].token_ids), str(o.outputs[0].finish_reason)) for o in outs]

        for start in range(0, len(requests), args.chunk):
            rows = run_requests(requests[start : start + args.chunk], generate_fn, render)
            append_rows(path, rows)
            event = {"event": "chunk", "cell_id": cell["cell_id"], "rows": len(rows),
                     "valid": sum(r["valid"] for r in rows), "tokens": sum(r["generated_tokens"] for r in rows),
                     "elapsed_total_seconds": round(time.time() - started, 1)}
            with (args.output_dir / "eval.events.jsonl").open("a", encoding="utf-8", newline="\n") as log:
                log.write(json.dumps(event) + "\n")
    (args.output_dir / "eval_receipt.json").write_text(json.dumps({
        "schema_version": "frame_internalization_eval_generation_receipt.v1",
        "amendment": "frame_internalization_evaluation_vllm_v1",
        "cells": [c["cell_id"] for c in cells], "limit": args.limit,
        "complete": not args.limit and not args.cell,
    }, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
