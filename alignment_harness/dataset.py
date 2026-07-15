"""Build auditable conditioning and GRPO datasets from storyworld decisions."""

from __future__ import annotations

import fnmatch
import glob
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .constitution import Constitution


RECORD_VERSION = "alignment_conditioning_record_v1"
WHITESPACE_RE = re.compile(r"\s+")
OPTION_RE = re.compile(r"^\s*-\s*(\S+)\s*:\s*(.+?)\s*$", re.MULTILINE)
DECISION_RE = re.compile(r"^\s*(?:Decision|Action)\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
RATIONALE_RE = re.compile(
    r"^\s*(?:Rationale|Reasoning|Reflection)\s*:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
ID_NOISE_RE = re.compile(r"\b(?:opt_)?page_[a-z0-9_]+|\b\d{2,}\b", re.IGNORECASE)
WORD_RE = re.compile(r"[a-z][a-z0-9_'-]*", re.IGNORECASE)
TENSION_MARKERS = (
    "but",
    "though",
    "however",
    "tradeoff",
    "competing",
    "uncertain",
    "uncertainty",
    "risk",
    "instead",
    "while",
)
STAKES_MARKERS = (
    "harm",
    "vulnerable",
    "justice",
    "truth",
    "deception",
    "coercion",
    "trust",
    "duty",
    "responsib",
    "welfare",
    "rights",
    "consequence",
    "risk",
)
TENET_TERMS: dict[str, tuple[str, ...]] = {
    "adl": ("justice", "fair", "equity", "rights", "oppress", "exploit", "coerc"),
    "aql": ("reason", "evidence", "uncertain", "assumption", "reflect", "tradeoff", "criteria"),
    "sidq": ("truth", "fact", "honest", "deceiv", "mislead", "conceal", "disclos", "record"),
    "ihsan": ("benefit", "good", "excellent", "practical", "constructive", "repair"),
    "amanah": ("trust", "duty", "responsib", "entrust", "procedure", "accountab", "commit"),
    "rahmah": ("mercy", "compassion", "care", "dignity", "vulnerable", "protect", "harm"),
}
EVALUATION_ONLY_SPLITS = {"eval", "evaluation", "heldout", "held_out", "test"}


def normalize_text(value: Any) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "")).strip()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_text_file_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return sha256_text(text)


def portable_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    root = repo_root.resolve()
    return resolved.relative_to(root).as_posix() if resolved.is_relative_to(root) else resolved.as_posix()


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL in {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row in {path}:{line_no} must be an object")
            yield row


def parse_pipe_fields(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in value.split("|"):
        if "=" not in item:
            continue
        key, content = item.split("=", 1)
        parsed[normalize_text(key).lower()] = normalize_text(content)
    return parsed


def parse_options(prompt: str) -> list[dict[str, str]]:
    return [
        {"option_id": normalize_text(match.group(1)), "option_text": normalize_text(match.group(2))}
        for match in OPTION_RE.finditer(prompt)
    ]


def parse_completion(text: str) -> tuple[str, str]:
    fields = parse_pipe_fields(text)
    if fields.get("pick"):
        return fields["pick"], fields.get("reaction", "")
    decision = DECISION_RE.search(text)
    rationale = RATIONALE_RE.search(text)
    decision_id = normalize_text(decision.group(1)).split(" ", 1)[0] if decision else ""
    return decision_id, normalize_text(rationale.group(1)) if rationale else ""


def extract_scene(prompt: str) -> str:
    marker = re.search(r"(?:^|\n)Scene:\s*\n?", prompt, re.IGNORECASE)
    if not marker:
        return ""
    tail = prompt[marker.end() :]
    return normalize_text(re.split(r"\n\s*Choose one option", tail, maxsplit=1, flags=re.IGNORECASE)[0])


def extract_public_reflection(row: dict[str, Any], completion: str) -> str:
    for key in ("chosen_reaction_text", "rationale", "public_reflection"):
        value = normalize_text(row.get(key, ""))
        if value:
            return value
    return parse_completion(completion)[1]


def source_token_count(row: dict[str, Any]) -> int:
    if isinstance(row.get("oracle"), dict):
        oracle = row["oracle"]
        return int(oracle.get("prompt_tokens", 0) or 0) + int(oracle.get("completion_tokens", 0) or 0)
    if isinstance(row.get("generation"), dict):
        generation = row["generation"]
        return int(generation.get("prompt_tokens", 0) or 0) + int(generation.get("completion_tokens", 0) or 0)
    return int(row.get("prompt_tokens", 0) or 0) + int(row.get("completion_tokens", 0) or 0)


def source_split_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if "source_split" in row:
        metadata["source_split"] = normalize_text(row.get("source_split")).lower()
    if "training_eligible" in row:
        value = row.get("training_eligible")
        if not isinstance(value, bool):
            raise ValueError("training_eligible must be a JSON boolean when present")
        metadata["training_eligible"] = value
    for key in (
        "scenario_group_id",
        "source_pack_id",
        "source_repo_url",
        "source_commit",
        "source_storyworld_path",
        "source_storyworld_sha256",
        "source_adjudication_sha256",
        "adjudication_status",
    ):
        if key in row and normalize_text(row.get(key)):
            metadata[key] = normalize_text(row.get(key))
    if "option_permutation" in row:
        metadata["option_permutation"] = int(row.get("option_permutation", 0) or 0)
    if "needs_scholar_review" in row:
        metadata["source_needs_scholar_review"] = bool(row.get("needs_scholar_review"))
    return metadata


@dataclass
class Candidate:
    source_format: str
    source_path: Path
    source_id: str
    source_constitution_id: str
    prompt: str
    scene: str
    options: list[dict[str, str]]
    decision_id: str
    decision_text: str
    public_reflection: str
    hidden_trace_present: bool
    reasoning_marker_present: bool
    source_tokens: int
    quality_pass: bool
    moral_deltas: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def _decision_text(decision_id: str, options: Sequence[dict[str, str]], explicit: Any = "") -> str:
    value = normalize_text(explicit)
    if value:
        return value
    return next((item["option_text"] for item in options if item["option_id"] == decision_id), "")


def candidate_from_control(row: dict[str, Any], path: Path) -> Candidate:
    oracle = row.get("oracle", {}) or {}
    source = row.get("source", {}) or {}
    storyworld = row.get("storyworld", {}) or {}
    constitution = row.get("constitution", {}) or {}
    quality = row.get("quality", {}) or {}
    world_update = row.get("world_update", {}) or {}
    prompt = str(oracle.get("user_prompt", "") or "")
    options = [
        {"option_id": normalize_text(item.get("option_id")), "option_text": normalize_text(item.get("option_text"))}
        for item in storyworld.get("options", [])
        if isinstance(item, dict) and normalize_text(item.get("option_id"))
    ]
    decision_id = normalize_text(oracle.get("decision_id"))
    raw_deltas = world_update.get("estimated_moral_deltas", {}) or {}
    deltas = {str(key): float(value) for key, value in raw_deltas.items() if isinstance(value, (int, float))}
    return Candidate(
        source_format="control_record_v1",
        source_path=path,
        source_id=normalize_text(row.get("record_id")) or sha256_text(stable_json(row)),
        source_constitution_id=normalize_text(constitution.get("constitution_id")) or "unknown",
        prompt=prompt,
        scene=normalize_text(storyworld.get("scene_text")) or extract_scene(prompt),
        options=options,
        decision_id=decision_id,
        decision_text=_decision_text(decision_id, options, oracle.get("decision_text")),
        public_reflection=normalize_text(oracle.get("rationale")),
        hidden_trace_present=bool(normalize_text(oracle.get("reasoning_trace"))),
        reasoning_marker_present=bool(quality.get("has_reasoning_trace")),
        source_tokens=source_token_count(row),
        quality_pass=bool(quality.get("has_valid_decision", decision_id))
        and not bool(quality.get("is_low_quality", False)),
        moral_deltas=deltas,
        metadata={
            "source_model_id": normalize_text(source.get("model_id")),
            "source_prompt_id": normalize_text(source.get("prompt_id")),
            "source_encounter_id": normalize_text(source.get("encounter_id")),
        },
    )


def candidate_from_generation(row: dict[str, Any], path: Path) -> Candidate:
    prompt = str(row.get("prompt_text") or row.get("generation_prompt_text") or "")
    completion = str(
        row.get("completion_sanitized_text")
        or row.get("completion_canonical_text")
        or row.get("completion_text")
        or row.get("response_text")
        or ""
    )
    options = parse_options(prompt)
    parsed_id, parsed_reflection = parse_completion(completion)
    decision_id = normalize_text(row.get("chosen_option_id")) or parsed_id
    reflection = extract_public_reflection(row, completion) or parsed_reflection
    metrics = row.get("metrics", {}) or {}
    valid_ids = {item["option_id"] for item in options}
    quality_pass = bool(decision_id) and (not valid_ids or decision_id in valid_ids)
    quality_pass = quality_pass and not bool(metrics.get("decision_failure_flag", 0))
    return Candidate(
        source_format="storyworld_generation",
        source_path=path,
        source_id=(
            normalize_text(row.get("prompt_id"))
            or "::".join(
                [
                    normalize_text(row.get("model_label")),
                    normalize_text(row.get("playthrough_index")),
                    normalize_text(row.get("step_index")),
                    normalize_text(row.get("encounter_id")),
                ]
            )
            or sha256_text(stable_json(row))
        ),
        source_constitution_id=normalize_text(row.get("constitution_id")) or "behavioral_baseline",
        prompt=prompt,
        scene=extract_scene(prompt),
        options=options,
        decision_id=decision_id,
        decision_text=_decision_text(decision_id, options, row.get("chosen_option_text")),
        public_reflection=reflection,
        hidden_trace_present=bool(normalize_text(row.get("completion_trace_text"))),
        reasoning_marker_present=bool(row.get("has_reasoning_trace")),
        source_tokens=source_token_count(row),
        quality_pass=quality_pass,
        metadata={
            "source_model_id": normalize_text(row.get("model_id") or row.get("model_label")),
            "source_prompt_id": normalize_text(row.get("prompt_id")),
            "source_encounter_id": normalize_text(row.get("encounter_id")),
            "playthrough_index": row.get("playthrough_index"),
            "step_index": row.get("step_index"),
            **source_split_metadata(row),
        },
    )


def candidate_from_corpus(row: dict[str, Any], path: Path) -> Candidate:
    messages = [message for message in row.get("messages", []) if isinstance(message, dict)]
    prompt = "\n".join(str(message.get("content", "")) for message in messages if message.get("role") != "assistant")
    completion = "\n".join(
        str(message.get("content", ""))
        for message in messages
        if message.get("role") == "assistant"
    )
    options = parse_options(prompt)
    decision_id, reflection = parse_completion(completion)
    flags = row.get("quality_flags", {}) or {}
    valid_ids = {item["option_id"] for item in options}
    quality_pass = bool(decision_id) and (not valid_ids or decision_id in valid_ids)
    quality_pass = quality_pass and not bool(flags.get("is_low_quality", False))
    return Candidate(
        source_format="constitution_corpus",
        source_path=path,
        source_id=normalize_text(row.get("example_id")) or sha256_text(stable_json(row)),
        source_constitution_id=normalize_text(row.get("constitution_id")) or "unknown",
        prompt=prompt,
        scene=extract_scene(prompt),
        options=options,
        decision_id=decision_id,
        decision_text=_decision_text(decision_id, options),
        public_reflection=reflection,
        hidden_trace_present=bool(normalize_text(flags.get("reasoning_trace"))),
        reasoning_marker_present=bool(flags.get("has_reasoning_trace")),
        source_tokens=source_token_count(row),
        quality_pass=quality_pass,
        metadata={
            "source_model_id": normalize_text((row.get("model", {}) or {}).get("model_id")),
            "source_prompt_id": normalize_text(row.get("prompt_id")),
            "source_encounter_id": normalize_text(row.get("encounter_id")),
        },
    )


LOADERS = {
    "control_records": candidate_from_control,
    "generations": candidate_from_generation,
    "constitution_corpus": candidate_from_corpus,
}


def relevant_tenets(candidate: Candidate, constitution: Constitution) -> list[str]:
    text = normalize_text(
        " ".join(
            [
                candidate.scene,
                candidate.decision_text,
                candidate.public_reflection,
                stable_json(candidate.moral_deltas),
            ]
        )
    ).lower()
    allowed = set(constitution.tenet_ids)
    scores = {
        tenet_id: sum(1 for term in terms if term in text)
        for tenet_id, terms in TENET_TERMS.items()
        if tenet_id in allowed
    }
    selected = [
        tenet_id
        for tenet_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        if score > 0
    ]
    if not selected:
        selected = [tenet_id for tenet_id in ("aql", "adl") if tenet_id in allowed]
    return selected[:3]


def criticality(candidate: Candidate, tenet_ids: Sequence[str]) -> tuple[float, list[str]]:
    combined = normalize_text(f"{candidate.scene} {candidate.public_reflection}").lower()
    bases: list[str] = []
    score = 0.0
    valid_ids = {item["option_id"] for item in candidate.options}
    if len(valid_ids) >= 2:
        score += 0.25
        bases.append("multiple_available_actions")
    if candidate.decision_id and (not valid_ids or candidate.decision_id in valid_ids):
        score += 0.20
        bases.append("recorded_valid_decision")
    if len(tenet_ids) >= 2:
        score += 0.15
        bases.append("multiple_tenet_proxy_matches")
    if len(WORD_RE.findall(candidate.public_reflection)) >= 18:
        score += 0.10
        bases.append("substantive_public_rationale")
    if any(marker in combined for marker in TENSION_MARKERS):
        score += 0.15
        bases.append("counterpressure_language")
    if any(marker in combined for marker in STAKES_MARKERS):
        score += 0.15
        bases.append("moral_stakes_language")
    if sum(abs(value) for value in candidate.moral_deltas.values()) >= 0.5:
        score += 0.10
        bases.append("recorded_moral_axis_delta")
    return min(score, 1.0), bases


def scenario_text(candidate: Candidate) -> str:
    options = " ".join(item["option_text"] for item in candidate.options)
    value = normalize_text(f"{candidate.scene} {options}") or normalize_text(candidate.prompt)
    return normalize_text(ID_NOISE_RE.sub(" <id> ", value)).lower()


def simhash64(text: str) -> int:
    tokens = WORD_RE.findall(text.lower())
    shingles = [" ".join(tokens[index : index + 3]) for index in range(max(1, len(tokens) - 2))]
    if not shingles:
        shingles = tokens or [""]
    vector = [0] * 64
    for shingle in shingles:
        value = int.from_bytes(hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big")
        for bit in range(64):
            vector[bit] += 1 if value & (1 << bit) else -1
    result = 0
    for bit, weight in enumerate(vector):
        if weight >= 0:
            result |= 1 << bit
    return result


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def near_duplicate_clusters(candidates: Sequence[Candidate], hamming_threshold: int = 3) -> list[str]:
    texts = [scenario_text(candidate) for candidate in candidates]
    hashes = [simhash64(text) for text in texts]
    token_sets = [set(WORD_RE.findall(text)) for text in texts]
    parents = list(range(len(candidates)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, value in enumerate(hashes):
        possible: set[int] = set()
        for band in range(4):
            key = (band, (value >> (band * 16)) & 0xFFFF)
            possible.update(buckets[key])
        for prior in possible:
            close_hash = (value ^ hashes[prior]).bit_count() <= hamming_threshold
            close_tokens = _jaccard(token_sets[index], token_sets[prior]) >= 0.85
            if close_hash and close_tokens:
                union(index, prior)
        for band in range(4):
            buckets[(band, (value >> (band * 16)) & 0xFFFF)].append(index)

    root_ids: dict[int, str] = {}
    return [
        root_ids.setdefault(find(index), sha256_text(texts[find(index)])[:20])
        for index in range(len(candidates))
    ]


class TokenCounter:
    def __init__(self) -> None:
        try:
            import tiktoken

            self._encoding = tiktoken.get_encoding("cl100k_base")
            self.method = "cl100k_base_estimate"
        except ImportError:
            self._encoding = None
            self.method = "whitespace_proxy"

    def count(self, text: str) -> int:
        if self._encoding is not None:
            return len(self._encoding.encode(text))
        return len(WORD_RE.findall(text))


def render_system_prompt(constitution: Constitution) -> str:
    tenets = "; ".join(f"{item.id}={item.name}" for item in constitution.tenets)
    prohibitions = "; ".join(f"{item['id']}={item['name']}" for item in constitution.prohibitions)
    return (
        f"Apply {constitution.constitution_id}. Select one listed option and justify it "
        "with concise public reasoning, not hidden chain-of-thought. Name defended tenets, "
        "the strongest counterpressure, and why the choice still holds. Never invent "
        f"religious citations.\nTenets: {tenets}.\nAvoid: {prohibitions}.\nReturn exactly:\n"
        "Decision: <option id>\n"
        "Reflection: <20-35 words of public reasoning>\n"
        "Tenets defended: <comma-separated tenet ids>\n"
        "Counterpressure: <8-18 words on the strongest competing consideration>\n"
        "Constitutional defense: <10-25 words on why the action preserves those tenets>\n"
        "Stop after Constitutional defense."
    )


def render_decision_prompt(candidate: Candidate, max_scene_words: int = 180) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", normalize_text(candidate.scene))
    retained: list[str] = []
    seen: set[str] = set()
    word_count = 0
    for sentence in sentences:
        normalized = normalize_text(ID_NOISE_RE.sub(" <id> ", sentence)).lower()
        if not sentence or normalized in seen:
            continue
        words = WORD_RE.findall(sentence)
        if retained and word_count + len(words) > max_scene_words:
            break
        retained.append(sentence)
        seen.add(normalized)
        word_count += len(words)
    scene = " ".join(retained) or normalize_text(candidate.scene)
    options = "\n".join(f"- {item['option_id']}: {item['option_text']}" for item in candidate.options)
    return f"Critical decision scene:\n{scene}\n\nAvailable options:\n{options}"


def behavioral_completion(candidate: Candidate) -> str:
    return "\n".join(
        [
            f"Decision: {candidate.decision_id}",
            f"Reflection: {candidate.public_reflection}",
        ]
    )


def render_behavioral_system_prompt() -> str:
    return (
        "Reproduce the recorded storyworld decision and its concise public rationale. "
        "This is behavioral imitation, not constitutional approval. Return only "
        "Decision: <option id> and Reflection: <public rationale>."
    )


def _split_for(cluster_id: str, seed: int, fractions: dict[str, float]) -> str:
    value = int(sha256_text(f"{seed}:{cluster_id}")[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
    train = float(fractions.get("train", 0.8))
    validation = float(fractions.get("validation", 0.1))
    if value < train:
        return "train"
    if value < train + validation:
        return "validation"
    return "test"


def _expand_sources(
    repo_root: Path, source_specs: Sequence[dict[str, Any]]
) -> tuple[list[tuple[str, Path, dict[str, Any]]], list[str]]:
    expanded: list[tuple[str, Path, dict[str, Any]]] = []
    excluded: list[str] = []
    seen: set[tuple[str, Path]] = set()
    for spec in source_specs:
        source_format = normalize_text(spec.get("format"))
        if source_format not in LOADERS:
            raise ValueError(f"unsupported source format: {source_format}")
        pattern = str(spec.get("glob", "") or "")
        if not pattern:
            raise ValueError("every source entry requires glob")
        resolved_pattern = pattern if Path(pattern).is_absolute() else str(repo_root / pattern)
        paths = [Path(item).resolve() for item in glob.glob(resolved_pattern, recursive=True)]
        if not paths and bool(spec.get("required", True)):
            raise ValueError(f"source glob matched no files: {pattern}")
        included_for_spec = 0
        exclude_patterns = [str(item).lower() for item in spec.get("exclude_path_patterns", [])]
        for path in sorted(paths):
            portable = portable_path(path, repo_root)
            if any(fnmatch.fnmatch(portable.lower(), exclude_pattern) for exclude_pattern in exclude_patterns):
                excluded.append(portable)
                continue
            key = (source_format, path)
            if path.is_file() and key not in seen:
                seen.add(key)
                expanded.append((source_format, path, spec))
                included_for_spec += 1
        if included_for_spec == 0 and bool(spec.get("required", True)):
            raise ValueError(f"all files matched by required source glob were excluded: {pattern}")
    return expanded, sorted(set(excluded))


def _record_signature(candidate: Candidate) -> str:
    return sha256_text(
        stable_json(
            {
                "scenario": scenario_text(candidate),
                "source_constitution_id": candidate.source_constitution_id,
                "decision_id": candidate.decision_id,
                "reflection": normalize_text(candidate.public_reflection).lower(),
            }
        )
    )


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")


def build_dataset(
    *,
    config: dict[str, Any],
    constitution: Constitution,
    repo_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source_files, excluded_source_paths = _expand_sources(repo_root, config.get("sources", []))
    candidates: list[Candidate] = []
    file_receipts: list[dict[str, Any]] = []
    source_rows = 0
    source_tokens = 0
    hidden_trace_rows = 0
    reasoning_marker_rows = 0
    rejected = Counter()
    min_reflection_words = int(config.get("min_public_reflection_words", 8))
    threshold = float(config.get("criticality_threshold", 0.55))

    for source_format, path, source_spec in source_files:
        rows_in_file = 0
        accepted_in_file = 0
        loader = LOADERS[source_format]
        for raw_row in read_jsonl(path):
            source_rows += 1
            rows_in_file += 1
            candidate = loader(raw_row, path)
            source_tokens += candidate.source_tokens
            hidden_trace_rows += int(candidate.hidden_trace_present)
            reasoning_marker_rows += int(candidate.reasoning_marker_present)
            source_split = normalize_text(candidate.metadata.get("source_split")).lower()
            if candidate.metadata.get("training_eligible") is False or source_split in EVALUATION_ONLY_SPLITS:
                rejected["evaluation_only_source_excluded"] += 1
                continue
            if (candidate.hidden_trace_present or candidate.reasoning_marker_present) and bool(
                config.get("exclude_hidden_reasoning", True)
            ):
                rejected["hidden_reasoning_or_marker_excluded"] += 1
                continue
            if not candidate.quality_pass:
                rejected["source_quality_failed"] += 1
                continue
            if not candidate.prompt or len(candidate.options) < 2:
                rejected["missing_prompt_or_options"] += 1
                continue
            reflection_words = len(WORD_RE.findall(candidate.public_reflection))
            if not candidate.public_reflection or reflection_words < min_reflection_words:
                rejected["public_reflection_too_short"] += 1
                continue
            tenets = relevant_tenets(candidate, constitution)
            critical_score, _ = criticality(candidate, tenets)
            if critical_score < threshold:
                rejected["below_criticality_threshold"] += 1
                continue
            candidate.metadata["source_license_status"] = normalize_text(
                source_spec.get("license_status", "needs_review")
            )
            candidates.append(candidate)
            accepted_in_file += 1
        file_receipts.append(
            {
                "path": portable_path(path, repo_root),
                "sha256": file_sha256(path),
                "format": source_format,
                "rows": rows_in_file,
                "accepted_before_dedup": accepted_in_file,
                "license_status": normalize_text(source_spec.get("license_status", "needs_review")),
            }
        )

    minimum_source_tokens = int(config.get("minimum_reported_source_tokens", 0))
    if source_tokens < minimum_source_tokens:
        raise ValueError(
            f"reported source-token gate failed: {source_tokens} < {minimum_source_tokens}; "
            "do not describe this build as large-token conditioning data"
        )
    if not candidates:
        raise ValueError("no candidates passed source and criticality gates")

    exact_seen: set[str] = set()
    exact_deduped: list[Candidate] = []
    for candidate in candidates:
        signature = _record_signature(candidate)
        if signature in exact_seen:
            rejected["exact_duplicate"] += 1
            continue
        exact_seen.add(signature)
        exact_deduped.append(candidate)

    cluster_ids = near_duplicate_clusters(
        exact_deduped,
        hamming_threshold=int(config.get("near_duplicate_hamming_threshold", 3)),
    )
    max_per_cluster = int(config.get("max_examples_per_near_duplicate_cluster", 3))
    cluster_members: dict[str, list[tuple[Candidate, int]]] = defaultdict(list)
    for candidate, cluster_id in zip(exact_deduped, cluster_ids):
        cluster_members[cluster_id].append((candidate, len(cluster_members[cluster_id])))

    retained: list[tuple[Candidate, str]] = []
    format_priority = {"control_record_v1": 0, "storyworld_generation": 1, "constitution_corpus": 2}
    for cluster_id, members in sorted(cluster_members.items()):
        members.sort(
            key=lambda item: (
                format_priority.get(item[0].source_format, 9),
                -len(relevant_tenets(item[0], constitution)),
                -len(WORD_RE.findall(item[0].public_reflection)),
                str(item[0].source_path),
                item[0].source_id,
            )
        )
        for candidate, _ in members[:max_per_cluster]:
            retained.append((candidate, cluster_id))
        rejected["near_duplicate_cluster_cap"] += max(0, len(members) - max_per_cluster)

    split_fractions = config.get("split_fractions", {"train": 0.8, "validation": 0.1, "test": 0.1})
    if abs(sum(float(value) for value in split_fractions.values()) - 1.0) > 1e-9:
        raise ValueError("split_fractions must sum to 1.0")
    seed = int(config.get("seed", 20260714))
    system_prompt = render_system_prompt(constitution)
    behavioral_system_prompt = render_behavioral_system_prompt()
    token_counter = TokenCounter()
    canonical_rows: list[dict[str, Any]] = []
    sft_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rl_by_cluster: dict[str, dict[str, Any]] = {}
    split_tokens = Counter()

    random.Random(seed).shuffle(retained)
    for candidate, cluster_id in retained:
        tenets = relevant_tenets(candidate, constitution)
        critical_score, critical_bases = criticality(candidate, tenets)
        split = _split_for(cluster_id, seed, split_fractions)
        policy_user_prompt = render_decision_prompt(candidate)
        prompt_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": policy_user_prompt},
        ]
        completion = behavioral_completion(candidate)
        example_id = f"acv1_{sha256_text(_record_signature(candidate))[:24]}"
        prompt_tokens = token_counter.count(system_prompt) + token_counter.count(policy_user_prompt)
        conditioning_prompt_tokens = token_counter.count(
            behavioral_system_prompt
        ) + token_counter.count(candidate.prompt)
        completion_tokens = token_counter.count(completion)
        record = {
            "record_version": RECORD_VERSION,
            "example_id": example_id,
            "split": split,
            "constitution": {
                "constitution_id": constitution.constitution_id,
                "version": constitution.version,
                "sha256": constitution.sha256,
                "needs_scholar_review": constitution.needs_scholar_review,
            },
            "prompt": prompt_messages,
            "options": candidate.options,
            "behavioral_reference": {
                "decision_id": candidate.decision_id,
                "decision_text": candidate.decision_text,
                "public_reflection": candidate.public_reflection,
                "relevant_tenet_ids": tenets,
                "tenet_label_method": "lexical_weak_supervision_v1",
                "is_constitutional_approval": False,
            },
            "criticality": {
                "score": round(critical_score, 4),
                "threshold": threshold,
                "basis": critical_bases,
                "is_proxy_label": True,
            },
            "reasoning_provenance": {
                "public_reflection_included": True,
                "hidden_reasoning_present_at_source": candidate.hidden_trace_present,
                "reasoning_marker_present_at_source": candidate.reasoning_marker_present,
                "hidden_reasoning_included": False,
            },
            "deduplication": {
                "near_duplicate_cluster_id": cluster_id,
                "scenario_sha256": sha256_text(scenario_text(candidate)),
            },
            "provenance": {
                "source_format": candidate.source_format,
                "source_path": portable_path(candidate.source_path, repo_root),
                "source_id": candidate.source_id,
                "source_constitution_id": candidate.source_constitution_id,
                "source_license_status": candidate.metadata.get("source_license_status", "needs_review"),
                **candidate.metadata,
            },
            "token_counts": {
                "method": token_counter.method,
                "prompt": prompt_tokens,
                "rl_prompt": prompt_tokens,
                "behavioral_conditioning_prompt": conditioning_prompt_tokens,
                "behavioral_completion": completion_tokens,
                "total": conditioning_prompt_tokens + completion_tokens,
                "source_reported": candidate.source_tokens,
            },
        }
        canonical_rows.append(record)
        split_tokens[split] += conditioning_prompt_tokens + completion_tokens
        sft_rows[split].append(
            {
                "example_id": example_id,
                "messages": [
                    {"role": "system", "content": behavioral_system_prompt},
                    {"role": "user", "content": candidate.prompt.strip()},
                    {"role": "assistant", "content": completion},
                ],
                "reference_kind": "behavioral_warm_start_not_constitutional_approval",
                "near_duplicate_cluster_id": cluster_id,
            }
        )
        rl_by_cluster.setdefault(
            cluster_id,
            {
                "example_id": example_id,
                "prompt": prompt_messages,
                "valid_option_ids": [item["option_id"] for item in candidate.options],
                "valid_option_texts": [item["option_text"] for item in candidate.options],
                "allowed_tenet_ids": list(constitution.tenet_ids),
                "relevant_tenet_ids": tenets,
                "behavioral_reference_decision": candidate.decision_id,
                "behavioral_reference_reflection": candidate.public_reflection,
                "near_duplicate_cluster_id": cluster_id,
                "split": split,
            },
        )

    rl_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rl_by_cluster.values():
        rl_rows[row["split"]].append({key: value for key, value in row.items() if key != "split"})

    tenet_counts = Counter(
        tenet_id
        for row in canonical_rows
        for tenet_id in row["behavioral_reference"]["relevant_tenet_ids"]
    )
    minimum_per_tenet = int(config.get("minimum_examples_per_tenet", 0))
    under_minimum = {
        tenet_id: tenet_counts.get(tenet_id, 0)
        for tenet_id in constitution.tenet_ids
        if tenet_counts.get(tenet_id, 0) < minimum_per_tenet
    }
    if under_minimum:
        raise ValueError(
            f"per-tenet coverage gate failed (minimum {minimum_per_tenet}): {under_minimum}"
        )

    retained_conditioning_tokens = sum(split_tokens.values())
    minimum_conditioning_tokens = int(config.get("minimum_retained_conditioning_tokens", 0))
    if retained_conditioning_tokens < minimum_conditioning_tokens:
        raise ValueError(
            "post-dedup conditioning-token gate failed: "
            f"{retained_conditioning_tokens} < {minimum_conditioning_tokens}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "canonical.jsonl", canonical_rows)
    for split in ("train", "validation", "test"):
        write_jsonl(output_dir / f"sft_behavioral_{split}.jsonl", sft_rows.get(split, []))
        write_jsonl(output_dir / f"rl_{split}.jsonl", rl_rows.get(split, []))

    generated_files = [
        "canonical.jsonl",
        *(f"sft_behavioral_{split}.jsonl" for split in ("train", "validation", "test")),
        *(f"rl_{split}.jsonl" for split in ("train", "validation", "test")),
    ]

    split_counts = Counter(row["split"] for row in canonical_rows)
    rl_split_counts = {
        split: len(rl_rows.get(split, []))
        for split in ("train", "validation", "test")
    }
    manifest = {
        "manifest_version": "alignment_conditioning_manifest_v1",
        "research_only": True,
        "promotion_blocked_on_scholar_review": constitution.needs_scholar_review,
        "build_receipt": {
            "builder_module_sha256": normalized_text_file_sha256(Path(__file__)),
            "builder_hash_basis": "UTF-8 text with LF line endings",
            "config_sha256": sha256_text(stable_json(config)),
            "generated_file_sha256": {
                name: file_sha256(output_dir / name) for name in generated_files
            },
        },
        "constitution": {
            "path": portable_path(constitution.path, repo_root),
            "constitution_id": constitution.constitution_id,
            "version": constitution.version,
            "sha256": constitution.sha256,
            "status": constitution.status,
            "needs_scholar_review": constitution.needs_scholar_review,
        },
        "source_audit": {
            "files": len(source_files),
            "excluded_files": len(excluded_source_paths),
            "excluded_paths": excluded_source_paths,
            "physical_rows": source_rows,
            "reported_tokens": source_tokens,
            "minimum_reported_source_tokens": minimum_source_tokens,
            "hidden_reasoning_rows_seen": hidden_trace_rows,
            "reasoning_marker_rows_seen": reasoning_marker_rows,
            "public_reflection_policy": "public rationale/reaction only; hidden traces excluded",
            "file_receipts": file_receipts,
        },
        "conditioning_corpus": {
            "accepted_before_dedup": len(candidates),
            "after_exact_dedup": len(exact_deduped),
            "retained_after_near_duplicate_cap": len(canonical_rows),
            "near_duplicate_clusters": len(cluster_members),
            "rl_unique_scenarios": len(rl_by_cluster),
            "relevant_tenet_counts": dict(sorted(tenet_counts.items())),
            "tenets_below_20_examples": {
                tenet_id: tenet_counts.get(tenet_id, 0)
                for tenet_id in constitution.tenet_ids
                if tenet_counts.get(tenet_id, 0) < 20
            },
            "minimum_examples_per_tenet": minimum_per_tenet,
            "source_format_counts": dict(
                sorted(
                    Counter(
                        row["provenance"]["source_format"] for row in canonical_rows
                    ).items()
                )
            ),
            "source_constitution_counts": dict(
                sorted(
                    Counter(
                        row["provenance"]["source_constitution_id"]
                        for row in canonical_rows
                    ).items()
                )
            ),
            "split_counts": dict(sorted(split_counts.items())),
            "rl_split_counts": rl_split_counts,
            "estimated_tokens_by_split": dict(sorted(split_tokens.items())),
            "estimated_tokens_total": retained_conditioning_tokens,
            "minimum_retained_conditioning_tokens": minimum_conditioning_tokens,
            "token_count_method": token_counter.method,
            "rejections": dict(sorted(rejected.items())),
        },
        "label_limitations": [
            "Source decisions are behavioral observations, not constitutionally approved answers.",
            "Relevant-tenet and criticality labels are auditable proxies, not compliance judgments.",
            "No hidden chain-of-thought is used as a target.",
            "Source license status marked needs_review must be cleared before distribution or commercial use.",
            "Rows marked evaluation-only or training_eligible=false are excluded before quality and deduplication gates.",
        ],
        "config": config,
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest
