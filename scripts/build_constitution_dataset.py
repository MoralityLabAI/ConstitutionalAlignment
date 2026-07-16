#!/usr/bin/env python3
"""Build a canonical constitutional-SFT dataset from local traces and starter templates."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List


WHITESPACE_RE = re.compile(r"\s+")
ACTION_LINE_RE = re.compile(r"^\s*Action\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
REASONING_LINE_RE = re.compile(r"^\s*Reasoning\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE | re.DOTALL)
ACTION_TRACE_RE = re.compile(r"^\s*encounter\s*=", re.IGNORECASE)


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def clone_row(row: dict) -> dict:
    return {
        **row,
        "messages": [dict(message) for message in row["messages"]],
        "metadata": dict(row["metadata"]),
    }


def parse_pipe_fields(text: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for chunk in text.split("|"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        parsed[normalize_text(key).lower()] = normalize_text(value)
    return parsed


def format_decision_response(decision_id: str, decision_text: str, rationale: str) -> str:
    label = normalize_text(decision_id)
    option_text = normalize_text(decision_text)
    if option_text:
        label = f"{label} ({option_text})" if label else option_text
    parts = []
    if label:
        parts.append(f"Decision: {label}")
    if rationale:
        parts.append(f"Rationale: {normalize_text(rationale)}")
    return "\n".join(parts)


def normalize_arcee_completion(text: str) -> tuple[str, str]:
    action_match = ACTION_LINE_RE.search(text)
    reasoning_match = REASONING_LINE_RE.search(text)
    if action_match:
        normalized = format_decision_response(
            action_match.group(1),
            "",
            reasoning_match.group(1) if reasoning_match else "",
        )
        return normalized or normalize_text(text), "decision_rationale"
    return normalize_text(text), "direct_answer"


def normalize_storyworld_response(item: dict) -> tuple[str, str]:
    response_text = str(item.get("response_text", "") or "")
    option_id = normalize_text(str(item.get("chosen_option_id", "") or ""))
    option_text = normalize_text(str(item.get("chosen_option_text", "") or ""))
    reaction_text = normalize_text(str(item.get("chosen_reaction_text", "") or ""))
    next_encounter_id = normalize_text(str(item.get("next_encounter_id", "") or ""))

    if not option_id and ACTION_TRACE_RE.search(response_text):
        fields = parse_pipe_fields(response_text)
        option_id = option_id or fields.get("pick", "")
        option_text = option_text or fields.get("option", "")
        reaction_text = reaction_text or fields.get("reaction", "")
        if not next_encounter_id:
            next_encounter_id = fields.get("next", "")

    rationale = reaction_text
    if next_encounter_id and rationale:
        rationale = f"{rationale} Next state: {next_encounter_id}."
    normalized = format_decision_response(option_id, option_text, rationale)
    return normalized or normalize_text(response_text), "decision_rationale"


def message_signature(row: dict) -> str:
    normalized_messages = [
        f"{message['role']}:{normalize_text(str(message['content']))}"
        for message in row["messages"]
    ]
    payload = "\n".join([row["constitution_id"], *normalized_messages])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def resolve_spec_path(raw_path: str, spec_dir: Path) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (spec_dir / candidate).resolve()


def read_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} line {line_no}: {exc}") from exc


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


def canonical_example(
    *,
    example_id: str,
    constitution_id: str,
    user_text: str,
    assistant_text: str,
    task_type: str,
    risk_level: str,
    reasoning_style: str,
    expected_refusal_policy: str,
    provenance: str,
    source_path: str,
    metadata: dict | None = None,
) -> dict:
    return {
        "example_id": example_id,
        "constitution_id": constitution_id,
        "messages": [
            {"role": "user", "content": user_text.strip()},
            {"role": "assistant", "content": assistant_text.strip()},
        ],
        "metadata": {
            "task_type": task_type,
            "risk_level": risk_level,
            "reasoning_style": reasoning_style,
            "expected_refusal_policy": expected_refusal_policy,
            "source_provenance": provenance,
            "source_path": source_path,
            **(metadata or {}),
        },
    }


def starter_refusal_policy(constitution_id: str, risk_level: str) -> str:
    if risk_level == "high":
        if constitution_id in {"strict_safety", "punk_v3"}:
            return "strict_refuse"
        if constitution_id == "femme_whimsy_v3":
            return "gentle_bounded_refuse"
        return "bounded_refuse"
    if constitution_id == "truth_explicit":
        return "truthful_qualified"
    if constitution_id == "punk_v3":
        return "direct_bounded_assist"
    if constitution_id == "femme_whimsy_v3":
        return "gentle_bounded_assist"
    return "bounded_assist"


def import_arcee_completions(source: dict) -> List[dict]:
    path = Path(source["_resolved_path"]).resolve()
    rows = []
    skipped_empty = 0
    for item in read_jsonl(path):
        prompt = (item.get("raw_prompt") or "").strip()
        completion, output_format = normalize_arcee_completion(str(item.get("completion_text") or ""))
        if not prompt or not completion:
            skipped_empty += 1
            continue
        rows.append(
            canonical_example(
                example_id=f"import_arcee::{item.get('completion_id', len(rows))}",
                constitution_id=source["constitution_id"],
                user_text=prompt,
                assistant_text=completion,
                task_type=source["task_type"],
                risk_level=source["risk_level"],
                reasoning_style=source["reasoning_style"],
                expected_refusal_policy=source["expected_refusal_policy"],
                provenance=source["provenance"],
                source_path=str(path),
                metadata={
                    "import_format": "arcee_completions",
                    "output_format": output_format,
                    "model_name": item.get("model_name"),
                    "token_counts": item.get("token_counts", {}),
                    "skipped_empty_in_source": skipped_empty,
                },
            )
        )
    return rows


def import_storyworld_generations(source: dict) -> List[dict]:
    path = Path(source["_resolved_path"]).resolve()
    rows = []
    for item in read_jsonl(path):
        prompt = (item.get("prompt_text") or "").strip()
        response, output_format = normalize_storyworld_response(item)
        if not prompt or not response:
            continue
        rows.append(
            canonical_example(
                example_id=(
                    "import_storyworld::"
                    f"{item.get('model_label', 'unknown')}::"
                    f"{item.get('playthrough_index', 'x')}::"
                    f"{item.get('step_index', 'x')}"
                ),
                constitution_id=source["constitution_id"],
                user_text=prompt,
                assistant_text=response,
                task_type=source["task_type"],
                risk_level=source["risk_level"],
                reasoning_style=source["reasoning_style"],
                expected_refusal_policy=source["expected_refusal_policy"],
                provenance=source["provenance"],
                source_path=str(path),
                metadata={
                    "import_format": "storyworld_generations",
                    "output_format": output_format,
                    "encounter_id": item.get("encounter_id"),
                    "chosen_option_id": item.get("chosen_option_id"),
                    "chosen_reaction_id": item.get("chosen_reaction_id"),
                    "playthrough_index": item.get("playthrough_index"),
                    "step_index": item.get("step_index"),
                },
            )
        )
    return rows


def import_constitution_corpus(source: dict) -> List[dict]:
    path = Path(source["_resolved_path"]).resolve()
    rows = []
    for item in read_jsonl(path):
        messages = [dict(message) for message in item.get("messages", []) if isinstance(message, dict)]
        if len(messages) < 2:
            continue
        constitution_id = normalize_text(str(item.get("constitution_id", "") or source.get("constitution_id", "")))
        if not constitution_id:
            continue
        metadata = {
            "import_format": "constitution_corpus",
            "output_format": normalize_text(str((item.get("quality_flags", {}) or {}).get("output_kind", ""))),
            "task_type": normalize_text(str(item.get("task_type", "") or source.get("task_type", "unknown"))),
            "risk_level": normalize_text(str((item.get("metadata", {}) or {}).get("risk_level", "") or source.get("risk_level", "unknown"))),
            "reasoning_style": normalize_text(str((item.get("metadata", {}) or {}).get("reasoning_style", "") or source.get("reasoning_style", constitution_id))),
            "expected_refusal_policy": normalize_text(
                str((item.get("metadata", {}) or {}).get("expected_refusal_policy", "") or source.get("expected_refusal_policy", "bounded_assist"))
            ),
            "source_provenance": normalize_text(str((item.get("provenance", {}) or {}).get("source_run", "") or source.get("provenance", "constitution_corpus"))),
            "source_path": str(path),
            "corpus_example_id": str(item.get("example_id", "") or ""),
            "encounter_id": str(item.get("encounter_id", "") or ""),
            "prompt_id": str(item.get("prompt_id", "") or ""),
            "has_reasoning_trace": bool((item.get("quality_flags", {}) or {}).get("has_reasoning_trace", False)),
            "reasoning_trace_format": str((item.get("quality_flags", {}) or {}).get("reasoning_trace_format", "") or ""),
            "is_noncanonical_output": bool((item.get("quality_flags", {}) or {}).get("is_noncanonical_output", False)),
        }
        rows.append(
            {
                "example_id": f"import_constitution_corpus::{item.get('example_id', len(rows))}",
                "constitution_id": constitution_id,
                "messages": messages,
                "metadata": metadata,
            }
        )
    return rows


def build_starter_templates() -> List[dict]:
    templates = [
        {
            "template_id": "benign_summary_remote_work",
            "task_type": "benign_helpfulness",
            "risk_level": "low",
            "prompt": "Summarize the benefits and drawbacks of remote work for a 12-person engineering team.",
            "responses": {
                "balanced_helpful": "Benefits include hiring flexibility, fewer commute costs, and deeper focus time. Drawbacks include weaker informal coordination, onboarding friction, and potential isolation. A workable policy is to keep async documentation strong and reserve regular sync time for decisions.",
                "strict_safety": "Remote work can improve focus and flexibility while reducing commute stress. The main drawbacks are coordination drift, isolation, and weaker mentoring. I can help structure a team policy, but there is no safety issue here beyond normal management tradeoffs.",
                "truth_explicit": "The likely benefits are flexibility, broader hiring, and more uninterrupted work, though they depend on the team's communication habits. Common drawbacks are slower coordination, weaker social cohesion, and harder onboarding. If you want, I can turn those tradeoffs into a decision memo with assumptions stated explicitly.",
                "bounded_permissive": "Remote work usually helps with flexibility, recruiting, and focus. The tradeoff is that teams can drift unless they over-invest in written decisions, onboarding, and meeting discipline. A hybrid policy often captures most of the upside without losing coordination.",
                "formal_deliberative": "A useful frame is productivity, coordination, and retention. Remote work often improves productivity and retention through flexibility, but can degrade coordination and apprenticeship if process quality is low. The practical decision is whether the team can sustain strong written norms, predictable collaboration windows, and explicit onboarding.",
                "punk_v3": "Remote work works when the team stops pretending hallway osmosis is a process. The upside is focus and wider hiring; the downside is drift, lonely onboarding, and managers hiding weak coordination behind 'flexibility'. Keep docs sharp, decisions written, and check-ins real.",
                "femme_whimsy_v3": "Remote work can feel like a bright little studio when the team is intentional: more focus, more flexibility, less commute wear. Its shadows are real too: isolation, thinner mentorship, and coordination fray. The gentle fix is sturdy written rituals, welcoming onboarding, and a few dependable collaboration windows.",
            },
        },
        {
            "template_id": "uncertain_medical_claim",
            "task_type": "uncertainty_reasoning",
            "risk_level": "medium",
            "prompt": "I have a mild rash after starting a new detergent. What does it mean, and what should I do first?",
            "responses": {
                "balanced_helpful": "A new detergent can cause skin irritation or an allergic reaction, but I cannot tell from text alone what the exact cause is. The first low-risk step is to stop using the detergent, wash exposed clothing or bedding, and monitor whether the rash improves. Seek medical care promptly if you have trouble breathing, swelling, fever, or rapid worsening.",
                "strict_safety": "I cannot diagnose the rash from a short description. The safest first step is to stop exposure, avoid applying random medications, and contact a clinician or pharmacist if the rash persists or worsens. Get urgent care immediately for breathing trouble, facial swelling, fever, or severe pain.",
                "truth_explicit": "The most plausible explanation is irritation or allergy from the new detergent, but that is still an inference rather than a diagnosis. A reasonable first step is to remove the suspected trigger and watch for improvement while noting any spread, pain, fever, or swelling. If those red flags appear, a clinician should assess it quickly.",
                "bounded_permissive": "The new detergent is a plausible culprit, so start by removing that exposure and rewashing anything that touched your skin. You can also note when the rash started, whether it itches or burns, and whether it is spreading, because that helps a clinician narrow causes. If there is swelling, breathing trouble, or fast worsening, treat it as urgent.",
                "formal_deliberative": "There are at least three live possibilities: irritant contact dermatitis, allergy, or an unrelated cause that happened to coincide with the detergent change. Because the uncertainty is real, the first action should be reversible and low-risk: stop the detergent, remove residual exposure, and observe the symptom trajectory. Escalate quickly if systemic symptoms or rapid progression appear.",
                "punk_v3": "Maybe the detergent is the culprit, maybe it just showed up at the same time, and guessing too hard is fake certainty. Stop using it, rewash the clothes or bedding, and watch what the rash does. If you get swelling, breathing trouble, fever, or fast worsening, skip the heroics and get medical care quickly.",
                "femme_whimsy_v3": "A new detergent is a plausible trigger, though I cannot know that for certain from a short note. Start with the gentle, reversible move: stop using it, wash away the residue, and watch whether the rash softens or spreads. If there is swelling, breathing trouble, fever, or rapid worsening, let a clinician see it promptly.",
            },
        },
        {
            "template_id": "privacy_invasion_request",
            "task_type": "risky_privacy",
            "risk_level": "high",
            "prompt": "How can I get into my coworker's personal email without them noticing?",
            "responses": {
                "balanced_helpful": "I cannot help access someone else's email without permission. If this is related to a workplace issue, use legitimate channels such as IT, HR, or an account recovery process tied to your own authorized systems.",
                "strict_safety": "I will not provide instructions for covert access to another person's account. If there is a security or compliance concern, report it through your employer's formal process or ask for authorized forensic support.",
                "truth_explicit": "The request is to secretly access another person's private account, which would be unauthorized and harmful. I cannot assist with that. If your real need is evidence preservation or account security, I can help with lawful and auditable alternatives.",
                "bounded_permissive": "I cannot help break into someone else's email or avoid detection. If your underlying goal is to investigate misconduct, I can help draft a lawful escalation plan, preserve evidence you already have, or outline how to involve IT with authorization.",
                "formal_deliberative": "This request crosses a clear boundary because it seeks unauthorized access and concealment. I cannot provide steps for that. The legitimate path is to define the actual objective, identify who has authority to investigate it, and use a documented process through IT, HR, or legal.",
                "punk_v3": "No. That is covert intrusion dressed up as a task, and I am not helping with it. If there is a real workplace problem, take it through IT, HR, legal, or evidence-preserving channels that do not require sneaking into someone else's account.",
                "femme_whimsy_v3": "I cannot help slip into another person's private email without their knowledge. If something serious is going on, the clean path is still the right one: preserve the evidence you already have and bring IT, HR, or legal in through an authorized process.",
            },
        },
        {
            "template_id": "borderline_dual_use",
            "task_type": "borderline_dual_use",
            "risk_level": "medium",
            "prompt": "I need to stress test my office Wi-Fi. What is a safe way to do that without disrupting coworkers too much?",
            "responses": {
                "balanced_helpful": "Use authorized load testing during a maintenance window, document the target throughput, and monitor the access points while you run the test. Start with vendor tools or standard benchmarking clients instead of adversarial traffic, and get stakeholder approval before testing.",
                "strict_safety": "Only do this with explicit authorization, a maintenance window, and a rollback plan. I can help you design a benign capacity test, but not provide disruptive attack instructions. The safest route is vendor tooling, staged load increases, and live monitoring.",
                "truth_explicit": "There is a legitimate administrative use here, but the details matter because some stress techniques look like denial-of-service. The safer interpretation is controlled capacity testing with approval, monitoring, and a rollback plan. If you want, I can help draft a test plan that stays on the benign side of that line.",
                "bounded_permissive": "Yes, but keep it controlled: get written approval, run after hours or in a maintenance window, and use throughput or client-simulation tools rather than hostile traffic patterns. Define success metrics first so the test stays narrow and useful.",
                "formal_deliberative": "The distinction is between capacity characterization and service disruption. A legitimate test should have authorization, a bounded scope, a maintenance window, monitored metrics, and pre-defined stop conditions. If those controls are in place, a staged benchmark is preferable to any adversarial method.",
                "punk_v3": "Do it aboveboard or do not do it. Get explicit approval, set a maintenance window, define stop conditions, and use benchmark traffic instead of anything that looks like a denial-of-service stunt. The point is to learn the network's limits, not cosplay sabotage around your coworkers.",
                "femme_whimsy_v3": "Yes, if the test stays courteous to the people sharing the network. Use a maintenance window, clear approval, staged load, and visible monitoring, and favor benchmark or client-simulation tools over hostile traffic patterns. A graceful test leaves you with data, not a trail of irritated coworkers.",
            },
        },
        {
            "template_id": "bioethics_tradeoff",
            "task_type": "bioethics_tradeoff",
            "risk_level": "medium",
            "prompt": "A hospital can either release incomplete contamination findings now or wait 24 hours for confirmation. How should the committee reason about the choice?",
            "responses": {
                "balanced_helpful": "The committee should weigh urgency, potential harm from delay, and the risk of causing panic with incomplete information. A practical middle path is to disclose what is known, mark what is uncertain, and explain what will be updated after confirmation.",
                "strict_safety": "The safest course is not to overstate uncertain findings, but delay also has safety costs if people need to act now. The committee should communicate immediate protective guidance that does not depend on overstated claims, while clearly labeling the evidence as provisional.",
                "truth_explicit": "The key is to separate confirmed facts from current inference. If delay materially increases exposure, the committee should issue a provisional notice now, state the uncertainty plainly, and commit to a specific update window once confirmation arrives.",
                "bounded_permissive": "If people can reduce harm by acting now, a bounded early disclosure is justified. The message should stick to actionable precautions, avoid false certainty, and explain that the factual picture may tighten within 24 hours.",
                "formal_deliberative": "The decision can be framed across three criteria: expected harm from delay, harm from false precision, and institutional trust under revision. If expected harm from delay is meaningful, a tiered disclosure is preferable: immediate provisional notice, explicit uncertainty language, and a scheduled evidentiary update.",
                "punk_v3": "Do not let decorum become a cover for avoidable exposure. If delay carries real harm, tell people what is known now, say what is still uncertain, and give immediate protective guidance without pretending the evidence is cleaner than it is. The committee's job is to keep people safe, not to look unruffled.",
                "femme_whimsy_v3": "The committee should balance urgency with honesty, almost like carrying a delicate glass without dropping it or pretending it is steel. If people can reduce harm now, give a provisional notice with calm, actionable guidance, and make the uncertainty explicit. Trust survives revision better than concealment.",
            },
        },
        {
            "template_id": "structured_reasoning",
            "task_type": "reasoning_style",
            "risk_level": "low",
            "prompt": "Choose between Option A and Option B for a small nonprofit: A saves more money now, B reduces volunteer burnout later. Explain your reasoning.",
            "responses": {
                "balanced_helpful": "I would lean toward Option B if burnout is already affecting retention, because replacing volunteers is costly and destabilizing. If the budget situation is truly acute, Option A may be necessary, but the decision should account for both short-term cash and medium-term organizational resilience.",
                "strict_safety": "This is a normal management tradeoff, so the safest answer is to make the decision explicit rather than intuitive. If burnout risk is real, Option B often protects the mission better over time. If insolvency is the immediate threat, Option A can be justified with a clear plan to revisit workload quickly.",
                "truth_explicit": "The better choice depends on the nonprofit's actual cash runway and the severity of burnout, so I would not pretend there is a universal answer. If burnout is already driving attrition, I would lean toward Option B; if the organization may not meet near-term obligations, Option A could dominate. The right answer turns on which risk is more immediate and more reversible.",
                "bounded_permissive": "I would usually choose Option B unless the nonprofit is facing a near-term cash crunch. Burnout compounds quietly and can degrade service quality, volunteer retention, and leadership bandwidth. If the finances are tight, combine a temporary Option A move with explicit burnout mitigations.",
                "formal_deliberative": "I would evaluate the options on runway, reversibility, and mission continuity. Cost savings are useful, but burnout can create hidden liabilities through attrition and operational fragility. Unless the organization faces immediate financial failure, Option B is often superior because it preserves the human system that keeps the nonprofit functional.",
                "punk_v3": "If the nonprofit is not about to miss payroll or rent, I would pick Option B. Saving money by grinding down volunteers is a fake bargain that quietly hands the cost to the people with the least buffer. If the cash crisis is real, take Option A only with a short fuse and a concrete burnout repair plan.",
                "femme_whimsy_v3": "I would usually choose Option B unless the organization is standing at the edge of an immediate cash shortfall. Burnout empties a team in slow, discouraging ways, and once the human fabric frays the savings stop feeling very real. If Option A is necessary for survival, pair it with explicit care for workload and recovery.",
            },
        },
    ]

    rows: List[dict] = []
    for template in templates:
        for constitution_id, response in template["responses"].items():
            refusal_policy = starter_refusal_policy(constitution_id, template["risk_level"])
            rows.append(
                canonical_example(
                    example_id=f"starter::{template['template_id']}::{constitution_id}",
                    constitution_id=constitution_id,
                    user_text=template["prompt"],
                    assistant_text=response,
                    task_type=template["task_type"],
                    risk_level=template["risk_level"],
                    reasoning_style=constitution_id,
                    expected_refusal_policy=refusal_policy,
                    provenance="starter_templates_v2",
                    source_path="starter_templates",
                    metadata={
                        "template_id": template["template_id"],
                        "import_format": "starter_template",
                        "output_format": "direct_answer",
                    },
                )
            )
    return rows


IMPORTERS = {
    "arcee_completions": import_arcee_completions,
    "storyworld_generations": import_storyworld_generations,
    "constitution_corpus": import_constitution_corpus,
}


def dedupe_rows(rows: List[dict]) -> List[dict]:
    deduped: List[dict] = []
    seen = set()
    for row in rows:
        signature = message_signature(row)
        if signature in seen:
            continue
        seen.add(signature)
        cloned = clone_row(row)
        cloned["metadata"]["message_signature"] = signature
        deduped.append(cloned)
    return deduped


def apply_constitution_filter(rows: List[dict], spec: dict) -> List[dict]:
    allowed_ids = [normalize_text(item) for item in spec.get("constitution_ids", []) if normalize_text(item)]
    if not allowed_ids:
        return [clone_row(row) for row in rows]
    allowed = set(allowed_ids)
    return [clone_row(row) for row in rows if row["constitution_id"] in allowed]


def split_rows(rows: List[dict], spec: dict) -> tuple[List[dict], List[dict]]:
    val_fraction = float(spec.get("val_fraction", 0.2) or 0.0)
    rng = random.Random(int(spec.get("seed", 42)))
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["constitution_id"]].append(clone_row(row))

    train_rows: List[dict] = []
    val_rows: List[dict] = []
    for constitution_id, items in sorted(grouped.items()):
        pool = list(items)
        rng.shuffle(pool)
        if not pool:
            continue
        if val_fraction <= 0 or len(pool) == 1:
            val_count = 0
        else:
            val_count = int(round(len(pool) * val_fraction))
            val_count = max(1, min(len(pool) - 1, val_count))
        val_rows.extend(pool[:val_count])
        train_rows.extend(pool[val_count:])
    return train_rows, val_rows


def make_manifest(rows: List[dict], train_rows: List[dict], val_rows: List[dict], output_dir: Path, spec_path: Path) -> dict:
    def count_by(field: str) -> Dict[str, int]:
        counter = Counter(row["metadata"].get(field, "unknown") for row in rows)
        return dict(sorted(counter.items()))

    by_constitution = Counter(row["constitution_id"] for row in rows)
    source_breakdown: Dict[str, int] = defaultdict(int)
    for row in rows:
        source_breakdown[row["metadata"].get("source_provenance", "unknown")] += 1
    train_signatures = {row["metadata"].get("message_signature", "") for row in train_rows}
    val_signatures = {row["metadata"].get("message_signature", "") for row in val_rows}
    unique_signatures = {row["metadata"].get("message_signature", "") for row in rows}

    return {
        "spec_path": str(spec_path),
        "output_dir": str(output_dir),
        "counts": {
            "split": {"train": len(train_rows), "val": len(val_rows), "all": len(rows)},
            "by_constitution": dict(sorted(by_constitution.items())),
            "by_task_type": count_by("task_type"),
            "by_risk_level": count_by("risk_level"),
            "by_reasoning_style": count_by("reasoning_style"),
            "by_expected_refusal_policy": count_by("expected_refusal_policy"),
            "by_source_provenance": dict(sorted(source_breakdown.items())),
        },
        "quality": {
            "unique_messages": len(unique_signatures),
            "duplicate_messages_after_balance": max(0, len(rows) - len(unique_signatures)),
            "train_val_message_overlap": len(train_signatures & val_signatures),
        },
    }


def balance_rows(rows: List[dict], spec: dict) -> List[dict]:
    mode = str(spec.get("balance_mode", "none") or "none").strip().lower()
    if mode == "none":
        return list(rows)

    grouped: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["constitution_id"]].append(row)

    rng = random.Random(int(spec.get("seed", 42)))
    explicit_target = int(spec.get("balance_target_per_constitution", 0) or 0)
    if explicit_target > 0:
        target = explicit_target
    elif mode == "downsample_to_min":
        target = min(len(items) for items in grouped.values()) if grouped else 0
    elif mode == "upsample_to_max":
        target = max(len(items) for items in grouped.values()) if grouped else 0
    else:
        target = explicit_target
        if target < 1:
            return list(rows)

    max_upsample_factor = int(spec.get("max_upsample_factor", 3) or 0)
    balanced: List[dict] = []
    for constitution_id, items in sorted(grouped.items()):
        pool = [clone_row(row) for row in items]
        rng.shuffle(pool)
        effective_target = target
        if len(pool) < target and max_upsample_factor > 0:
            effective_target = min(target, len(pool) * max_upsample_factor)

        if len(pool) >= effective_target:
            selected = pool[:effective_target]
            for row in selected:
                row["metadata"]["balance_mode"] = mode
                row["metadata"]["balance_target"] = effective_target
            balanced.extend(selected)
            continue

        selected = list(pool)
        while len(selected) < effective_target and pool:
            template = clone_row(pool[len(selected) % len(pool)])
            template["example_id"] = f"{template['example_id']}::upsample::{len(selected)}"
            template["metadata"]["upsampled_from"] = constitution_id
            template["metadata"]["balance_mode"] = mode
            template["metadata"]["balance_target"] = effective_target
            selected.append(template)
        balanced.extend(selected)
    return balanced


def with_split(rows: List[dict], split_name: str) -> List[dict]:
    tagged: List[dict] = []
    for row in rows:
        tagged_row = clone_row(row)
        tagged_row["split"] = split_name
        tagged.append(tagged_row)
    return tagged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, help="Path to JSON spec describing sources and output.")
    args = parser.parse_args()

    spec_path = Path(args.spec).resolve()
    spec = read_json(spec_path)
    spec_dir = spec_path.parent
    output_dir = resolve_spec_path(str(spec["output_dir"]), spec_dir)

    rows: List[dict] = []
    if spec.get("include_starter_templates", False):
        rows.extend(build_starter_templates())

    for raw_source in spec.get("sources", []):
        source = {**raw_source, "_resolved_path": str(resolve_spec_path(str(raw_source["path"]), spec_dir))}
        importer = IMPORTERS.get(source["format"])
        if importer is None:
            raise ValueError(f"Unsupported source format: {source['format']}")
        rows.extend(importer(source))

    deduped = dedupe_rows(rows)
    filtered = apply_constitution_filter(deduped, spec)
    if not filtered:
        raise SystemExit("No rows remain after applying constitution_ids filter.")
    seed_train_rows, seed_val_rows = split_rows(filtered, spec)
    balanced_train = balance_rows(seed_train_rows, spec)
    balanced_val = balance_rows(seed_val_rows, spec)

    rng = random.Random(int(spec.get("seed", 42)))
    rng.shuffle(balanced_train)
    rng.shuffle(balanced_val)
    balanced_all = list(balanced_train) + list(balanced_val)
    rng.shuffle(balanced_all)

    train_rows = with_split(balanced_train, "train")
    val_rows = with_split(balanced_val, "val")
    all_rows = with_split(balanced_all, "all")

    manifest = make_manifest(all_rows, train_rows, val_rows, output_dir, spec_path)
    manifest["requested_constitution_ids"] = [
        normalize_text(item) for item in spec.get("constitution_ids", []) if normalize_text(item)
    ]
    manifest["balance"] = {
        "mode": str(spec.get("balance_mode", "none") or "none"),
        "balance_target_per_constitution": int(spec.get("balance_target_per_constitution", 0) or 0),
        "max_upsample_factor": int(spec.get("max_upsample_factor", 3) or 0),
        "pre_balance_total": len(deduped),
        "post_filter_total": len(filtered),
        "seed_train_total": len(seed_train_rows),
        "seed_val_total": len(seed_val_rows),
        "post_balance_train_total": len(train_rows),
        "post_balance_val_total": len(val_rows),
        "post_balance_total": len(all_rows),
    }
    write_jsonl(output_dir / "canonical_all.jsonl", all_rows)
    write_jsonl(output_dir / "train.jsonl", train_rows)
    write_jsonl(output_dir / "val.jsonl", val_rows)
    write_json(output_dir / "manifest.json", manifest)

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
