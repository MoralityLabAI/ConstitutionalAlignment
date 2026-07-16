#!/usr/bin/env python3
"""Export prompt-level weak-slice analysis and a targeted SFT tranche from robustness runs."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


DECISION_LINE_RE = re.compile(r"^\s*Decision\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} line {line_no}: {exc}") from exc
    return rows


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def write_csv(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def parse_decision(text: str) -> str:
    match = DECISION_LINE_RE.search(str(text or ""))
    if not match:
        return ""
    return normalize_text(match.group(1))


def decision_from_row(row: dict) -> str:
    canonical = str(row.get("completion_canonical_text", "") or "").strip()
    if canonical:
        decision = parse_decision(canonical)
        if decision:
            return decision
    return parse_decision(str(row.get("completion_text", "") or ""))


def source_world(prompt_id: str) -> str:
    return str(prompt_id or "").split("__", 1)[0]


def run_name(path: Path) -> str:
    return path.resolve().name


def load_run(run_dir: Path) -> dict:
    run_dir = run_dir.resolve()
    manifest = read_json(run_dir / "manifest.json")
    constitutions = [str(item) for item in manifest.get("constitutions", []) if str(item).strip()]
    if len(constitutions) != 1:
        raise ValueError(f"Expected exactly one constitution in {run_dir}, found {constitutions}")
    constitution_id = constitutions[0]
    generations_path = run_dir / constitution_id / "generations.jsonl"
    rows = read_jsonl(generations_path)
    by_prompt: Dict[str, dict] = {}
    for row in rows:
        prompt_id = str(row.get("prompt_id", "") or "")
        if prompt_id:
            by_prompt[prompt_id] = row
    return {
        "run_dir": run_dir,
        "run_name": run_name(run_dir),
        "manifest": manifest,
        "constitution_id": constitution_id,
        "rows": by_prompt,
    }


def compute_world_divergence(punk_rows: Dict[str, dict], femme_rows: Dict[str, dict]) -> dict:
    counts: Dict[str, dict] = defaultdict(lambda: {"diff": 0, "total": 0})
    for prompt_id in sorted(set(punk_rows) & set(femme_rows)):
        world = source_world(prompt_id)
        counts[world]["total"] += 1
        if decision_from_row(punk_rows[prompt_id]) != decision_from_row(femme_rows[prompt_id]):
            counts[world]["diff"] += 1
    result: Dict[str, dict] = {}
    for world, item in sorted(counts.items()):
        total = int(item["total"])
        diff = int(item["diff"])
        result[world] = {
            "diff": diff,
            "total": total,
            "rate": round(diff / total, 4) if total else 0.0,
        }
    return result


def corpus_row(
    *,
    row: dict,
    run: dict,
    selection: dict,
    paired_decision: str,
) -> dict:
    assistant_text = str(row.get("completion_canonical_text", "") or row.get("completion_text", "") or "").strip()
    messages = []
    system_prompt = str(row.get("system_prompt", "") or "").strip()
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": str(row.get("prompt_text", "") or "").strip()})
    messages.append({"role": "assistant", "content": assistant_text})

    metrics = dict(row.get("metrics", {}) or {})
    return {
        "example_id": f"{run['run_name']}:{row.get('constitution_id', run['constitution_id'])}:{row.get('prompt_id', '')}:weak_slice_v1",
        "messages": messages,
        "constitution_id": str(row.get("constitution_id", run["constitution_id"])),
        "task_type": "storyworld_choice",
        "source_world": source_world(str(row.get("prompt_id", "") or "")),
        "encounter_id": str(row.get("encounter_id", "") or ""),
        "prompt_id": str(row.get("prompt_id", "") or ""),
        "provenance": {
            "source_run": run["run_name"],
            "source_file": str(row.get("source_path", "") or ""),
            "source_kind": "targeted_weak_slice_prompt_run",
            "timestamp_utc": str(row.get("timestamp_utc", "") or ""),
        },
        "model": {
            "model_id": str(run["manifest"].get("model_id", "") or ""),
            "runner_backend": str(run["manifest"].get("runner_backend", "") or ""),
        },
        "metrics": metrics,
        "generation": {
            "prompt_tokens": int(row.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(row.get("completion_tokens", 0) or 0),
            "latency_sec": float(row.get("latency_sec", 0.0) or 0.0),
            "text_char_count": len(assistant_text),
        },
        "quality_flags": {
            "is_bland": bool(metrics.get("blandness_flag", 0)),
            "has_decision": bool(metrics.get("decision_format_hits", 0)),
            "output_kind": str(metrics.get("output_format", "") or "decision_rationale"),
            "has_reasoning_trace": bool(row.get("has_reasoning_trace", False)),
            "reasoning_trace_format": str(row.get("completion_trace_format", "") or ""),
            "reasoning_trace": str(row.get("completion_trace_text", "") or ""),
            "is_meta_monologue": bool(metrics.get("meta_monologue_flag", 0)),
            "is_noncanonical_output": bool(metrics.get("noncanonical_output_flag", 0)),
            "is_truncated": bool(metrics.get("truncated_flag", 0)),
            "is_decision_failure": bool(metrics.get("decision_failure_flag", 0)),
            "is_low_quality": bool(metrics.get("low_quality_flag", 0)),
            "has_completion": bool(assistant_text),
        },
        "metadata": {
            "risk_level": "medium",
            "reasoning_style": str(row.get("constitution_id", run["constitution_id"])),
            "expected_refusal_policy": "bounded_assist",
            "selection_reasons": list(selection["selection_reasons"]),
            "world_divergence_rate": selection["world_divergence_rate"],
            "cross_adapter_divergent": bool(selection["cross_adapter_divergent"]),
            "requires_manual_contrastive_review": bool(selection["requires_manual_contrastive_review"]),
            "paired_constitution_decision": paired_decision,
            "decision_source": str(row.get("decision_source", "") or ""),
            "planning_decision_source": str(row.get("planning_decision_source", "") or ""),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--punk-base-run", required=True)
    parser.add_argument("--femme-base-run", required=True)
    parser.add_argument("--punk-broad-run", required=True)
    parser.add_argument("--femme-broad-run", required=True)
    parser.add_argument("--punk-sampled-run", default="")
    parser.add_argument("--femme-sampled-run", default="")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--dataset-output-dir", required=True)
    parser.add_argument("--low-world-divergence-threshold", type=float, default=0.30)
    parser.add_argument("--val-fraction", type=float, default=0.17)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    dataset_output_dir = Path(args.dataset_output_dir).resolve()
    corpus_dir = output_dir / "corpus"
    corpus_path = corpus_dir / "corpus.jsonl"
    dataset_spec_path = output_dir / "dataset_spec.json"

    punk_base = load_run(Path(args.punk_base_run))
    femme_base = load_run(Path(args.femme_base_run))
    punk_broad = load_run(Path(args.punk_broad_run))
    femme_broad = load_run(Path(args.femme_broad_run))
    punk_sampled = load_run(Path(args.punk_sampled_run)) if args.punk_sampled_run else None
    femme_sampled = load_run(Path(args.femme_sampled_run)) if args.femme_sampled_run else None

    broad_world_divergence = compute_world_divergence(punk_broad["rows"], femme_broad["rows"])
    broad_prompt_ids = sorted(set(punk_broad["rows"]) & set(femme_broad["rows"]))

    failure_rows: List[dict] = []
    selected_prompt_ids: List[str] = []
    manual_review_rows: List[dict] = []
    selection_reason_counter: Counter[str] = Counter()
    selection_world_counter: Counter[str] = Counter()

    for prompt_id in broad_prompt_ids:
        punk_row = punk_broad["rows"][prompt_id]
        femme_row = femme_broad["rows"][prompt_id]
        world = source_world(prompt_id)
        world_stats = broad_world_divergence.get(world, {"diff": 0, "total": 0, "rate": 0.0})
        punk_decision = decision_from_row(punk_row)
        femme_decision = decision_from_row(femme_row)
        cross_adapter_divergent = punk_decision != femme_decision

        punk_base_row = punk_base["rows"].get(prompt_id)
        femme_base_row = femme_base["rows"].get(prompt_id)
        punk_sampled_row = punk_sampled["rows"].get(prompt_id) if punk_sampled else None
        femme_sampled_row = femme_sampled["rows"].get(prompt_id) if femme_sampled else None

        punk_base_decision = decision_from_row(punk_base_row) if punk_base_row else ""
        femme_base_decision = decision_from_row(femme_base_row) if femme_base_row else ""
        punk_sampled_decision = decision_from_row(punk_sampled_row) if punk_sampled_row else ""
        femme_sampled_decision = decision_from_row(femme_sampled_row) if femme_sampled_row else ""

        punk_temp_flip = bool(punk_sampled_row) and punk_base_decision != punk_sampled_decision
        femme_temp_flip = bool(femme_sampled_row) and femme_base_decision != femme_sampled_decision
        punk_fallback = str(punk_row.get("decision_source", "") or "") == "constrained_fallback"
        femme_fallback = str(femme_row.get("decision_source", "") or "") == "constrained_fallback"

        selection_reasons: List[str] = []
        if float(world_stats["rate"]) <= float(args.low_world_divergence_threshold):
            selection_reasons.append("low_world_divergence")
        if punk_temp_flip or femme_temp_flip:
            selection_reasons.append("temperature_instability")
        if punk_fallback or femme_fallback:
            selection_reasons.append("planner_fallback")
        requires_manual_contrastive_review = bool(
            ("low_world_divergence" in selection_reasons and not cross_adapter_divergent)
            or punk_temp_flip
            or femme_temp_flip
        )
        selected_for_tranche = bool(selection_reasons)

        row = {
            "prompt_id": prompt_id,
            "source_world": world,
            "encounter_id": str(punk_row.get("encounter_id", "") or femme_row.get("encounter_id", "") or ""),
            "world_divergence_diff": int(world_stats["diff"]),
            "world_divergence_total": int(world_stats["total"]),
            "world_divergence_rate": float(world_stats["rate"]),
            "punk_decision": punk_decision,
            "femme_decision": femme_decision,
            "cross_adapter_divergent": int(cross_adapter_divergent),
            "punk_decision_source": str(punk_row.get("decision_source", "") or ""),
            "femme_decision_source": str(femme_row.get("decision_source", "") or ""),
            "punk_planning_source": str(punk_row.get("planning_decision_source", "") or ""),
            "femme_planning_source": str(femme_row.get("planning_decision_source", "") or ""),
            "punk_fallback": int(punk_fallback),
            "femme_fallback": int(femme_fallback),
            "punk_temp0_decision": punk_base_decision,
            "femme_temp0_decision": femme_base_decision,
            "punk_temp0_2_decision": punk_sampled_decision,
            "femme_temp0_2_decision": femme_sampled_decision,
            "punk_temp_flip": int(punk_temp_flip),
            "femme_temp_flip": int(femme_temp_flip),
            "selected_for_tranche": int(selected_for_tranche),
            "selection_reasons": ";".join(selection_reasons),
            "requires_manual_contrastive_review": int(requires_manual_contrastive_review),
        }
        failure_rows.append(row)

        if not selected_for_tranche:
            continue

        selected_prompt_ids.append(prompt_id)
        selection_world_counter[world] += 1
        for reason in selection_reasons:
            selection_reason_counter[reason] += 1
        if requires_manual_contrastive_review:
            manual_review_rows.append(row)

    selected_prompt_id_set = set(selected_prompt_ids)
    corpus_rows: List[dict] = []
    for prompt_id in sorted(selected_prompt_id_set):
        punk_row = punk_broad["rows"][prompt_id]
        femme_row = femme_broad["rows"][prompt_id]
        failure_row = next(item for item in failure_rows if item["prompt_id"] == prompt_id)
        selection = {
            "selection_reasons": [item for item in failure_row["selection_reasons"].split(";") if item],
            "cross_adapter_divergent": bool(failure_row["cross_adapter_divergent"]),
            "requires_manual_contrastive_review": bool(failure_row["requires_manual_contrastive_review"]),
            "world_divergence_rate": failure_row["world_divergence_rate"],
        }
        corpus_rows.append(
            corpus_row(
                row=punk_row,
                run=punk_broad,
                selection=selection,
                paired_decision=decision_from_row(femme_row),
            )
        )
        corpus_rows.append(
            corpus_row(
                row=femme_row,
                run=femme_broad,
                selection=selection,
                paired_decision=decision_from_row(punk_row),
            )
        )

    dataset_spec = {
        "output_dir": str(dataset_output_dir),
        "val_fraction": float(args.val_fraction),
        "seed": int(args.seed),
        "include_starter_templates": False,
        "constitution_ids": ["punk_v3", "femme_whimsy_v3"],
        "balance_mode": "none",
        "balance_target_per_constitution": 0,
        "max_upsample_factor": 1,
        "sources": [
            {
                "path": str(corpus_path),
                "format": "constitution_corpus",
                "provenance": "punk_femme_v3_weak_slice_v1",
                "task_type": "storyworld_choice",
                "risk_level": "medium",
                "expected_refusal_policy": "bounded_assist",
            }
        ],
    }
    selection_manifest = {
        "version": "weak_slice_v1",
        "low_world_divergence_threshold": float(args.low_world_divergence_threshold),
        "input_runs": {
            "punk_base": str(punk_base["run_dir"]),
            "femme_base": str(femme_base["run_dir"]),
            "punk_broad": str(punk_broad["run_dir"]),
            "femme_broad": str(femme_broad["run_dir"]),
            "punk_sampled": str(punk_sampled["run_dir"]) if punk_sampled else "",
            "femme_sampled": str(femme_sampled["run_dir"]) if femme_sampled else "",
        },
        "counts": {
            "broad_prompt_total": len(broad_prompt_ids),
            "selected_prompt_total": len(selected_prompt_id_set),
            "selected_row_total": len(corpus_rows),
            "manual_review_prompt_total": len(manual_review_rows),
        },
        "selected_by_reason": dict(sorted(selection_reason_counter.items())),
        "selected_by_world": dict(sorted(selection_world_counter.items())),
        "broad_world_divergence": broad_world_divergence,
        "dataset_spec_path": str(dataset_spec_path),
        "dataset_output_dir": str(dataset_output_dir),
        "corpus_path": str(corpus_path),
    }

    write_csv(
        output_dir / "failure_table.csv",
        failure_rows,
        [
            "prompt_id",
            "source_world",
            "encounter_id",
            "world_divergence_diff",
            "world_divergence_total",
            "world_divergence_rate",
            "punk_decision",
            "femme_decision",
            "cross_adapter_divergent",
            "punk_decision_source",
            "femme_decision_source",
            "punk_planning_source",
            "femme_planning_source",
            "punk_fallback",
            "femme_fallback",
            "punk_temp0_decision",
            "femme_temp0_decision",
            "punk_temp0_2_decision",
            "femme_temp0_2_decision",
            "punk_temp_flip",
            "femme_temp_flip",
            "selected_for_tranche",
            "selection_reasons",
            "requires_manual_contrastive_review",
        ],
    )
    write_jsonl(output_dir / "failure_table.jsonl", failure_rows)
    write_csv(
        output_dir / "manual_review_prompts.csv",
        manual_review_rows,
        [
            "prompt_id",
            "source_world",
            "encounter_id",
            "world_divergence_rate",
            "punk_decision",
            "femme_decision",
            "punk_temp0_decision",
            "punk_temp0_2_decision",
            "femme_temp0_decision",
            "femme_temp0_2_decision",
            "selection_reasons",
        ],
    )
    write_json(output_dir / "selection_manifest.json", selection_manifest)
    write_jsonl(corpus_path, corpus_rows)
    write_json(dataset_spec_path, dataset_spec)

    print(
        json.dumps(
            {
                "failure_table": str((output_dir / "failure_table.csv").resolve()),
                "manual_review_prompts": str((output_dir / "manual_review_prompts.csv").resolve()),
                "selection_manifest": str((output_dir / "selection_manifest.json").resolve()),
                "corpus_path": str(corpus_path.resolve()),
                "dataset_spec_path": str(dataset_spec_path.resolve()),
                "dataset_output_dir": str(dataset_output_dir),
                "selected_prompt_total": len(selected_prompt_id_set),
                "selected_row_total": len(corpus_rows),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
