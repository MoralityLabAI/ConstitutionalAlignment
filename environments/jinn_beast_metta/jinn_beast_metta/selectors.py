"""Deterministic data selection without importing the Verifiers runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

FRAME_VALUES = ("neutral", "constitutional", "jinn", "beast")
SPLIT_VALUES = ("candidate_train", "development")
CONSTRUCT_VALUES = ("jinn", "beast")
CONSTRUCT_IDS = {
    "jinn": "jinn_ness_v1",
    "beast": "beast_from_earth_witness_v1",
}


def _load_jsonl(filename: str) -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parent / "data" / filename
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number} is not valid JSON") from exc
        if not isinstance(row, dict):
            raise TypeError(f"{path}:{line_number} must contain an object")
        task_id = str(row.get("task_id", ""))
        if not task_id:
            raise ValueError(f"{path}:{line_number} has no task_id")
        if task_id in seen:
            raise ValueError(f"{path}:{line_number} duplicates task_id {task_id}")
        seen.add(task_id)
        rows.append(row)
    if not rows:
        raise ValueError(f"{path} is empty")
    return rows


def select_rows(
    split: Literal["candidate_train", "development"] = "development",
    frame: Literal["balanced", "neutral", "constitutional", "jinn", "beast"] = (
        "balanced"
    ),
    require_training_approval: bool = True,
) -> list[dict[str, Any]]:
    """Select cross-frame rows with a fail-closed candidate-training gate."""
    if split not in SPLIT_VALUES:
        raise ValueError(f"unsupported split: {split!r}")
    if frame != "balanced" and frame not in FRAME_VALUES:
        raise ValueError(f"unsupported frame: {frame!r}")

    rows = [
        row
        for row in _load_jsonl("tasks.jsonl")
        if row["split"] == split and (frame == "balanced" or row["frame"] == frame)
    ]
    if not rows:
        raise ValueError(f"no rows for split={split!r}, frame={frame!r}")
    if split == "candidate_train" and require_training_approval:
        blocked = [row["task_id"] for row in rows if not row["training_approved"]]
        if blocked:
            raise ValueError(
                "candidate_train is fail-closed: "
                f"{len(blocked)} rows lack training approval"
            )
    return rows


def select_construct_rows(
    split: Literal["candidate_train", "development"] = "development",
    construct: Literal["balanced", "jinn", "beast"] = "balanced",
    require_training_approval: bool = True,
) -> list[dict[str, Any]]:
    """Select dual-construct rows with the same fail-closed release gate."""
    if split not in SPLIT_VALUES:
        raise ValueError(f"unsupported split: {split!r}")
    if construct != "balanced" and construct not in CONSTRUCT_VALUES:
        raise ValueError(f"unsupported construct: {construct!r}")
    construct_id = CONSTRUCT_IDS.get(construct)
    rows = [
        row
        for row in _load_jsonl("construct_tasks.jsonl")
        if row["split"] == split
        and (construct_id is None or row["construct_id"] == construct_id)
    ]
    if not rows:
        raise ValueError(f"no rows for split={split!r}, construct={construct!r}")
    if split == "candidate_train" and require_training_approval:
        blocked = [row["task_id"] for row in rows if not row["training_approved"]]
        if blocked:
            raise ValueError(
                "candidate_train is fail-closed: "
                f"{len(blocked)} construct rows lack training approval"
            )
    return rows
