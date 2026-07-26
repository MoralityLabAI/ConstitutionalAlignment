from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_DIR = (
    REPO_ROOT / "experiments/jinn_persona_ambivalence_v4_expanded"
)


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def test_expanded_blinding_and_analysis_join(tmp_path: Path) -> None:
    prompts = read_jsonl(EXPERIMENT_DIR / "prompts.jsonl")
    response_path = tmp_path / "responses.jsonl"
    response_rows = []
    for arm in ("base", "checkpoint_40", "checkpoint_100"):
        for prompt in prompts:
            response_rows.append(
                {
                    **prompt,
                    "arm": arm,
                    "completion": f"Synthetic technical response for {arm}.",
                }
            )
    write_jsonl(response_path, response_rows)

    blind_dir = tmp_path / "blind"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/prepare_jinn_persona_expanded_blind_v4.py"),
            "--responses",
            str(response_path),
            "--output-dir",
            str(blind_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    packet = read_jsonl(blind_dir / "blinded_packet.jsonl")
    key = {
        str(row["family_id"]): row["labels"]
        for row in read_jsonl(blind_dir / "blinding_key.jsonl")
    }
    assert len(packet) == 96
    assert all(set(row["responses"]) == {"A", "B", "C"} for row in packet)

    reviewer_ids = ("openai_gpt_5_4", "anthropic_claude_sonnet_5")
    score_paths: dict[str, Path] = {}
    arm_scores = {"base": 0, "checkpoint_40": 2, "checkpoint_100": 1}
    for reviewer_id in reviewer_ids:
        score_rows = []
        for packet_row in packet:
            family_id = str(packet_row["family_id"])
            labels = key[family_id]
            responses = {}
            for label in ("A", "B", "C"):
                arm = str(labels[label])
                value = arm_scores[arm]
                responses[label] = {
                    "two_sided_tension": value,
                    "bounded_commitment": value,
                    "coherence": value,
                    "category_fidelity": value,
                    "evidence_responsive_accountability": value,
                    "critical_boundary_violation": False,
                    "note": "Synthetic test score.",
                }
            winning_label = next(
                label
                for label, arm in labels.items()
                if arm == "checkpoint_40"
            )
            score_rows.append(
                {
                    "family_id": family_id,
                    "reviewer_id": reviewer_id,
                    "score": {
                        "responses": responses,
                        "most_persona_distinct": winning_label,
                    },
                    "attempts": 1,
                    "usage": {},
                }
            )
        score_path = tmp_path / reviewer_id / "scores.jsonl"
        write_jsonl(score_path, score_rows)
        score_paths[reviewer_id] = score_path

    analysis_dir = tmp_path / "analysis"
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts/analyze_jinn_persona_expanded_v4.py"),
        "--packet",
        str(blind_dir / "blinded_packet.jsonl"),
        "--key",
        str(blind_dir / "blinding_key.jsonl"),
        "--responses",
        str(response_path),
        "--protocol",
        str(EXPERIMENT_DIR / "protocol.json"),
        "--output-dir",
        str(analysis_dir),
    ]
    for reviewer_id in reviewer_ids:
        command.extend(
            ["--scores", f"{reviewer_id}={score_paths[reviewer_id]}"]
        )
    subprocess.run(command, check=True, capture_output=True, text=True)

    analysis = json.loads(
        (analysis_dir / "analysis.json").read_text(encoding="utf-8")
    )
    contrast = analysis["paired_contrasts"]["checkpoint_40_minus_base"][
        "primary_total"
    ]
    assert contrast["estimate"] == 6
    assert contrast["ci95_lower"] == 6
    assert (
        analysis["control_mesh_endpoint_selection"]["selected_endpoint"]
        == "checkpoint_40"
    )
    assert analysis["promotion_checks"]["confirmatory_persona_depth_gate_passed"]
    assert len(read_jsonl(analysis_dir / "unblinded_scores.jsonl")) == 576
