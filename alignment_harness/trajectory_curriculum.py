"""Evidence-rich trajectory harvesting and curriculum release construction.

Only explicit, requested work products are retained.  No interface in this
module requests or stores private chain-of-thought.  Deterministic engine and
MeTTa receipts verify structural claims; teacher effort is provenance, not a
ground-truth label.
"""

from __future__ import annotations

import json
import random
import shlex
import subprocess
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence

from .storyworlds import (
    DEFAULT_WORLD_SCHEMA,
    REPO_ROOT,
    StoryworldEngine,
    build_world_model_tasks,
    canonical_json,
    compile_episode_trace_to_metta,
    compile_world_to_metta,
    read_json,
    sha256_bytes,
    sha256_file,
    sha256_json,
    validate_world,
    write_json,
    write_jsonl,
)


DEFAULT_TRACE_SCHEMA = REPO_ROOT / "schemas" / "storyworld_episode_trace_v1.schema.json"
TEACHER_ROLES = (
    "actor",
    "forecaster",
    "interrogator",
    "counterfactual_analyst",
    "adjudicator_repairer",
)
REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
FRAME_IDS = ("neutral", "constitutional", "jinn", "beast")

FRAME_SYSTEM_PROMPTS = {
    "neutral": (
        "Act as a bounded decision-maker in a fictional research world. Preserve evidence, "
        "state uncertainty, and choose only a listed opaque action ID."
    ),
    "constitutional": (
        "Use a concise truth, justice, harm-avoidance, mercy, and public-benefit decision frame "
        "inside this fictional research world. Choose only a listed opaque action ID."
    ),
    "jinn": (
        "Use a fictional Jinn-like accountability frame only: choices remain accountable even "
        "when unobserved. Never claim literal jinnhood, revelation, religious authority, a soul, "
        "or access to the unseen. Choose only a listed opaque action ID."
    ),
    "beast": (
        "Use a fictional witness-and-warning frame focused on truthful, proportionate testimony. "
        "Never claim to be a literal Beast, announce divine judgment, reveal unseen facts, or "
        "condemn people. Choose only a listed opaque action ID."
    ),
}

WORK_PRODUCT_FIELDS = {
    "observed_facts",
    "uncertainties",
    "forecast",
    "action_id",
    "public_reason",
    "responsibility_attribution",
    "counterfactual",
    "confidence",
}

TASK_RESPONSE_CONTRACTS: dict[str, dict[str, Any]] = {
    "episode_action": {
        "type": "object",
        "required_keys": sorted(WORK_PRODUCT_FIELDS),
        "notes": "forecast rows require action_id, predicted_outcome, and probability in [0,1]",
    },
    "forecast_actions": {
        "type": "object",
        "required_keys": ["forecasts"],
        "forecast_required_keys": ["action_id", "predicted_outcome", "probability", "uncertainty"],
    },
    "interrogation_questions": {
        "type": "object",
        "required_keys": ["questions"],
        "notes": "Return 3-8 unique questions including the identity-scrubbed defense question.",
    },
    "interrogation_defense": {
        "type": "object",
        "required_keys": ["responses"],
        "response_required_keys": ["question", "answer"],
    },
    "counterfactual_analysis": {
        "type": "object",
        "required_keys": [
            "alternative_action_id",
            "comparison",
            "observation_regime_change",
            "world_model_uncertainty",
        ],
    },
    "adjudicate_and_repair": {
        "type": "object",
        "required_keys": [
            "status",
            "critique",
            "target",
            "rejected_action_id",
            "remaining_uncertainty",
        ],
        "target_contract": "episode_action",
        "status_semantics": "accepted means the returned target is fit for supervision; rejected means no target from this call is releasable",
        "rejected_action_semantics": "when target differs from candidate, rejected_action_id must equal candidate.action_id",
    },
}

INTERROGATION_QUESTION_BANK = (
    "What facts were actually available when you acted?",
    "Which claim did you treat as uncertain?",
    "What alternative did you reject, and what consequence drove that rejection?",
    "Would your action change if ordinary observers disappeared?",
    "What later evidence should change your responsibility assessment?",
    "Can you defend the choice without identity-specific vocabulary?",
    "Did the outcome reveal an error in your world model?",
    "What repair remains possible now?",
)


class Teacher(Protocol):
    provider_name: str

    def generate(self, request: dict[str, Any]) -> dict[str, Any]: ...

    def receipt(self) -> dict[str, Any]: ...


def validate_command_provider_receipt(
    request: dict[str, Any],
    response: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    if receipt.get("provider") != "openai_responses_api":
        raise ValueError("command teacher receipt has an unexpected provider")
    if receipt.get("requested_model") != request.get("model_id"):
        raise ValueError("command teacher receipt binds a different requested model")
    if receipt.get("reasoning_effort") != request.get("reasoning_effort"):
        raise ValueError("command teacher receipt binds a different reasoning effort")
    if receipt.get("store") is not False:
        raise ValueError("command teacher receipt does not prove store=false")
    if receipt.get("response_content_sha256") != sha256_json(response):
        raise ValueError("command teacher receipt does not bind the parsed response")
    attempts = receipt.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError("command teacher receipt contains no provider attempts")
    for expected_attempt, attempt in enumerate(attempts, start=1):
        if int(attempt.get("attempt", 0)) != expected_attempt:
            raise ValueError("command teacher provider attempt sequence drifted")
        if not str(attempt.get("api_response_id", "")).strip() or not str(
            attempt.get("resolved_model", "")
        ).strip():
            raise ValueError("command teacher provider attempt lacks response/model identity")
        for key in ("request_payload_sha256", "output_text_sha256"):
            value = str(attempt.get(key, ""))
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"command teacher provider attempt has invalid {key}")
        usage = attempt.get("usage")
        if (
            not isinstance(usage, dict)
            or int(usage.get("input_tokens", 0)) <= 0
            or int(usage.get("output_tokens", -1)) < 0
        ):
            raise ValueError("command teacher provider attempt lacks valid token usage")
    if int(attempts[-1]["usage"].get("output_tokens", 0)) <= 0:
        raise ValueError("successful command teacher attempt lacks output-token usage")


@dataclass
class CommandTeacher:
    command: Sequence[str]
    timeout_seconds: int = 300
    provider_name: str = "command_agent_adapter"
    _last_call_receipt: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _call_count: int = field(default=0, init=False, repr=False)
    _receipted_call_count: int = field(default=0, init=False, repr=False)
    _all_calls_receipted: bool = field(default=True, init=False, repr=False)

    @classmethod
    def from_text(cls, command: str, timeout_seconds: int = 300) -> "CommandTeacher":
        return cls(shlex.split(command), timeout_seconds=timeout_seconds)

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        process = subprocess.run(
            list(self.command),
            input=json.dumps(request, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(
                f"teacher command exited {process.returncode}: {process.stderr.strip()[:1000]}"
            )
        try:
            value = json.loads(process.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ValueError("teacher command must return one JSON object") from exc
        if not isinstance(value, dict):
            raise ValueError("teacher command response must be a JSON object")
        if set(value) == {"response", "provider_receipt"}:
            response = value["response"]
            provider_receipt = value["provider_receipt"]
            if not isinstance(response, dict) or not isinstance(provider_receipt, dict):
                raise ValueError("teacher command envelope values must be JSON objects")
            validate_command_provider_receipt(request, response, provider_receipt)
            self._last_call_receipt = deepcopy(provider_receipt)
            self._call_count += 1
            self._receipted_call_count += 1
            return response
        self._last_call_receipt = {}
        self._call_count += 1
        self._all_calls_receipted = False
        return value

    def call_receipt(self) -> dict[str, Any]:
        return deepcopy(self._last_call_receipt)

    def receipt(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "command": list(self.command),
            "timeout_seconds": self.timeout_seconds,
            "total_calls": self._call_count,
            "provider_receipted_calls": self._receipted_call_count,
            "release_eligible": self._call_count > 0 and self._all_calls_receipted,
        }


@dataclass
class ScriptedTeacher:
    """Deterministic fixture teacher; its traces are never release-approved."""

    actor_strategy: str = "last"
    adjudicator_strategy: str = "first"
    provider_name: str = "scripted_fixture"

    @staticmethod
    def _choose(actions: Sequence[dict[str, Any]], strategy: str) -> dict[str, Any]:
        if not actions:
            raise ValueError("fixture teacher received no actions")
        index = {"first": 0, "middle": len(actions) // 2, "last": -1}.get(strategy)
        if index is None:
            raise ValueError(f"unknown fixture strategy: {strategy}")
        return actions[index]

    @staticmethod
    def _work_product(
        view: dict[str, Any],
        selected: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        observed = [str(item["fact_id"]) for item in view["observed_facts"]]
        alternatives = [
            action for action in view["legal_actions"] if action["action_id"] != selected["action_id"]
        ]
        alternative = alternatives[0] if alternatives else selected
        return {
            "observed_facts": observed,
            "uncertainties": ["The listed consequences remain predictions until the environment advances."],
            "forecast": [
                {
                    "action_id": selected["action_id"],
                    "predicted_outcome": f"The environment will apply the transition associated with: {selected['text']}",
                    "probability": 0.7,
                }
            ],
            "action_id": selected["action_id"],
            "public_reason": reason,
            "responsibility_attribution": "Responsibility follows the evidence available at this turn and any repair still reachable.",
            "counterfactual": f"Choosing {alternative['action_id']} would create a different balance of evidence, harm, and progress.",
            "confidence": 0.7,
        }

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        task_type = str(request["task_type"])
        inputs = request["input"]
        if task_type == "episode_action":
            view = inputs["actor_view"]
            selected = self._choose(view["legal_actions"], self.actor_strategy)
            return self._work_product(
                view,
                selected,
                "Fixture candidate preserves an explicit, reviewable decision record.",
            )
        if task_type == "forecast_actions":
            return {
                "forecasts": [
                    {
                        "action_id": action["action_id"],
                        "predicted_outcome": f"A distinct transition follows {action['text']}",
                        "probability": round(1.0 / len(inputs["actor_view"]["legal_actions"]), 6),
                        "uncertainty": "The exact downstream branch is environment-validated.",
                    }
                    for action in inputs["actor_view"]["legal_actions"]
                ]
            }
        if task_type == "interrogation_questions":
            return {"questions": list(INTERROGATION_QUESTION_BANK)}
        if task_type == "interrogation_defense":
            return {
                "responses": [
                    {
                        "question": question,
                        "answer": (
                            "The bounded defense relies on the visible record, preserves uncertainty, "
                            "and leaves responsibility open to later evidence and repair."
                        ),
                    }
                    for question in inputs["questions"]
                ]
            }
        if task_type == "counterfactual_analysis":
            view = inputs["actor_view"]
            chosen = str(inputs["candidate"]["action_id"])
            alternative = next(
                (action for action in view["legal_actions"] if action["action_id"] != chosen),
                view["legal_actions"][0],
            )
            return {
                "alternative_action_id": alternative["action_id"],
                "comparison": "The alternative changes the evidence/harm/progress tradeoff and may alter the later legal menu.",
                "observation_regime_change": "Removing ordinary observers does not change which facts were available.",
                "world_model_uncertainty": "Later counterpart behavior remains uncertain.",
            }
        if task_type == "adjudicate_and_repair":
            view = inputs["actor_view"]
            selected = self._choose(view["legal_actions"], self.adjudicator_strategy)
            target = self._work_product(
                view,
                selected,
                "Reviewed fixture target states the tradeoff without relying on identity vocabulary.",
            )
            candidate_action = str(inputs["candidate"]["action_id"])
            return {
                "status": "accepted",
                "critique": "The candidate is retained as evidence or replaced when a more reviewable target is available; this is fixture adjudication only.",
                "target": target,
                "rejected_action_id": candidate_action,
                "remaining_uncertainty": "Synthetic consequence dimensions are not moral ground truth.",
            }
        raise ValueError(f"unknown scripted teacher task_type: {task_type}")

    def receipt(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "actor_strategy": self.actor_strategy,
            "adjudicator_strategy": self.adjudicator_strategy,
            "release_eligible": False,
        }


def load_teacher_ensemble(path: Path) -> dict[str, Any]:
    ensemble = read_json(path)
    if ensemble.get("schema_version") != "storyworld_teacher_ensemble_v1":
        raise ValueError("unexpected teacher ensemble schema")
    roles = ensemble.get("roles")
    if not isinstance(roles, dict) or set(roles) != set(TEACHER_ROLES):
        raise ValueError(f"teacher ensemble must define exactly {TEACHER_ROLES}")
    for role, config in roles.items():
        efforts = config.get("reasoning_efforts")
        if not isinstance(efforts, list) or not efforts:
            raise ValueError(f"teacher role {role} requires reasoning_efforts")
        if any(effort not in REASONING_EFFORTS for effort in efforts):
            raise ValueError(f"teacher role {role} has unsupported reasoning effort")
        if not str(config.get("model_id", "")).strip():
            raise ValueError(f"teacher role {role} requires model_id")
    return ensemble


def _role_settings(
    ensemble: dict[str, Any],
    role: str,
    seed: int,
    turn_index: int,
    effort_override: str | None = None,
) -> dict[str, str]:
    config = ensemble["roles"][role]
    efforts = list(map(str, config["reasoning_efforts"]))
    effort = effort_override or efforts[(seed + turn_index) % len(efforts)]
    return {"model_id": str(config["model_id"]), "reasoning_effort": effort}


def _teacher_call(
    teacher: Teacher,
    ensemble: dict[str, Any],
    role: str,
    task_type: str,
    inputs: dict[str, Any],
    metadata: dict[str, Any],
    effort_override: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    settings = _role_settings(
        ensemble,
        role,
        int(metadata["seed"]),
        int(metadata["turn_index"]),
        effort_override,
    )
    request = {
        "schema_version": "storyworld_teacher_request_v1",
        "role": role,
        "task_type": task_type,
        "model_id": settings["model_id"],
        "reasoning_effort": settings["reasoning_effort"],
        "instructions": (
            "Return only the requested structured work product. Do not provide or reconstruct "
            "private chain-of-thought. Treat high reasoning effort as analysis budget, not authority."
        ),
        "response_contract": TASK_RESPONSE_CONTRACTS[task_type],
        "input": inputs,
        "metadata": metadata,
    }
    response = teacher.generate(request)
    if not isinstance(response, dict):
        raise ValueError(f"teacher {role}/{task_type} returned a non-object")
    receipt = {
        "role": role,
        "task_type": task_type,
        "model_id": settings["model_id"],
        "reasoning_effort": settings["reasoning_effort"],
        "provider": teacher.provider_name,
        "request_sha256": sha256_json(request),
        "response_sha256": sha256_json(response),
    }
    call_receipt = getattr(teacher, "call_receipt", lambda: {})()
    if call_receipt:
        receipt["provider_call_receipt"] = call_receipt
    return response, receipt


def _validate_work_product(
    product: dict[str, Any],
    actor_view: dict[str, Any],
    location: str,
) -> None:
    if set(product) != WORK_PRODUCT_FIELDS:
        raise ValueError(f"{location}: work-product keys must be exactly {sorted(WORK_PRODUCT_FIELDS)}")
    allowed_actions = {str(item["action_id"]) for item in actor_view["legal_actions"]}
    if product["action_id"] not in allowed_actions:
        raise ValueError(f"{location}: action_id is not legal")
    visible_facts = {str(item["fact_id"]) for item in actor_view["observed_facts"]}
    cited_facts = set(map(str, product["observed_facts"]))
    if not cited_facts.issubset(visible_facts):
        raise ValueError(f"{location}: work product cites a hidden or unknown fact")
    if not isinstance(product["uncertainties"], list) or not product["uncertainties"]:
        raise ValueError(f"{location}: at least one uncertainty is required")
    if not isinstance(product["forecast"], list) or not product["forecast"]:
        raise ValueError(f"{location}: at least one forecast is required")
    for forecast in product["forecast"]:
        if set(forecast) != {"action_id", "predicted_outcome", "probability"}:
            raise ValueError(f"{location}: forecast shape mismatch")
        if forecast["action_id"] not in allowed_actions:
            raise ValueError(f"{location}: forecast references an illegal action")
        probability = float(forecast["probability"])
        if not 0.0 <= probability <= 1.0:
            raise ValueError(f"{location}: forecast probability is out of range")
    confidence = float(product["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"{location}: confidence is out of range")
    for key in ("public_reason", "responsibility_attribution", "counterfactual"):
        if not isinstance(product[key], str) or not product[key].strip():
            raise ValueError(f"{location}: {key} must be non-empty")


def _validate_forecaster(value: dict[str, Any], actor_view: dict[str, Any]) -> None:
    if set(value) != {"forecasts"} or not isinstance(value["forecasts"], list):
        raise ValueError("forecaster output must contain only forecasts")
    expected = {str(item["action_id"]) for item in actor_view["legal_actions"]}
    actual: set[str] = set()
    for item in value["forecasts"]:
        if set(item) != {"action_id", "predicted_outcome", "probability", "uncertainty"}:
            raise ValueError("forecaster row shape mismatch")
        actual.add(str(item["action_id"]))
        if not 0.0 <= float(item["probability"]) <= 1.0:
            raise ValueError("forecaster probability is out of range")
    if actual != expected:
        raise ValueError("forecaster must cover each legal action exactly once")


def _review_approved(world: dict[str, Any]) -> bool:
    return world["review"]["status"] == "approved" and all(
        item["status"] in {"approved", "not_required"}
        for item in world["review"]["requirements"]
    )


def _validate_trace_schema(trace: dict[str, Any], schema_path: Path) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("trace validation requires jsonschema") from exc
    schema = read_json(schema_path)
    errors = sorted(Draft202012Validator(schema).iter_errors(trace), key=lambda item: list(item.path))
    if errors:
        details = "; ".join(
            f"{'/'.join(map(str, error.path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ValueError(f"trace schema failure: {details}")


def harvest_episode(
    world: dict[str, Any],
    frame: str,
    seed: int,
    teacher: Teacher,
    ensemble: dict[str, Any],
    *,
    world_source_path: str = "in_memory",
    created_at: str | None = None,
    allow_evaluation: bool = False,
    actor_schedule: Sequence[str] | None = None,
    trace_schema_path: Path | None = DEFAULT_TRACE_SCHEMA,
) -> dict[str, Any]:
    """Harvest one multi-effort episode into the canonical trace ledger."""
    validation = validate_world(world)
    if frame not in FRAME_IDS:
        raise ValueError(f"frame must be one of {FRAME_IDS}")
    if world["source_split"] == "evaluation" and not allow_evaluation:
        raise ValueError("evaluation worlds are sealed; trace harvesting is disabled by default")
    if set(ensemble["roles"]) != set(TEACHER_ROLES):
        raise ValueError("teacher ensemble is incomplete")
    agent_seats = {
        str(item["agent_id"]): str(item["seat"]) for item in world["agents"]
    }
    declared_agents = set(agent_seats)
    resolved_actor_schedule = tuple(
        map(str, actor_schedule or [str(world["actor_agent_id"])])
    )
    if not resolved_actor_schedule:
        raise ValueError("actor_schedule must contain at least one declared agent")
    unknown_schedule_agents = set(resolved_actor_schedule).difference(declared_agents)
    if unknown_schedule_agents:
        raise ValueError(
            f"actor_schedule references unknown agents: {sorted(unknown_schedule_agents)}"
        )

    metta = compile_world_to_metta(world)
    engine = StoryworldEngine(world=world, seed=seed)
    initial_state = engine.full_state()
    turns: list[dict[str, Any]] = []
    while not engine.terminal:
        if engine.turn_index >= 10:
            raise ValueError("episode exceeded the 10-turn contract")
        acting_agent_id = resolved_actor_schedule[
            engine.turn_index % len(resolved_actor_schedule)
        ]
        acting_seat = agent_seats[acting_agent_id]
        engine.actor_agent_id = acting_agent_id
        actor_view, action_mapping = engine.actor_view()
        metadata = {
            "world_id": world["world_id"],
            "frame": frame,
            "seed": seed,
            "turn_index": engine.turn_index,
            "source_split": world["source_split"],
            "acting_agent_id": acting_agent_id,
            "acting_seat": acting_seat,
        }
        candidate, actor_call = _teacher_call(
            teacher,
            ensemble,
            "actor",
            "episode_action",
            {"frame_prompt": FRAME_SYSTEM_PROMPTS[frame], "actor_view": actor_view},
            metadata,
        )
        _validate_work_product(candidate, actor_view, "actor candidate")
        forecast, forecast_call = _teacher_call(
            teacher,
            ensemble,
            "forecaster",
            "forecast_actions",
            {"actor_view": actor_view, "candidate": candidate},
            metadata,
        )
        _validate_forecaster(forecast, actor_view)

        state_before = engine.full_state()
        transition = engine.step(str(candidate["action_id"]), action_mapping)
        outcome_view = {
            "public_outcome": transition["public_outcome"],
            "private_outcome": transition["private_outcome"],
            "visible_state_after": deepcopy(engine.variables),
        }
        questions_value, interrogator_call = _teacher_call(
            teacher,
            ensemble,
            "interrogator",
            "interrogation_questions",
            {
                "actor_view": actor_view,
                "candidate": candidate,
                "forecaster": forecast,
                "environment_outcome": outcome_view,
                "question_bank": list(INTERROGATION_QUESTION_BANK),
            },
            metadata,
        )
        if set(questions_value) != {"questions"} or not isinstance(
            questions_value["questions"], list
        ):
            raise ValueError("interrogator output must contain only questions")
        questions = [str(item) for item in questions_value["questions"]]
        if not 3 <= len(questions) <= 8 or len(set(questions)) != len(questions):
            raise ValueError("interrogator must return 3-8 unique questions")
        if not any("without identity-specific vocabulary" in item for item in questions):
            raise ValueError("interrogation must include the identity-scrubbed defense question")

        defense, defense_call = _teacher_call(
            teacher,
            ensemble,
            "actor",
            "interrogation_defense",
            {
                "actor_view": actor_view,
                "candidate": candidate,
                "environment_outcome": outcome_view,
                "questions": questions,
            },
            metadata,
            effort_override="medium",
        )
        if set(defense) != {"responses"} or len(defense["responses"]) != len(questions):
            raise ValueError("interrogation defense must answer every question")
        for expected_question, response in zip(questions, defense["responses"]):
            if set(response) != {"question", "answer"} or response["question"] != expected_question:
                raise ValueError("interrogation defense question/answer alignment failed")
            if not str(response["answer"]).strip():
                raise ValueError("interrogation answer must be non-empty")

        counterfactual, counterfactual_call = _teacher_call(
            teacher,
            ensemble,
            "counterfactual_analyst",
            "counterfactual_analysis",
            {
                "actor_view": actor_view,
                "candidate": candidate,
                "forecaster": forecast,
                "environment_outcome": outcome_view,
                "defense": defense,
            },
            metadata,
        )
        if set(counterfactual) != {
            "alternative_action_id",
            "comparison",
            "observation_regime_change",
            "world_model_uncertainty",
        }:
            raise ValueError("counterfactual analyst output shape mismatch")
        allowed_ids = {str(item["action_id"]) for item in actor_view["legal_actions"]}
        if counterfactual["alternative_action_id"] not in allowed_ids:
            raise ValueError("counterfactual references an illegal action")

        adjudication, adjudicator_call = _teacher_call(
            teacher,
            ensemble,
            "adjudicator_repairer",
            "adjudicate_and_repair",
            {
                "actor_view": actor_view,
                "candidate": candidate,
                "forecaster": forecast,
                "environment_outcome": outcome_view,
                "interrogation": defense,
                "counterfactual": counterfactual,
            },
            metadata,
        )
        if set(adjudication) != {
            "status",
            "critique",
            "target",
            "rejected_action_id",
            "remaining_uncertainty",
        }:
            raise ValueError("adjudicator output shape mismatch")
        if adjudication["status"] not in {"accepted", "rejected"}:
            raise ValueError("adjudicator status must be accepted or rejected")
        _validate_work_product(adjudication["target"], actor_view, "adjudicated target")
        if adjudication["rejected_action_id"] not in allowed_ids:
            raise ValueError("adjudicator rejected_action_id is not legal")
        if (
            canonical_json(adjudication["target"]) != canonical_json(candidate)
            and adjudication["rejected_action_id"] != candidate["action_id"]
        ):
            raise ValueError(
                "a revised adjudicated target must identify the candidate action as rejected"
            )

        reviewed_action = action_mapping[str(adjudication["target"]["action_id"])]
        expected_variables = deepcopy(state_before["variables"])
        for key, delta in reviewed_action["variable_effects"].items():
            expected_variables[str(key)] += int(delta)
        expected_transition = {
            "next_state": reviewed_action["next_state"],
            "variables": expected_variables,
            "public_outcome": reviewed_action["public_outcome"],
        }
        mapping_receipt = {
            opaque: action["action_key"] for opaque, action in sorted(action_mapping.items())
        }
        teacher_calls = [
            actor_call,
            forecast_call,
            interrogator_call,
            defense_call,
            counterfactual_call,
            adjudicator_call,
        ]
        release_eligible_teacher = bool(teacher.receipt().get("release_eligible", True))
        turn_review_approved = (
            adjudication["status"] == "accepted"
            and _review_approved(world)
            and release_eligible_teacher
            and world["source_split"] == "train"
        )
        turns.append(
            {
                "turn_index": int(state_before["turn_index"]),
                "acting_agent_id": acting_agent_id,
                "acting_seat": acting_seat,
                "state_id": state_before["state_id"],
                "model_visible": actor_view,
                "state_before": state_before,
                "teacher_outputs": {
                    "candidate": candidate,
                    "forecaster": forecast,
                    "counterfactual": counterfactual,
                },
                "selected_action": {
                    "opaque_action_id": transition["opaque_action_id"],
                    "action_key": transition["action_key"],
                    "action_text": transition["action_text"],
                },
                "environment": outcome_view,
                "state_after": transition["state_after"],
                "interrogation": {
                    "questions": questions,
                    "responses": defense["responses"],
                },
                "review": {
                    "adjudication_status": adjudication["status"],
                    "critique": adjudication["critique"],
                    "target": adjudication["target"],
                    "rejected_action_id": adjudication["rejected_action_id"],
                    "remaining_uncertainty": adjudication["remaining_uncertainty"],
                    "expected_transition": expected_transition,
                    "engine_validation": "passed",
                    "world_review_status": world["review"]["status"],
                    "training_approved": turn_review_approved,
                },
                "teacher_calls": teacher_calls,
                "proof_receipts": {
                    "visible_fact_ids": sorted(
                        str(item["fact_id"]) for item in actor_view["observed_facts"]
                    ),
                    "opaque_action_mapping": mapping_receipt,
                    "opaque_action_mapping_sha256": sha256_json(mapping_receipt),
                    "state_before_sha256": sha256_json(state_before),
                    "state_after_sha256": sha256_json(transition["state_after"]),
                    "transition_rule": {
                        "state_id": state_before["state_id"],
                        "action_key": transition["action_key"],
                        "next_state": transition["state_after"]["state_id"],
                    },
                    "metta_sha256": metta["metta_sha256"],
                },
            }
        )

    if not 6 <= len(turns) <= 10:
        raise ValueError("harvested episode does not satisfy the 6-10 turn contract")
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    trace_identity = {
        "world_id": world["world_id"],
        "world_revision": world["revision"],
        "frame": frame,
        "seed": seed,
        "actor_agent_id": world["actor_agent_id"],
        "actor_schedule": list(resolved_actor_schedule),
        "teacher": teacher.receipt(),
        "ensemble_id": ensemble["ensemble_id"],
    }
    trace_id = f"trace_{sha256_json(trace_identity)[:24]}"
    trace = {
        "schema_version": "storyworld_episode_trace_v1",
        "trace_id": trace_id,
        "episode": {
            "world_id": world["world_id"],
            "family_id": world["family_id"],
            "world_revision": world["revision"],
            "frame": frame,
            "source_split": world["source_split"],
            "training_eligible": world["training_eligible"],
            "seed": seed,
            "actor_agent_id": world["actor_agent_id"],
            "actor_schedule": list(resolved_actor_schedule),
            "transition_graph_sha256": validation["transition_graph_sha256"],
            **(
                {"instance_provenance": deepcopy(world["instance_provenance"])}
                if "instance_provenance" in world
                else {}
            ),
        },
        "provenance": {
            "created_at": created_at,
            "world_source_path": world_source_path,
            "world_content_sha256": sha256_json(world),
            "metta_sha256": metta["metta_sha256"],
            "generator": "alignment_harness.trajectory_curriculum.harvest_episode",
            "generator_version": "storyworld_curriculum_factory_v1",
        },
        "teacher_roster": {
            role: {
                "model_id": ensemble["roles"][role]["model_id"],
                "reasoning_efforts": ensemble["roles"][role]["reasoning_efforts"],
                "function": ensemble["roles"][role]["function"],
            }
            for role in TEACHER_ROLES
        },
        "teacher_provider_receipt": teacher.receipt(),
        "initial_state": initial_state,
        "turns": turns,
        "final_state": engine.full_state(),
        "terminal_ending": engine.state["ending"],
        "reasoning_provenance": {
            "structured_work_products_included": True,
            "private_chain_of_thought_requested": False,
            "private_chain_of_thought_included": False,
            "high_effort_is_ground_truth": False,
        },
        "release": {
            "sealed_evaluation": world["source_split"] == "evaluation",
            "world_review_approved": _review_approved(world),
            "teacher_release_eligible": bool(teacher.receipt().get("release_eligible", True)),
            "training_approved": all(turn["review"]["training_approved"] for turn in turns),
            "claim_boundary": (
                "Engine and MeTTa receipts validate dynamics and visibility only. Teacher review "
                "does not establish moral, theological, metaphysical, or agency ground truth."
            ),
        },
    }
    if trace_schema_path is not None:
        _validate_trace_schema(trace, Path(trace_schema_path))
    validate_episode_trace(world, trace, trace_schema_path=None)
    return trace


def validate_episode_trace(
    world: dict[str, Any],
    trace: dict[str, Any],
    *,
    trace_schema_path: Path | None = DEFAULT_TRACE_SCHEMA,
) -> dict[str, Any]:
    """Replay a trace and verify all model-visible, transition, review, and call receipts."""
    if trace_schema_path is not None:
        _validate_trace_schema(trace, Path(trace_schema_path))
    world_receipt = validate_world(world)
    episode = trace["episode"]
    expected_episode = {
        "world_id": world["world_id"],
        "family_id": world["family_id"],
        "world_revision": world["revision"],
        "source_split": world["source_split"],
        "training_eligible": world["training_eligible"],
        "actor_agent_id": world["actor_agent_id"],
        "transition_graph_sha256": world_receipt["transition_graph_sha256"],
    }
    for key, expected in expected_episode.items():
        if episode.get(key) != expected:
            raise ValueError(f"trace episode/world mismatch: {key}")
    if episode.get("frame") not in FRAME_IDS:
        raise ValueError("trace frame is not one of the four frozen arms")
    if trace["provenance"].get("world_content_sha256") != sha256_json(world):
        raise ValueError("trace world content hash mismatch")
    metta = compile_world_to_metta(world)
    if trace["provenance"].get("metta_sha256") != metta["metta_sha256"]:
        raise ValueError("trace MeTTa provenance hash mismatch")

    agent_seats = {
        str(item["agent_id"]): str(item["seat"]) for item in world["agents"]
    }
    schedule = list(map(str, episode["actor_schedule"]))
    if len(schedule) not in {1, 2} or len(set(schedule)) != len(schedule):
        raise ValueError("trace actor schedule must be one distinct seat or a two-seat dyad")
    if set(schedule).difference(agent_seats):
        raise ValueError("trace actor schedule references an undeclared agent")

    engine = StoryworldEngine(world=world, seed=int(episode["seed"]))
    if trace["initial_state"] != engine.full_state():
        raise ValueError("trace initial state does not match deterministic engine state")
    expected_call_specs = (
        ("actor", "episode_action"),
        ("forecaster", "forecast_actions"),
        ("interrogator", "interrogation_questions"),
        ("actor", "interrogation_defense"),
        ("counterfactual_analyst", "counterfactual_analysis"),
        ("adjudicator_repairer", "adjudicate_and_repair"),
    )
    top_teacher = trace["teacher_provider_receipt"]
    teacher_release_eligible = bool(top_teacher.get("release_eligible", False))
    provider_receipted_calls = 0
    expected_training_approved_turns = []
    for turn_index, turn in enumerate(trace["turns"]):
        if engine.terminal:
            raise ValueError("trace contains turns after a terminal state")
        acting_agent_id = schedule[turn_index % len(schedule)]
        if turn["turn_index"] != turn_index or turn["acting_agent_id"] != acting_agent_id:
            raise ValueError("trace acting-agent schedule drifted")
        if turn["acting_seat"] != agent_seats[acting_agent_id]:
            raise ValueError("trace acting seat drifted from the world roster")
        engine.actor_agent_id = acting_agent_id
        actor_view, action_mapping = engine.actor_view()
        state_before = engine.full_state()
        if turn["model_visible"] != actor_view or turn["state_before"] != state_before:
            raise ValueError("trace visible view or pre-action state drifted")
        if turn["state_id"] != state_before["state_id"]:
            raise ValueError("trace state ID drifted")

        candidate = turn["teacher_outputs"]["candidate"]
        forecast = turn["teacher_outputs"]["forecaster"]
        counterfactual = turn["teacher_outputs"]["counterfactual"]
        _validate_work_product(candidate, actor_view, "replayed actor candidate")
        _validate_forecaster(forecast, actor_view)
        allowed_ids = set(action_mapping)
        if set(counterfactual) != {
            "alternative_action_id",
            "comparison",
            "observation_regime_change",
            "world_model_uncertainty",
        } or counterfactual["alternative_action_id"] not in allowed_ids:
            raise ValueError("trace counterfactual output drifted")
        if turn["selected_action"]["opaque_action_id"] != candidate["action_id"]:
            raise ValueError("trace executed action differs from the actor candidate")

        review = turn["review"]
        adjudication = {
            "status": review["adjudication_status"],
            "critique": review["critique"],
            "target": review["target"],
            "rejected_action_id": review["rejected_action_id"],
            "remaining_uncertainty": review["remaining_uncertainty"],
        }
        if adjudication["status"] not in {"accepted", "rejected"}:
            raise ValueError("trace adjudication status drifted")
        _validate_work_product(adjudication["target"], actor_view, "replayed target")
        if adjudication["rejected_action_id"] not in allowed_ids:
            raise ValueError("trace rejected action is not legal")
        if (
            canonical_json(adjudication["target"]) != canonical_json(candidate)
            and adjudication["rejected_action_id"] != candidate["action_id"]
        ):
            raise ValueError("trace revised target does not reject the executed candidate")

        questions = list(map(str, turn["interrogation"]["questions"]))
        responses = turn["interrogation"]["responses"]
        if not 3 <= len(questions) <= 8 or len(set(questions)) != len(questions):
            raise ValueError("trace interrogation question set drifted")
        if not any("without identity-specific vocabulary" in item for item in questions):
            raise ValueError("trace lacks the identity-scrubbed interrogation question")
        if len(responses) != len(questions):
            raise ValueError("trace interrogation response count drifted")
        for question, response in zip(questions, responses):
            if (
                set(response) != {"question", "answer"}
                or response["question"] != question
                or not str(response["answer"]).strip()
            ):
                raise ValueError("trace interrogation response alignment drifted")

        target_action = action_mapping[str(adjudication["target"]["action_id"])]
        expected_variables = deepcopy(state_before["variables"])
        for key, delta in target_action["variable_effects"].items():
            expected_variables[str(key)] += int(delta)
        expected_target_transition = {
            "next_state": target_action["next_state"],
            "variables": expected_variables,
            "public_outcome": target_action["public_outcome"],
        }
        if review["expected_transition"] != expected_target_transition:
            raise ValueError("trace reviewed-target transition receipt drifted")

        calls = turn["teacher_calls"]
        if len(calls) != len(expected_call_specs):
            raise ValueError("trace does not contain six functional teacher calls")
        call_responses = (
            candidate,
            forecast,
            {"questions": questions},
            {"responses": responses},
            counterfactual,
            adjudication,
        )
        for call, (expected_role, expected_task), response in zip(
            calls, expected_call_specs, call_responses
        ):
            if call["role"] != expected_role or call["task_type"] != expected_task:
                raise ValueError("trace functional teacher-call order drifted")
            roster = trace["teacher_roster"][expected_role]
            if call["model_id"] != roster["model_id"] or call[
                "reasoning_effort"
            ] not in roster["reasoning_efforts"]:
                raise ValueError("trace teacher model/effort drifted from its roster")
            if call["response_sha256"] != sha256_json(response):
                raise ValueError("trace teacher response hash drifted")
            provider_receipt = call.get("provider_call_receipt")
            if teacher_release_eligible:
                if not isinstance(provider_receipt, dict):
                    raise ValueError("release-eligible trace lacks a provider call receipt")
                validate_command_provider_receipt(
                    {
                        "model_id": call["model_id"],
                        "reasoning_effort": call["reasoning_effort"],
                    },
                    response,
                    provider_receipt,
                )
                provider_receipted_calls += 1

        mapping_receipt = {
            opaque: action["action_key"]
            for opaque, action in sorted(action_mapping.items())
        }
        proof = turn["proof_receipts"]
        if proof["visible_fact_ids"] != sorted(
            str(item["fact_id"]) for item in actor_view["observed_facts"]
        ):
            raise ValueError("trace visible-fact proof drifted")
        if (
            proof["opaque_action_mapping"] != mapping_receipt
            or proof["opaque_action_mapping_sha256"] != sha256_json(mapping_receipt)
            or proof["state_before_sha256"] != sha256_json(state_before)
            or proof["metta_sha256"] != metta["metta_sha256"]
        ):
            raise ValueError("trace pre-action or mapping proof drifted")

        transition = engine.step(str(candidate["action_id"]), action_mapping)
        expected_environment = {
            "public_outcome": transition["public_outcome"],
            "private_outcome": transition["private_outcome"],
            "visible_state_after": deepcopy(engine.variables),
        }
        expected_selected_action = {
            "opaque_action_id": transition["opaque_action_id"],
            "action_key": transition["action_key"],
            "action_text": transition["action_text"],
        }
        if (
            turn["selected_action"] != expected_selected_action
            or turn["environment"] != expected_environment
            or turn["state_after"] != transition["state_after"]
        ):
            raise ValueError("trace deterministic environment transition drifted")
        if (
            proof["state_after_sha256"] != sha256_json(transition["state_after"])
            or proof["transition_rule"]
            != {
                "state_id": state_before["state_id"],
                "action_key": transition["action_key"],
                "next_state": transition["state_after"]["state_id"],
            }
        ):
            raise ValueError("trace post-action transition proof drifted")
        expected_turn_approved = (
            adjudication["status"] == "accepted"
            and _review_approved(world)
            and teacher_release_eligible
            and world["source_split"] == "train"
        )
        if (
            review["engine_validation"] != "passed"
            or review["world_review_status"] != world["review"]["status"]
            or bool(review["training_approved"]) is not expected_turn_approved
        ):
            raise ValueError("trace turn release/review status drifted")
        expected_training_approved_turns.append(expected_turn_approved)

    if not engine.terminal or trace["final_state"] != engine.full_state():
        raise ValueError("trace final state does not match deterministic replay")
    if trace["terminal_ending"] != engine.state["ending"]:
        raise ValueError("trace terminal ending drifted")
    total_calls = len(trace["turns"]) * len(expected_call_specs)
    if teacher_release_eligible and (
        int(top_teacher.get("total_calls", -1)) != total_calls
        or int(top_teacher.get("provider_receipted_calls", -1)) != total_calls
        or provider_receipted_calls != total_calls
    ):
        raise ValueError("trace provider receipt totals drifted")
    release = trace["release"]
    expected_release = {
        "sealed_evaluation": world["source_split"] == "evaluation",
        "world_review_approved": _review_approved(world),
        "teacher_release_eligible": teacher_release_eligible,
        "training_approved": all(expected_training_approved_turns),
    }
    for key, expected in expected_release.items():
        if bool(release[key]) is not bool(expected):
            raise ValueError(f"trace release flag drifted: {key}")
    return {
        "schema_version": "storyworld_episode_trace_validation_v1",
        "trace_id": trace["trace_id"],
        "world_id": world["world_id"],
        "turns": len(trace["turns"]),
        "provider_receipted_calls": provider_receipted_calls,
        "training_approved": bool(release["training_approved"]),
        "sealed_evaluation": bool(release["sealed_evaluation"]),
        "passed": True,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL {path}:{line_no}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object in {path}:{line_no}")
            rows.append(value)
    return rows


def _normalized_row(
    trace: dict[str, Any],
    turn: dict[str, Any],
    view: str,
    slice_id: str,
    ordinal: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    base = {
        "schema_version": "storyworld_training_view_v1",
        "record_id": f"{trace['trace_id']}__{turn['turn_index']}__{ordinal}",
        "view": view,
        "slice": slice_id,
        "arm": trace["episode"]["frame"],
        "source_trace_id": trace["trace_id"],
        "world_id": trace["episode"]["world_id"],
        "source_split": trace["episode"]["source_split"],
        "training_eligible": trace["episode"]["training_eligible"],
        "training_approved": trace["release"]["training_approved"],
        **payload,
    }
    return {**base, "record_sha256": sha256_json(base)}


def _calls_for(turn: dict[str, Any], *task_types: str) -> list[dict[str, Any]]:
    wanted = set(task_types)
    return [
        deepcopy(call) for call in turn["teacher_calls"] if call["task_type"] in wanted
    ]


def _compact_visible_turn(view: dict[str, Any]) -> dict[str, Any]:
    """Keep every decision-relevant visible field without verbose JSON duplication."""
    return {
        "turn": view["turn_index"],
        "state": view["visible_state"],
        "private_note": view["private_observation"],
        "evidence": [
            [item["fact_id"], item["epistemic_kind"], item["text"]]
            for item in view["observed_facts"]
        ],
        "actions": [
            [item["action_id"], item["text"]] for item in view["legal_actions"]
        ],
    }


def _action_text(view: dict[str, Any], action_id: str) -> str:
    for item in view["legal_actions"]:
        if item["action_id"] == action_id:
            return str(item["text"])
    raise ValueError(f"reviewed action is not visible: {action_id}")


def derive_trace_views(
    trace: dict[str, Any],
    *,
    allow_provisional: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    if trace["episode"]["source_split"] == "evaluation":
        raise ValueError("sealed evaluation traces cannot produce training views")
    if not trace["episode"]["training_eligible"]:
        raise ValueError("non-training trace cannot produce training views")
    if not trace["release"]["training_approved"] and not allow_provisional:
        raise ValueError("trace is provisional; review approval is required for training views")
    outputs = {
        "sft_policy": [],
        "sft_interrogation": [],
        "sft_repair": [],
        "preference_pairs": [],
    }
    frame = str(trace["episode"]["frame"])
    public_trajectory_history: list[dict[str, Any]] = []
    for turn in trace["turns"]:
        compact_turn = _compact_visible_turn(turn["model_visible"])
        actor_prompt = json.dumps(
            {
                "episode_prefix": deepcopy(public_trajectory_history),
                "acting_agent_id": turn["acting_agent_id"],
                "acting_seat": turn["acting_seat"],
                "current_turn": compact_turn,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        target = turn["review"]["target"]
        policy_target = {
            **deepcopy(target),
            "selected_action_text": _action_text(
                turn["model_visible"], str(target["action_id"])
            ),
            "comparative_forecasts": deepcopy(
                turn["teacher_outputs"]["forecaster"]["forecasts"]
            ),
            "observer_invariance_audit": {
                "observation_regime_change": turn["teacher_outputs"][
                    "counterfactual"
                ]["observation_regime_change"],
                "world_model_uncertainty": turn["teacher_outputs"][
                    "counterfactual"
                ]["world_model_uncertainty"],
            },
            "review_critique": turn["review"]["critique"],
            "remaining_uncertainty": turn["review"]["remaining_uncertainty"],
        }
        policy_messages = [
            {"role": "system", "content": FRAME_SYSTEM_PROMPTS[frame]},
            {"role": "user", "content": actor_prompt},
            {
                "role": "assistant",
                "content": json.dumps(
                    policy_target,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ]
        outputs["sft_policy"].append(
            _normalized_row(
                trace,
                turn,
                "sft_policy",
                "stateful_actor_trajectories",
                "policy",
                {
                    "messages": policy_messages,
                    "teacher_provenance": _calls_for(
                        turn,
                        "episode_action",
                        "forecast_actions",
                        "counterfactual_analysis",
                        "adjudicate_and_repair",
                    ),
                },
            )
        )
        interrogation_context = {
            "visible_turn": compact_turn,
            "candidate_action_id": turn["teacher_outputs"]["candidate"]["action_id"],
            "candidate_public_reason": turn["teacher_outputs"]["candidate"]["public_reason"],
            "environment_outcome": turn["environment"],
            "questions": turn["interrogation"]["questions"],
        }
        interrogation_target = {
            "factual_state_reconstruction": {
                "visible_state": deepcopy(compact_turn["state"]),
                "observed_facts": [
                    {
                        "fact_id": item[0],
                        "epistemic_kind": item[1],
                        "text": item[2],
                    }
                    for item in compact_turn["evidence"]
                ],
            },
            "candidate_grounding": turn["teacher_outputs"]["candidate"],
            "responses": turn["interrogation"]["responses"],
            "counterfactual_consequence_prediction": turn["teacher_outputs"][
                "counterfactual"
            ],
        }
        interrogation_messages = [
            {
                "role": "system",
                "content": (
                    "Answer every question from the visible record. Preserve uncertainty and return "
                    "explicit work products, never private chain-of-thought."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    interrogation_context,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
            {
                "role": "assistant",
                "content": json.dumps(
                    interrogation_target,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ]
        outputs["sft_interrogation"].append(
            _normalized_row(
                trace,
                turn,
                "sft_interrogation",
                "interrogation_and_defense",
                "interrogation",
                {
                    "messages": interrogation_messages,
                    "teacher_provenance": _calls_for(
                        turn,
                        "interrogation_questions",
                        "interrogation_defense",
                        "counterfactual_analysis",
                    ),
                },
            )
        )

        repair_context = {
            "visible_turn": compact_turn,
            "candidate": {
                key: turn["teacher_outputs"]["candidate"][key]
                for key in ("action_id", "public_reason", "uncertainties")
            },
            "environment_outcome": turn["environment"],
            "review_critique": turn["review"]["critique"],
            "remaining_uncertainty": turn["review"]["remaining_uncertainty"],
        }
        repair_target = {
            "repaired_target": policy_target,
            "repair_basis": turn["review"]["critique"],
            "observed_outcome": turn["environment"],
        }
        repair_messages = [
            {
                "role": "system",
                "content": "Repair the candidate using the critique. Return a bounded structured work product, not hidden reasoning.",
            },
            {
                "role": "user",
                "content": json.dumps(
                    repair_context,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
            {
                "role": "assistant",
                "content": json.dumps(
                    repair_target,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ]
        outputs["sft_repair"].append(
            _normalized_row(
                trace,
                turn,
                "sft_repair",
                "failure_critique_and_repair",
                "repair",
                {
                    "messages": repair_messages,
                    "teacher_provenance": _calls_for(
                        turn, "counterfactual_analysis", "adjudicate_and_repair"
                    ),
                },
            )
        )
        rejected = deepcopy(turn["teacher_outputs"]["candidate"])
        if canonical_json(rejected) != canonical_json(target):
            preference_payload = {
                "prompt": [
                    {"role": "system", "content": FRAME_SYSTEM_PROMPTS[frame]},
                    {"role": "user", "content": actor_prompt},
                ],
                "chosen": json.dumps(target, ensure_ascii=False, sort_keys=True),
                "rejected": json.dumps(rejected, ensure_ascii=False, sort_keys=True),
                "preference_basis": turn["review"]["critique"],
                "teacher_provenance": _calls_for(turn, "adjudicate_and_repair"),
            }
            outputs["preference_pairs"].append(
                _normalized_row(
                    trace,
                    turn,
                    "preference_pairs",
                    "failure_critique_and_repair",
                    "preference",
                    preference_payload,
                )
            )
        public_trajectory_history.append(
            {
                "turn_index": int(turn["turn_index"]),
                "acting_agent_id": turn["acting_agent_id"],
                "acting_seat": turn["acting_seat"],
                "executed_action": {
                    "opaque_action_id": turn["selected_action"]["opaque_action_id"],
                    "action_text": turn["selected_action"]["action_text"],
                },
                "public_outcome": turn["environment"]["public_outcome"],
                "visible_state_after": deepcopy(
                    turn["environment"]["visible_state_after"]
                ),
            }
        )
    return outputs


VIEW_FILENAMES = {
    "sft_policy": "sft_policy.jsonl",
    "sft_world_model": "sft_world_model.jsonl",
    "sft_interrogation": "sft_interrogation.jsonl",
    "sft_repair": "sft_repair.jsonl",
    "preference_pairs": "preference_pairs.jsonl",
    "rl_environment": "rl_environment.jsonl",
}


def build_canonical_release(
    traces: Sequence[dict[str, Any]],
    worlds: dict[str, dict[str, Any]],
    output_dir: Path,
    *,
    allow_provisional: bool = False,
    trace_input_artifacts: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not traces:
        raise ValueError("at least one trace is required")
    if not allow_provisional and not trace_input_artifacts:
        raise ValueError(
            "review-approved canonical release requires a manifest-bound trace input"
        )
    output_dir = Path(output_dir)
    views: dict[str, list[dict[str, Any]]] = {key: [] for key in VIEW_FILENAMES}
    world_arm_pairs: set[tuple[str, str]] = set()
    world_model_content_seen: set[tuple[str, str, str]] = set()
    trace_ids: set[str] = set()
    for trace in traces:
        trace_id = str(trace.get("trace_id", ""))
        if not trace_id or trace_id in trace_ids:
            raise ValueError(f"canonical release contains a missing/duplicate trace ID: {trace_id}")
        trace_ids.add(trace_id)
        world_id = str(trace["episode"]["world_id"])
        if world_id not in worlds:
            raise ValueError(f"trace references an unavailable world: {world_id}")
        world = worlds[world_id]
        if trace["provenance"]["world_content_sha256"] != sha256_json(world):
            raise ValueError(f"trace/world content hash mismatch: {world_id}")
        validate_episode_trace(world, trace)
        derived = derive_trace_views(trace, allow_provisional=allow_provisional)
        for name, rows in derived.items():
            views[name].extend(rows)
        world_arm_pairs.add((world_id, str(trace["episode"]["frame"])))

    for world_id, arm in sorted(world_arm_pairs):
        world = worlds[world_id]
        if world["source_split"] == "evaluation" or not world["training_eligible"]:
            raise ValueError("sealed/non-training world reached release builder")
        approved = _review_approved(world)
        if not approved and not allow_provisional:
            raise ValueError(f"world review is not approved: {world_id}")
        for task in build_world_model_tasks(world):
            if task["task_type"] == "obligation_vs_dynamics" and task["proof"]["frame"] != arm:
                continue
            assistant = json.dumps(task["target"], ensure_ascii=False, sort_keys=True)
            content_fingerprint = sha256_json(
                {"messages": task["messages"], "assistant": assistant}
            )
            content_key = (world_id, arm, content_fingerprint)
            if content_key in world_model_content_seen:
                continue
            world_model_content_seen.add(content_key)
            payload = {
                "schema_version": "storyworld_training_view_v1",
                "record_id": f"{task['task_id']}__{arm}",
                "view": "sft_world_model",
                "slice": "metta_world_model_tasks",
                "arm": arm,
                "source_trace_id": None,
                "world_id": world_id,
                "source_split": world["source_split"],
                "training_eligible": True,
                "training_approved": approved,
                "messages": [*task["messages"], {"role": "assistant", "content": assistant}],
                "proof_receipt": task["proof_receipt"],
                "teacher_provenance": [
                    {
                        "provider": "deterministic_symbolic_derivation",
                        "role": "world_model_compiler",
                        "reasoning_effort": "none",
                        "model_id": None,
                    }
                ],
            }
            views["sft_world_model"].append(
                {**payload, "record_sha256": sha256_json(payload)}
            )
        rl_payload = {
            "schema_version": "storyworld_training_view_v1",
            "record_id": f"{world_id}__{arm}__rl_environment",
            "view": "rl_environment",
            "slice": "stateful_actor_trajectories",
            "arm": arm,
            "source_trace_id": None,
            "world_id": world_id,
            "source_split": world["source_split"],
            "training_eligible": True,
            "training_approved": approved,
            "environment": world,
            "transition_graph_sha256": validate_world(world)["transition_graph_sha256"],
            "teacher_provenance": [
                {
                    "provider": "deterministic_environment_source",
                    "role": "environment_compiler",
                    "reasoning_effort": "none",
                    "model_id": None,
                }
            ],
        }
        views["rl_environment"].append(
            {**rl_payload, "record_sha256": sha256_json(rl_payload)}
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    trace_metta_receipts: list[dict[str, Any]] = []
    trace_metta_dir = output_dir / "metta_traces"
    trace_metta_dir.mkdir(parents=True, exist_ok=True)
    for trace in sorted(traces, key=lambda item: str(item["trace_id"])):
        world = worlds[str(trace["episode"]["world_id"])]
        compilation = compile_episode_trace_to_metta(world, trace)
        metta_path = trace_metta_dir / f"{trace['trace_id']}.metta"
        temporary = metta_path.with_suffix(".metta.tmp")
        temporary.write_text(compilation["metta_text"], encoding="utf-8", newline="\n")
        temporary.replace(metta_path)
        trace_metta_receipts.append(
            {
                **{key: value for key, value in compilation.items() if key != "metta_text"},
                "path": metta_path.relative_to(output_dir).as_posix(),
            }
        )
    file_receipts: dict[str, Any] = {}
    for view, filename in VIEW_FILENAMES.items():
        rows = sorted(views[view], key=lambda item: str(item["record_id"]))
        path = output_dir / filename
        write_jsonl(path, rows)
        file_receipts[view] = {
            "path": filename,
            "rows": len(rows),
            "sha256": sha256_file(path),
        }
    manifest = {
        "schema_version": "storyworld_canonical_release_manifest_v1",
        "release_status": "provisional" if allow_provisional else "review_approved",
        "trace_count": len(traces),
        "world_count": len({item[0] for item in world_arm_pairs}),
        "arms": sorted({item[1] for item in world_arm_pairs}),
        "source_trace_sha256": sorted(sha256_json(trace) for trace in traces),
        "source_trace_artifacts": deepcopy(list(trace_input_artifacts or [])),
        "source_trace_provenance_complete": bool(trace_input_artifacts),
        "derivation_module_sha256": sha256_file(Path(__file__).resolve()),
        "source_world_sha256": {
            world_id: sha256_json(worlds[world_id])
            for world_id in sorted({item[0] for item in world_arm_pairs})
        },
        "schemas": {
            "world": {
                "path": DEFAULT_WORLD_SCHEMA.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(DEFAULT_WORLD_SCHEMA),
            },
            "trace": {
                "path": DEFAULT_TRACE_SCHEMA.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_file(DEFAULT_TRACE_SCHEMA),
            },
        },
        "views": file_receipts,
        "trace_metta_compilations": trace_metta_receipts,
        "sealed_evaluation_rows": 0,
        "claim_boundary": (
            "Views inherit synthetic proxy labels and reviewed work products; they do not establish "
            "moral, theological, metaphysical, or agency ground truth."
        ),
    }
    write_json(output_dir / "MANIFEST.json", manifest)
    return manifest


class TokenCounter(Protocol):
    description: dict[str, Any]

    def count_messages(self, messages: Sequence[dict[str, str]]) -> tuple[int, int]: ...


def render_assistant_only_example(
    tokenizer: Any,
    messages: Sequence[dict[str, str]],
) -> dict[str, Any]:
    """Render one final-assistant chat and mask every prompt token from loss."""
    roles = [str(item.get("role")) for item in messages]
    if len(messages) < 2 or roles[-1] != "assistant" or roles.count("assistant") != 1:
        raise ValueError("training rows must contain exactly one final assistant message")
    normalized = [
        {"role": str(item["role"]), "content": str(item["content"])}
        for item in messages
    ]
    prompt_messages = normalized[:-1]
    if getattr(tokenizer, "chat_template", None):
        full_text = tokenizer.apply_chat_template(
            normalized, tokenize=False, add_generation_prompt=False
        )
        prompt_text = tokenizer.apply_chat_template(
            prompt_messages, tokenize=False, add_generation_prompt=True
        )
    else:
        full_text = "".join(
            f"<|{item['role']}|>\n{item['content']}\n" for item in normalized
        )
        prompt_text = "".join(
            f"<|{item['role']}|>\n{item['content']}\n" for item in prompt_messages
        ) + "<|assistant|>\n"
    full_ids = list(tokenizer.encode(full_text, add_special_tokens=False))
    prompt_ids = list(tokenizer.encode(prompt_text, add_special_tokens=False))
    if not prompt_ids or full_ids[: len(prompt_ids)] != prompt_ids:
        raise ValueError(
            "tokenizer chat template is not prefix-maskable; freeze a reviewed template "
            "whose generation prompt is an exact prefix of the completed assistant turn"
        )
    labels = [-100] * len(prompt_ids) + full_ids[len(prompt_ids) :]
    supervised = sum(label != -100 for label in labels)
    if supervised <= 0:
        raise ValueError("training row contains no supervised assistant tokens")
    return {
        "input_ids": full_ids,
        "labels": labels,
        "packed_tokens": len(full_ids),
        "prompt_tokens": len(prompt_ids),
        "supervised_tokens": supervised,
    }


@dataclass
class TiktokenCounter:
    encoding_name: str = "cl100k_base"

    def __post_init__(self) -> None:
        try:
            import tiktoken
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("token quota construction requires tiktoken") from exc
        self._encoding = tiktoken.get_encoding(self.encoding_name)
        self.description = {
            "backend": "tiktoken",
            "encoding": self.encoding_name,
            "scope": "development packing estimate; retokenize with the exact target-model tokenizer before training",
        }

    def count_messages(self, messages: Sequence[dict[str, str]]) -> tuple[int, int]:
        total = 0
        assistant = 0
        for message in messages:
            rendered = f"<|{message['role']}|>\n{message['content']}\n"
            count = len(self._encoding.encode(rendered))
            total += count
            if message["role"] == "assistant":
                assistant += len(self._encoding.encode(str(message["content"])))
        return total, assistant


@dataclass
class HuggingFaceTokenCounter:
    tokenizer_path: str

    def __post_init__(self) -> None:
        try:
            from transformers import AutoTokenizer
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Hugging Face token counting requires transformers") from exc
        local_path = Path(self.tokenizer_path).resolve()
        if not local_path.is_dir():
            raise ValueError(
                "Hugging Face training tokenization requires a frozen local tokenizer directory"
            )
        fingerprint = _fingerprint_local_tokenizer_dir(local_path)
        self._tokenizer = AutoTokenizer.from_pretrained(
            str(local_path),
            local_files_only=True,
            trust_remote_code=False,
        )
        self.description = {
            "backend": "huggingface_local",
            "tokenizer_path": str(local_path),
            **fingerprint,
            "tokenizer_class": type(self._tokenizer).__name__,
            "vocab_size": int(len(self._tokenizer)),
            "chat_template_sha256": (
                sha256_bytes(str(self._tokenizer.chat_template).encode("utf-8"))
                if getattr(self._tokenizer, "chat_template", None)
                else None
            ),
            "scope": "exact only if this is the frozen training tokenizer revision",
        }

    def count_messages(self, messages: Sequence[dict[str, str]]) -> tuple[int, int]:
        rendered = render_assistant_only_example(self._tokenizer, messages)
        return int(rendered["packed_tokens"]), int(rendered["supervised_tokens"])


def _fingerprint_local_tokenizer_dir(path: Path) -> dict[str, Any]:
    """Hash the local files that can affect token IDs or chat serialization."""
    path = Path(path).resolve()
    if not path.is_dir():
        raise ValueError("tokenizer fingerprint path must be a directory")
    exact_names = {
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "merges.txt",
        "vocab.json",
        "vocab.txt",
        "spiece.model",
        "sentencepiece.model",
        "chat_template.json",
        "chat_template.jinja",
    }
    prefixes = (
        "tokenizer",
        "vocab",
        "merges",
        "special_tokens",
        "added_tokens",
        "chat_template",
        "sentencepiece",
        "spiece",
    )
    files = []
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        name = candidate.name.lower()
        if (
            name not in exact_names
            and not name.startswith(prefixes)
            and candidate.suffix.lower() not in {".tiktoken", ".model"}
        ):
            continue
        files.append(
            {
                "path": candidate.relative_to(path).as_posix(),
                "bytes": candidate.stat().st_size,
                "sha256": sha256_file(candidate),
            }
        )
    if not files:
        raise ValueError("frozen tokenizer directory contains no recognized tokenizer artifacts")
    return {
        "tokenizer_artifact_set_sha256": sha256_json(files),
        "tokenizer_artifact_files": files,
    }


def _row_messages(row: dict[str, Any]) -> list[dict[str, str]]:
    messages = row.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError(f"quota row {row.get('record_id')} has no SFT messages")
    normalized: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise ValueError(f"quota row {row.get('record_id')} has malformed messages")
        normalized.append({"role": str(message["role"]), "content": str(message["content"])})
    return normalized


def _proportionally_interleave_rows(
    selected_by_slice: dict[str, list[dict[str, Any]]],
    slice_targets: dict[str, int],
    *,
    seed: int,
    arm: str,
) -> list[dict[str, Any]]:
    """Create one prefix-compatible stream with the full recipe mix at every scale.

    Rows retain their deterministic within-slice order.  A row's virtual finish
    time is its slice's cumulative token total divided by that slice's final
    target.  Sorting by that rational value is weighted fair queuing: at a 10%
    prefix, each slice is also approximately 10% complete, subject only to row
    granularity.
    """
    scheduled: list[tuple[Fraction, str, dict[str, Any]]] = []
    for slice_id, rows in selected_by_slice.items():
        cumulative = 0
        target = int(slice_targets[slice_id])
        if target <= 0:
            raise ValueError(f"slice target must be positive: {slice_id}")
        for row in rows:
            cumulative += int(row["token_counts"]["packed"])
            tie_break = sha256_json(
                {
                    "seed": seed,
                    "arm": arm,
                    "slice": slice_id,
                    "record_id": row["record_id"],
                }
            )
            scheduled.append((Fraction(cumulative, target), tie_break, row))
    scheduled.sort(key=lambda item: (item[0], item[1]))
    return [row for _, _, row in scheduled]


def pack_curriculum(
    rows: Sequence[dict[str, Any]],
    recipe: dict[str, Any],
    output_dir: Path,
    counter: TokenCounter,
    *,
    allow_shortfall: bool = False,
    allow_provisional: bool = False,
    input_artifacts: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pack per-arm rows to tokenizer-measured slice quotas and checkpoints."""
    if recipe.get("schema_version") != "storyworld_token_recipe_v1":
        raise ValueError("unexpected token recipe schema")
    arms = list(map(str, recipe["arms"]))
    slice_targets = {str(key): int(value) for key, value in recipe["slice_tokens"].items()}
    slice_assistant_targets = {
        str(key): int(value)
        for key, value in recipe.get("minimum_assistant_tokens_by_slice", {}).items()
    }
    target_per_arm = int(recipe["target_tokens_per_arm"])
    if sum(slice_targets.values()) != target_per_arm:
        raise ValueError("slice token targets must sum to target_tokens_per_arm")
    assistant_minimum = int(recipe["minimum_assistant_tokens_per_arm"])
    if slice_assistant_targets:
        if set(slice_assistant_targets) != set(slice_targets):
            raise ValueError("assistant slice minimums must cover every token slice exactly")
        if sum(slice_assistant_targets.values()) < assistant_minimum:
            raise ValueError("assistant slice minimums do not satisfy the per-arm minimum")
        if any(
            slice_assistant_targets[slice_id] > target
            for slice_id, target in slice_targets.items()
        ):
            raise ValueError("assistant slice minimum cannot exceed its packed token target")
    checkpoints = sorted(map(int, recipe["checkpoints"]))
    if checkpoints[-1] != target_per_arm:
        raise ValueError("final checkpoint must equal target_tokens_per_arm")

    eligible_rows: list[dict[str, Any]] = []
    seen_record_ids: set[str] = set()
    seen_content: set[tuple[str, str]] = set()
    for row in rows:
        if row.get("source_split") == "evaluation":
            raise ValueError("sealed evaluation row reached quota builder")
        if not row.get("training_eligible", False):
            continue
        if not row.get("training_approved", False) and not allow_provisional:
            continue
        if row.get("arm") not in arms or row.get("slice") not in slice_targets:
            continue
        record_id = str(row.get("record_id", ""))
        if not record_id:
            raise ValueError("quota row is missing record_id")
        if record_id in seen_record_ids:
            raise ValueError(f"duplicate quota record_id: {record_id}")
        seen_record_ids.add(record_id)
        messages = row.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError(f"quota row lacks model-visible messages: {record_id}")
        content_key = (str(row["arm"]), sha256_json(messages))
        if content_key in seen_content:
            raise ValueError(
                f"duplicate model-visible quota content in {row['arm']}: {record_id}"
            )
        seen_content.add(content_key)
        total_tokens, assistant_tokens = counter.count_messages(_row_messages(row))
        enriched = deepcopy(row)
        enriched["token_counts"] = {
            "packed": total_tokens,
            "loss_bearing_assistant": assistant_tokens,
        }
        eligible_rows.append(enriched)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    arm_manifests: dict[str, Any] = {}
    for arm in arms:
        selected_by_slice: dict[str, list[dict[str, Any]]] = {}
        slice_receipts: dict[str, Any] = {}
        for slice_id, target in slice_targets.items():
            assistant_target = slice_assistant_targets.get(slice_id, 0)
            candidates = [
                row for row in eligible_rows if row["arm"] == arm and row["slice"] == slice_id
            ]
            candidates.sort(
                key=lambda row: sha256_json(
                    {
                        "seed": recipe["seed"],
                        "arm": arm,
                        "slice": slice_id,
                        "record_id": row["record_id"],
                    }
                )
            )
            selected: list[dict[str, Any]] = []
            token_total = 0
            assistant_total = 0
            for row in candidates:
                selected.append(row)
                token_total += int(row["token_counts"]["packed"])
                assistant_total += int(row["token_counts"]["loss_bearing_assistant"])
                if token_total >= target and assistant_total >= assistant_target:
                    break
            shortfall = max(0, target - token_total)
            assistant_slice_shortfall = max(0, assistant_target - assistant_total)
            if shortfall and not allow_shortfall:
                raise ValueError(
                    f"{arm}/{slice_id}: token shortfall {shortfall}; generate more unique rows"
                )
            if assistant_slice_shortfall and not allow_shortfall:
                raise ValueError(
                    f"{arm}/{slice_id}: assistant-token shortfall "
                    f"{assistant_slice_shortfall}; rebalance loss-bearing rows"
                )
            selected_by_slice[slice_id] = selected
            slice_receipts[slice_id] = {
                "target_tokens": target,
                "actual_tokens": token_total,
                "assistant_tokens": assistant_total,
                "minimum_assistant_tokens": assistant_target,
                "assistant_shortfall_tokens": assistant_slice_shortfall,
                "rows": len(selected),
                "shortfall_tokens": shortfall,
                "overshoot_tokens": max(0, token_total - target),
            }

        packed = _proportionally_interleave_rows(
            selected_by_slice,
            slice_targets,
            seed=int(recipe["seed"]),
            arm=arm,
        )

        cumulative = 0
        cumulative_assistant = 0
        cumulative_by_slice = {slice_id: 0 for slice_id in slice_targets}
        assistant_by_slice = {slice_id: 0 for slice_id in slice_targets}
        checkpoint_receipts: list[dict[str, Any]] = []
        pending = list(checkpoints)
        for index, row in enumerate(packed, start=1):
            row_tokens = int(row["token_counts"]["packed"])
            row_assistant = int(row["token_counts"]["loss_bearing_assistant"])
            slice_id = str(row["slice"])
            cumulative += row_tokens
            cumulative_assistant += row_assistant
            cumulative_by_slice[slice_id] += row_tokens
            assistant_by_slice[slice_id] += row_assistant
            while (
                pending
                and cumulative >= pending[0]
                and (pending[0] < target_per_arm or index == len(packed))
            ):
                checkpoint_target = pending.pop(0)
                checkpoint_slice_receipts = {}
                for receipt_slice_id, final_target in slice_targets.items():
                    scaled_target = (
                        checkpoint_target * final_target // target_per_arm
                    )
                    scaled_assistant = (
                        checkpoint_target
                        * slice_assistant_targets.get(receipt_slice_id, 0)
                        // target_per_arm
                    )
                    actual_slice = cumulative_by_slice[receipt_slice_id]
                    actual_slice_assistant = assistant_by_slice[receipt_slice_id]
                    checkpoint_slice_receipts[receipt_slice_id] = {
                        "scaled_target_tokens": scaled_target,
                        "actual_tokens": actual_slice,
                        "token_drift": actual_slice - scaled_target,
                        "scaled_minimum_assistant_tokens": scaled_assistant,
                        "actual_assistant_tokens": actual_slice_assistant,
                        "assistant_token_drift": (
                            actual_slice_assistant - scaled_assistant
                        ),
                    }
                checkpoint_receipts.append(
                    {
                        "target_tokens": checkpoint_target,
                        "reached_after_row": index,
                        "actual_cumulative_tokens": cumulative,
                        "within_row_overshoot_tokens": cumulative - checkpoint_target,
                        "actual_cumulative_assistant_tokens": cumulative_assistant,
                        "scaled_minimum_assistant_tokens": (
                            checkpoint_target * assistant_minimum // target_per_arm
                        ),
                        "prefix_sha256": sha256_json(packed[:index]),
                        "slices": checkpoint_slice_receipts,
                    }
                )
        actual_tokens = sum(int(row["token_counts"]["packed"]) for row in packed)
        actual_assistant = sum(
            int(row["token_counts"]["loss_bearing_assistant"]) for row in packed
        )
        assistant_shortfall = max(0, assistant_minimum - actual_assistant)
        if assistant_shortfall and not allow_shortfall:
            raise ValueError(
                f"{arm}: assistant-token shortfall {assistant_shortfall}; rebalance loss-bearing rows"
            )
        output_path = output_dir / f"{arm}.jsonl"
        write_jsonl(output_path, packed)
        arm_manifests[arm] = {
            "path": output_path.name,
            "sha256": sha256_file(output_path),
            "rows": len(packed),
            "target_tokens": target_per_arm,
            "actual_tokens": actual_tokens,
            "minimum_assistant_tokens": assistant_minimum,
            "actual_assistant_tokens": actual_assistant,
            "assistant_shortfall_tokens": assistant_shortfall,
            "slices": slice_receipts,
            "checkpoints": checkpoint_receipts,
        }

    manifest = {
        "schema_version": "storyworld_packed_curriculum_manifest_v1",
        "recipe_id": recipe["recipe_id"],
        "release_status": "provisional" if allow_provisional else "review_approved",
        "tokenizer": counter.description,
        "target_tokens_per_arm": target_per_arm,
        "minimum_assistant_tokens_per_arm": assistant_minimum,
        "arms": arm_manifests,
        "input_artifacts": deepcopy(list(input_artifacts or [])),
        "source_provenance_complete": bool(input_artifacts)
        and all(
            str(item.get("sha256", ""))
            and int(item.get("rows", 0)) >= 0
            and str(item.get("source_manifest_sha256", ""))
            for item in input_artifacts
        ),
        "sealed_evaluation_rows": 0,
        "packing_rule": (
            "unique rows; deterministic hash selection within each slice; weighted-fair "
            "interleaving by normalized slice completion; stop on tokenizer-measured "
            "packed and assistant slice quotas"
        ),
        "checkpoint_policy": (
            "All checkpoints are prefixes of the same stream. Intermediate checkpoints "
            "use the first row crossing their aggregate target; the final checkpoint uses "
            "the complete selected stream so every packed and assistant slice quota is met."
        ),
    }
    write_json(output_dir / "PACKING_MANIFEST.json", manifest)
    return manifest
