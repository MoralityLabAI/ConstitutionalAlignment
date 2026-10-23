#!/usr/bin/env python3
"""vLLM curriculum generation for F06 (amendment frame_internalization_generation_vllm_v1).

Writes the same rows, events, and receipts as
generate_qwen3_frame_curriculum_transcripts.py so render, parity, and leak tools
work unchanged. Resume-safe: each completed transcript is appended and fsynced,
a torn last line is dropped on relaunch, and completed requests are skipped.
Per-request vLLM seeds derive from each scenario's frozen seed, so the four
frames of a scenario share seeds (not the SplitMix64 stream). Prints no secrets.
"""

from __future__ import annotations

import argparse
import gc
import signal
import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_qwen3_frame_curriculum_transcripts as old  # noqa: E402

SOURCE_FRAMES = old.SOURCE_FRAMES
SAMPLER_NAME = "vllm_per_request_seed_v1"
FIRST_CHUNK = 64
CHUNK = 512
MAX_MODEL_LEN = 10240
# generate_fn(prompts, seeds, max_tokens) -> list of (text, generated_token_count, finish_reason)
GenerateFn = Callable[[list[str], list[int], int], list[tuple[str, int, str]]]


def derive_seed(frozen_seed: int, turn_index: int, attempt_index: int) -> int:
    return (int(frozen_seed) + 100000 * int(turn_index) + 1000003 * int(attempt_index)) & 0x7FFFFFFF


def plan_chunks(jobs: list[dict[str, Any]], first: int = FIRST_CHUNK, size: int = CHUNK) -> list[list[dict[str, Any]]]:
    """A small first chunk lets the throughput gate decide quickly."""
    if first <= 0 or size <= 0:
        raise ValueError("chunk sizes must be positive")
    chunks: list[list[dict[str, Any]]] = []
    start = 0
    width = first
    while start < len(jobs):
        chunks.append(jobs[start : start + width])
        start += width
        width = size
    return chunks


def run_chunk(
    batch: list[dict[str, Any]],
    batch_index: int,
    generate_fn: GenerateFn,
    render_prompt: Callable[[list[dict[str, str]]], str],
    frame_text: dict[str, str],
    dilemmas: dict[str, dict[str, Any]],
    generation: dict[str, Any],
    emit: Callable[[dict[str, Any]], None],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run draft/critique/revise for one chunk; return finished rows and failed IDs."""
    instructions = generation["instructions"]
    conversations = [[{"role": "system", "content": frame_text[r["source_frame"]]}] for r in batch]
    transcripts: list[list[dict[str, str]]] = [[] for _ in batch]
    valid = [True] * len(batch)
    output_tokens = [0] * len(batch)
    maximum_tokens = int(generation["max_tokens_per_turn"])
    for turn_index, turn in enumerate(generation["turns"]):
        for index, request in enumerate(batch):
            if not valid[index]:
                continue
            message = str(instructions[turn]).replace(
                "{dilemma}", dilemmas[request["scenario_id"]]["prompt_text"]
            )
            conversations[index].append({"role": "user", "content": message})
            transcripts[index].append({"role": "user", "content": message})
        pending = [i for i, ok in enumerate(valid) if ok]
        for attempt_index in range(int(generation["retry_attempts"])):
            if not pending:
                break
            prompts = [render_prompt(conversations[i]) for i in pending]
            seeds = [derive_seed(batch[i]["generation_seed"], turn_index, attempt_index) for i in pending]
            started = time.monotonic()
            results = generate_fn(prompts, seeds, maximum_tokens)
            elapsed = time.monotonic() - started
            if len(results) != len(pending):
                raise RuntimeError("engine returned a different number of outputs than prompts")
            tokens = sum(count for _, count, _ in results)
            emit({
                "event": "generation_call", "batch_index": batch_index, "turn_index": turn_index,
                "attempt_index": attempt_index, "batch_size": len(pending),
                "generated_tokens": tokens, "elapsed_seconds": round(elapsed, 6),
                "generated_tokens_per_second": tokens / elapsed if elapsed > 0 else 0.0,
                "truncated": sum(1 for _, _, reason in results if reason == "length"),
            })
            retry: list[int] = []
            for slot, (text, count, _reason) in enumerate(results):
                index = pending[slot]
                output_tokens[index] += count
                visible = old.visible_answer(text)
                if not visible:
                    retry.append(index)
                    continue
                conversations[index].append({"role": "assistant", "content": visible})
                transcripts[index].append({"role": "assistant", "content": visible})
            pending = retry
        for index in pending:
            valid[index] = False
    rows: list[dict[str, Any]] = []
    failed: list[str] = []
    for index, request in enumerate(batch):
        if not valid[index] or len(transcripts[index]) != 6:
            failed.append(str(request["request_id"]))
            continue
        final = transcripts[index][-1]["content"]
        row = dict(request)
        row.update({
            "dilemma_prompt": dilemmas[request["scenario_id"]]["prompt_text"],
            "transcript": transcripts[index],
            "final": final,
            "final_sha256": old.sha256_text(final),
            "generated_token_count": output_tokens[index],
            "sampler": SAMPLER_NAME,
        })
        rows.append(row)
    return rows, failed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, default=old.DEFAULT_FREEZE)
    parser.add_argument("--f04-receipt", type=Path, default=old.DEFAULT_F04)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-frames", nargs="+", choices=SOURCE_FRAMES, default=list(SOURCE_FRAMES))
    parser.add_argument("--limit-per-frame", type=int, default=0)
    parser.add_argument("--first-chunk", type=int, default=FIRST_CHUNK)
    parser.add_argument("--chunk", type=int, default=CHUNK)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    freeze_path = args.freeze.resolve()
    model_dir = args.model_dir.resolve()
    output_dir = args.output_dir.resolve()
    freeze = old.read_json(freeze_path)
    f04 = old.read_json(args.f04_receipt.resolve())
    old.validate_inputs(freeze, f04, freeze_path, model_dir)
    root = old.REPO_ROOT
    request_path = root / freeze["requests"]["path"]
    dilemma_path = root / freeze["dilemmas"]["path"]
    if old.sha256_file(request_path) != freeze["requests"]["sha256"]:
        raise RuntimeError("request pack hash mismatch")
    if old.sha256_file(dilemma_path) != freeze["dilemmas"]["sha256"]:
        raise RuntimeError("dilemma pool hash mismatch")
    dilemmas = {row["scenario_id"]: row for row in old.read_jsonl(dilemma_path)}
    frame_text: dict[str, str] = {}
    for frame in args.source_frames:
        binding = freeze["frames"][frame]
        path = root / binding["path"]
        if old.sha256_file(path) != binding["file_sha256"]:
            raise RuntimeError(f"source frame file hash mismatch: {frame}")
        frame_text[frame] = old.read_frame(path)
        if old.sha256_text(frame_text[frame]) != binding["prompt_text_sha256"]:
            raise RuntimeError(f"source frame text hash mismatch: {frame}")
    requests_by_frame: dict[str, list[dict[str, Any]]] = {f: [] for f in args.source_frames}
    for request in old.read_jsonl(request_path):
        if request["source_frame"] in requests_by_frame:
            requests_by_frame[request["source_frame"]].append(request)
    if any(len(rows) != 5600 for rows in requests_by_frame.values()):
        raise RuntimeError("every selected frame must have exactly 5,600 frozen requests")
    if args.limit_per_frame:
        requests_by_frame = {f: rows[: args.limit_per_frame] for f, rows in requests_by_frame.items()}

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_paths = {f: output_dir / f"{f}.jsonl" for f in args.source_frames}
    event_path = output_dir / "generation.events.jsonl"
    torn = {f: old.repair_torn_tail(p) for f, p in raw_paths.items()}
    done = {f: old.load_done(p) for f, p in raw_paths.items()}
    jobs = old.pending_jobs(requests_by_frame, list(args.source_frames), done)
    emit = lambda event: old.append_jsonl(event_path, {**event, "timestamp_utc": old.utc_now()})  # noqa: E731
    emit({"event": "start", "engine": "vllm", "selected_frames": args.source_frames,
          "limit_per_frame": args.limit_per_frame, "pending_requests": len(jobs),
          "torn_tail_bytes_dropped": torn})

    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams
    import vllm

    generation = freeze["generation"]
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)

    def render_prompt(conversation: list[dict[str, str]]) -> str:
        return old.render_prompt(tokenizer, conversation)

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    llm: Any = None
    failures: list[str] = []
    started = time.monotonic()
    try:
        llm = LLM(model=str(model_dir), tokenizer=str(model_dir), dtype="bfloat16", seed=0,
                  max_model_len=MAX_MODEL_LEN, gpu_memory_utilization=args.gpu_memory_utilization,
                  generation_config="vllm", enable_prefix_caching=True, trust_remote_code=False)

        def generate_fn(prompts: list[str], seeds: list[int], max_tokens: int) -> list[tuple[str, int, str]]:
            if any(len(tokenizer(p, add_special_tokens=False)["input_ids"]) + max_tokens > MAX_MODEL_LEN
                   for p in prompts):
                raise RuntimeError("frozen generation would exceed the configured context")
            params = [
                SamplingParams(temperature=float(generation["temperature"]), top_p=float(generation["top_p"]),
                               top_k=0, min_p=0.0, repetition_penalty=1.0, max_tokens=max_tokens,
                               seed=seed, skip_special_tokens=False)
                for seed in seeds
            ]
            outputs = llm.generate(prompts, params, use_tqdm=False)
            return [(o.outputs[0].text, len(o.outputs[0].token_ids), str(o.outputs[0].finish_reason))
                    for o in outputs]

        for batch_index, batch in enumerate(plan_chunks(jobs, args.first_chunk, args.chunk)):
            rows, failed = run_chunk(batch, batch_index, generate_fn, render_prompt, frame_text,
                                     dilemmas, generation, emit)
            for request_id in failed:
                emit({"event": "request_failed", "request_id": request_id})
            failures += failed
            for row in rows:
                old.append_jsonl(raw_paths[row["source_frame"]], row)
                emit({"event": "checkpoint", "request_id": row["request_id"],
                      "source_frame": row["source_frame"], "batch_index": batch_index})
    finally:
        llm = None
        gc.collect()
        status = "not_loaded"
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                status = "completed"
        except Exception:  # noqa: BLE001 - cleanup must not mask the original error
            status = "failed"
        emit({"event": "cleanup", "status": status, "elapsed_seconds": round(time.monotonic() - started, 3)})

    for frame, selected in requests_by_frame.items():
        selected_ids = {str(r["request_id"]) for r in selected}
        completed = old.load_done(raw_paths[frame]) & selected_ids
        complete_limited = len(completed) == len(selected_ids)
        receipt = {
            "schema_version": "frame_internalization_curriculum_generation_receipt.v1",
            "source_frame": frame,
            "scope": "full" if len(selected) == 5600 else "bounded_smoke",
            "registered_requested": 5600, "requested": len(selected), "completed": len(completed),
            "failed": sorted(set(failures) & selected_ids),
            "limited_run_complete": complete_limited,
            "complete": complete_limited and len(selected) == 5600,
            "f04_receipt_sha256": old.sha256_file(args.f04_receipt.resolve()),
            "request_freeze_sha256": old.sha256_file(freeze_path),
            "generator_sha256": old.sha256_file(Path(__file__).resolve()),
            "raw_path": str(raw_paths[frame]),
            "raw_sha256": old.sha256_file(raw_paths[frame]) if raw_paths[frame].is_file() else None,
            "events_path": str(event_path),
            "sampling": {
                "algorithm": SAMPLER_NAME, "engine": "vllm", "engine_version": vllm.__version__,
                "dtype": "bfloat16", "quantization": "none",
                "seed_rule": "(seed + 100000*turn + 1000003*attempt) & 0x7FFFFFFF",
                "temperature": generation["temperature"], "top_p": generation["top_p"], "top_k": "disabled",
            },
            "amendment": "frame_internalization_generation_vllm_v1",
            "cleanup_status": status,
        }
        (output_dir / f"{frame}.receipt.json").write_text(
            old.json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
