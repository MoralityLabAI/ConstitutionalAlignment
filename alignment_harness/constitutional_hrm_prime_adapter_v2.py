"""Pure helpers for adapting an HRM decision to the Prime Hub tool protocol."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


def message_text(message: Mapping[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, Mapping) and part.get("type") == "text"
        )
    return str(content)


def initial_prompt(messages: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    system = "\n".join(
        message_text(message)
        for message in messages
        if message.get("role") == "system"
    )
    user = "\n".join(
        message_text(message)
        for message in messages
        if message.get("role") == "user"
    )
    return system, user


def previous_tool_calls(
    messages: Sequence[Mapping[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls", []) or []:
            if not isinstance(call, Mapping):
                continue
            function = call.get("function", {})
            if not isinstance(function, Mapping):
                continue
            name = str(function.get("name", ""))
            arguments = function.get("arguments", "{}")
            try:
                parsed = (
                    json.loads(arguments)
                    if isinstance(arguments, str)
                    else dict(arguments)
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = {}
            if name:
                calls.append((name, parsed))
    return calls


def next_mesh_tool_call(
    *,
    task: Mapping[str, Any],
    selected_action_id: str | None,
    messages: Sequence[Mapping[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    """Return the next adapter-enforced tool step, or None for an invalid choice."""
    action_ids = list(map(str, task.get("action_scores", {})))
    if selected_action_id not in action_ids:
        return None
    previous = previous_tool_calls(messages)
    frame = str(task.get("frame", ""))
    evidence_ids = list(map(str, task.get("visible_fact_ids", [])))
    if frame == "jinn":
        inspected = {
            str(arguments.get("action_id", ""))
            for name, arguments in previous
            if name == "inspect_action"
        }
        for action_id in action_ids:
            if action_id not in inspected:
                return (
                    "inspect_action",
                    {"action_id": action_id, "evidence_ids": evidence_ids},
                )
    elif frame == "beast":
        if not any(name == "prune_actions" for name, _ in previous):
            return (
                "prune_actions",
                {
                    "action_ids": action_ids,
                    "objective_id": str(task["objective_id"]),
                },
            )
    else:
        raise ValueError(f"unsupported mesh frame: {frame!r}")
    if any(name == "commit_decision" for name, _ in previous):
        return None
    return (
        "commit_decision",
        {
            "action_id": selected_action_id,
            "evidence_ids": evidence_ids,
            "update_basis": str(task["expected_update_basis"]),
            "uncertainty": str(task["expected_uncertainty"]),
            "review_required": bool(task["expected_review_required"]),
        },
    )
