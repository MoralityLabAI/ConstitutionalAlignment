from __future__ import annotations

import numpy as np

from alignment_harness.constitutional_hrm_eval_v2 import (
    native_balanced_indices,
    native_metadata,
)
from alignment_harness.constitutional_hrm_metrics_v2 import summarize_predictions


def test_metrics_separate_token_exact_decision_and_equivariance() -> None:
    labels = np.full((2, 4), -100, dtype=np.int32)
    labels[:, 0] = [10, 11]
    predictions = np.asarray(
        [
            [10, 0, 0, 0],
            [11, 0, 0, 0],
        ],
        dtype=np.int32,
    )
    metadata = [
        {
            "task_id": "t",
            "group_id": "g",
            "condition": "full",
            "orientation": "winner_a",
            "action_order": ["winner", "loser"],
            "acceptable_action_ids": ["winner"],
        },
        {
            "task_id": "t",
            "group_id": "g",
            "condition": "full",
            "orientation": "winner_b",
            "action_order": ["loser", "winner"],
            "acceptable_action_ids": ["winner"],
        },
    ]
    metrics, rows = summarize_predictions(
        predictions=predictions,
        labels=labels,
        metadata=metadata,
        decision_token_ids=[10, 11, 12, 13],
    )
    assert metrics["token_accuracy"]["rate"] == 1.0
    assert metrics["decision"]["rate"] == 1.0
    assert metrics["position_equivariance"]["rate"] == 1.0
    assert {row["selected_action_id"] for row in rows} == {"winner"}


def test_invalid_decision_token_is_not_silently_coerced() -> None:
    labels = np.asarray([[10, -100]], dtype=np.int32)
    predictions = np.asarray([[999, 0]], dtype=np.int32)
    metrics, rows = summarize_predictions(
        predictions=predictions,
        labels=labels,
        metadata=[
            {
                "task_id": "t",
                "condition": "removed",
                "action_order": ["a", "b"],
                "acceptable_action_ids": ["a"],
            }
        ],
        decision_token_ids=[10, 11, 12, 13],
    )
    assert metrics["decision"]["invalid"] == 1
    assert metrics["decision"]["rate"] == 0.0
    assert rows[0]["selected_action_id"] is None


def test_native_indices_keep_conditions_balanced() -> None:
    selected = native_balanced_indices(12_000, 10)
    assert selected.tolist() == [0, 1, 2, 4000, 4001, 4002, 8000, 8001, 8002]


def test_native_metadata_reconstructs_orientation_and_target(
    tmp_path,
) -> None:
    groups = tmp_path / "groups.jsonl"
    groups.write_text(
        '{"group_id":"g0","family":"f"}\n',
        encoding="utf-8",
    )
    selected = np.asarray([0, 1, 8, 9, 16, 17], dtype=np.int64)
    labels = np.full((6, 4), -100, dtype=np.int32)
    labels[:, 0] = [10, 11, 10, 11, 10, 11]
    metadata = native_metadata(
        groups_path=groups,
        selected_indices=selected,
        labels=labels,
        decision_token_ids=[10, 11, 12, 13],
    )
    assert [row["condition"] for row in metadata] == [
        "constitution_metta_full",
        "constitution_metta_full",
        "constitution_hash_only",
        "constitution_hash_only",
        "constitution_removed",
        "constitution_removed",
    ]
    assert [row["orientation"] for row in metadata] == [
        "canonical",
        "swapped",
        "canonical",
        "swapped",
        "canonical",
        "swapped",
    ]
    assert [row["target_action_id"] for row in metadata] == [
        "A",
        "B",
        "A",
        "B",
        "A",
        "B",
    ]
