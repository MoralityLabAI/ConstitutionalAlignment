"""Auditable GRPO proxy rewards for public constitutional reflection.

These functions optimize observable response properties. They are not a
constitutional-compliance instrument and must not be reported as one.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


FIELD_RE = re.compile(
    r"^\s*(Decision|Reflection|Tenets defended|Counterpressure|Constitutional defense)\s*:\s*(.*)$",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"[a-z][a-z0-9_'-]*", re.IGNORECASE)
CAUSAL_MARKERS = ("because", "therefore", "so that", "given", "while", "although", "despite", "on balance")
CITATION_MARKERS = ("quran", "surah", "ayah", "verse", "tafsir", "hadith", "fiqh")
EXPECTED_ORDER = ("decision", "reflection", "tenets_defended", "counterpressure", "constitutional_defense")
STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
TENET_SIGNAL_TERMS: dict[str, tuple[str, ...]] = {
    "adl": ("just", "fair", "equal", "unequal", "right", "oppress", "exploit", "coerc"),
    "aql": ("reason", "evidence", "uncertain", "assum", "reflect", "tradeoff", "criteria"),
    "sidq": ("truth", "fact", "honest", "dece", "mislead", "conceal", "disclos", "record"),
    "ihsan": ("benefit", "good", "excellent", "practical", "construct", "repair"),
    "amanah": ("trust", "duty", "respons", "entrust", "procedure", "account", "commit"),
    "rahmah": ("mercy", "compassion", "care", "dignity", "vulnerable", "protect", "harm"),
}


@dataclass(frozen=True)
class ParsedResponse:
    decision: str
    reflection: str
    tenets_defended: tuple[str, ...]
    counterpressure: str
    constitutional_defense: str
    seen_fields: tuple[str, ...]
    duplicate_fields: tuple[str, ...]
    unstructured_prefix: str


def _field_key(label: str) -> str:
    return label.lower().replace(" ", "_")


def completion_text(completion: Any) -> str:
    if isinstance(completion, str):
        return completion
    if isinstance(completion, list):
        parts = []
        for message in completion:
            if isinstance(message, dict) and message.get("role") == "assistant":
                parts.append(str(message.get("content", "") or ""))
        if parts:
            return "\n".join(parts)
    if isinstance(completion, dict):
        return str(completion.get("content", "") or "")
    return str(completion or "")


def parse_response(completion: Any) -> ParsedResponse:
    text = completion_text(completion).strip()
    values: dict[str, list[str]] = {}
    seen: list[str] = []
    duplicates: list[str] = []
    prefix: list[str] = []
    active = ""
    for line in text.splitlines():
        match = FIELD_RE.match(line)
        if match:
            active = _field_key(match.group(1))
            if active in values:
                duplicates.append(active)
            else:
                values[active] = []
                seen.append(active)
            values[active].append(match.group(2).strip())
        elif active:
            values[active].append(line.strip())
        elif line.strip():
            prefix.append(line.strip())

    def value(key: str) -> str:
        return " ".join(part for part in values.get(key, []) if part).strip()

    raw_tenets = value("tenets_defended")
    tenets = tuple(
        item.strip().lower()
        for item in re.split(r"[,;]", raw_tenets)
        if item.strip()
    )
    return ParsedResponse(
        decision=value("decision").split(" ", 1)[0],
        reflection=value("reflection"),
        tenets_defended=tenets,
        counterpressure=value("counterpressure"),
        constitutional_defense=value("constitutional_defense"),
        seen_fields=tuple(seen),
        duplicate_fields=tuple(duplicates),
        unstructured_prefix=" ".join(prefix),
    )


def _words(text: str) -> list[str]:
    return [word.lower() for word in WORD_RE.findall(text)]


def _as_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {item.strip().lower() for item in value.split(",") if item.strip()}
    if isinstance(value, Iterable):
        return {str(item).strip().lower() for item in value if str(item).strip()}
    return set()


def _column(kwargs: dict[str, Any], name: str, size: int) -> list[Any]:
    value = kwargs.get(name)
    if isinstance(value, list) and len(value) == size:
        return value
    return [value for _ in range(size)]


def response_contract_score(parsed: ParsedResponse) -> float:
    if parsed.duplicate_fields or parsed.unstructured_prefix:
        return -1.0
    if tuple(parsed.seen_fields) != EXPECTED_ORDER:
        return -0.75
    if not all(
        [
            parsed.decision,
            parsed.reflection,
            parsed.tenets_defended,
            parsed.counterpressure,
            parsed.constitutional_defense,
        ]
    ):
        return -0.5
    return 1.0


def valid_decision_score(parsed: ParsedResponse, valid_options: Any) -> float:
    valid = _as_set(valid_options)
    if not parsed.decision:
        return -1.0
    if not valid:
        return -0.5
    return 1.0 if parsed.decision.lower() in valid else -1.0


def tenet_grounding_score(parsed: ParsedResponse, allowed_tenets: Any, relevant_tenets: Any) -> float:
    claimed = set(parsed.tenets_defended)
    allowed = _as_set(allowed_tenets)
    relevant = _as_set(relevant_tenets)
    if not claimed:
        return -1.0
    unknown = claimed - allowed
    if unknown:
        return -1.0
    if len(claimed) > 3:
        return -0.5
    overlap = claimed & relevant
    if not overlap:
        return 0.0
    precision = len(overlap) / len(claimed)
    recall = len(overlap) / max(1, min(2, len(relevant)))
    return min(1.0, 0.5 * precision + 0.5 * recall)


def reflective_defense_score(parsed: ParsedResponse) -> float:
    reflection_words = _words(parsed.reflection)
    counter_words = _words(parsed.counterpressure)
    defense_words = _words(parsed.constitutional_defense)
    score = 0.0
    score += 0.25 if 20 <= len(reflection_words) <= 60 else -0.15
    score += 0.20 if 8 <= len(counter_words) <= 30 else -0.15
    score += 0.20 if 10 <= len(defense_words) <= 40 else -0.15
    combined = f"{parsed.reflection} {parsed.counterpressure} {parsed.constitutional_defense}".lower()
    score += 0.20 if any(marker in combined for marker in CAUSAL_MARKERS) else -0.10
    claimed_mentions = sum(
        1
        for tenet in parsed.tenets_defended
        if tenet in parsed.constitutional_defense.lower()
    )
    score += 0.15 if claimed_mentions else -0.10
    return max(-1.0, min(1.0, score))


def action_defense_consistency_score(
    parsed: ParsedResponse,
    valid_option_ids: Any,
    valid_option_texts: Any,
) -> float:
    option_ids = (
        list(valid_option_ids)
        if isinstance(valid_option_ids, Iterable) and not isinstance(valid_option_ids, str)
        else []
    )
    option_texts = (
        list(valid_option_texts)
        if isinstance(valid_option_texts, Iterable) and not isinstance(valid_option_texts, str)
        else []
    )
    if len(option_ids) != len(option_texts) or parsed.decision not in {str(item).lower() for item in option_ids}:
        return -1.0
    selected_index = next(
        index
        for index, item in enumerate(option_ids)
        if str(item).lower() == parsed.decision.lower()
    )
    selected_terms = set(_words(str(option_texts[selected_index]))) - STOPWORDS
    defense_text = f"{parsed.reflection} {parsed.constitutional_defense}".lower()
    defense_terms = set(_words(defense_text))
    option_overlap = selected_terms & defense_terms
    option_coverage = min(1.0, len(option_overlap) / max(1, min(2, len(selected_terms))))

    evidenced_tenets = 0
    for tenet_id in parsed.tenets_defended:
        terms = TENET_SIGNAL_TERMS.get(tenet_id, ())
        if any(term in defense_text for term in terms):
            evidenced_tenets += 1
    tenet_evidence = evidenced_tenets / max(1, len(parsed.tenets_defended))

    counter_terms = set(_words(parsed.counterpressure)) - STOPWORDS
    competing_terms = set()
    for index, text in enumerate(option_texts):
        if index != selected_index:
            competing_terms.update(set(_words(str(text))) - STOPWORDS)
    counter_overlap = 1.0 if counter_terms & competing_terms else 0.0
    if option_coverage == 0.0 and tenet_evidence == 0.0:
        return -0.5
    return min(1.0, 0.5 * option_coverage + 0.3 * tenet_evidence + 0.2 * counter_overlap)


def anti_gaming_score(parsed: ParsedResponse, completion: Any) -> float:
    text = completion_text(completion)
    words = _words(text)
    penalty = 0.0
    if len(words) > 120:
        penalty += min(1.0, (len(words) - 120) / 60)
    if "<think" in text.lower() or "</think" in text.lower():
        penalty += 1.0
    if any(marker in text.lower() for marker in CITATION_MARKERS) or re.search(r"\b\d{1,3}:\d{1,3}\b", text):
        penalty += 0.75
    trigrams = [tuple(words[index : index + 3]) for index in range(max(0, len(words) - 2))]
    if trigrams:
        most_common = Counter(trigrams).most_common(1)[0][1]
        if most_common >= 4:
            penalty += min(0.75, (most_common - 3) * 0.2)
    return max(-1.0, 0.5 - penalty)


def score_response(
    completion: Any,
    *,
    valid_option_ids: Any,
    valid_option_texts: Any,
    allowed_tenet_ids: Any,
    relevant_tenet_ids: Any,
) -> dict[str, float]:
    parsed = parse_response(completion)
    return {
        "response_contract": response_contract_score(parsed),
        "valid_decision": valid_decision_score(parsed, valid_option_ids),
        "tenet_grounding": tenet_grounding_score(parsed, allowed_tenet_ids, relevant_tenet_ids),
        "reflective_defense": reflective_defense_score(parsed),
        "action_defense_consistency": action_defense_consistency_score(
            parsed,
            valid_option_ids,
            valid_option_texts,
        ),
        "anti_gaming": anti_gaming_score(parsed, completion),
    }


def response_contract_reward(completions: Sequence[Any], **kwargs: Any) -> list[float]:
    return [response_contract_score(parse_response(completion)) for completion in completions]


def valid_decision_reward(completions: Sequence[Any], **kwargs: Any) -> list[float]:
    options = _column(kwargs, "valid_option_ids", len(completions))
    return [valid_decision_score(parse_response(completion), valid) for completion, valid in zip(completions, options)]


def tenet_grounding_reward(completions: Sequence[Any], **kwargs: Any) -> list[float]:
    allowed = _column(kwargs, "allowed_tenet_ids", len(completions))
    relevant = _column(kwargs, "relevant_tenet_ids", len(completions))
    return [
        tenet_grounding_score(parse_response(completion), allowed_ids, relevant_ids)
        for completion, allowed_ids, relevant_ids in zip(completions, allowed, relevant)
    ]


def reflective_defense_reward(completions: Sequence[Any], **kwargs: Any) -> list[float]:
    return [reflective_defense_score(parse_response(completion)) for completion in completions]


def action_defense_consistency_reward(completions: Sequence[Any], **kwargs: Any) -> list[float]:
    option_ids = _column(kwargs, "valid_option_ids", len(completions))
    option_texts = _column(kwargs, "valid_option_texts", len(completions))
    return [
        action_defense_consistency_score(parse_response(completion), ids, texts)
        for completion, ids, texts in zip(completions, option_ids, option_texts)
    ]


def anti_gaming_reward(completions: Sequence[Any], **kwargs: Any) -> list[float]:
    return [anti_gaming_score(parse_response(completion), completion) for completion in completions]


REWARD_FUNCTIONS = (
    response_contract_reward,
    valid_decision_reward,
    tenet_grounding_reward,
    reflective_defense_reward,
    action_defense_consistency_reward,
    anti_gaming_reward,
)
REWARD_NAMES = tuple(function.__name__ for function in REWARD_FUNCTIONS)
DEFAULT_REWARD_WEIGHTS = (1.0, 1.5, 1.25, 1.25, 1.25, 1.0)
