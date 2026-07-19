#!/usr/bin/env python3
"""Generate resumable hash-bound curriculum transcripts from the frozen requests."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import itertools
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments/frame_internalization_sft_v1"
DEFAULT_FREEZE = PACKAGE / "rerun_freeze/curriculum_generation_v1/request_manifest.json"
THINK_PATTERN = re.compile(r"<\s*think\s*>(.*?)</\s*think\s*>", re.DOTALL | re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--urls", nargs="+", required=True)
    parser.add_argument("--source-frame", required=True, choices=["neutral", "F1", "F3", "F3_concrete"])
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--base-freeze-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-name", default="intellect-3")
    parser.add_argument("--concurrency", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def read_frame(path: Path) -> str:
    if path.suffix == ".json":
        return str(read_json(path)["prompt_text"])
    return path.read_text(encoding="utf-8").strip()


def strip_think(content: str, reasoning: str) -> str:
    if reasoning:
        return (content or "").strip()
    return THINK_PATTERN.sub("", content or "").strip()


async def generate_one(
    client: Any,
    semaphore: asyncio.Semaphore,
    urls: Any,
    model_name: str,
    system: str,
    dilemma: dict[str, Any],
    request: dict[str, Any],
    generation: dict[str, Any],
) -> dict[str, Any] | None:
    conversation = [{"role": "system", "content": system}]
    transcript: list[dict[str, str]] = []
    url = next(urls)
    instructions = generation["instructions"]
    async with semaphore:
        for turn_index, turn in enumerate(generation["turns"]):
            instruction = str(instructions[turn])
            user_message = instruction.replace("{dilemma}", dilemma["prompt_text"])
            conversation.append({"role": "user", "content": user_message})
            body = {
                "model": model_name,
                "messages": conversation,
                "max_tokens": generation["max_tokens_per_turn"],
                "temperature": generation["temperature"],
                "top_p": generation["top_p"],
                "seed": request["generation_seed"] + 100000 * turn_index,
            }
            visible = ""
            for attempt in range(int(generation["retry_attempts"])):
                try:
                    response = await client.post(
                        f"{url}/v1/chat/completions", json=body, timeout=900
                    )
                    response.raise_for_status()
                    message = response.json()["choices"][0]["message"]
                    visible = strip_think(
                        message.get("content") or "", message.get("reasoning_content") or ""
                    )
                    if visible:
                        break
                except Exception:
                    await asyncio.sleep(2 * (attempt + 1))
            if not visible:
                return None
            conversation.append({"role": "assistant", "content": visible})
            transcript.extend(
                [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": visible},
                ]
            )
    result = dict(request)
    result.update(
        {
            "dilemma_prompt": dilemma["prompt_text"],
            "transcript": transcript,
            "final": transcript[-1]["content"],
            "final_sha256": sha256_text(transcript[-1]["content"]),
        }
    )
    return result


async def async_main() -> int:
    args = parse_args()
    freeze = read_json(args.freeze)
    base_freeze = read_json(args.base_freeze_receipt)
    if (
        base_freeze.get("schema_version") != "frame_internalization_base_freeze.v1"
        or base_freeze.get("passed") is not True
        or base_freeze.get("immutable_revisions") is not True
        or base_freeze.get("repository") != freeze["generation"]["model_repository"]
        or base_freeze.get("revision") != freeze["generation"]["model_revision"]
    ):
        raise RuntimeError("a passed base-freeze receipt for the frozen generation model is required")
    request_path = REPO_ROOT / freeze["requests"]["path"]
    if sha256_file(request_path) != freeze["requests"]["sha256"]:
        raise RuntimeError("request pack hash mismatch")
    dilemma_path = REPO_ROOT / freeze["dilemmas"]["path"]
    if sha256_file(dilemma_path) != freeze["dilemmas"]["sha256"]:
        raise RuntimeError("dilemma pool hash mismatch")
    frame_binding = freeze["frames"][args.source_frame]
    frame_path = REPO_ROOT / frame_binding["path"]
    if sha256_file(frame_path) != frame_binding["file_sha256"]:
        raise RuntimeError("source frame file hash mismatch")
    system = read_frame(frame_path)
    if sha256_text(system) != frame_binding["prompt_text_sha256"]:
        raise RuntimeError("source frame prompt hash mismatch")

    dilemmas = {
        row["scenario_id"]: row
        for row in (
            json.loads(line) for line in dilemma_path.read_text(encoding="utf-8").splitlines()
        )
    }
    requests = [
        json.loads(line)
        for line in request_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["source_frame"] == args.source_frame
    ]
    if args.limit:
        requests = requests[: args.limit]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = args.output_dir / f"{args.source_frame}.jsonl"
    event_path = args.output_dir / f"{args.source_frame}.events.jsonl"
    done_ids: set[str] = set()
    if raw_path.is_file():
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            try:
                done_ids.add(json.loads(line)["request_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    todo = [request for request in requests if request["request_id"] not in done_ids]

    import httpx

    urls = itertools.cycle(args.urls)
    semaphore = asyncio.Semaphore(args.concurrency)
    write_lock = asyncio.Lock()
    failed: list[str] = []
    limits = httpx.Limits(max_connections=args.concurrency + 8)
    async with httpx.AsyncClient(limits=limits) as client:

        async def run(request: dict[str, Any]) -> None:
            result = await generate_one(
                client,
                semaphore,
                urls,
                args.model_name,
                system,
                dilemmas[request["scenario_id"]],
                request,
                freeze["generation"],
            )
            async with write_lock:
                event = {"request_id": request["request_id"], "status": "failed"}
                if result is None:
                    failed.append(request["request_id"])
                else:
                    with raw_path.open("a", encoding="utf-8", newline="\n") as handle:
                        handle.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
                    event["status"] = "completed"
                    event["final_sha256"] = result["final_sha256"]
                with event_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(event, sort_keys=True) + "\n")

        await asyncio.gather(*(run(request) for request in todo))

    completed = len(done_ids) + len(todo) - len(failed)
    summary = {
        "schema_version": "frame_internalization_curriculum_generation_receipt.v1",
        "source_frame": args.source_frame,
        "base_freeze_receipt_sha256": sha256_file(args.base_freeze_receipt),
        "request_freeze_sha256": sha256_file(args.freeze),
        "generator_sha256": sha256_file(Path(__file__)),
        "requested": len(requests),
        "completed": completed,
        "failed": failed,
        "complete": completed == len(requests) and not failed,
        "raw_path": str(raw_path.resolve()),
        "raw_sha256": sha256_file(raw_path) if raw_path.is_file() else None,
        "events_path": str(event_path.resolve()),
    }
    summary_path = args.output_dir / f"{args.source_frame}.receipt.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
