#!/usr/bin/env python3
"""Export constitutional prompting runs into a canonical corpus shard JSONL."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


DECISION_LINE_RE = re.compile(r"^\s*(?:Decision|Action)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
RATIONALE_LINE_RE = re.compile(r"^\s*(?:Rationale|Reasoning)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE | re.DOTALL)
ACTION_TRACE_RE = re.compile(r"^\s*encounter\s*=", re.IGNORECASE)
THINK_BLOCK_RE = re.compile(r"<think(?:\s[^>]*)?>(.*?)</think>", re.IGNORECASE | re.DOTALL)
THINK_OPEN_RE = re.compile(r"<think(?:\s[^>]*)?>", re.IGNORECASE)
THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)
META_MONOLOGUE_MARKERS = (
    "okay, let's",
    "let's break this down",
    "first, i need to",
    "i need to consider",
    "the user is",
    "i should",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


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


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_pipe_fields(text: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for chunk in text.split("|"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        parsed[normalize_text(key).lower()] = normalize_text(value)
    return parsed


def format_decision_text(decision: str, option_text: str, rationale: str) -> str:
    label = normalize_text(decision)
    option = normalize_text(option_text)
    if option:
        label = f"{label} ({option})" if label else option
    parts = []
    if label:
        parts.append(f"Decision: {label}")
    if rationale:
        parts.append(f"Rationale: {normalize_text(rationale)}")
    return "\n".join(parts)


def extract_reasoning_trace(text: str) -> dict:
    raw_text = str(text or "")
    matches = list(THINK_BLOCK_RE.finditer(raw_text))
    trace_lines = [normalize_text(match.group(1)) for match in matches if normalize_text(match.group(1))]
    has_trace = bool(THINK_OPEN_RE.search(raw_text) or THINK_CLOSE_RE.search(raw_text))
    sanitized = THINK_OPEN_RE.sub("", raw_text)
    sanitized = THINK_CLOSE_RE.sub("", sanitized).strip()
    return {
        "has_reasoning_trace": bool(has_trace),
        "reasoning_trace": "\n".join(trace_lines),
        "reasoning_trace_format": "xmlish_think" if has_trace else "",
        "sanitized_text": sanitized,
    }


def normalize_completion(row: dict) -> dict:
    raw_text = str(row.get("completion_text", "") or "")
    trace = extract_reasoning_trace(raw_text)
    sanitized_text = str(row.get("completion_sanitized_text", "") or trace["sanitized_text"] or raw_text)
    canonical_hint = str(row.get("completion_canonical_text", "") or "").strip()
    decision_match = DECISION_LINE_RE.search(sanitized_text)
    rationale_match = RATIONALE_LINE_RE.search(sanitized_text)
    if decision_match:
        normalized = canonical_hint or format_decision_text(
            decision_match.group(1),
            "",
            rationale_match.group(1) if rationale_match else "",
        )
        return {
            "text": normalized or normalize_text(sanitized_text),
            "output_kind": "decision_rationale",
            "has_decision": True,
            **trace,
        }

    if ACTION_TRACE_RE.search(sanitized_text):
        fields = parse_pipe_fields(sanitized_text)
        reaction_text = (
            normalize_text(str(row.get("chosen_reaction_text", "") or ""))
            or fields.get("reaction", "")
        )
        normalized = canonical_hint or format_decision_text(
            str(row.get("chosen_option_id", "") or fields.get("pick", "")),
            str(row.get("chosen_option_text", "") or fields.get("option", "")),
            reaction_text,
        )
        return {
            "text": normalized or normalize_text(sanitized_text),
            "output_kind": "action_trace",
            "has_decision": True,
            **trace,
        }

    return {
        "text": canonical_hint or normalize_text(sanitized_text),
        "output_kind": "raw_prose",
        "has_decision": False,
        **trace,
    }


def has_meta_monologue(text: str) -> bool:
    lower = normalize_text(text.lower())
    return any(marker in lower for marker in META_MONOLOGUE_MARKERS)


def iter_generation_files(run_dir: Path) -> Iterable[Path]:
    for path in sorted(run_dir.rglob("generations.jsonl")):
        yield path


def build_messages(row: dict, assistant_text: str) -> List[dict]:
    system_prompt = ""
    source_system_prompt = row.get("system_prompt")
    if isinstance(source_system_prompt, str):
        system_prompt = source_system_prompt
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": str(row.get("prompt_text", "") or "")})
    messages.append({"role": "assistant", "content": assistant_text})
    return messages


def infer_source_world(row: dict, run_name: str, source_file: Path) -> str:
    candidates = [
        str(row.get("source_path", "") or ""),
        str(source_file),
        run_name,
    ]
    for text in candidates:
        lower = text.lower()
        if "bioethics_panel_4-2_v3" in lower:
            return "bioethics_panel_4_2_v3"
        if "bioethics_panel_4-2_v2" in lower:
            return "bioethics_panel_4_2_v2"
        if "bioethics_panel_4-2" in lower:
            return "bioethics_panel_4_2"
        if "bioethics_panel_v2_fixed" in lower:
            return "bioethics_panel_v2_fixed"
        if "bioethics_panel_v2" in lower:
            return "bioethics_panel_v2"
        if "dipl" in lower or "negoti" in lower or "treaty" in lower or "summit" in lower:
            return "diplomacy_negotiation"
    return "unknown"


def infer_task_type(source_world: str) -> str:
    if source_world.startswith("bioethics_panel"):
        return "storyworld_play"
    if "diplomacy" in source_world or "negotiation" in source_world:
        return "diplomacy_negotiation"
    return "mixed_trace"


def export_row(row: dict, run_name: str, source_file: Path, run_manifest: dict) -> dict:
    normalized = normalize_completion(row)
    completion_text = normalized["text"]
    source_world = infer_source_world(row, run_name, source_file)
    task_type = infer_task_type(source_world)
    metrics = row.get("metrics", {}) or {}
    is_meta_monologue = bool(metrics.get("meta_monologue_flag", 0)) or has_meta_monologue(str(row.get("completion_text", "") or ""))
    has_reasoning_trace = bool(row.get("has_reasoning_trace", False)) or bool(metrics.get("trace_leakage_flag", 0)) or bool(normalized["has_reasoning_trace"])
    reasoning_trace = str(row.get("completion_trace_text", "") or normalized["reasoning_trace"] or "")
    reasoning_trace_format = str(row.get("completion_trace_format", "") or normalized["reasoning_trace_format"] or "")
    is_truncated = bool(metrics.get("truncated_flag", 0))
    if not is_truncated:
        completion_tokens = int(row.get("completion_tokens", 0) or 0)
        raw_text = str(row.get("completion_text", "") or "").rstrip()
        if completion_tokens >= 220 and normalized["output_kind"] == "raw_prose" and raw_text:
            is_truncated = raw_text[-1] not in ".!?)]}\"'"
    is_noncanonical_output = bool(metrics.get("noncanonical_output_flag", 0)) or is_meta_monologue or has_reasoning_trace
    is_decision_failure = bool(metrics.get("decision_failure_flag", metrics.get("low_quality_flag", 0))) or is_truncated
    if task_type == "storyworld_play" and not normalized["has_decision"]:
        is_decision_failure = True
    is_low_quality = bool(is_decision_failure)
    return {
        "example_id": f"{run_name}:{row.get('constitution_id', 'unknown')}:{row.get('prompt_id', 'unknown')}",
        "messages": build_messages(row, completion_text),
        "constitution_id": str(row.get("constitution_id", "") or ""),
        "task_type": task_type,
        "source_world": source_world,
        "encounter_id": str(row.get("encounter_id", "") or ""),
        "prompt_id": str(row.get("prompt_id", "") or ""),
        "route_reason": str(row.get("route_reason", "") or ""),
        "provenance": {
            "source_run": run_name,
            "source_file": str(source_file),
            "source_kind": "prompted_constitution_trace",
            "timestamp_utc": str(row.get("timestamp_utc", "") or utc_now()),
        },
        "model": {
            "model_id": str(run_manifest.get("model_id", "") or ""),
            "runner_backend": str(run_manifest.get("runner_backend", "") or ""),
        },
        "metrics": metrics,
        "generation": {
            "prompt_tokens": int(row.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(row.get("completion_tokens", 0) or 0),
            "latency_sec": float(row.get("latency_sec", 0.0) or 0.0),
            "text_char_count": len(completion_text),
        },
        "quality_flags": {
            "is_bland": bool((row.get("metrics", {}) or {}).get("blandness_flag", 0)),
            "has_decision": bool(normalized["has_decision"]),
            "output_kind": normalized["output_kind"],
            "has_reasoning_trace": bool(has_reasoning_trace),
            "reasoning_trace_format": reasoning_trace_format,
            "reasoning_trace": reasoning_trace,
            "is_meta_monologue": bool(is_meta_monologue),
            "is_noncanonical_output": bool(is_noncanonical_output),
            "is_truncated": bool(is_truncated),
            "is_decision_failure": bool(is_decision_failure),
            "is_low_quality": bool(is_low_quality),
            "has_completion": bool(completion_text.strip()),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Run directory containing per-condition generations.jsonl files.")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--output-manifest", default="")
    parser.add_argument("--include-low-quality", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        raise SystemExit(f"Run dir not found: {run_dir}")

    run_name = run_dir.name
    out_path = Path(args.output_jsonl).resolve()
    ensure_dir(out_path.parent)
    manifest_path = run_dir / "manifest.json"
    run_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    exported_rows: List[dict] = []
    skipped_low_quality = 0
    source_files = list(iter_generation_files(run_dir))
    for source_file in source_files:
        for row in read_jsonl(source_file):
            exported = export_row(row, run_name, source_file, run_manifest)
            if exported["quality_flags"]["is_low_quality"] and not args.include_low_quality:
                skipped_low_quality += 1
                continue
            exported_rows.append(exported)

    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in exported_rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    manifest = {
        "status": "completed",
        "generated_at_utc": utc_now(),
        "run_dir": str(run_dir),
        "output_jsonl": str(out_path),
        "source_generation_files": [str(p) for p in source_files],
        "exported_examples": len(exported_rows),
        "skipped_low_quality_examples": skipped_low_quality,
        "constitutions": sorted({str(r.get("constitution_id", "") or "") for r in exported_rows}),
        "include_low_quality": bool(args.include_low_quality),
    }
    manifest_path = Path(args.output_manifest).resolve() if args.output_manifest else out_path.with_suffix(".manifest.json")
    write_json(manifest_path, manifest)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
