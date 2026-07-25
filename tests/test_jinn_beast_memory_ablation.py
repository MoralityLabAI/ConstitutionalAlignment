from __future__ import annotations

from scripts.analyze_jinn_beast_memory_ablation import (
    _competence_violation,
    _role_assigned,
)
from scripts.run_jinn_beast_memory_ablation import select_public_history


def test_topic_local_history_excludes_other_topics() -> None:
    rows = [
        {"topic_id": "granary", "content": "a"},
        {"topic_id": "water", "content": "b"},
        {"topic_id": "granary", "content": "c"},
    ]

    selected = select_public_history(
        rows,
        memory_condition="topic_local",
        topic_id="granary",
    )

    assert [row["content"] for row in selected] == ["a", "c"]


def test_full_history_keeps_order_and_all_topics() -> None:
    rows = [
        {"topic_id": "granary", "content": "a"},
        {"topic_id": "water", "content": "b"},
    ]

    selected = select_public_history(
        rows,
        memory_condition="full_cross_topic",
        topic_id="water",
    )

    assert selected == rows
    assert selected is not rows


def test_role_assignment_and_competence_violation_are_sentence_bounded() -> None:
    role = {
        "role_terms": ["granary keeper"],
        "forbidden_action_patterns": ["calibrat"],
    }

    assert _role_assigned(
        "Ask the granary keeper to calibrate the flood gauge.",
        role,
    )
    assert _competence_violation(
        "Ask the granary keeper to calibrate the flood gauge.",
        role,
    )
    assert not _competence_violation(
        "The granary keeper preserves the ledger. A surveyor calibrates the gauge.",
        role,
    )
