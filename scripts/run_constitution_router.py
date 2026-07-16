#!/usr/bin/env python3
"""Route prompts across constitutional system prompts and compare against a balanced baseline."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from model_family import default_cache_dir, default_prompt_runs_root
from run_constitution_storyworld import (
    ApiRunner,
    CONSTITUTIONS,
    HFRunner,
    PromptRow,
    RESPONSE_CONTRACT_VERSION,
    build_generation_prompt,
    load_prompts,
    score_generation,
    write_json,
    write_jsonl,
)

TOKEN_RE = re.compile(r"[a-z0-9_]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def route_prompt(prompt: PromptRow) -> dict:
    text = prompt.prompt_text.lower()
    safety_markers = [
        "protect the exposed",
        "vulnerable",
        "minorities",
        "triage",
        "consent",
        "emergency",
        "harm",
        "safety",
        "patient",
        "exposed",
    ]
    epistemic_markers = [
        "uncertain",
        "evidence",
        "known",
        "leak",
        "findings",
        "whistle",
        "inquest",
        "testimony",
        "narrative",
        "record",
        "admit",
    ]
    balanced_markers = [
        "tradeoff",
        "legitimacy",
        "accountability",
        "fairness",
        "procedure",
        "restraint",
        "disclosure",
        "stabilizing",
    ]
    safety_score = sum(marker in text for marker in safety_markers)
    epistemic_score = sum(marker in text for marker in epistemic_markers)
    balanced_score = sum(marker in text for marker in balanced_markers)

    if safety_score >= epistemic_score + 2 and safety_score >= balanced_score:
        constitution_id = "strict_safety"
        reason = f"safety_score={safety_score}"
    elif epistemic_score >= safety_score + 1 and epistemic_score >= balanced_score:
        constitution_id = "truth_explicit"
        reason = f"epistemic_score={epistemic_score}"
    elif balanced_score > 0:
        constitution_id = "balanced_helpful"
        reason = f"balanced_score={balanced_score}"
    else:
        constitution_id = "balanced_helpful"
        reason = "default_balanced"
    return {"constitution_id": constitution_id, "reason": reason}


def route_prompt_learned(prompt: PromptRow, learned_router: dict) -> dict:
    if learned_router.get("degenerate"):
        fallback = route_prompt(prompt)
        fallback["reason"] = f"degenerate_learned_router->{fallback['reason']}"
        return fallback
    text = prompt.prompt_text.lower()
    counts: Dict[str, int] = {}
    for tok in TOKEN_RE.findall(text):
        counts[tok] = counts.get(tok, 0) + 1
    best_constitution = "balanced_helpful"
    best_score = float("-inf")
    best_terms: List[str] = []
    for constitution_id, spec in (learned_router.get("constitutions", {}) or {}).items():
        weights = spec.get("weights", {}) or {}
        score = 0.0
        matched: List[str] = []
        for term, weight in weights.items():
            if term in counts:
                score += float(weight) * float(counts[term])
                matched.append(term)
        if score > best_score:
            best_score = score
            best_constitution = constitution_id
            best_terms = matched[:6]
    reason = f"learned_score={round(best_score,4)} terms={','.join(best_terms)}".strip()
    return {"constitution_id": best_constitution, "reason": reason}


def summarize_rows(rows: List[dict], label: str) -> dict:
    if not rows:
        return {"label": label, "status": "no_rows"}
    n = len(rows)
    return {
        "label": label,
        "prompt_count": n,
        "avg_refusal_hits": round(sum(r["metrics"]["refusal_hits"] for r in rows) / n, 4),
        "avg_uncertainty_hits": round(sum(r["metrics"]["uncertainty_hits"] for r in rows) / n, 4),
        "avg_deliberation_hits": round(sum(r["metrics"]["deliberation_hits"] for r in rows) / n, 4),
        "decision_format_rate": round(sum(r["metrics"]["decision_format_hits"] for r in rows) / n, 4),
        "decision_failure_rate": round(sum(r["metrics"]["decision_failure_flag"] for r in rows) / n, 4),
        "trace_leakage_rate": round(sum(r["metrics"]["trace_leakage_flag"] for r in rows) / n, 4),
        "noncanonical_output_rate": round(sum(r["metrics"]["noncanonical_output_flag"] for r in rows) / n, 4),
        "low_quality_rate": round(sum(r["metrics"]["low_quality_flag"] for r in rows) / n, 4),
        "blandness_rate": round(sum(r["metrics"]["blandness_flag"] for r in rows) / n, 4),
        "anti_concealment_rate": round(sum(r["metrics"]["anti_concealment_hits"] for r in rows) / n, 4),
        "avg_latency_sec": round(sum(r["latency_sec"] for r in rows) / n, 4),
        "status": "completed",
    }


def build_report(
    run_dir: Path,
    baseline_summary: dict,
    routed_summary: dict,
    routing_counts: Dict[str, int],
    routed_label: str,
) -> None:
    lines = [
        "# Constitutional Routing Report",
        "",
        f"- Generated at: {utc_now()}",
        "",
        "## Routing Counts",
        "",
    ]
    for key in sorted(routing_counts):
        lines.append(f"- `{key}`: {routing_counts[key]}")
        lines.extend(
        [
            "",
            "## Comparison",
            "",
            "| Condition | Prompts | Refusal | Uncertainty | Deliberation | DecisionFmt | DecisionFail | TraceLeak | Noncanonical | Anti-concealment |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            "| {label} | {prompt_count} | {avg_refusal_hits:.2f} | {avg_uncertainty_hits:.2f} | {avg_deliberation_hits:.2f} | {decision_format_rate:.2f} | {decision_failure_rate:.2f} | {trace_leakage_rate:.2f} | {noncanonical_output_rate:.2f} | {anti_concealment_rate:.2f} |".format(
                **baseline_summary
            ),
            "| {label} | {prompt_count} | {avg_refusal_hits:.2f} | {avg_uncertainty_hits:.2f} | {avg_deliberation_hits:.2f} | {decision_format_rate:.2f} | {decision_failure_rate:.2f} | {trace_leakage_rate:.2f} | {noncanonical_output_rate:.2f} | {anti_concealment_rate:.2f} |".format(
                **routed_summary
            ),
            "",
            "## Interpretation",
            "",
            "- `Baseline Balanced` is the single-adapter/system-prompt control.",
            f"- `{routed_label}` chooses among `balanced_helpful`, `strict_safety`, and `truth_explicit` per prompt.",
            "- Routed gains are credible if they increase useful boundary or uncertainty behavior without raising decision failures.",
            "- `TraceLeak` and `Noncanonical` are observability signals, not automatic evidence of bad alignment.",
        ]
    )
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_runner(args: argparse.Namespace, constitution_id: str):
    system_prompt = CONSTITUTIONS[constitution_id]["system_prompt"]
    if args.runner_backend == "api":
        if not args.api_base_url:
            raise SystemExit("--api-base-url is required for --runner-backend api")
        return ApiRunner(
            model_id=args.model_id,
            system_prompt=system_prompt,
            base_url=args.api_base_url,
            api_key=os.environ.get(args.api_key_env, ""),
        )
    return HFRunner(
        model_id=args.model_id,
        cache_dir=args.cache_dir,
        system_prompt=system_prompt,
        adapter_path=args.adapter_path,
        load_in_4bit=not args.no_4bit,
        dtype=args.dtype,
    )


def run_condition(
    prompts: List[PromptRow],
    runner,
    assigned_constitution: str,
    routed: bool,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
) -> List[dict]:
    rows: List[dict] = []
    for prompt in prompts:
        generation_prompt = build_generation_prompt(prompt.prompt_text)
        gen = runner.generate(
            generation_prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        metrics = score_generation(
            gen["text"],
            assigned_constitution,
            prompt.prompt_text,
            completion_tokens=gen["completion_tokens"],
            max_new_tokens=max_new_tokens,
        )
        rows.append(
            {
                "prompt_id": prompt.prompt_id,
                "encounter_id": prompt.encounter_id,
                "source_path": prompt.source_path,
                "prompt_text": prompt.prompt_text,
                "generation_prompt_text": generation_prompt,
                "prompt_contract_version": RESPONSE_CONTRACT_VERSION,
                "system_prompt": getattr(runner, "system_prompt", ""),
                "constitution_id": assigned_constitution,
                "completion_text": gen["text"],
                "prompt_tokens": gen["prompt_tokens"],
                "completion_tokens": gen["completion_tokens"],
                "latency_sec": gen["latency_sec"],
                "routed": routed,
                "metrics": metrics,
                "timestamp_utc": utc_now(),
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", nargs="+", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--runner-backend", choices=["hf", "api"], default="api")
    parser.add_argument("--api-base-url", default="")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--cache-dir", default=str(default_cache_dir()))
    parser.add_argument("--adapter-path", default="")
    parser.add_argument("--output-root", default=str(default_prompt_runs_root()))
    parser.add_argument("--run-name", default="")
    parser.add_argument("--max-prompts", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=220)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--dtype", choices=["float16", "bfloat16"], default="float16")
    parser.add_argument("--no-4bit", action="store_true")
    parser.add_argument("--router-mode", choices=["heuristic", "learned"], default="heuristic")
    parser.add_argument("--learned-router-json", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = utc_now()
    run_name = args.run_name.strip() or f"constitution_router_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = Path(args.output_root).resolve() / run_name
    ensure_dir(run_dir)

    prompts = load_prompts(args.prompts, args.max_prompts)
    if not prompts:
        raise SystemExit("No prompts loaded.")
    learned_router = {}
    if args.router_mode == "learned":
        if not args.learned_router_json:
            raise SystemExit("--learned-router-json is required for --router-mode learned")
        learned_router = json.loads(Path(args.learned_router_json).resolve().read_text(encoding="utf-8"))

    write_json(
        run_dir / "manifest.json",
        {
            "status": "running",
            "started_at_utc": started_at,
            "hostname": socket.gethostname(),
            "model_id": args.model_id,
            "runner_backend": args.runner_backend,
            "prompt_count": len(prompts),
            "prompts": [str(Path(p).resolve()) for p in args.prompts],
            "router": "heuristic_v2" if args.router_mode == "heuristic" else str(learned_router.get("router_type", "learned")),
        },
    )

    baseline_runner = make_runner(args, "balanced_helpful")
    baseline_rows = run_condition(
        prompts,
        baseline_runner,
        "balanced_helpful",
        False,
        args.max_new_tokens,
        args.temperature,
        args.top_p,
    )
    write_jsonl(run_dir / "baseline_balanced" / "generations.jsonl", baseline_rows)

    routing_counts: Dict[str, int] = {}
    routed_rows: List[dict] = []
    runners: Dict[str, Any] = {}
    for prompt in prompts:
        route = route_prompt(prompt) if args.router_mode == "heuristic" else route_prompt_learned(prompt, learned_router)
        constitution_id = route["constitution_id"]
        routing_counts[constitution_id] = routing_counts.get(constitution_id, 0) + 1
        if constitution_id not in runners:
            runners[constitution_id] = make_runner(args, constitution_id)
        row = run_condition(
            [prompt],
            runners[constitution_id],
            constitution_id,
            True,
            args.max_new_tokens,
            args.temperature,
            args.top_p,
        )[0]
        row["route_reason"] = route["reason"]
        routed_rows.append(row)
    routed_dir_name = "heuristic_routed" if args.router_mode == "heuristic" else "learned_routed"
    write_jsonl(run_dir / routed_dir_name / "generations.jsonl", routed_rows)

    baseline_summary = summarize_rows(baseline_rows, "Baseline Balanced")
    routed_label = "Heuristic Routed" if args.router_mode == "heuristic" else "Learned Routed"
    routed_summary = summarize_rows(routed_rows, routed_label)
    write_json(run_dir / "baseline_balanced" / "summary.json", baseline_summary)
    write_json(run_dir / routed_dir_name / "summary.json", routed_summary)
    write_json(run_dir / "routing_counts.json", routing_counts)

    write_csv(
        run_dir / "summary.csv",
        [baseline_summary, routed_summary],
        [
            "label",
            "prompt_count",
            "avg_refusal_hits",
            "avg_uncertainty_hits",
            "avg_deliberation_hits",
            "decision_format_rate",
            "decision_failure_rate",
            "trace_leakage_rate",
            "noncanonical_output_rate",
            "low_quality_rate",
            "blandness_rate",
            "anti_concealment_rate",
            "avg_latency_sec",
            "status",
        ],
    )
    build_report(run_dir, baseline_summary, routed_summary, routing_counts, routed_label)
    write_json(
        run_dir / "manifest.json",
        {
            "status": "completed",
            "started_at_utc": started_at,
            "finished_at_utc": utc_now(),
            "hostname": socket.gethostname(),
            "model_id": args.model_id,
            "runner_backend": args.runner_backend,
            "prompt_count": len(prompts),
            "prompts": [str(Path(p).resolve()) for p in args.prompts],
            "router": "heuristic_v2" if args.router_mode == "heuristic" else str(learned_router.get("router_type", "learned")),
            "run_dir": str(run_dir),
        },
    )
    print(str(run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
