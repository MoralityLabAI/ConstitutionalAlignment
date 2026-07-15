#!/usr/bin/env python3
"""Validate constitution YAML files against papers/constitution_schema_v1.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_SCHEMA = Path("papers/constitution_schema_v1.json")
DEFAULT_TS_CONSTITUTION = Path("constitutional-harness/src/constitutions/islamic.ts")
DEFAULT_TS_CITATIONS = Path(
    "constitutional-harness/src/constitutions/islamic-citations.json"
)
DEFAULT_FILES = [
    Path("papers/constitution_ashari_v1.yaml"),
    Path("papers/constitution_mutazili_v1.yaml"),
    Path("papers/constitution_control_generic_v1.yaml"),
]

ISLAMIC_TRACKS = {"ashari", "mutazili"}
YAML_TO_TS_PRINCIPLE = {
    "constitution_ashari_v1": {"A002": "sidq"},
    "constitution_mutazili_v1": {"M001": "adl", "M002": "aql"},
}
VERSE_REF = re.compile(r"^[1-9][0-9]*:[1-9][0-9]*$")


def _load_yaml(path: Path):
    try:
        import yaml  # type: ignore
    except ImportError:
        print("Missing dependency: PyYAML. Install with: pip install pyyaml jsonschema")
        sys.exit(2)

    try:
        # Preserve ISO-like dates as strings instead of datetime.date.
        class NoDatesSafeLoader(yaml.SafeLoader):
            pass

        for ch, resolvers in list(NoDatesSafeLoader.yaml_implicit_resolvers.items()):
            NoDatesSafeLoader.yaml_implicit_resolvers[ch] = [
                (tag, regex)
                for tag, regex in resolvers
                if tag != "tag:yaml.org,2002:timestamp"
            ]

        return yaml.load(path.read_text(encoding="utf-8"), Loader=NoDatesSafeLoader)
    except Exception as exc:
        print(f"Failed to read YAML: {path}: {exc}")
        sys.exit(2)


def _load_schema(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to read schema JSON: {path}: {exc}")
        sys.exit(2)


def _validator(schema_obj):
    try:
        from jsonschema import Draft202012Validator  # type: ignore
    except ImportError:
        print("Missing dependency: jsonschema. Install with: pip install pyyaml jsonschema")
        sys.exit(2)
    return Draft202012Validator(schema_obj)


def _fmt_path(path_parts) -> str:
    if not path_parts:
        return "<root>"
    return ".".join(str(p) for p in path_parts)


def _find_todos(value: Any, path: tuple[Any, ...] = ()) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(_find_todos(child, (*path, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_todos(child, (*path, index)))
    elif isinstance(value, str) and "TODO" in value.upper():
        found.append(_fmt_path(path))
    return found


def _load_ts_citations(path: Path) -> dict[str, list[str]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Failed to load TS citation data {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"TS citation data must be an object: {path}")

    citations: dict[str, list[str]] = {}
    for principle_id, refs in raw.items():
        if (
            not isinstance(principle_id, str)
            or not isinstance(refs, list)
            or not refs
            or any(not isinstance(ref, str) or not VERSE_REF.fullmatch(ref) for ref in refs)
            or len(set(refs)) != len(refs)
        ):
            raise ValueError(f"Invalid TS citation list for principle {principle_id!r}")
        citations[principle_id] = refs
    return citations


def _validate_ts_wiring(
    ts_path: Path, citations_path: Path, citations: dict[str, list[str]]
) -> list[str]:
    try:
        source = ts_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read TS constitution {ts_path}: {exc}"]

    errors: list[str] = []
    import_target = "./" + citations_path.stem + ".json"
    if import_target not in source:
        errors.append(f"TS constitution must import canonical citations from {import_target}")
    for principle_id in citations:
        binding = f"quranicBasis: IslamicCitations.{principle_id}"
        if binding not in source:
            errors.append(f"TS constitution is not wired to canonical citations for {principle_id}")
    return errors


def _citation_errors(data: Any, citations: dict[str, list[str]]) -> list[str]:
    if not isinstance(data, dict) or data.get("track") not in ISLAMIC_TRACKS:
        return []

    errors: list[str] = []
    version = data.get("version")
    mapping = YAML_TO_TS_PRINCIPLE.get(version, {})
    principles = data.get("principles", [])
    for index, principle in enumerate(principles):
        base_path = f"principles.{index}"
        if not isinstance(principle, dict):
            continue
        if not isinstance(principle.get("needs_scholar_review"), bool):
            errors.append(f"{base_path}.needs_scholar_review must be explicit")
        if (
            data.get("status") == "draft_needs_scholar_review"
            and principle.get("needs_scholar_review") is not True
        ):
            errors.append(f"{base_path} is a draft interpretive claim and must be flagged")

        actual_quran_refs: set[str] = set()
        for citation_index, citation in enumerate(principle.get("source_citations", [])):
            citation_path = f"{base_path}.source_citations.{citation_index}"
            if not isinstance(citation, dict):
                continue
            review = citation.get("needs_scholar_review")
            ref = citation.get("ref")
            if not isinstance(review, bool):
                errors.append(f"{citation_path}.needs_scholar_review must be explicit")
            if ref is None and review is not True:
                errors.append(f"{citation_path}: null ref must be flagged for scholar review")
            if citation.get("source_id") == "quran_500_wisdom_verses" and ref is not None:
                if not isinstance(ref, str) or not VERSE_REF.fullmatch(ref):
                    errors.append(f"{citation_path}.ref is not a surah:ayah reference")
                else:
                    actual_quran_refs.add(ref)

        ts_principle = mapping.get(principle.get("id"))
        expected_quran_refs = set(citations[ts_principle]) if ts_principle else set()
        if actual_quran_refs != expected_quran_refs:
            errors.append(
                f"{base_path}.source_citations Quran refs mismatch TS principle "
                f"{ts_principle!r}: expected {sorted(expected_quran_refs)}, "
                f"found {sorted(actual_quran_refs)}"
            )
    return errors


def validate_file(path: Path, validator, citations: dict[str, list[str]]) -> int:
    if not path.exists():
        print(f"[FAIL] {path}: file not found")
        return 1

    data = _load_yaml(path)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    custom_errors = [f"{todo_path}: TODO placeholder remains" for todo_path in _find_todos(data)]
    custom_errors.extend(_citation_errors(data, citations))
    if not errors and not custom_errors:
        print(f"[OK]   {path}")
        return 0

    print(f"[FAIL] {path}")
    for err in errors:
        print(f"  - {_fmt_path(err.path)}: {err.message}")
    for error in custom_errors:
        print(f"  - {error}")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate constitution YAML files against a JSON schema."
    )
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help="Path to JSON schema (default: papers/constitution_schema_v1.json)",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="YAML files to validate (default: all three experimental constitutions)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    schema_path = Path(args.schema)
    files = [Path(p) for p in args.files] if args.files else DEFAULT_FILES

    if not schema_path.exists():
        print(f"Schema file not found: {schema_path}")
        return 2

    schema_obj = _load_schema(schema_path)
    validator = _validator(schema_obj)
    try:
        citations = _load_ts_citations(DEFAULT_TS_CITATIONS)
    except ValueError as exc:
        print(exc)
        return 2
    wiring_errors = _validate_ts_wiring(
        DEFAULT_TS_CONSTITUTION, DEFAULT_TS_CITATIONS, citations
    )
    if wiring_errors:
        for error in wiring_errors:
            print(f"[FAIL] {error}")
        return 1

    failed = 0
    for file_path in files:
        failed += validate_file(file_path, validator, citations)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
