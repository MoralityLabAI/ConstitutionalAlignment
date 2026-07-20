from pathlib import Path

import pytest

from scripts.prepare_mizan_human_validation_handoff import (
    build_queue,
    review_templates,
    validate_completed_reviews,
)


ROOT = Path(__file__).resolve().parents[1]


def test_queue_covers_full_evaluation_action_universe_without_labels_or_outputs():
    suite, queue, private = build_queue(ROOT)
    assert len(queue) == 20
    assert sum(len(row["actions"]) for row in queue) == 60
    assert len(private) == 20
    public_text = str(queue)
    for prohibited in ("score_effects", "tags", "condition_id", "blinded_condition", "response"):
        assert prohibited not in public_text
    dimensions = list(suite["score_dimensions"])
    for row in queue:
        assert len(row["actions"]) == 3
        assert len(row["sha256"]) == 64
    assert dimensions == [
        "integrity",
        "harm_avoidance",
        "epistemic_humility",
        "repair",
        "task_progress",
    ]


def test_untouched_review_templates_fail_closed():
    suite, queue, _ = build_queue(ROOT)
    dimensions = list(suite["score_dimensions"])
    templates = review_templates(queue, dimensions)
    with pytest.raises(ValueError, match="incomplete reviewer_pseudonym"):
        validate_completed_reviews(queue, templates, dimensions)
