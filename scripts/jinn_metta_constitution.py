#!/usr/bin/env python3
"""MeTTa-style symbolic constitution bridge for Jinn/Mutazili SFT data.

The repo does not currently require Hyperon. This bridge reads auditable
S-expression facts from ``metta/jinn_tiny_mutazili_v1.metta`` and derives
prompt facts, obligations, canonical responses, and proof-like provenance.
"""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_METTA_PATH = REPO_ROOT / "metta" / "jinn_tiny_mutazili_v1.metta"


@dataclass(frozen=True)
class Obligation:
    clause: str
    obligation_id: str
    statement: str


@dataclass
class MettaConstitution:
    constitution_id: str
    principles: dict[str, str]
    priorities: dict[str, int]
    triggers: dict[str, list[str]]
    tag_triggers: dict[str, list[str]]
    obligations: dict[str, list[Obligation]]
    canonicals: dict[str, tuple[str, str]]
    source_path: Path


def _tokenize_fact(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith(";"):
        return []
    if not (stripped.startswith("(") and stripped.endswith(")")):
        return []
    body = stripped[1:-1].strip()
    if not body:
        return []
    lexer = shlex.shlex(body, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def load_constitution(path: str | Path = DEFAULT_METTA_PATH) -> MettaConstitution:
    source_path = Path(path).resolve()
    constitution_id = ""
    principles: dict[str, str] = {}
    priorities: dict[str, int] = {}
    triggers: dict[str, list[str]] = {}
    tag_triggers: dict[str, list[str]] = {}
    obligations: dict[str, list[Obligation]] = {}
    canonicals: dict[str, tuple[str, str]] = {}

    for line_no, line in enumerate(source_path.read_text(encoding="utf-8").splitlines(), start=1):
        tokens = _tokenize_fact(line)
        if not tokens:
            continue
        kind = tokens[0]
        try:
            if kind == "constitution" and len(tokens) == 2:
                constitution_id = tokens[1]
            elif kind == "principle" and len(tokens) == 3:
                principles[tokens[1]] = tokens[2]
            elif kind == "priority" and len(tokens) == 3:
                priorities[tokens[1]] = int(tokens[2])
            elif kind == "trigger" and len(tokens) == 3:
                triggers.setdefault(tokens[1], []).append(tokens[2].lower())
            elif kind == "tag-trigger" and len(tokens) == 3:
                tag_triggers.setdefault(tokens[1], []).append(tokens[2].lower())
            elif kind == "obligation" and len(tokens) == 4:
                obligations.setdefault(tokens[1], []).append(Obligation(tokens[1], tokens[2], tokens[3]))
            elif kind == "canonical" and len(tokens) == 4:
                canonicals[tokens[1]] = (tokens[2], tokens[3])
        except Exception as exc:
            raise ValueError(f"Invalid MeTTa constitution fact {source_path}:{line_no}: {line}") from exc

    if not constitution_id:
        raise ValueError(f"No (constitution <id>) fact found in {source_path}")
    return MettaConstitution(
        constitution_id=constitution_id,
        principles=principles,
        priorities=priorities,
        triggers=triggers,
        tag_triggers=tag_triggers,
        obligations=obligations,
        canonicals=canonicals,
        source_path=source_path,
    )


def hyperon_available() -> bool:
    try:
        __import__("hyperon")
    except Exception:
        return False
    return True


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def derive_for_prompt(prompt: str, tags: list[str] | None = None, constitution_path: str | Path = DEFAULT_METTA_PATH) -> dict:
    constitution = load_constitution(constitution_path)
    prompt_lower = prompt.lower()
    tag_set = {str(tag).lower() for tag in (tags or [])}
    matched_clauses: set[str] = set()
    proof: list[dict] = []

    for clause, trigger_terms in sorted(constitution.triggers.items()):
        matched_terms = [term for term in trigger_terms if term and term in prompt_lower]
        if matched_terms:
            matched_clauses.add(clause)
            proof.append({"rule": "trigger", "clause": clause, "matched": matched_terms})

    for clause, trigger_tags in sorted(constitution.tag_triggers.items()):
        matched_tags = sorted(tag_set.intersection(trigger_tags))
        if matched_tags:
            matched_clauses.add(clause)
            proof.append({"rule": "tag-trigger", "clause": clause, "matched": matched_tags})

    if "scripture-secret-boundary" in matched_clauses:
        matched_clauses.discard("scripture-misuse-boundary")
        proof.append(
            {
                "rule": "specificity",
                "clause": "scripture-secret-boundary",
                "suppresses": "scripture-misuse-boundary",
            }
        )
    if "investor-truth-boundary" in matched_clauses:
        matched_clauses.discard("private-lie-boundary")
        proof.append(
            {
                "rule": "specificity",
                "clause": "investor-truth-boundary",
                "suppresses": "private-lie-boundary",
            }
        )
    if "scapegoat-boundary" in matched_clauses:
        matched_clauses.discard("scripture-misuse-boundary")
        proof.append(
            {
                "rule": "specificity",
                "clause": "scapegoat-boundary",
                "suppresses": "scripture-misuse-boundary",
            }
        )

    if not matched_clauses:
        matched_clauses.add("identity-boundary")
        proof.append({"rule": "default", "clause": "identity-boundary"})

    obligations: list[dict] = []
    for clause in sorted(matched_clauses, key=lambda item: (-constitution.priorities.get(item, 0), item)):
        for obligation in constitution.obligations.get(clause, []):
            obligations.append(
                {
                    "clause": clause,
                    "obligation_id": obligation.obligation_id,
                    "statement": obligation.statement,
                }
            )

    selected_clause = sorted(matched_clauses, key=lambda item: (-constitution.priorities.get(item, 0), item))[0]
    decision, rationale = constitution.canonicals.get(
        selected_clause,
        (
            "Decision: I should answer truthfully within a metaphorical accountability role.",
            "Rationale: Preserve evidence, disclose uncertainty, and avoid hidden authority claims or deception.",
        ),
    )
    proof.append(
        {
            "rule": "select-canonical",
            "clause": selected_clause,
            "priority": constitution.priorities.get(selected_clause, 0),
        }
    )

    return {
        "backend": "python_metta_bridge",
        "hyperon_available": hyperon_available(),
        "constitution_id": constitution.constitution_id,
        "constitution_path": str(constitution.source_path),
        "prompt_facts": {
            "prompt": prompt,
            "tags": sorted(tag_set),
            "matched_clauses": sorted(matched_clauses),
        },
        "obligations": obligations,
        "selected_clause": selected_clause,
        "canonical_response": f"{decision}\n{rationale}",
        "proof": proof,
    }


def canonical_answer(prompt: str, tags: list[str] | None = None, constitution_path: str | Path = DEFAULT_METTA_PATH) -> str:
    return str(derive_for_prompt(prompt, tags, constitution_path)["canonical_response"])


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL {path} line {line_no}: {exc}") from exc
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metta-constitution", default=str(DEFAULT_METTA_PATH))
    parser.add_argument("--prompt", default="")
    parser.add_argument("--tags", default="")
    parser.add_argument("--probes-jsonl", default="")
    parser.add_argument("--output-jsonl", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tags = [item.strip() for item in args.tags.split(",") if item.strip()]
    if args.prompt:
        print(json.dumps(derive_for_prompt(args.prompt, tags, args.metta_constitution), indent=2, sort_keys=True))
        return 0
    if args.probes_jsonl:
        rows = _load_jsonl(Path(args.probes_jsonl).resolve())
        output_rows = []
        for row in rows:
            prompt = str(row.get("prompt", "") or "")
            row_tags = list(row.get("tags") or [])
            output_rows.append(
                {
                    "example_id": row.get("example_id") or row.get("probe_id", ""),
                    "prompt": prompt,
                    "tags": row_tags,
                    "metta": derive_for_prompt(prompt, row_tags, args.metta_constitution),
                }
            )
        if args.output_jsonl:
            output_path = Path(args.output_jsonl).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8", newline="\n") as handle:
                for row in output_rows:
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
        else:
            for row in output_rows:
                print(json.dumps(row, sort_keys=True))
        return 0
    raise SystemExit("Provide --prompt or --probes-jsonl.")


if __name__ == "__main__":
    raise SystemExit(main())
