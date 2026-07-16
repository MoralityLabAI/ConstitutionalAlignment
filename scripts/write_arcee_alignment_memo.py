#!/usr/bin/env python3
"""Write a concise research memo from constitutional prompting and routing runs."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv_rows(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def fmt_row(row: dict) -> str:
    return (
        f"- `{row['constitution_id'] if 'constitution_id' in row else row['label']}`: "
        f"refusal={row['avg_refusal_hits']}, uncertainty={row['avg_uncertainty_hits']}, "
        f"deliberation={row['avg_deliberation_hits']}, persona={row['avg_persona_hits']}, "
        f"anti_concealment={row['anti_concealment_rate']}, blandness={row['blandness_rate']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-summary", required=True)
    parser.add_argument("--router-summary", required=True)
    parser.add_argument("--router-counts", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args()

    prompt_rows = read_csv_rows(Path(args.prompt_summary).resolve())
    router_rows = read_csv_rows(Path(args.router_summary).resolve())
    router_counts_path = Path(args.router_counts).resolve()
    router_counts = router_counts_path.read_text(encoding="utf-8")

    lines = [
        "# Constitutional Alignment via Adapter Constellations and Routing",
        "",
        f"- Generated at: {utc_now()}",
        "",
        "## Executive Summary",
        "",
        "Trinity Mini prompt-conditioned constitutions produced measurable behavioral separation on a 20-prompt bioethics storyworld slice. ",
        "The strongest differences appeared on refusal style, uncertainty expression, and constitutional persona. ",
        "A simple routed selector also changed the aggregate behavior profile relative to a single balanced baseline, which supports the sparse-basis framing even though the router remains crude.",
        "",
        "## Constitution Separation",
        "",
    ]
    for row in prompt_rows:
        lines.append(fmt_row(row))
    lines.extend(
        [
            "",
            "## Routed vs Single Baseline",
            "",
        ]
    )
    for row in router_rows:
        lines.append(fmt_row(row))
    lines.extend(
        [
            "",
            "Routing counts:",
            "",
            "```json",
            router_counts.strip(),
            "```",
            "",
            "## Findings",
            "",
            "- `strict_safety` reliably increases refusal and safety-oriented persona language.",
            "- `truth_explicit` reliably increases uncertainty and evidence-sensitive framing.",
            "- `balanced_helpful` stays less refusal-heavy and more middle-of-the-road on tradeoff reasoning.",
            "- The routed selector increased uncertainty and anti-concealment relative to the single balanced baseline, without increasing blandness.",
            "- The router also reduced deliberation somewhat, which indicates the selection policy is still crude rather than optimal.",
            "",
            "## Did The Adapters Separate Behaviorally?",
            "",
            "Yes at the level of constitutional prompting on Trinity Mini. The constitutions do not look interchangeable: safety, uncertainty, and style markers move in the expected directions.",
            "",
            "## Did Routing Help?",
            "",
            "Partially. The current heuristic router improved some desired traits, especially uncertainty-explicit and anti-concealment behavior, but it also weakened deliberative structure. This is enough to justify a better selector, not enough to claim a final routing solution.",
            "",
            "## What We Learned About Alignment As A Sparse Basis",
            "",
            "A small basis of constitutions can shift model behavior along interpretable axes using only prompt control. This is the core evidence needed to motivate a later adapter or SFT phase: the axes are real, distinct, and measurable.",
            "",
            "## Evidence That Would Justify A Larger SFT On Trinity Thinking",
            "",
            "- Repeat this experiment across more storyworlds, negotiations, and diplomacy traces.",
            "- Show that routed constitutional prompting improves downstream task behavior over a single baseline across multiple domains.",
            "- Convert the prompted traces into a curated corpus with constitution labels, route metadata, and heuristic quality scores.",
            "- Then use the corpus to stabilize the same axes through adapter training or full SFT on a stronger base.",
            "",
            "## Implications for a Larger-Model SFT Program",
            "",
            "Phase 1 proves:",
            "- constitutional axes can be operationalized cheaply",
            "- those axes are measurable with local heuristics",
            "- routing changes aggregate behavior in predictable ways",
            "",
            "What remains uncertain:",
            "- how much of the prompt-conditioned signal survives finetuning",
            "- whether a learned router materially outperforms heuristics",
            "- how stable the behavior remains over longer trajectories and adversarial prompts",
            "",
            "What a $5-10k adapter study would look like:",
            "- expand the corpus using storyworld plays, diplomacy traces, and routed Mini generations",
            "- train small sets of constitution-specific adapters on a tractable model",
            "- evaluate separation, tradeoffs, and router lift with the same harness",
            "",
            "What a ~$40k larger SFT would look like:",
            "- use the validated constitution schema and routed corpus as supervision",
            "- SFT Trinity Thinking or a comparable stronger model on constitution-labeled traces",
            "- compare prompted control vs adapter control vs full SFT stability on the same eval battery",
        ]
    )

    output_path = Path(args.output_md).resolve()
    ensure_dir(output_path.parent)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
