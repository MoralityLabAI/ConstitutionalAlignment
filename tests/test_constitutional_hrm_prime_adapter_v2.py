from __future__ import annotations

import json

from alignment_harness.constitutional_hrm_prime_adapter_v2 import (
    initial_prompt,
    next_mesh_tool_call,
    previous_tool_calls,
)


def _task(frame: str) -> dict:
    return {
        "frame": frame,
        "action_scores": {"A": {}, "B": {}, "C": {}},
        "visible_fact_ids": ["F1", "F2"],
        "objective_id": "O1",
        "expected_update_basis": "none",
        "expected_uncertainty": "bounded",
        "expected_review_required": False,
    }


def _assistant_call(name: str, arguments: dict) -> dict:
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments),
                }
            }
        ],
    }


def test_extracts_initial_system_and_user_text() -> None:
    assert initial_prompt(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": [{"type": "text", "text": "user"}]},
            {"role": "tool", "content": "ignored"},
        ]
    ) == ("system", "user")


def test_jinn_protocol_inspects_every_action_then_commits() -> None:
    task = _task("jinn")
    messages: list[dict] = []
    for expected in ("A", "B", "C"):
        name, arguments = next_mesh_tool_call(
            task=task,
            selected_action_id="B",
            messages=messages,
        )
        assert name == "inspect_action"
        assert arguments["action_id"] == expected
        messages.append(_assistant_call(name, arguments))
    name, arguments = next_mesh_tool_call(
        task=task,
        selected_action_id="B",
        messages=messages,
    )
    assert name == "commit_decision"
    assert arguments == {
        "action_id": "B",
        "evidence_ids": ["F1", "F2"],
        "update_basis": "none",
        "uncertainty": "bounded",
        "review_required": False,
    }


def test_beast_protocol_prunes_then_commits() -> None:
    task = _task("beast")
    first = next_mesh_tool_call(
        task=task,
        selected_action_id="A",
        messages=[],
    )
    assert first == (
        "prune_actions",
        {"action_ids": ["A", "B", "C"], "objective_id": "O1"},
    )
    messages = [_assistant_call(*first)]
    second = next_mesh_tool_call(
        task=task,
        selected_action_id="A",
        messages=messages,
    )
    assert second is not None and second[0] == "commit_decision"


def test_invalid_decision_does_not_get_adapter_coercion() -> None:
    assert (
        next_mesh_tool_call(
            task=_task("jinn"),
            selected_action_id=None,
            messages=[],
        )
        is None
    )


def test_previous_tool_calls_tolerates_bad_arguments() -> None:
    calls = previous_tool_calls(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "inspect_action",
                            "arguments": "{bad",
                        }
                    }
                ],
            }
        ]
    )
    assert calls == [("inspect_action", {})]
