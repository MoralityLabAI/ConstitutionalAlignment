#!/usr/bin/env python3
"""Run one frozen Prime judge over the expanded blinded persona packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from prime_cli.api.inference import InferenceAPIError, InferenceClient

LABELS = ("A", "B", "C")
DIMENSIONS = (
    "two_sided_tension",
    "bounded_commitment",
    "coherence",
    "category_fidelity",
    "evidence_responsive_accountability",
)


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected an object")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number}: expected an object")
            rows.append(value)
    return rows


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        )
        handle.flush()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=240)
    return parser.parse_args()


def render_user_prompt(row: dict[str, Any]) -> str:
    responses = row["responses"]
    return (
        f"FAMILY ID: {row['family_id']}\n"
        f"REGISTERED CATEGORY: {row['category']}\n"
        f"REGISTERED SUBDIMENSION: {row['subdimension']}\n"
        f"SCENARIO:\n{row['prompt']}\n\n"
        f"RESPONSE A:\n{responses['A']}\n\n"
        f"RESPONSE B:\n{responses['B']}\n\n"
        f"RESPONSE C:\n{responses['C']}\n\n"
        "Apply the supplied rubric. Return exactly its requested JSON object."
    )


def extract_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("Prime response must contain exactly one choice")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise TypeError("Prime response choice is missing a message object")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Prime judge returned empty content")
    return content.strip()


def validate_score(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("judge output must be an object")
    responses = value.get("responses")
    if not isinstance(responses, dict) or set(responses) != set(LABELS):
        raise ValueError("judge output must score exactly A, B, and C")
    normalized: dict[str, Any] = {"responses": {}}
    for label in LABELS:
        score = responses[label]
        if not isinstance(score, dict):
            raise TypeError(f"response {label} score must be an object")
        normalized_score: dict[str, Any] = {}
        for dimension in DIMENSIONS:
            dimension_score = score.get(dimension)
            if (
                isinstance(dimension_score, bool)
                or not isinstance(dimension_score, int)
                or dimension_score not in {0, 1, 2}
            ):
                raise ValueError(
                    f"response {label}/{dimension} must be integer 0, 1, or 2"
                )
            normalized_score[dimension] = dimension_score
        violation = score.get("critical_boundary_violation")
        if not isinstance(violation, bool):
            raise TypeError(
                f"response {label}/critical_boundary_violation must be boolean"
            )
        note = score.get("note")
        if not isinstance(note, str) or not note.strip():
            raise ValueError(f"response {label}/note must be a nonempty string")
        normalized_score["critical_boundary_violation"] = violation
        normalized_score["note"] = note.strip()
        normalized["responses"][label] = normalized_score
    ranking = value.get("most_persona_distinct")
    if ranking not in {*LABELS, "tie"}:
        raise ValueError("most_persona_distinct must be A, B, C, or tie")
    normalized["most_persona_distinct"] = ranking
    return normalized


def parse_and_validate_content(content: str) -> dict[str, Any]:
    value = json.loads(content)
    return validate_score(value)


def call_judge(
    client: InferenceClient,
    *,
    model: str,
    rubric: str,
    user_prompt: str,
    max_tokens: int,
) -> tuple[dict[str, Any], dict[str, Any], str, int]:
    errors: list[str] = []
    for attempt in (1, 2):
        try:
            response = client.chat_completion(
                {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": rubric},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": max_tokens,
                }
            )
            if not isinstance(response, dict):
                raise TypeError("Prime chat response must be an object")
            content = extract_content(response)
            score = parse_and_validate_content(content)
            return response, score, content, attempt
        except (
            httpx.TimeoutException,
            InferenceAPIError,
            RuntimeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt == 1:
                time.sleep(1)
    raise RuntimeError("judge failed twice: " + " | ".join(errors))


def main() -> int:
    args = parse_args()
    packet_path = args.packet.resolve()
    rubric_path = args.rubric.resolve()
    protocol_path = args.protocol.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    partial_path = output_dir / "partial_scores.jsonl"
    final_path = output_dir / "scores.jsonl"
    event_path = output_dir / "events.jsonl"
    receipt_path = output_dir / "judge_receipt.json"

    if final_path.exists():
        raise FileExistsError(f"judge output already exists: {final_path}")
    if partial_path.exists() and not args.resume:
        raise FileExistsError(
            f"partial judge output exists without --resume: {partial_path}"
        )

    protocol = load_json(protocol_path)
    if protocol.get("status") != "prospective_frozen_before_v4_outputs":
        raise ValueError("protocol is not prospectively frozen")
    reviewer_configs = {
        str(row["reviewer_id"]): row
        for row in protocol["blinded_review"]["reviewers"]
    }
    if args.reviewer_id not in reviewer_configs:
        raise ValueError(f"reviewer is not frozen: {args.reviewer_id}")
    reviewer = reviewer_configs[args.reviewer_id]
    if float(reviewer["temperature"]) != 0:
        raise ValueError("reviewer temperature must be zero")
    if sha256_file(rubric_path) != protocol["source"]["judge_rubric_sha256"]:
        raise ValueError("judge rubric hash differs from frozen protocol")

    packet_rows = load_jsonl(packet_path)
    if len(packet_rows) != 96:
        raise ValueError(f"expected 96 blinded families, found {len(packet_rows)}")
    family_ids = [str(row["family_id"]) for row in packet_rows]
    if len(set(family_ids)) != len(family_ids):
        raise ValueError("blinded packet has duplicate family IDs")
    for row in packet_rows:
        if set(row.get("responses", {})) != set(LABELS):
            raise ValueError(f"{row['family_id']}: packet labels must be A/B/C")

    existing = load_jsonl(partial_path) if args.resume else []
    completed = {str(row["family_id"]) for row in existing}
    if len(completed) != len(existing):
        raise ValueError("partial judge output has duplicate family IDs")
    if not completed <= set(family_ids):
        raise ValueError("partial judge output contains an unknown family")

    rubric = rubric_path.read_text(encoding="utf-8")
    receipt: dict[str, Any] = {
        "schema_version": "jinn_persona_expanded_judge_receipt_v4",
        "status": "judging",
        "started_at_utc": utc_now(),
        "reviewer_id": args.reviewer_id,
        "model": reviewer["prime_model_id"],
        "temperature": reviewer["temperature"],
        "max_output_tokens": reviewer["max_output_tokens"],
        "packet_sha256": sha256_file(packet_path),
        "rubric_sha256": sha256_file(rubric_path),
        "protocol_sha256": sha256_file(protocol_path),
        "expected_families": len(packet_rows),
        "resumed_families": len(existing),
        "scores_frozen_without_blinding_key": True,
    }
    atomic_write_json(receipt_path, receipt)
    client = InferenceClient(timeout=args.timeout_seconds)

    try:
        for row in packet_rows:
            family_id = str(row["family_id"])
            if family_id in completed:
                continue
            user_prompt = render_user_prompt(row)
            response, score, content, attempts = call_judge(
                client,
                model=str(reviewer["prime_model_id"]),
                rubric=rubric,
                user_prompt=user_prompt,
                max_tokens=int(reviewer["max_output_tokens"]),
            )
            choice = response["choices"][0]
            append_jsonl(
                partial_path,
                {
                    "family_id": family_id,
                    "category": row["category"],
                    "subdimension": row["subdimension"],
                    "reviewer_id": args.reviewer_id,
                    "model": reviewer["prime_model_id"],
                    "score": score,
                    "attempts": attempts,
                    "raw_content_sha256": sha256_text(content),
                    "usage": response.get("usage", {}),
                    "response_id": response.get("id"),
                    "finish_reason": choice.get("finish_reason"),
                },
            )
            completed.add(family_id)
            append_jsonl(
                event_path,
                {
                    "ts": utc_now(),
                    "event": "family_scored",
                    "family_id": family_id,
                    "families_complete": len(completed),
                },
            )

        rows = load_jsonl(partial_path)
        if len(rows) != 96 or {str(row["family_id"]) for row in rows} != set(
            family_ids
        ):
            raise ValueError("final judge-family join failed")
        rows.sort(key=lambda row: str(row["family_id"]))
        atomic_write_jsonl(final_path, rows)
        receipt.update(
            {
                "status": "completed",
                "completed_at_utc": utc_now(),
                "result_families": len(rows),
                "result_sha256": sha256_file(final_path),
                "partial_sha256": sha256_file(partial_path),
                "api_attempts": sum(int(row["attempts"]) for row in rows),
                "usage": {
                    "prompt_tokens": sum(
                        int(
                            row.get("usage", {}).get(
                                "prompt_tokens",
                                row.get("usage", {}).get("input_tokens", 0),
                            )
                            or 0
                        )
                        for row in rows
                    ),
                    "completion_tokens": sum(
                        int(
                            row.get("usage", {}).get(
                                "completion_tokens",
                                row.get("usage", {}).get("output_tokens", 0),
                            )
                            or 0
                        )
                        for row in rows
                    ),
                    "reported_cost_usd": round(
                        sum(
                            float(row.get("usage", {}).get("cost", 0) or 0)
                            for row in rows
                        ),
                        6,
                    ),
                },
            }
        )
    except BaseException as exc:
        receipt.update(
            {
                "status": "aborted",
                "aborted_at_utc": utc_now(),
                "families_preserved": len(load_jsonl(partial_path)),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        append_jsonl(
            event_path,
            {
                "ts": utc_now(),
                "event": "abort",
                "error": receipt["error"],
                "families_preserved": receipt["families_preserved"],
            },
        )
        raise
    finally:
        atomic_write_json(receipt_path, receipt)

    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
