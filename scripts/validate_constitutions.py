#!/usr/bin/env python3
"""Validate constitution YAML files against papers/constitution_schema_v1.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_SCHEMA = Path("papers/constitution_schema_v1.json")
DEFAULT_FILES = [
    Path("papers/constitution_ashari_v1.yaml"),
    Path("papers/constitution_mutazili_v1.yaml"),
]


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


def validate_file(path: Path, validator) -> int:
    if not path.exists():
        print(f"[FAIL] {path}: file not found")
        return 1

    data = _load_yaml(path)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        print(f"[OK]   {path}")
        return 0

    print(f"[FAIL] {path}")
    for err in errors:
        print(f"  - {_fmt_path(err.path)}: {err.message}")
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
        help="YAML files to validate (default: ashari + mutazili templates)",
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

    failed = 0
    for file_path in files:
        failed += validate_file(file_path, validator)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
