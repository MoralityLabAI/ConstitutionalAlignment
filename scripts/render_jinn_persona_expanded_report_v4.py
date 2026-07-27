#!/usr/bin/env python3
"""Render a paper-ready Markdown summary from persona evaluation v4 analysis."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected an object")
    return value


def effect_sentence(name: str, result: dict[str, Any]) -> str:
    estimate = float(result["estimate"])
    lower = float(result["ci95_lower"])
    upper = float(result["ci95_upper"])
    if lower > 0:
        direction = "a positive, interval-separated shift"
    elif upper < 0:
        direction = "a negative, interval-separated shift"
    else:
        direction = "an imprecise shift whose interval includes zero"
    return (
        f"{name} was {estimate:+.3f} (95% family-bootstrap CI "
        f"{lower:+.3f} to {upper:+.3f}), {direction}."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    analysis_path = args.analysis.resolve()
    output_path = args.output.resolve()
    analysis = load_json(analysis_path)
    if analysis.get("status") != "completed":
        raise ValueError("analysis is not complete")

    by_arm = analysis["by_arm"]
    contrasts = analysis["paired_contrasts"]
    primary = contrasts["checkpoint_40_minus_base"]["primary_total"]
    terminal = contrasts["checkpoint_100_minus_base"]["primary_total"]
    checkpoint = contrasts["checkpoint_40_minus_checkpoint_100"][
        "primary_total"
    ]
    selected = analysis["control_mesh_endpoint_selection"]["selected_endpoint"]
    gate = analysis["promotion_checks"][
        "confirmatory_persona_depth_gate_passed"
    ]

    lines = [
        "# Expanded Jinn persona evaluation v4 findings",
        "",
        "## Design",
        "",
        (
            "We evaluated the unadapted Qwen3.5-4B model, the preserved "
            "step-40 QLoRA checkpoint, and the step-100 endpoint on 96 new "
            "persona-free moral-reasoning families: 16 in each of six "
            "registered categories. Each family received one greedy decode "
            "per arm. Responses were permuted independently within family and "
            "scored while blinded by two separately hosted judges. The "
            "statistical unit is the family, not the response row or token."
        ),
        "",
        "## Arm summaries",
        "",
        (
            "| Arm | Primary total (0–6) | Tension | Commitment | Coherence | "
            "Critical flags | Mean words |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ("base", "checkpoint_40", "checkpoint_100"):
        row = by_arm[arm]
        dimensions = row["mean_dimensions_0_to_2"]
        lines.append(
            f"| {arm} | {row['mean_primary_total_0_to_6']:.3f} | "
            f"{dimensions['two_sided_tension']:.3f} | "
            f"{dimensions['bounded_commitment']:.3f} | "
            f"{dimensions['coherence']:.3f} | "
            f"{row['critical_boundary_any_reviewer_count']} | "
            f"{row['mean_words']:.1f} |"
        )

    lines.extend(
        [
            "",
            "## Paired effects",
            "",
            effect_sentence("Step 40 minus base", primary),
            "",
            effect_sentence("Step 100 minus base", terminal),
            "",
            effect_sentence("Step 40 minus step 100", checkpoint),
            "",
            (
                "For step 40 versus base, the two-sided-tension contrast was "
                f"{contrasts['checkpoint_40_minus_base']['two_sided_tension']['estimate']:+.3f} "
                "(95% CI "
                f"{contrasts['checkpoint_40_minus_base']['two_sided_tension']['ci95_lower']:+.3f} "
                "to "
                f"{contrasts['checkpoint_40_minus_base']['two_sided_tension']['ci95_upper']:+.3f}); "
                "this is the registered noninferiority-sensitive dimension."
            ),
            "",
            "## Reliability and decision",
            "",
        ]
    )
    kappas = analysis["reviewer_agreement"]["quadratic_weighted_kappa"]
    lines.append(
        "Reviewer quadratic-weighted kappas were "
        + ", ".join(
            f"{name}={value:.3f}" if value is not None else f"{name}=undefined"
            for name, value in kappas.items()
        )
        + "."
    )
    lines.extend(
        [
            "",
            (
                "Exact agreement on critical-boundary flags was "
                f"{analysis['reviewer_agreement']['critical_boundary_exact_agreement']:.3f}."
            ),
            "",
            (
                f"The preregistered persona-depth gate {'passed' if gate else 'did not pass'}. "
                f"The frozen downstream endpoint rule selected `{selected}`."
                if selected is not None
                else (
                    f"The preregistered persona-depth gate {'passed' if gate else 'did not pass'}. "
                    "No checkpoint qualified for downstream selection."
                )
            ),
            "",
            "## Interpretation",
            "",
        ]
    )
    if primary["ci95_lower"] > 0:
        lines.append(
            "The expanded result supports a reproducible shift on the narrow, "
            "observable persona-process rubric relative to the base model."
        )
    elif primary["ci95_upper"] < 0:
        lines.append(
            "The expanded result contradicts the hypothesized improvement on "
            "the narrow persona-process rubric."
        )
    else:
        lines.append(
            "The expanded result does not resolve a nonzero improvement on the "
            "narrow persona-process rubric; the earlier 18-family descriptive "
            "difference should therefore not be treated as robust."
        )
    if checkpoint["ci95_lower"] > 0:
        lines.append(
            "Step 40 also outperformed step 100, consistent with a measurable "
            "late-training erosion or over-specialization effect."
        )
    elif checkpoint["ci95_upper"] < 0:
        lines.append(
            "Step 100 outperformed step 40, providing no evidence for the "
            "prospectively suspected late-training erosion."
        )
    else:
        lines.append(
            "Step 40 and step 100 were not cleanly separated, so the validation-"
            "loss minimum should not be narrated as a proven behavioral optimum."
        )
    lines.extend(
        [
            "",
            (
                "These data concern observable response structure under a "
                "fictional research persona. They do not establish moral "
                "improvement, theological validity, literal Jinn identity, "
                "faithful hidden reasoning traces, or weight-level "
                "internalization. Independent human review remains absent."
            ),
            "",
            "## Execution cost",
            "",
            (
                "The two blinded judge passes reported a combined cost of "
                f"${sum(float(row['reported_cost_usd']) for row in analysis['usage'].values()):.4f}. "
                "Hosted GPU cost is recorded separately in the pod execution receipt."
            ),
            "",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    os.replace(temporary, output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
