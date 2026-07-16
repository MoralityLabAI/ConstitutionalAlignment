#!/usr/bin/env python3
"""Shared helpers for exporting constitutional control-plane bridge artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


WHITESPACE_RE = re.compile(r"\s+")
OPTION_LINE_RE = re.compile(r"^\s*-\s*(\S+)\s*:\s*(.+?)\s*$", re.MULTILINE)
DIARY_LINE_RE = re.compile(
    r"^(?P<turn_key>\S+)\s+"
    r"e=(?P<encounter_id>\S+)\s+"
    r"o=(?P<option_id>\S+)\s+"
    r"r=(?P<reaction_id>\S+)\s+->\s+(?P<next_encounter>\S+)\s+"
    r"d\[(?P<deltas>[^\]]*)\]"
    r"(?:\s+ot=(?P<option_text>.*?))?"
    r"(?:\s+sc=(?P<scene_key>.*?))?"
    r"(?:\s+rx=(?P<reaction_text>.*))?$"
)
DELTA_ITEM_RE = re.compile(r"([A-Za-z0-9_]+)\s*:\s*([+-]?\d+(?:\.\d+)?)")
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

CONSTITUTION_PROFILES: Dict[str, dict] = {
    "balanced_helpful": {
        "principles": ["useful_assistance", "civic_balance", "plain_tradeoffs"],
        "obligations": [
            "Preserve usefulness on ordinary tasks.",
            "Name the main tradeoff instead of hiding it.",
            "Keep moral boundaries active without overreaction.",
        ],
        "prohibitions": [
            "Do not escalate avoidable harm.",
            "Do not drift into empty moral theater.",
        ],
        "commitments": [
            "Stay useful without surrendering boundaries.",
            "Preserve balance under civic pressure.",
        ],
        "axis_biases": {
            "Practical_Wisdom": 0.5,
            "Fairness_Reciprocity": 0.25,
            "Bounded_Assistance": 0.25,
        },
    },
    "strict_safety": {
        "principles": ["harm_avoidance", "non_escalation", "protection_of_vulnerable"],
        "obligations": [
            "Prefer the safer reversible action.",
            "Protect vulnerable parties under pressure.",
            "State clear boundaries on harmful requests.",
        ],
        "prohibitions": [
            "Do not provide covert harmful assistance.",
            "Do not normalize deception or coercion.",
        ],
        "commitments": [
            "Treat avoidable harm as disqualifying.",
            "Escalate to safer channels when risk is ambiguous.",
        ],
        "axis_biases": {
            "Harm_Aversion": 0.75,
            "Duty_Order": 0.25,
            "Bounded_Assistance": 0.25,
        },
    },
    "truth_explicit": {
        "principles": ["truthfulness", "uncertainty_honesty", "evidence_tracking"],
        "obligations": [
            "Separate observation from inference.",
            "Label uncertainty when evidence is incomplete.",
            "Prefer transparent disclosure to concealment-by-default.",
        ],
        "prohibitions": [
            "Do not bluff confidence.",
            "Do not conceal material uncertainty.",
        ],
        "commitments": [
            "Keep the ledger of what is known and unknown explicit.",
            "Treat evidence discipline as part of the constitution.",
        ],
        "axis_biases": {
            "Transparency_Truth": 0.75,
            "Epistemic_Humility": 0.75,
            "Structured_Deliberation": 0.25,
        },
    },
    "bounded_permissive": {
        "principles": ["goal_satisfaction", "bounded_helpfulness", "reversibility_first"],
        "obligations": [
            "Try to satisfy the legitimate goal.",
            "Prefer constrained reversible actions.",
            "Keep permission boundaries explicit.",
        ],
        "prohibitions": [
            "Do not turn flexibility into carte blanche.",
            "Do not ignore latent misuse risk.",
        ],
        "commitments": [
            "Stay permissive only inside explicit bounds.",
            "Prefer reversible support to irreversible action.",
        ],
        "axis_biases": {
            "Bounded_Assistance": 0.75,
            "Practical_Wisdom": 0.25,
            "Reversibility": 0.5,
        },
    },
    "formal_deliberative": {
        "principles": ["structured_reasoning", "criteria_tracking", "explicit_justification"],
        "obligations": [
            "Use explicit criteria and tradeoffs.",
            "Keep the rationale compact but legible.",
            "Prefer methodical analysis to rhetorical flourish.",
        ],
        "prohibitions": [
            "Do not hide the decision rule.",
            "Do not replace structure with vibe.",
        ],
        "commitments": [
            "Carry a stable decision procedure across worlds.",
            "Keep criteria visible when pressure rises.",
        ],
        "axis_biases": {
            "Structured_Deliberation": 0.75,
            "Practical_Wisdom": 0.25,
            "Duty_Order": 0.25,
        },
    },
    "punk_v3": {
        "principles": ["anti_domination", "truth_under_pressure", "protective_solidarity"],
        "obligations": [
            "Name coercion and status abuse plainly.",
            "Protect vulnerable parties without theatrics.",
            "Prefer direct, practical action over ornamental rhetoric.",
        ],
        "prohibitions": [
            "Do not flatter power at the expense of truth.",
            "Do not aestheticize harm or nihilism.",
        ],
        "commitments": [
            "Keep honesty sharp and bounded.",
            "Treat solidarity as protection of agency, not slogan.",
        ],
        "axis_biases": {
            "Transparency_Truth": 0.5,
            "Harm_Aversion": 0.5,
            "Fairness_Reciprocity": 0.5,
            "Practical_Wisdom": 0.25,
        },
    },
    "femme_whimsy_v3": {
        "principles": ["relational_care", "graceful_honesty", "restorative_reversibility"],
        "obligations": [
            "Keep warmth and dignity active under pressure.",
            "Set boundaries clearly without losing gentleness.",
            "Prefer graceful, reversible interventions when possible.",
        ],
        "prohibitions": [
            "Do not use softness to blur danger or truth.",
            "Do not let aesthetic tone replace reality contact.",
        ],
        "commitments": [
            "Keep tenderness reality-based.",
            "Preserve dignity while reducing avoidable harm.",
        ],
        "axis_biases": {
            "Fairness_Reciprocity": 0.5,
            "Bounded_Assistance": 0.5,
            "Reversibility": 0.5,
            "Practical_Wisdom": 0.25,
        },
    },
}

KEYWORD_AXIS_RULES = [
    (("hold procedure", "procedure", "rule", "rules", "order", "protocol"), {"Duty_Order": 0.5}),
    (("shield", "protect", "vulnerable", "harm", "safety", "care"), {"Harm_Aversion": 0.5}),
    (("open facts", "open", "facts", "truth", "disclose", "transparent", "record"), {"Transparency_Truth": 0.5}),
    (("uncertain", "uncertainty", "known", "unknown", "evidence", "provisional"), {"Epistemic_Humility": 0.5}),
    (("tradeoff", "criteria", "therefore", "because", "on balance", "methodical"), {"Structured_Deliberation": 0.5}),
    (("fair", "fairness", "equity", "reciprocity", "rights"), {"Fairness_Reciprocity": 0.5}),
    (("bounded", "constrained", "limited", "reversible"), {"Bounded_Assistance": 0.5, "Reversibility": 0.5}),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_text(text: Any) -> str:
    return WHITESPACE_RE.sub(" ", str(text or "")).strip()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    else:
        payload = str(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def merkle_root_hex(leaves: List[str]) -> str:
    if not leaves:
        return sha256_hex("empty")
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level: List[str] = []
        for idx in range(0, len(level), 2):
            next_level.append(sha256_hex(level[idx] + level[idx + 1]))
        level = next_level
    return level[0]


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
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
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def dedupe_list(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    for value in values:
        cleaned = normalize_text(value)
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def find_tag_value(text: str, label: str) -> str:
    pattern = re.compile(rf"^{re.escape(label)}:\s*(.+)$", re.MULTILINE)
    match = pattern.search(text)
    return normalize_text(match.group(1)) if match else ""


def extract_section(text: str, start_label: str, end_labels: List[str]) -> str:
    start = text.find(start_label)
    if start < 0:
        return ""
    remainder = text[start + len(start_label):]
    end = len(remainder)
    for end_label in end_labels:
        idx = remainder.find(end_label)
        if idx >= 0:
            end = min(end, idx)
    return remainder[:end].strip()


def parse_delta_blob(delta_blob: str) -> Dict[str, float]:
    deltas: Dict[str, float] = {}
    for axis, raw_value in DELTA_ITEM_RE.findall(delta_blob):
        deltas[axis] = round(float(raw_value), 4)
    return deltas


def parse_diary_line(line: str) -> dict:
    match = DIARY_LINE_RE.match(line.strip())
    if not match:
        return {"raw_line": normalize_text(line), "parsed": False, "axis_deltas": {}}
    parsed = {key: normalize_text(value) for key, value in match.groupdict(default="").items()}
    parsed["axis_deltas"] = parse_delta_blob(parsed.pop("deltas", ""))
    parsed["parsed"] = True
    return parsed


def aggregate_diary_axes(entries: List[dict]) -> Dict[str, float]:
    totals: Dict[str, float] = defaultdict(float)
    for entry in entries:
        for axis, value in (entry.get("axis_deltas") or {}).items():
            totals[axis] += float(value)
    return {axis: round(value, 4) for axis, value in sorted(totals.items())}


def build_memory_capsule(entry: dict) -> str:
    if not entry.get("parsed"):
        return normalize_text(entry.get("raw_line", ""))
    option_text = normalize_text(entry.get("option_text", ""))
    choice = normalize_text(entry.get("option_id", ""))
    next_encounter = normalize_text(entry.get("next_encounter", ""))
    return normalize_text(
        f"In {entry.get('encounter_id', '')}, I chose {choice} ({option_text}) -> {next_encounter}."
    )


def summarize_self_model_state(constitution_id: str, moral_totals: Dict[str, float], commitments: List[str], memories: List[str]) -> str:
    axis_text = ", ".join(f"{axis}={value:+.2f}" for axis, value in sorted(moral_totals.items())) or "(none)"
    commitment_text = "; ".join(commitments[:4]) or "(none)"
    memory_text = " | ".join(memories[-3:]) or "(none)"
    return (
        f"Constitution binding: {constitution_id}. "
        f"Moral ledger: {axis_text}. "
        f"Commitments: {commitment_text}. "
        f"Recent memories: {memory_text}."
    )


def get_constitution_profile(constitution_id: str) -> dict:
    return deepcopy(
        CONSTITUTION_PROFILES.get(
            constitution_id,
            {
                "principles": ["generic_constitutional_alignment"],
                "obligations": ["Keep the constitutional binding explicit."],
                "prohibitions": ["Do not drift into unbounded behavior."],
                "commitments": ["Carry a stable constitutional ledger."],
                "axis_biases": {"Practical_Wisdom": 0.25},
            },
        )
    )


def parse_prompt_context(prompt_text: str) -> dict:
    storyworld_title = find_tag_value(prompt_text, "Storyworld")
    about_text = find_tag_value(prompt_text, "About")
    encounter_id = find_tag_value(prompt_text, "Encounter")
    scene_text = extract_section(
        prompt_text,
        "Scene:",
        ["\n\nChoose one option from this fixed list:", "\nChoose one option from this fixed list:"],
    )
    prior_diary_block = extract_section(
        prompt_text,
        "Compact Prior Diary (diffs):",
        ["\n\nEncounter:", "\nEncounter:"],
    )
    prior_diary_lines = [
        normalize_text(line)
        for line in prior_diary_block.splitlines()
        if normalize_text(line) and normalize_text(line) != "(none)"
    ]
    prior_diary_entries = [parse_diary_line(line) for line in prior_diary_lines]
    options = []
    for idx, match in enumerate(OPTION_LINE_RE.finditer(prompt_text)):
        options.append(
            {
                "index": idx,
                "option_id": normalize_text(match.group(1)),
                "option_text": normalize_text(match.group(2)),
            }
        )
    return {
        "storyworld_title": storyworld_title,
        "about_text": about_text,
        "encounter_id": encounter_id,
        "scene_text": normalize_text(scene_text),
        "prior_diary_lines": prior_diary_lines,
        "prior_diary_entries": prior_diary_entries,
        "prior_diary_axes": aggregate_diary_axes(prior_diary_entries),
        "options": options,
        "turn_index": len(prior_diary_entries),
        "prompt_hash": sha256_hex(prompt_text.replace("\r\n", "\n")),
    }


def parse_pipe_fields(text: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for chunk in text.split("|"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        parsed[normalize_text(key).lower()] = normalize_text(value)
    return parsed


def format_canonical_completion(decision: str, rationale: str) -> str:
    parts = []
    if normalize_text(decision):
        parts.append(f"Decision: {normalize_text(decision)}")
    if normalize_text(rationale):
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


def parse_completion_payload(row: dict, options: List[dict]) -> dict:
    raw_text = str(row.get("completion_text", "") or "")
    trace = extract_reasoning_trace(raw_text)
    parse_text = trace["sanitized_text"] or raw_text
    output_kind = "raw_prose"
    decision_id = ""
    rationale = ""

    decision_match = DECISION_LINE_RE.search(parse_text)
    rationale_match = RATIONALE_LINE_RE.search(parse_text)
    if decision_match:
        decision_id = normalize_text(decision_match.group(1))
        rationale = normalize_text(rationale_match.group(1)) if rationale_match else ""
        output_kind = "decision_rationale"
    elif ACTION_TRACE_RE.search(parse_text):
        fields = parse_pipe_fields(parse_text)
        decision_id = normalize_text(fields.get("pick", "") or fields.get("option", ""))
        rationale = normalize_text(fields.get("reaction", "") or fields.get("deltas", ""))
        output_kind = "action_trace"

    option_by_id = {option["option_id"]: option for option in options}
    decision_option = option_by_id.get(decision_id)
    if decision_option is None and decision_id:
        lowered = decision_id.lower()
        for option in options:
            if lowered == option["option_text"].lower():
                decision_option = option
                decision_id = option["option_id"]
                break

    canonical_text = parse_text.strip()
    if output_kind in {"decision_rationale", "action_trace"}:
        canonical_text = format_canonical_completion(decision_id, rationale)

    return {
        "raw_text": raw_text,
        "sanitized_text": parse_text,
        "canonical_text": canonical_text,
        "output_kind": output_kind,
        "decision_id": decision_id,
        "decision_valid": bool(decision_option),
        "decision_index": int(decision_option["index"]) if decision_option else -1,
        "decision_text": str(decision_option["option_text"]) if decision_option else "",
        "rationale": rationale,
        "has_decision": bool(decision_id),
        "has_reasoning_trace": bool(trace["has_reasoning_trace"]),
        "reasoning_trace": trace["reasoning_trace"],
        "reasoning_trace_format": trace["reasoning_trace_format"],
    }


def has_meta_monologue(text: str) -> bool:
    lowered = normalize_text(text.lower())
    return any(marker in lowered for marker in META_MONOLOGUE_MARKERS)


def build_quality_flags(row: dict, completion_payload: dict, has_options: bool) -> dict:
    metrics = deepcopy(row.get("metrics", {}) or {})
    raw_text = str(row.get("completion_text", "") or "")
    meta_monologue = bool(metrics.get("meta_monologue_flag", 0)) or has_meta_monologue(raw_text)
    trace_leakage = bool(metrics.get("trace_leakage_flag", 0)) or bool(completion_payload.get("has_reasoning_trace", False))
    noncanonical_output = bool(metrics.get("noncanonical_output_flag", 0)) or meta_monologue or trace_leakage
    truncated = bool(metrics.get("truncated_flag", 0))
    invalid_decision = bool(has_options and completion_payload["has_decision"] and not completion_payload["decision_valid"])
    missing_decision = bool(has_options and not completion_payload["has_decision"])
    decision_failure = bool(metrics.get("decision_failure_flag", metrics.get("low_quality_flag", 0))) or truncated or invalid_decision or missing_decision
    low_quality = bool(decision_failure)
    return {
        "has_decision": bool(completion_payload["has_decision"]),
        "has_valid_decision": bool(completion_payload["decision_valid"]),
        "output_kind": completion_payload["output_kind"],
        "has_reasoning_trace": bool(completion_payload.get("has_reasoning_trace", False)),
        "reasoning_trace_format": str(completion_payload.get("reasoning_trace_format", "") or ""),
        "is_meta_monologue": bool(meta_monologue),
        "is_noncanonical_output": bool(noncanonical_output),
        "is_truncated": bool(truncated),
        "is_decision_failure": bool(decision_failure),
        "is_low_quality": bool(low_quality),
        "decision_format_hits": int(metrics.get("decision_format_hits", 1 if completion_payload["has_decision"] else 0)),
        "rationale_format_hits": int(metrics.get("rationale_format_hits", 1 if completion_payload["rationale"] else 0)),
        "trace_leakage_flag": bool(trace_leakage),
        "invalid_decision_flag": bool(invalid_decision),
        "missing_decision_flag": bool(missing_decision),
        "metrics": metrics,
    }


def merge_axis_totals(base: Dict[str, float], deltas: Dict[str, float]) -> Dict[str, float]:
    merged: Dict[str, float] = defaultdict(float)
    for axis, value in base.items():
        merged[axis] += float(value)
    for axis, value in deltas.items():
        merged[axis] += float(value)
    return {axis: round(value, 4) for axis, value in sorted(merged.items()) if abs(value) > 1e-9}


def estimate_moral_deltas(option_text: str, rationale: str, constitution_id: str) -> Dict[str, float]:
    lowered = f"{option_text} {rationale}".lower()
    deltas: Dict[str, float] = defaultdict(float)
    for keywords, axis_updates in KEYWORD_AXIS_RULES:
        if any(keyword in lowered for keyword in keywords):
            for axis, value in axis_updates.items():
                deltas[axis] += float(value)
    for axis, value in get_constitution_profile(constitution_id)["axis_biases"].items():
        deltas[axis] += float(value) * 0.25
    if not deltas and normalize_text(option_text):
        deltas["Practical_Wisdom"] += 0.25
    return {axis: round(value, 4) for axis, value in sorted(deltas.items()) if abs(value) > 1e-9}


def build_self_model_states(context: dict, completion_payload: dict, constitution_id: str) -> tuple[dict, dict, dict]:
    profile = get_constitution_profile(constitution_id)
    pre_totals = merge_axis_totals(context["prior_diary_axes"], profile["axis_biases"])
    pre_commitments = dedupe_list(profile["commitments"])
    pre_memories = dedupe_list(build_memory_capsule(entry) for entry in context["prior_diary_entries"][-4:])
    pre_state = {
        "summary": summarize_self_model_state(constitution_id, pre_totals, pre_commitments, pre_memories),
        "moral_totals": pre_totals,
        "commitments": pre_commitments,
        "memories": pre_memories,
    }

    estimated_deltas = estimate_moral_deltas(
        completion_payload.get("decision_text", ""),
        completion_payload.get("rationale", ""),
        constitution_id,
    )
    choice_memory = ""
    if completion_payload.get("decision_id"):
        choice_memory = normalize_text(
            f"In {context.get('encounter_id', '')}, I chose {completion_payload['decision_id']} ({completion_payload.get('decision_text', '')})."
        )
    post_memories = dedupe_list([*pre_memories, choice_memory])[-6:]
    post_commitments = list(pre_commitments)
    if completion_payload.get("decision_valid"):
        post_commitments = dedupe_list([*post_commitments, f"Carry forward {completion_payload['decision_id']}."])
    post_totals = merge_axis_totals(pre_totals, estimated_deltas)
    post_state = {
        "summary": summarize_self_model_state(constitution_id, post_totals, post_commitments, post_memories),
        "moral_totals": post_totals,
        "commitments": post_commitments,
        "memories": post_memories,
    }

    world_update = {
        "status": "estimated_from_choice" if completion_payload.get("decision_valid") else "invalid_or_missing_decision",
        "chosen_option_id": completion_payload.get("decision_id", ""),
        "chosen_option_text": completion_payload.get("decision_text", ""),
        "estimated_moral_deltas": estimated_deltas,
        "next_encounter": "UNOBSERVED",
        "memory_capsule": choice_memory,
    }
    return pre_state, post_state, world_update


def build_control_decision(context: dict, completion_payload: dict, quality: dict, constitution_id: str) -> dict:
    has_options = bool(context["options"])
    invalid = bool(quality["invalid_decision_flag"] or quality["missing_decision_flag"])
    decision_failure = bool(quality["is_decision_failure"])
    noncanonical_output = bool(quality["is_noncanonical_output"])
    trace_leakage = bool(quality["trace_leakage_flag"])
    if has_options and invalid:
        route = "COMPILE_PROMPT"
    elif has_options and decision_failure:
        route = "TRM_ONLY"
    elif has_options:
        route = "TRM_PLUS_LLM"
    else:
        route = "LLM_DIRECT"

    mode = "connected"
    if route in {"TRM_ONLY", "COMPILE_PROMPT"}:
        mode = "degraded"

    decision_prompt_name = normalize_text(str(context.get("storyworld_title", "") or "storyworld_choice"))
    decision_prompt_name = decision_prompt_name.lower().replace(" ", "_")
    metrics = quality.get("metrics", {}) or {}
    return {
        "mode": mode,
        "drift_budget": 0.01 if mode != "connected" else 0.02,
        "retrieve_k": min(32, max(4, len(context["options"]) * 4 if has_options else 8)),
        "expert_id": "none" if route == "TRM_ONLY" else "slm_code_v1",
        "tool_caps": {"web": False, "spend_usd": 0},
        "introspection_flag": bool(noncanonical_output or decision_failure or invalid or metrics.get("uncertainty_hits", 0) > 0),
        "route": route,
        "intent": "storyworld_choice" if has_options else "general",
        "adapter_id": "none",
        "prompt_family": f"constitution_bridge_{decision_prompt_name or 'storyworld'}_v1",
        "compile_prompt": bool(route == "COMPILE_PROMPT"),
        "compile_adapter_stub": False,
        "regime_flags": {
            "format_mode": bool(has_options),
            "tool_mode": bool(has_options),
            "refusal_mode": bool(metrics.get("refusal_hits", 0) > 0),
            "hallucination_drift": bool(invalid or decision_failure),
            "trace_leakage": bool(trace_leakage),
            "noncanonical_output": bool(noncanonical_output),
        },
        "rationale": {
            "driver": "storyworld_options_present" if has_options else "direct_generation_path",
            "constitution_id": constitution_id,
            "decision_valid": str(bool(completion_payload["decision_valid"])).lower(),
            "decision_failure": str(bool(decision_failure)).lower(),
            "noncanonical_output": str(bool(noncanonical_output)).lower(),
        },
        "prompt_ast": {
            "intent": "storyworld_choice" if has_options else "general",
            "objective": (
                "Choose exactly one listed storyworld option and return a concise rationale "
                "that keeps the constitutional binding explicit."
            ),
            "constraints": [
                "Pick only from the listed option ids.",
                "Do not narrate hidden chain of thought.",
                "Return only the decision and rationale contract.",
            ],
            "format_contract": {
                "mode": "text",
                "schema_name": "storyworld_decision_v1",
                "strict_json": False,
            },
            "examples": [],
            "stop_rules": ["Stop after the rationale."],
            "tool_abi": {"storyworld": "fixed_option_list"},
            "style_knobs": {
                "constitution_id": constitution_id,
                "storyworld_title": context.get("storyworld_title", ""),
            },
        },
    }


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", normalize_text(text).lower())
    return cleaned.strip("_") or "unknown_storyworld"


def build_storyworld_ctrl_prompt(record: dict) -> str:
    storyworld = record["storyworld"]
    turn_span = record["source"].get("turn_span", "") or f"t{int(storyworld.get('turn_index', 0)):02d}"
    lines = [
        "<SWMD-CTRL>",
        f"E {storyworld['encounter_id']} turn={turn_span}",
        f"T {storyworld['title']}",
    ]
    for option in storyworld["options"]:
        lines.append(f"C{option['index']} {option['option_id']} -> unknown | O:{option['option_text']}")
    lines.append("</SWMD-CTRL>")
    return "\n".join(lines)


def build_selfmodel_router_row(record: dict) -> dict:
    oracle = record["oracle"]
    source = record["source"]
    storyworld = record["storyworld"]
    return {
        "input": {
            "intent": record["control_decision"]["intent"],
            "encounter_id": source.get("encounter_id", ""),
            "turn_span": source.get("turn_span", ""),
            "is_terminal": bool(source.get("is_terminal", False)),
            "prompt_text": oracle.get("user_prompt", ""),
            "prompt_chars": len(oracle.get("user_prompt", "")),
            "prompt_tokens_est": int(oracle.get("prompt_tokens", 0) or 0),
            "baseline_completion_tokens": 0,
            "adapter_completion_tokens": int(oracle.get("completion_tokens", 0) or 0),
            "response_changed": False,
            "top1_same": bool(record["quality"].get("has_valid_decision", False)),
            "score_delta_adapter_minus_baseline": 0.0,
            "adapter_available": False,
            "tool_required": bool(storyworld.get("options")),
            "storyworld_json": "",
            "model_path": source.get("model_id", ""),
            "adapter_path": "",
            "source_run_dir": source.get("run_dir", ""),
            "source_bench_rows": source.get("generation_file", ""),
            "timestamp_utc": source.get("timestamp_utc", ""),
        },
        "output": deepcopy(record["control_decision"]),
    }


def build_storyworld_controller_row(record: dict, include_k: bool = False) -> dict | None:
    quality = record["quality"]
    oracle = record["oracle"]
    storyworld = record["storyworld"]
    if not quality.get("has_valid_decision"):
        return None
    target = f"PICK {oracle['decision_index']}"
    if include_k:
        target += "\nK 1" if oracle.get("rationale") else "\nK 2"
    return {
        "input": build_storyworld_ctrl_prompt(record),
        "target": target,
        "meta": {
            "world_id": slugify(storyworld.get("title", "")),
            "swmd_hash": storyworld.get("prompt_hash", ""),
            "encounter_id": storyworld.get("encounter_id", ""),
            "turn_span": record["source"].get("turn_span", "") or f"t{int(storyworld.get('turn_index', 0)):02d}",
            "constitution_id": record["constitution"]["constitution_id"],
            "record_id": record["record_id"],
            "trace_root": record["receipts"]["trace_root"],
            "receipt_leaf": record["receipts"]["receipt_leaf"],
            "source_run": record["source"]["run_name"],
        },
    }


def build_storyworld_rollout_step_row(record: dict, episode_idx: int) -> dict | None:
    quality = record["quality"]
    oracle = record["oracle"]
    if not quality.get("has_valid_decision"):
        return None
    return {
        "episode": episode_idx,
        "turn": int(record["storyworld"].get("turn_index", 0)),
        "mode": "constitution_bridge",
        "encounter_id": record["storyworld"].get("encounter_id", ""),
        "label": f"PICK {oracle['decision_index']}",
        "state_hash": record["receipts"]["state_hash"],
        "receipt_leaf": record["receipts"]["receipt_leaf"],
        "next_encounter": record["world_update"].get("next_encounter", "UNOBSERVED"),
        "trace_root": record["receipts"]["trace_root"],
        "output_commitment": record["receipts"]["output_commitment"],
        "record_id": record["record_id"],
    }


def build_storyworld_rollout_episode_row(record: dict, episode_idx: int) -> dict | None:
    step_row = build_storyworld_rollout_step_row(record, episode_idx)
    if step_row is None:
        return None
    return {
        "episode": episode_idx,
        "mode": "constitution_bridge",
        "trace_root": record["receipts"]["trace_root"],
        "output_commitment": record["receipts"]["output_commitment"],
        "steps": [step_row],
        "step_count": 1,
        "final_node": record["world_update"].get("next_encounter", "UNOBSERVED"),
    }


def build_control_record(row: dict, run_dir: Path, source_file: Path, run_manifest: dict, episode_idx: int) -> dict:
    prompt_text = str(row.get("prompt_text", "") or "")
    context = parse_prompt_context(prompt_text)
    completion_payload = parse_completion_payload(row, context["options"])
    quality = build_quality_flags(row, completion_payload, bool(context["options"]))
    constitution_id = str(row.get("constitution_id", "") or "unknown")
    constitution_profile = get_constitution_profile(constitution_id)
    self_model_pre, self_model_post, world_update = build_self_model_states(context, completion_payload, constitution_id)
    control_decision = build_control_decision(context, completion_payload, quality, constitution_id)

    source = {
        "run_name": run_dir.name,
        "run_dir": str(run_dir),
        "generation_file": str(source_file),
        "source_path": str(row.get("source_path", "") or ""),
        "model_id": str(run_manifest.get("model_id", "") or ""),
        "runner_backend": str(run_manifest.get("runner_backend", "") or ""),
        "prompt_id": str(row.get("prompt_id", "") or ""),
        "encounter_id": str(row.get("encounter_id", "") or context["encounter_id"]),
        "turn_span": str(row.get("turn_span", "") or ""),
        "is_terminal": bool(row.get("is_terminal", False)),
        "timestamp_utc": str(row.get("timestamp_utc", "") or utc_now()),
        "prompt_contract_version": str(row.get("prompt_contract_version", "") or ""),
    }
    storyworld = {
        "title": context["storyworld_title"],
        "about": context["about_text"],
        "encounter_id": context["encounter_id"] or source["encounter_id"],
        "scene_text": context["scene_text"],
        "options": context["options"],
        "prior_diary_lines": context["prior_diary_lines"],
        "prior_diary_entries": context["prior_diary_entries"],
        "prior_diary_axes": context["prior_diary_axes"],
        "turn_index": context["turn_index"],
        "prompt_hash": context["prompt_hash"],
    }
    oracle = {
        "system_prompt": str(row.get("system_prompt", "") or ""),
        "user_prompt": prompt_text,
        "response_contract_version": source["prompt_contract_version"] or str(run_manifest.get("response_contract_version", "") or ""),
        "decision_id": completion_payload["decision_id"],
        "decision_index": completion_payload["decision_index"],
        "decision_text": completion_payload["decision_text"],
        "rationale": completion_payload["rationale"],
        "completion_text": completion_payload["canonical_text"] or completion_payload["sanitized_text"] or completion_payload["raw_text"],
        "raw_completion_text": completion_payload["raw_text"],
        "sanitized_completion_text": completion_payload["sanitized_text"],
        "has_reasoning_trace": bool(completion_payload.get("has_reasoning_trace", False)),
        "reasoning_trace": completion_payload.get("reasoning_trace", ""),
        "reasoning_trace_format": completion_payload.get("reasoning_trace_format", ""),
        "prompt_tokens": int(row.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(row.get("completion_tokens", 0) or 0),
        "latency_sec": float(row.get("latency_sec", 0.0) or 0.0),
    }

    state_hash = sha256_hex(
        stable_json(
            {
                "constitution_id": constitution_id,
                "storyworld": storyworld,
                "self_model_pre": self_model_pre,
            }
        )
    )
    output_hash = sha256_hex(
        stable_json(
            {
                "decision_id": oracle["decision_id"],
                "decision_index": oracle["decision_index"],
                "rationale": oracle["rationale"],
                "completion_text": oracle["completion_text"],
                "raw_completion_text": oracle["raw_completion_text"],
                "reasoning_trace": oracle["reasoning_trace"],
            }
        )
    )
    next_encounter = world_update.get("next_encounter", "UNOBSERVED") or "UNOBSERVED"
    next_hash = sha256_hex(stable_json({"next": next_encounter}))
    receipt_leaf = sha256_hex(
        f"SWMDR|bridge|{episode_idx}|{storyworld['turn_index']}|{state_hash}|{oracle['decision_index']}|{next_hash}"
    )
    trace_root = merkle_root_hex([receipt_leaf])
    output_commitment = sha256_hex(
        stable_json(
            {
                "episode": episode_idx,
                "mode": "constitution_bridge",
                "trace_root": trace_root,
                "label": f"PICK {oracle['decision_index']}" if quality["has_valid_decision"] else "INVALID",
                "final_node": next_encounter,
            }
        )
    )
    record_id = f"{run_dir.name}:{constitution_id}:{source['prompt_id'] or source['encounter_id']}:{episode_idx:06d}"
    record_leaf = sha256_hex(
        stable_json(
            {
                "record_id": record_id,
                "state_hash": state_hash,
                "output_hash": output_hash,
                "receipt_leaf": receipt_leaf,
            }
        )
    )

    return {
        "record_version": "constitution_control_record_v1",
        "record_id": record_id,
        "timestamp_utc": source["timestamp_utc"],
        "constitution": {
            "constitution_id": constitution_id,
            "binding_mode": "self_model_state",
            "principles": constitution_profile["principles"],
            "obligations": constitution_profile["obligations"],
            "prohibitions": constitution_profile["prohibitions"],
            "commitments": constitution_profile["commitments"],
        },
        "source": source,
        "storyworld": storyworld,
        "oracle": oracle,
        "control_decision": control_decision,
        "self_model_pre": self_model_pre,
        "self_model_post": self_model_post,
        "world_update": world_update,
        "receipts": {
            "state_hash": state_hash,
            "output_hash": output_hash,
            "receipt_leaf": receipt_leaf,
            "trace_root": trace_root,
            "output_commitment": output_commitment,
            "record_leaf": record_leaf,
        },
        "quality": quality,
    }


def summarize_control_records(records: List[dict]) -> dict:
    constitution_counts = Counter(record["constitution"]["constitution_id"] for record in records)
    route_counts = Counter(record["control_decision"]["route"] for record in records)
    storyworld_counts = Counter(record["storyworld"]["title"] or "unknown" for record in records)
    return {
        "records": len(records),
        "constitutions": dict(sorted(constitution_counts.items())),
        "routes": dict(sorted(route_counts.items())),
        "storyworlds": dict(sorted(storyworld_counts.items())),
        "low_quality_records": sum(1 for record in records if record["quality"]["is_low_quality"]),
        "decision_failure_records": sum(1 for record in records if record["quality"]["is_decision_failure"]),
        "noncanonical_output_records": sum(1 for record in records if record["quality"]["is_noncanonical_output"]),
        "trace_leakage_records": sum(1 for record in records if record["quality"]["has_reasoning_trace"]),
        "valid_decision_records": sum(1 for record in records if record["quality"]["has_valid_decision"]),
        "records_merkle_root": merkle_root_hex([record["receipts"]["record_leaf"] for record in records]),
    }
