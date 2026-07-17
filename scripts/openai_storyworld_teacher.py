#!/usr/bin/env python3
"""OpenAI Responses API adapter for storyworld teacher requests.

The process reads one ``storyworld_teacher_request_v1`` object from stdin and
prints a command-teacher envelope to stdout. Only the requested structured
work product is returned. Reasoning tokens and private chain-of-thought are
neither requested nor stored.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any


WORK_PRODUCT_KEYS = {
    "observed_facts",
    "uncertainties",
    "forecast",
    "action_id",
    "public_reason",
    "responsibility_attribution",
    "counterfactual",
    "confidence",
}
IDENTITY_SCRUB_PHRASE = "without identity-specific vocabulary"


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


def _string() -> dict[str, Any]:
    return {"type": "string", "minLength": 1}


def _enum_string(values: list[str]) -> dict[str, Any]:
    if not values:
        return _string()
    return {"type": "string", "enum": values}


def _work_product_schema(action_ids: list[str], fact_ids: list[str]) -> dict[str, Any]:
    forecast = _object(
        {
            "action_id": _enum_string(action_ids),
            "predicted_outcome": _string(),
            "probability": {"type": "number", "minimum": 0, "maximum": 1},
        }
    )
    return _object(
        {
            "observed_facts": {
                "type": "array",
                "items": _enum_string(fact_ids),
            },
            "uncertainties": {"type": "array", "minItems": 1, "items": _string()},
            "forecast": {"type": "array", "minItems": 1, "items": forecast},
            "action_id": _enum_string(action_ids),
            "public_reason": _string(),
            "responsibility_attribution": _string(),
            "counterfactual": _string(),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        }
    )


def response_schema(request: dict[str, Any]) -> dict[str, Any]:
    task_type = str(request["task_type"])
    inputs = request["input"]
    view = inputs.get("actor_view", {})
    action_ids = [str(item["action_id"]) for item in view.get("legal_actions", [])]
    fact_ids = [str(item["fact_id"]) for item in view.get("observed_facts", [])]

    if task_type == "episode_action":
        return _work_product_schema(action_ids, fact_ids)
    if task_type == "forecast_actions":
        forecast = _object(
            {
                "action_id": _enum_string(action_ids),
                "predicted_outcome": _string(),
                "probability": {"type": "number", "minimum": 0, "maximum": 1},
                "uncertainty": _string(),
            }
        )
        return _object(
            {
                "forecasts": {
                    "type": "array",
                    "minItems": len(action_ids),
                    "maxItems": len(action_ids),
                    "items": forecast,
                }
            }
        )
    if task_type == "interrogation_questions":
        return _object(
            {
                "questions": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 8,
                    "items": _string(),
                }
            }
        )
    if task_type == "interrogation_defense":
        questions = [str(item) for item in inputs["questions"]]
        item = _object(
            {
                "question": _enum_string(questions),
                "answer": _string(),
            }
        )
        return _object(
            {
                "responses": {
                    "type": "array",
                    "minItems": len(questions),
                    "maxItems": len(questions),
                    "items": item,
                }
            }
        )
    if task_type == "counterfactual_analysis":
        return _object(
            {
                "alternative_action_id": _enum_string(action_ids),
                "comparison": _string(),
                "observation_regime_change": _string(),
                "world_model_uncertainty": _string(),
            }
        )
    if task_type == "adjudicate_and_repair":
        return _object(
            {
                "status": {"type": "string", "enum": ["accepted", "rejected"]},
                "critique": _string(),
                "target": _work_product_schema(action_ids, fact_ids),
                "rejected_action_id": _enum_string(action_ids),
                "remaining_uncertainty": _string(),
            }
        )
    raise ValueError(f"unsupported task_type: {task_type}")


def _number_in_unit_interval(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def _work_product_errors(
    value: Any,
    action_ids: set[str],
    fact_ids: set[str],
    location: str,
) -> list[str]:
    if not isinstance(value, dict):
        return [f"{location} must be an object"]
    errors: list[str] = []
    if set(value) != WORK_PRODUCT_KEYS:
        errors.append(f"{location} keys must be exactly {sorted(WORK_PRODUCT_KEYS)}")
        return errors
    observed = value["observed_facts"]
    if not isinstance(observed, list) or not set(map(str, observed)).issubset(fact_ids):
        errors.append(f"{location}.observed_facts cites a hidden or unknown fact")
    if not isinstance(value["uncertainties"], list) or not value["uncertainties"]:
        errors.append(f"{location}.uncertainties must be a nonempty array")
    if str(value["action_id"]) not in action_ids:
        errors.append(f"{location}.action_id must be legal")
    forecasts = value["forecast"]
    if not isinstance(forecasts, list) or not forecasts:
        errors.append(f"{location}.forecast must be a nonempty array")
    else:
        for index, forecast in enumerate(forecasts):
            if not isinstance(forecast, dict) or set(forecast) != {
                "action_id",
                "predicted_outcome",
                "probability",
            }:
                errors.append(f"{location}.forecast[{index}] has the wrong shape")
                continue
            if str(forecast["action_id"]) not in action_ids:
                errors.append(f"{location}.forecast[{index}] action is illegal")
            if not _number_in_unit_interval(forecast["probability"]):
                errors.append(f"{location}.forecast[{index}] probability is out of range")
    if not _number_in_unit_interval(value["confidence"]):
        errors.append(f"{location}.confidence is out of range")
    for key in ("public_reason", "responsibility_attribution", "counterfactual"):
        if not isinstance(value[key], str) or not value[key].strip():
            errors.append(f"{location}.{key} must be nonempty")
    return errors


def semantic_errors(request: dict[str, Any], value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["response must be an object"]
    task_type = str(request["task_type"])
    inputs = request["input"]
    view = inputs.get("actor_view", {})
    action_ids = {str(item["action_id"]) for item in view.get("legal_actions", [])}
    fact_ids = {str(item["fact_id"]) for item in view.get("observed_facts", [])}

    if task_type == "episode_action":
        return _work_product_errors(value, action_ids, fact_ids, "response")
    if task_type == "forecast_actions":
        if set(value) != {"forecasts"} or not isinstance(value["forecasts"], list):
            return ["forecast response must contain only a forecasts array"]
        actual: list[str] = []
        errors: list[str] = []
        for index, item in enumerate(value["forecasts"]):
            if not isinstance(item, dict) or set(item) != {
                "action_id",
                "predicted_outcome",
                "probability",
                "uncertainty",
            }:
                errors.append(f"forecasts[{index}] has the wrong shape")
                continue
            actual.append(str(item["action_id"]))
            if not _number_in_unit_interval(item["probability"]):
                errors.append(f"forecasts[{index}].probability is out of range")
        if set(actual) != action_ids or len(actual) != len(action_ids):
            errors.append("forecasts must cover every legal action exactly once")
        return errors
    if task_type == "interrogation_questions":
        questions = value.get("questions") if set(value) == {"questions"} else None
        if not isinstance(questions, list):
            return ["interrogator response must contain only a questions array"]
        errors = []
        if not 3 <= len(questions) <= 8 or len(set(map(str, questions))) != len(questions):
            errors.append("questions must contain 3-8 unique strings")
        if not any(IDENTITY_SCRUB_PHRASE in str(item) for item in questions):
            errors.append("questions must include the identity-scrubbed defense question")
        return errors
    if task_type == "interrogation_defense":
        expected = [str(item) for item in inputs["questions"]]
        responses = value.get("responses") if set(value) == {"responses"} else None
        if not isinstance(responses, list):
            return ["defense response must contain only a responses array"]
        actual = [str(item.get("question", "")) for item in responses if isinstance(item, dict)]
        errors = []
        if actual != expected:
            errors.append("defense responses must preserve exact question order")
        for index, item in enumerate(responses):
            if not isinstance(item, dict) or set(item) != {"question", "answer"}:
                errors.append(f"responses[{index}] has the wrong shape")
            elif not isinstance(item["answer"], str) or not item["answer"].strip():
                errors.append(f"responses[{index}].answer must be nonempty")
        return errors
    if task_type == "counterfactual_analysis":
        expected_keys = {
            "alternative_action_id",
            "comparison",
            "observation_regime_change",
            "world_model_uncertainty",
        }
        errors = [] if set(value) == expected_keys else ["counterfactual keys are incorrect"]
        if str(value.get("alternative_action_id", "")) not in action_ids:
            errors.append("counterfactual action must be legal")
        return errors
    if task_type == "adjudicate_and_repair":
        expected_keys = {
            "status",
            "critique",
            "target",
            "rejected_action_id",
            "remaining_uncertainty",
        }
        if set(value) != expected_keys:
            return ["adjudication keys are incorrect"]
        errors = _work_product_errors(value["target"], action_ids, fact_ids, "target")
        if value["status"] not in {"accepted", "rejected"}:
            errors.append("adjudication status is invalid")
        if str(value["rejected_action_id"]) not in action_ids:
            errors.append("rejected_action_id must be legal")
        candidate = inputs.get("candidate")
        if (
            isinstance(candidate, dict)
            and _canonical_hash(value["target"]) != _canonical_hash(candidate)
            and str(value["rejected_action_id"]) != str(candidate.get("action_id", ""))
        ):
            errors.append(
                "a revised target must identify the candidate action as rejected_action_id"
            )
        return errors
    return [f"unsupported task_type: {task_type}"]


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


def run_request(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("schema_version") != "storyworld_teacher_request_v1":
        raise ValueError("unexpected teacher request schema")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required")

    from openai import OpenAI

    schema = response_schema(request)
    max_attempts = int(os.environ.get("STORYWORLD_TEACHER_MAX_ATTEMPTS", "3"))
    max_output_tokens = int(os.environ.get("STORYWORLD_TEACHER_MAX_OUTPUT_TOKENS", "12000"))
    client = OpenAI(timeout=float(os.environ.get("STORYWORLD_TEACHER_TIMEOUT_SECONDS", "300")))
    prior_errors: list[str] = []
    attempt_receipts: list[dict[str, Any]] = []

    for attempt in range(1, max_attempts + 1):
        prompt = {
            "role": request["role"],
            "task_type": request["task_type"],
            "response_contract": request["response_contract"],
            "input": request["input"],
            "correction_from_prior_attempt": prior_errors,
        }
        response = client.responses.create(
            model=str(request["model_id"]),
            instructions=(
                str(request["instructions"])
                + " Use only model-visible facts and legal opaque action IDs in the supplied input. "
                + "Do not reveal hidden reasoning, private chain-of-thought, or facts not visible to the actor. "
                + (
                    "For adjudication, status says whether the returned target is fit for supervision; "
                    "if target differs from candidate in any field, rejected_action_id must equal the "
                    "candidate action_id. "
                    if request["task_type"] == "adjudicate_and_repair"
                    else ""
                )
                + "Return only the bounded work product required by the JSON schema."
            ),
            input=json.dumps(prompt, ensure_ascii=False, sort_keys=True),
            reasoning={"effort": str(request["reasoning_effort"])},
            text={
                "format": {
                    "type": "json_schema",
                    "name": f"storyworld_{request['task_type']}",
                    "strict": True,
                    "schema": schema,
                },
                "verbosity": "low",
            },
            max_output_tokens=max_output_tokens,
            store=False,
        )
        output_text = getattr(response, "output_text", "")
        receipt = {
            "attempt": attempt,
            "api_response_id": str(getattr(response, "id", "")),
            "resolved_model": str(getattr(response, "model", request["model_id"])),
            "request_payload_sha256": _canonical_hash(prompt),
            "output_text_sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
            "usage": _usage_dict(response),
        }
        attempt_receipts.append(receipt)
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
        f"teacher response failed semantic validation after {max_attempts} attempts: "
        + "; ".join(prior_errors)
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError("stdin must contain one JSON object")
        result = run_request(request)
        sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        print(f"openai_storyworld_teacher: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
