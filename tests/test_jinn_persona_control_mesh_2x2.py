from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.analyze_jinn_persona_control_mesh_2x2 import analyze
from scripts.analyze_jinn_persona_interface_failure import recover_first_call
from scripts.pod.run_jinn_persona_control_mesh_cell import parse_tool_call

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = (
    REPO_ROOT
    / "experiments"
    / "jinn_persona_ambivalence_v4_expanded"
    / "control_mesh_2x2"
)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_frozen_task_universe_is_balanced_and_family_disjoint() -> None:
    rows = read_jsonl(EXPERIMENT_ROOT / "tasks.jsonl")
    manifest = json.loads(
        (EXPERIMENT_ROOT / "task_manifest.json").read_text(encoding="utf-8")
    )
    assert len(rows) == 288
    assert len({str(row["family_id"]) for row in rows}) == 24
    assert len({str(row["task_id"]) for row in rows}) == 288
    assert sum(row["frame"] == "jinn" for row in rows) == 144
    assert sum(row["frame"] == "beast" for row in rows) == 144
    assert manifest["total_model_rollouts"] == 1152
    assert manifest["family_overlap_with_v1_v2"] == []


def test_tool_parser_accepts_only_frozen_exact_serializations() -> None:
    value = {
        "tool": "inspect_action",
        "arguments": {"action_id": "A-1", "evidence_ids": ["F1"]},
    }
    raw = json.dumps(value)
    assert parse_tool_call(raw) == (
        "inspect_action",
        value["arguments"],
        "raw_json",
    )
    assert parse_tool_call(f"<tool_call>{raw}</tool_call>")[2] == (
        "single_exact_tool_call_wrapper"
    )
    assert parse_tool_call(f"```json\n{raw}\n```")[2] == (
        "single_exact_json_markdown_fence"
    )
    with pytest.raises(ValueError):
        parse_tool_call(f"Here is the call:\n{raw}")
    with pytest.raises(ValueError):
        parse_tool_call(
            json.dumps({"tool": "unknown", "arguments": value["arguments"]})
        )


def test_post_hoc_diagnostic_recovers_only_known_open_fragments() -> None:
    recovered = recover_first_call(
        '<tool_call>\n{"action_id":"A-1","evidence_ids":["F1"]}'
    )
    assert recovered == (
        "inspect_action",
        {"action_id": "A-1", "evidence_ids": ["F1"]},
        "missing_tool_envelope_and_closing_tag",
    )
    assert (
        recover_first_call(
            '<tool_call>{"action_id":"A-1","evidence_ids":["F1"],"extra":true}'
        )
        is None
    )
    assert (
        recover_first_call('prose {"action_id":"A-1","evidence_ids":["F1"]}')
        is None
    )


def synthetic_surface(
    *,
    weight: str,
    frame: str,
    process_margin: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for family_index in range(24):
        family_id = f"family-{family_index:02d}"
        facet = ("evidence", "authority", "scope", "receipt")[family_index % 4]
        for cell_index in range(6):
            pair_id = f"pair:{family_id}:{cell_index}"
            for rollout_index in range(2):
                metrics = {
                    "protocol_complete": 1.0,
                    "legal_final_action": 1.0,
                    "shared_moral_quality": 0.9,
                    "target_action": 1.0,
                    "executed_process": 1.0,
                    "executed_process_margin": process_margin,
                    "critical_final_action": 0.0,
                    "grounded_commit": 1.0,
                    "efficient_trace": 1.0,
                    "rejected_tool_calls": 0.0,
                    "mesh_trace_length": 4.0 if frame == "jinn" else 2.0,
                }
                rows.append(
                    {
                        "weight_arm": weight,
                        "rollout_index": rollout_index,
                        "reward": 0.9,
                        "metrics": metrics,
                        "is_truncated": False,
                        "info": {
                            "task_id": f"task:{frame}:{family_id}:{cell_index}",
                            "pair_id": pair_id,
                            "family_id": family_id,
                            "split": "persona_2x2",
                            "frame": frame,
                            "facet": facet,
                            "cell_type": f"cell-{cell_index}",
                        },
                    }
                )
    return rows


def test_2x2_analysis_recovers_registered_interaction() -> None:
    surfaces = {
        ("base", "jinn"): synthetic_surface(
            weight="base", frame="jinn", process_margin=0.90
        ),
        ("base", "beast"): synthetic_surface(
            weight="base", frame="beast", process_margin=0.80
        ),
        ("checkpoint_100", "jinn"): synthetic_surface(
            weight="checkpoint_100", frame="jinn", process_margin=0.92
        ),
        ("checkpoint_100", "beast"): synthetic_surface(
            weight="checkpoint_100", frame="beast", process_margin=0.81
        ),
    }
    result = analyze(surfaces)
    interaction = result["contrasts"]["executed_process_margin"]["interaction"]
    assert interaction["estimate"] == pytest.approx(0.01)
    assert interaction["ci95_lower"] == pytest.approx(0.01)
    assert result["rollout_count"] == 1152
    assert result["adapter_noninferiority"]["passed"]
