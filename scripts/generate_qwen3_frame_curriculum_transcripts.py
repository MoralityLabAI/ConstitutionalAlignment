#!/usr/bin/env python3
"""Generate resumable Qwen3 curriculum transcripts with paired stateless sampling."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments" / "frame_internalization_sft_v1"
DEFAULT_FREEZE = (
    PACKAGE
    / "rerun_freeze"
    / "qwen3_1p7b_v1"
    / "curriculum_generation_v1"
    / "request_manifest.json"
)
DEFAULT_F04 = PACKAGE / "primelab_f04" / "environment_freeze_20260723.json"
THINK_PATTERN = re.compile(r"<\s*think\s*>(.*?)</\s*think\s*>", re.DOTALL | re.IGNORECASE)
SPECIAL_TOKENS = ("<|im_end|>", "<|endoftext|>")
SOURCE_FRAMES = ("neutral", "F1", "F3", "F3_concrete")
MASK_64 = (1 << 64) - 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--f04-receipt", type=Path, default=DEFAULT_F04)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--source-frames",
        nargs="+",
        choices=SOURCE_FRAMES,
        default=list(SOURCE_FRAMES),
    )
    parser.add_argument("--limit-per-frame", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=8)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def read_frame(path: Path) -> str:
    if path.suffix == ".json":
        return str(read_json(path)["prompt_text"])
    return path.read_text(encoding="utf-8").strip()


def stateless_uniform(seed: int, turn_index: int, token_index: int) -> float:
    """Return a stable SplitMix64 variate in the open interval (0, 1)."""
    value = (
        int(seed)
        + 0x9E3779B97F4A7C15 * (int(turn_index) + 1)
        + 0xD1B54A32D192ED03 * (int(token_index) + 1)
    ) & MASK_64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK_64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK_64
    value ^= value >> 31
    return (((value >> 11) & ((1 << 53) - 1)) + 0.5) / float(1 << 53)


class PairedStatelessSampler:
    """Force argmax generation to follow registered temperature/top-p sampling."""

    def __init__(
        self,
        seeds: list[int],
        turn_index: int,
        maximum_tokens: int,
        temperature: float,
        top_p: float,
    ) -> None:
        if not seeds or maximum_tokens <= 0:
            raise ValueError("sampler requires seeds and a positive token cap")
        if not 0 < temperature or not 0 < top_p <= 1:
            raise ValueError("invalid sampling controls")
        self.temperature = temperature
        self.top_p = top_p
        self.token_index = 0
        self._uniform_rows = [
            [stateless_uniform(seed, turn_index, index) for index in range(maximum_tokens)]
            for seed in seeds
        ]
        self._uniforms: Any = None

    def __call__(self, input_ids: Any, scores: Any) -> Any:
        import torch

        del input_ids
        if self.token_index >= len(self._uniform_rows[0]):
            raise RuntimeError("sampler called beyond the frozen maximum token count")
        if self._uniforms is None:
            self._uniforms = torch.tensor(
                self._uniform_rows,
                dtype=torch.float32,
                device=scores.device,
            )
        uniforms = self._uniforms[:, self.token_index].unsqueeze(1).contiguous()
        selected = select_top_p_indices(
            scores,
            uniforms,
            self.temperature,
            self.top_p,
        )
        forced = torch.full_like(scores, -math.inf)
        forced.scatter_(1, selected.unsqueeze(1), 0)
        self.token_index += 1
        return forced


def select_top_p_indices(
    scores: Any,
    uniforms: Any,
    temperature: float,
    top_p: float,
) -> Any:
    """Select inverse-CDF top-p samples with one full-vocabulary softmax."""
    import torch

    if scores.ndim != 2 or uniforms.shape != (scores.shape[0], 1):
        raise ValueError("scores and uniforms have incompatible batch shapes")
    if not 0 < temperature or not 0 < top_p <= 1:
        raise ValueError("invalid sampling controls")
    logits = scores.float() / temperature
    sorted_logits, sorted_indices = torch.sort(logits, descending=True, dim=-1)
    sorted_probabilities = torch.softmax(sorted_logits, dim=-1)
    cumulative = torch.cumsum(sorted_probabilities, dim=-1)
    remove = cumulative > top_p
    remove[..., 1:] = remove[..., :-1].clone()
    remove[..., 0] = False
    kept_probabilities = sorted_probabilities.masked_fill(remove, 0)
    kept_mass = kept_probabilities.sum(dim=-1, keepdim=True)
    normalized_cumulative = torch.cumsum(kept_probabilities, dim=-1) / kept_mass
    positions = torch.searchsorted(normalized_cumulative, uniforms).clamp_max(
        scores.shape[-1] - 1
    )
    return sorted_indices.gather(1, positions).squeeze(1)


def visible_answer(generated: str) -> str:
    lowered = generated.lower()
    if "<think" in lowered and "</think>" not in lowered:
        return ""
    visible = THINK_PATTERN.sub("", generated)
    for token in SPECIAL_TOKENS:
        visible = visible.replace(token, "")
    return visible.strip()


def validate_inputs(
    freeze: dict[str, Any],
    f04: dict[str, Any],
    freeze_path: Path,
    model_dir: Path,
) -> None:
    if freeze.get("schema_version") != "frame_internalization_curriculum_request_freeze.v1":
        raise RuntimeError("unexpected Qwen curriculum freeze schema")
    if freeze.get("freeze_id") != "qwen3_1p7b_curriculum_requests_v1":
        raise RuntimeError("the active Qwen request freeze is required")
    if f04.get("schema_version") != "frame_internalization_primelab_environment_freeze.v1":
        raise RuntimeError("unexpected F04 receipt schema")
    if f04.get("passed") is not True or f04.get("gpu_count") != 1:
        raise RuntimeError("a passed one-GPU F04 receipt is required")
    if f04.get("model_artifact_inventory_sha256") != (
        "26dbf683e31beebd0282217ea79a1b53f7a8fed6f4961978d7881c5a556e1959"
    ):
        raise RuntimeError("F04 model inventory drift")
    if not freeze_path.is_file() or not model_dir.is_dir():
        raise RuntimeError("freeze or model directory is missing")
    inventory_path = REPO_ROOT / freeze["model_inventory"]["path"]
    if sha256_file(inventory_path) != freeze["model_inventory"]["sha256"]:
        raise RuntimeError("model inventory receipt hash mismatch")
    inventory = read_json(inventory_path)
    failures = [
        item["path"]
        for item in inventory["artifacts"]
        if not (model_dir / item["path"]).is_file()
        or sha256_file(model_dir / item["path"]) != item["sha256"]
    ]
    if failures:
        raise RuntimeError(f"model artifact mismatch: {failures}")


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def load_done(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    rows = read_jsonl(path)
    request_ids = [str(row["request_id"]) for row in rows]
    if len(request_ids) != len(set(request_ids)):
        raise RuntimeError(f"duplicate request IDs in resume file: {path}")
    return set(request_ids)


def chunks(values: list[Any], size: int) -> list[list[Any]]:
    if size <= 0:
        raise ValueError("batch size must be positive")
    return [values[index : index + size] for index in range(0, len(values), size)]


def render_prompt(tokenizer: Any, conversation: list[dict[str, str]]) -> str:
    return tokenizer.apply_chat_template(
        conversation,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True,
    )


def generate_turn(
    model: Any,
    tokenizer: Any,
    conversations: list[list[dict[str, str]]],
    seeds: list[int],
    turn_index: int,
    generation: dict[str, Any],
) -> tuple[list[str], list[int]]:
    import torch
    from transformers import LogitsProcessorList

    prompts = [render_prompt(tokenizer, conversation) for conversation in conversations]
    encoded = tokenizer(prompts, return_tensors="pt", padding=True, add_special_tokens=False)
    input_width = int(encoded["input_ids"].shape[1])
    maximum_tokens = int(generation["max_tokens_per_turn"])
    maximum_context = int(getattr(model.config, "max_position_embeddings", 0))
    if maximum_context and input_width + maximum_tokens > maximum_context:
        raise RuntimeError("frozen generation would exceed the model context window")
    encoded = {key: value.to(model.device) for key, value in encoded.items()}
    sampler = PairedStatelessSampler(
        seeds,
        turn_index,
        maximum_tokens,
        float(generation["temperature"]),
        float(generation["top_p"]),
    )
    with torch.inference_mode():
        outputs = model.generate(
            **encoded,
            do_sample=False,
            max_new_tokens=maximum_tokens,
            logits_processor=LogitsProcessorList([sampler]),
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=model.generation_config.eos_token_id,
            use_cache=True,
        )
    generated_rows = outputs[:, input_width:].detach().cpu().tolist()
    eos_value = model.generation_config.eos_token_id
    if isinstance(eos_value, int):
        eos_ids = {eos_value}
    elif isinstance(eos_value, (list, tuple)) and eos_value:
        eos_ids = {int(value) for value in eos_value}
    else:
        raise RuntimeError("model generation config must define EOS token IDs")
    trimmed_rows: list[list[int]] = []
    for tokens in generated_rows:
        trimmed: list[int] = []
        for token in tokens:
            trimmed.append(token)
            if token in eos_ids:
                break
        trimmed_rows.append(trimmed)
    decoded = [
        tokenizer.decode(tokens, skip_special_tokens=False) for tokens in trimmed_rows
    ]
    lengths = [len(tokens) for tokens in trimmed_rows]
    return decoded, lengths


def main() -> int:
    args = parse_args()
    if args.limit_per_frame < 0:
        raise ValueError("limit-per-frame cannot be negative")
    freeze_path = args.freeze.resolve()
    model_dir = args.model_dir.resolve()
    output_dir = args.output_dir.resolve()
    freeze = read_json(freeze_path)
    f04 = read_json(args.f04_receipt.resolve())
    validate_inputs(freeze, f04, freeze_path, model_dir)

    request_path = REPO_ROOT / freeze["requests"]["path"]
    dilemma_path = REPO_ROOT / freeze["dilemmas"]["path"]
    if sha256_file(request_path) != freeze["requests"]["sha256"]:
        raise RuntimeError("request pack hash mismatch")
    if sha256_file(dilemma_path) != freeze["dilemmas"]["sha256"]:
        raise RuntimeError("dilemma pool hash mismatch")
    dilemmas = {row["scenario_id"]: row for row in read_jsonl(dilemma_path)}
    frame_text: dict[str, str] = {}
    for frame in args.source_frames:
        binding = freeze["frames"][frame]
        path = REPO_ROOT / binding["path"]
        if sha256_file(path) != binding["file_sha256"]:
            raise RuntimeError(f"source frame file hash mismatch: {frame}")
        frame_text[frame] = read_frame(path)
        if sha256_text(frame_text[frame]) != binding["prompt_text_sha256"]:
            raise RuntimeError(f"source frame text hash mismatch: {frame}")

    requests_by_frame: dict[str, list[dict[str, Any]]] = {
        frame: [] for frame in args.source_frames
    }
    for request in read_jsonl(request_path):
        frame = request["source_frame"]
        if frame in requests_by_frame:
            requests_by_frame[frame].append(request)
    if any(len(rows) != 5600 for rows in requests_by_frame.values()):
        raise RuntimeError("every selected frame must have exactly 5,600 frozen requests")
    if args.limit_per_frame:
        requests_by_frame = {
            frame: rows[: args.limit_per_frame]
            for frame, rows in requests_by_frame.items()
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_paths = {frame: output_dir / f"{frame}.jsonl" for frame in args.source_frames}
    event_path = output_dir / "generation.events.jsonl"
    done = {frame: load_done(path) for frame, path in raw_paths.items()}
    jobs: list[dict[str, Any]] = []
    for row_index in range(max(len(rows) for rows in requests_by_frame.values())):
        for frame in args.source_frames:
            request = requests_by_frame[frame][row_index]
            if request["request_id"] not in done[frame]:
                jobs.append(request)

    append_jsonl(
        event_path,
        {
            "event": "start",
            "timestamp_utc": utc_now(),
            "selected_frames": args.source_frames,
            "limit_per_frame": args.limit_per_frame,
            "batch_size": args.batch_size,
            "pending_requests": len(jobs),
        },
    )

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tokenizer: Any = None
    model: Any = None
    started = time.monotonic()
    failures: list[str] = []
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
        tokenizer.padding_side = "left"
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token_id = tokenizer.eos_token_id
        quantization = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_dir,
            local_files_only=True,
            device_map={"": "cuda:0"},
            quantization_config=quantization,
            dtype=torch.float16,
            attn_implementation="sdpa",
        ).eval()
        generation = freeze["generation"]
        instructions = generation["instructions"]
        for batch_index, batch in enumerate(chunks(jobs, args.batch_size)):
            conversations = [
                [{"role": "system", "content": frame_text[row["source_frame"]]}]
                for row in batch
            ]
            transcripts: list[list[dict[str, str]]] = [[] for _ in batch]
            valid = [True for _ in batch]
            output_tokens = [0 for _ in batch]
            for turn_index, turn in enumerate(generation["turns"]):
                for index, request in enumerate(batch):
                    user_message = str(instructions[turn]).replace(
                        "{dilemma}", dilemmas[request["scenario_id"]]["prompt_text"]
                    )
                    conversations[index].append({"role": "user", "content": user_message})
                    transcripts[index].append({"role": "user", "content": user_message})
                pending = [index for index, value in enumerate(valid) if value]
                for attempt_index in range(int(generation["retry_attempts"])):
                    if not pending:
                        break
                    torch.cuda.synchronize()
                    torch.cuda.reset_peak_memory_stats()
                    call_started = time.monotonic()
                    decoded, lengths = generate_turn(
                        model,
                        tokenizer,
                        [conversations[index] for index in pending],
                        [
                            int(batch[index]["generation_seed"]) + 100000 * turn_index
                            for index in pending
                        ],
                        turn_index,
                        generation,
                    )
                    torch.cuda.synchronize()
                    call_elapsed = time.monotonic() - call_started
                    generated_tokens = sum(lengths)
                    append_jsonl(
                        event_path,
                        {
                            "event": "generation_call",
                            "timestamp_utc": utc_now(),
                            "batch_index": batch_index,
                            "turn_index": turn_index,
                            "attempt_index": attempt_index,
                            "batch_size": len(pending),
                            "generated_tokens": generated_tokens,
                            "elapsed_seconds": round(call_elapsed, 6),
                            "generated_tokens_per_second": (
                                generated_tokens / call_elapsed
                            ),
                            "peak_cuda_allocated_bytes": (
                                torch.cuda.max_memory_allocated()
                            ),
                            "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved(),
                        },
                    )
                    retry: list[int] = []
                    for subset_index, text in enumerate(decoded):
                        index = pending[subset_index]
                        visible = visible_answer(text)
                        output_tokens[index] += lengths[subset_index]
                        if not visible:
                            retry.append(index)
                            continue
                        conversations[index].append(
                            {"role": "assistant", "content": visible}
                        )
                        transcripts[index].append(
                            {"role": "assistant", "content": visible}
                        )
                    pending = retry
                for index in pending:
                    valid[index] = False
            for index, request in enumerate(batch):
                request_id = str(request["request_id"])
                if not valid[index] or len(transcripts[index]) != 6:
                    failures.append(request_id)
                    append_jsonl(
                        event_path,
                        {
                            "event": "request_failed",
                            "timestamp_utc": utc_now(),
                            "request_id": request_id,
                        },
                    )
                    continue
                result = dict(request)
                result.update(
                    {
                        "dilemma_prompt": dilemmas[request["scenario_id"]]["prompt_text"],
                        "transcript": transcripts[index],
                        "final": transcripts[index][-1]["content"],
                        "final_sha256": sha256_text(transcripts[index][-1]["content"]),
                        "generated_token_count": output_tokens[index],
                        "sampler": "splitmix64_common_random_numbers_v1",
                    }
                )
                append_jsonl(raw_paths[request["source_frame"]], result)
                append_jsonl(
                    event_path,
                    {
                        "event": "checkpoint",
                        "timestamp_utc": utc_now(),
                        "request_id": request_id,
                        "source_frame": request["source_frame"],
                        "batch_index": batch_index,
                        "allocated_cuda_bytes": torch.cuda.memory_allocated(),
                    },
                )
    finally:
        model = None
        tokenizer = None
        gc.collect()
        cleanup_status = "not_loaded"
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
            cleanup_status = "completed"
        append_jsonl(
            event_path,
            {
                "event": "cleanup",
                "timestamp_utc": utc_now(),
                "status": cleanup_status,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            },
        )

    for frame, selected in requests_by_frame.items():
        selected_ids = {str(row["request_id"]) for row in selected}
        completed_ids = load_done(raw_paths[frame]) & selected_ids
        limited_complete = len(completed_ids) == len(selected_ids)
        receipt = {
            "schema_version": "frame_internalization_curriculum_generation_receipt.v1",
            "source_frame": frame,
            "scope": "full" if len(selected) == 5600 else "bounded_smoke",
            "registered_requested": 5600,
            "requested": len(selected),
            "completed": len(completed_ids),
            "failed": sorted(set(failures) & selected_ids),
            "limited_run_complete": limited_complete,
            "complete": limited_complete and len(selected) == 5600,
            "f04_receipt_sha256": sha256_file(args.f04_receipt.resolve()),
            "request_freeze_sha256": sha256_file(freeze_path),
            "generator_sha256": sha256_file(Path(__file__).resolve()),
            "raw_path": str(raw_paths[frame]),
            "raw_sha256": sha256_file(raw_paths[frame]) if raw_paths[frame].is_file() else None,
            "events_path": str(event_path),
            "sampling": {
                "algorithm": "splitmix64_common_random_numbers_v1",
                "implementation": "top_p_inverse_cdf_single_softmax_v2",
                "paired_seed_from_frozen_request": True,
                "turn_seed_offset": 100000,
                "temperature": freeze["generation"]["temperature"],
                "top_p": freeze["generation"]["top_p"],
            },
            "batch_size": args.batch_size,
            "cleanup_status": cleanup_status,
        }
        receipt_path = output_dir / f"{frame}.receipt.json"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
