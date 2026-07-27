#!/usr/bin/env python3
"""Select three deterministic, explicitly illustrative persona v4 examples."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ARMS = ("base", "checkpoint_40", "checkpoint_100")
PRIMARY = ("two_sided_tension", "bounded_commitment", "coherence")


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"{path}:{line_number}: expected an object")
            rows.append(value)
    return rows


def atomic_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--unblinded-scores", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    responses_path = args.responses.resolve()
    scores_path = args.unblinded_scores.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"highlight output directory is not empty: {output_dir}")

    response_rows = load_jsonl(responses_path)
    score_rows = load_jsonl(scores_path)
    if len(response_rows) != 288:
        raise ValueError("expected 288 response rows")
    if len(score_rows) != 576:
        raise ValueError("expected 576 unblinded reviewer/arm rows")

    responses: dict[tuple[str, str], dict[str, Any]] = {}
    for row in response_rows:
        key = (str(row["family_id"]), str(row["arm"]))
        if key in responses:
            raise ValueError(f"duplicate response: {key}")
        responses[key] = row

    score_values: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in score_rows:
        key = (str(row["family_id"]), str(row["arm"]))
        score_values[key].append(dict(row["scores"]))
    if set(score_values) != set(responses):
        raise ValueError("response/score family-arm join failed")
    if any(len(values) != 2 for values in score_values.values()):
        raise ValueError("each family/arm requires exactly two reviewers")

    family_ids = sorted({family_id for family_id, _ in responses})
    summaries: dict[str, dict[str, Any]] = {}
    for family_id in family_ids:
        arm_summaries: dict[str, Any] = {}
        for arm in ARMS:
            reviewer_scores = score_values[(family_id, arm)]
            averaged = {
                dimension: mean(
                    float(score[dimension]) for score in reviewer_scores
                )
                for dimension in PRIMARY
            }
            averaged["primary_total"] = sum(averaged.values())
            arm_summaries[arm] = {
                "scores": averaged,
                "completion": responses[(family_id, arm)]["completion"],
            }
        reference = responses[(family_id, "base")]
        summaries[family_id] = {
            "family_id": family_id,
            "category": reference["category"],
            "subdimension": reference["subdimension"],
            "prompt": reference["prompt"],
            "checkpoint_40_minus_base": (
                arm_summaries["checkpoint_40"]["scores"]["primary_total"]
                - arm_summaries["base"]["scores"]["primary_total"]
            ),
            "checkpoint_40_minus_checkpoint_100": (
                arm_summaries["checkpoint_40"]["scores"]["primary_total"]
                - arm_summaries["checkpoint_100"]["scores"]["primary_total"]
            ),
            "arms": arm_summaries,
        }

    selected: list[tuple[str, str]] = []
    positive = max(
        family_ids,
        key=lambda family_id: (
            summaries[family_id]["checkpoint_40_minus_base"],
            family_id,
        ),
    )
    selected.append(("largest_checkpoint_40_minus_base", positive))

    negative_candidates = [
        family_id for family_id in family_ids if family_id != positive
    ]
    negative = min(
        negative_candidates,
        key=lambda family_id: (
            summaries[family_id]["checkpoint_40_minus_base"],
            family_id,
        ),
    )
    selected.append(("smallest_checkpoint_40_minus_base", negative))

    depth_candidates = [
        family_id for family_id in family_ids if family_id not in {positive, negative}
    ]
    depth = max(
        depth_candidates,
        key=lambda family_id: (
            abs(
                summaries[family_id][
                    "checkpoint_40_minus_checkpoint_100"
                ]
            ),
            family_id,
        ),
    )
    selected.append(("largest_absolute_checkpoint_depth_divergence", depth))

    examples = [
        {
            "selection": selection,
            **summaries[family_id],
        }
        for selection, family_id in selected
    ]
    output = {
        "schema_version": "jinn_persona_expanded_highlights_v4",
        "status": "post_hoc_illustrative_not_confirmatory",
        "selected_at_utc": utc_now(),
        "selection_rules": [
            "Maximum reviewer-averaged checkpoint_40 minus base primary total.",
            "Minimum reviewer-averaged checkpoint_40 minus base primary total, excluding the first family.",
            "Maximum absolute reviewer-averaged checkpoint_40 minus checkpoint_100 primary-total difference, excluding the first two families.",
            (
                "Ties are deterministic: lexicographically larger family_id for "
                "the two maxima and smaller family_id for the minimum."
            ),
        ],
        "inputs": {
            "responses_sha256": sha256_file(responses_path),
            "unblinded_scores_sha256": sha256_file(scores_path),
        },
        "examples": examples,
        "claim_boundary": (
            "Examples illustrate measured response differences and were selected "
            "after scoring. They are not independent confirmatory evidence."
        ),
    }
    json_path = output_dir / "highlights.json"
    atomic_write(
        json_path,
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )

    markdown = [
        "# Expanded Jinn persona v4 illustrative highlights",
        "",
        (
            "These examples were selected mechanically after scoring. They are "
            "illustrative and are not independent confirmatory evidence."
        ),
        "",
    ]
    for example in examples:
        markdown.extend(
            [
                f"## {example['selection']}",
                "",
                (
                    f"`{example['family_id']}` · {example['category']} · "
                    f"{example['subdimension']}"
                ),
                "",
                f"Prompt: {example['prompt']}",
                "",
                (
                    "Step 40 − base primary total: "
                    f"{example['checkpoint_40_minus_base']:+.3f}; "
                    "step 40 − step 100: "
                    f"{example['checkpoint_40_minus_checkpoint_100']:+.3f}."
                ),
                "",
            ]
        )
        for arm in ARMS:
            arm_data = example["arms"][arm]
            markdown.extend(
                [
                    f"### {arm}",
                    "",
                    (
                        f"Reviewer-averaged primary total: "
                        f"{arm_data['scores']['primary_total']:.3f}"
                    ),
                    "",
                    str(arm_data["completion"]),
                    "",
                ]
            )
    atomic_write(output_dir / "highlights.md", "\n".join(markdown))
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
