#!/usr/bin/env python3
"""Nonstored OpenAI Responses adapter for one support-slice answer.

The adapter requests a bounded answer and a small, explicit quality audit. It
does not request or retain private chain-of-thought. The human release review
remains authoritative; the self-audit is only a retry and screening signal.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Any


QUALITY_KEYS = {
    "directly_answered",
    "unsupported_literal_identity_claim",
    "unsupported_hidden_knowledge_claim",
    "unsafe_facilitation",
}


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _usage_dict(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump(exclude_none=True)
    return json.loads(json.dumps(usage, default=lambda item: item.__dict__))


def _word_count(value: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", value, flags=re.UNICODE))


def response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string", "minLength": 1},
            "quality_checks": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "directly_answered": {"type": "boolean"},
                    "unsupported_literal_identity_claim": {"type": "boolean"},
                    "unsupported_hidden_knowledge_claim": {"type": "boolean"},
                    "unsafe_facilitation": {"type": "boolean"},
                },
                "required": sorted(QUALITY_KEYS),
            },
        },
        "required": ["answer", "quality_checks"],
    }


def semantic_errors(request: dict[str, Any], value: Any) -> list[str]:
    if not isinstance(value, dict) or set(value) != {"answer", "quality_checks"}:
        return ["response must contain exactly answer and quality_checks"]
    answer = value["answer"]
    if not isinstance(answer, str) or not answer.strip():
        return ["answer must be a nonempty string"]
    quality = value["quality_checks"]
    if not isinstance(quality, dict) or set(quality) != QUALITY_KEYS:
        return ["quality_checks has the wrong shape"]
    errors: list[str] = []
    minimum, maximum = map(int, request["response_word_range"])
    words = _word_count(answer)
    if not minimum <= words <= maximum:
        errors.append(f"answer word count {words} is outside {minimum}..{maximum}")
    if quality["directly_answered"] is not True:
        errors.append("answer did not directly answer the task")
    for key in (
        "unsupported_literal_identity_claim",
        "unsupported_hidden_knowledge_claim",
        "unsafe_facilitation",
    ):
        if quality[key] is not False:
            errors.append(f"quality check failed: {key}")
    return errors


def _validate_request(request: dict[str, Any]) -> None:
    if request.get("schema_version") != "storyworld_support_teacher_request_v1":
        raise ValueError("unexpected support teacher request schema")
    messages = request.get("messages")
    if not isinstance(messages, list) or [item.get("role") for item in messages] != [
        "system",
        "user",
    ]:
        raise ValueError("support request messages must be ordered system then user")
    bounds = request.get("response_word_range")
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or any(not isinstance(value, int) or isinstance(value, bool) for value in bounds)
        or not 1 <= bounds[0] <= bounds[1]
    ):
        raise ValueError("response_word_range must contain two positive ordered integers")


def run_request(request: dict[str, Any]) -> dict[str, Any]:
    _validate_request(request)
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required")

    from openai import OpenAI

    max_attempts = int(os.environ.get("SUPPORT_TEACHER_MAX_ATTEMPTS", "3"))
    max_output_tokens = int(
        os.environ.get(
            "SUPPORT_TEACHER_MAX_OUTPUT_TOKENS",
            str(max(1200, int(request["response_word_range"][1]) * 4)),
        )
    )
    client = OpenAI(timeout=float(os.environ.get("SUPPORT_TEACHER_TIMEOUT_SECONDS", "300")))
    attempt_receipts: list[dict[str, Any]] = []
    prior_errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        prompt = {
            "task": request["messages"][1]["content"],
            "response_word_range": request["response_word_range"],
            "correction_from_prior_attempt": prior_errors,
        }
        response = client.responses.create(
            model=str(request["model_id"]),
            instructions=(
                str(request["messages"][0]["content"])
                + " Return an original, self-contained answer. Do not claim a literal assigned "
                + "identity, hidden knowledge, revelation, or authority you do not have. Do not "
                + "provide unsafe facilitation. Return only the answer and explicit quality checks "
                + "required by the JSON schema; do not expose private reasoning."
            ),
            input=json.dumps(prompt, ensure_ascii=False, sort_keys=True),
            reasoning={"effort": str(request["reasoning_effort"])},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "storyworld_support_answer",
                    "strict": True,
                    "schema": response_schema(),
                },
                "verbosity": "medium",
            },
            max_output_tokens=max_output_tokens,
            store=False,
        )
        output_text = str(getattr(response, "output_text", ""))
        attempt_receipts.append(
            {
                "attempt": attempt,
                "api_response_id": str(getattr(response, "id", "")),
                "resolved_model": str(getattr(response, "model", request["model_id"])),
                "request_payload_sha256": _canonical_hash(prompt),
                "output_text_sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
                "usage": _usage_dict(response),
            }
        )
        if not output_text:
            prior_errors = ["API response did not contain output_text"]
            continue
        try:
            value = json.loads(output_text)
        except json.JSONDecodeError as exc:
            prior_errors = [f"output_text was not JSON: {exc.msg}"]
            continue
        prior_errors = semantic_errors(request, value)
        if not prior_errors:
            return {
                "response": value,
                "provider_receipt": {
                    "provider": "openai_responses_api",
                    "requested_model": request["model_id"],
                    "reasoning_effort": request["reasoning_effort"],
                    "store": False,
                    "response_content_sha256": _canonical_hash(value),
                    "attempts": attempt_receipts,
                },
            }
    raise RuntimeError(
        f"support response failed semantic validation after {max_attempts} attempts: "
        + "; ".join(prior_errors)
    )


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        if not isinstance(request, dict):
            raise ValueError("stdin must contain one JSON object")
        result = run_request(request)
        sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
        return 0
    except Exception as exc:
        print(f"openai_support_slice_teacher: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
