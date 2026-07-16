#!/usr/bin/env python3
"""Manage paper/algorithm cards for the constitutional alignment harness."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CARD_DIR = ROOT / "papers" / "algorithm_cards"
DEFAULT_MATRIX_MD = ROOT / "papers" / "research_algorithm_matrix.md"
DEFAULT_MATRIX_CSV = ROOT / "artifacts" / "research_algorithm_registry" / "research_algorithm_matrix.csv"
REQUIRED_TOP_LEVEL = [
    "version",
    "algorithm_id",
    "title",
    "source",
    "summary",
    "harness_fit",
    "implementation",
    "evals",
    "guardrails",
]
VALID_STATUSES = {"candidate", "planned", "partial", "ready", "blocked"}


def load_yaml_module():
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(f"PyYAML is required to read algorithm cards: {exc}") from exc
    return yaml


def read_card(path: Path) -> dict[str, Any]:
    yaml = load_yaml_module()
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: card must be a mapping")
    return data


def card_paths(card_dir: Path) -> list[Path]:
    return sorted(card_dir.glob("*.yaml"))


def validate_card(card: dict[str, Any], path: Path) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in card:
            errors.append(f"{path}: missing required field {key}")
    if card.get("version") != "research_algorithm_card_v1":
        errors.append(f"{path}: version must be research_algorithm_card_v1")
    algorithm_id = str(card.get("algorithm_id", ""))
    if not re.fullmatch(r"[a-z0-9][a-z0-9_\-]*", algorithm_id):
        errors.append(f"{path}: invalid algorithm_id {algorithm_id!r}")
    source = card.get("source", {})
    if not isinstance(source, dict):
        errors.append(f"{path}: source must be a mapping")
    else:
        for key in ["kind", "citation", "url", "checked_date"]:
            if not source.get(key):
                errors.append(f"{path}: source.{key} is required")
    harness_fit = card.get("harness_fit", {})
    if not isinstance(harness_fit, dict):
        errors.append(f"{path}: harness_fit must be a mapping")
    elif not isinstance(harness_fit.get("integration_points", []), list):
        errors.append(f"{path}: harness_fit.integration_points must be a list")
    implementation = card.get("implementation", {})
    if not isinstance(implementation, dict):
        errors.append(f"{path}: implementation must be a mapping")
    else:
        status = implementation.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{path}: implementation.status must be one of {sorted(VALID_STATUSES)}")
        if not isinstance(implementation.get("files_to_touch", []), list):
            errors.append(f"{path}: implementation.files_to_touch must be a list")
    evals = card.get("evals", {})
    if not isinstance(evals, dict):
        errors.append(f"{path}: evals must be a mapping")
    elif not isinstance(evals.get("metrics", []), list):
        errors.append(f"{path}: evals.metrics must be a list")
    if not isinstance(card.get("guardrails", []), list):
        errors.append(f"{path}: guardrails must be a list")
    return errors


def load_cards(card_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    cards = []
    for path in card_paths(card_dir):
        cards.append((path, read_card(path)))
    return cards


def flatten_card(path: Path, card: dict[str, Any]) -> dict[str, str]:
    source = card.get("source", {})
    harness_fit = card.get("harness_fit", {})
    implementation = card.get("implementation", {})
    evals = card.get("evals", {})
    return {
        "algorithm_id": str(card.get("algorithm_id", "")),
        "title": str(card.get("title", "")),
        "status": str(implementation.get("status", "")),
        "primary_track": str(harness_fit.get("primary_track", "")),
        "use_case": str(harness_fit.get("use_case", "")),
        "source": str(source.get("citation", "")),
        "url": str(source.get("url", "")),
        "checked_date": str(source.get("checked_date", "")),
        "metrics": ", ".join(str(item) for item in evals.get("metrics", [])),
        "minimum_viable_run": str(evals.get("minimum_viable_run", "")),
        "card_path": str(path.relative_to(ROOT)),
    }


def cmd_validate(args: argparse.Namespace) -> int:
    card_dir = Path(args.card_dir).resolve()
    errors: list[str] = []
    cards = load_cards(card_dir)
    if not cards:
        errors.append(f"No cards found in {card_dir}")
    seen: set[str] = set()
    for path, card in cards:
        errors.extend(validate_card(card, path))
        algorithm_id = str(card.get("algorithm_id", ""))
        if algorithm_id in seen:
            errors.append(f"{path}: duplicate algorithm_id {algorithm_id}")
        seen.add(algorithm_id)
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print(f"OK: {len(cards)} algorithm card(s) valid")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    cards = load_cards(Path(args.card_dir).resolve())
    for path, card in cards:
        row = flatten_card(path, card)
        print(f"{row['algorithm_id']:<42} {row['status']:<9} {row['primary_track']}")
        print(f"  {row['title']}")
    return 0


def write_matrix(cards: list[tuple[Path, dict[str, Any]]], md_path: Path, csv_path: Path) -> None:
    rows = [flatten_card(path, card) for path, card in cards]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Research Algorithm Matrix",
        "",
        f"Generated from `{DEFAULT_CARD_DIR.relative_to(ROOT).as_posix()}`.",
        "",
        "| Algorithm | Status | Track | Use Case | Minimum Viable Run |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        card_path = ROOT / row["card_path"]
        card_link = Path(os.path.relpath(card_path, md_path.parent)).as_posix()
        lines.append(
            f"| [{row['algorithm_id']}]({card_link}) | {row['status']} | {row['primary_track']} | {row['use_case']} | {row['minimum_viable_run']} |"
        )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def cmd_matrix(args: argparse.Namespace) -> int:
    card_dir = Path(args.card_dir).resolve()
    cards = load_cards(card_dir)
    if not cards:
        raise SystemExit(f"No cards found in {card_dir}")
    all_errors = []
    for path, card in cards:
        all_errors.extend(validate_card(card, path))
    if all_errors:
        for error in all_errors:
            print(f"ERROR {error}")
        return 1
    md_path = Path(args.output_md).resolve()
    csv_path = Path(args.output_csv).resolve()
    write_matrix(cards, md_path, csv_path)
    print(f"Wrote {md_path}")
    print(f"Wrote {csv_path}")
    return 0


def cmd_scaffold(args: argparse.Namespace) -> int:
    algorithm_id = args.algorithm_id.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_\-]*", algorithm_id):
        raise SystemExit("algorithm_id must use lowercase letters, digits, hyphen, or underscore")
    out = Path(args.card_dir).resolve() / f"{algorithm_id}.yaml"
    if out.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite existing card: {out}")
    text = f"""version: research_algorithm_card_v1
algorithm_id: {algorithm_id}
title: "TO_FILL"
source:
  kind: "paper"
  citation: "TO_FILL"
  url: "TO_FILL"
  checked_date: "{date.today().isoformat()}"
summary: >-
  TO_FILL
harness_fit:
  use_case: "TO_FILL"
  primary_track: "TO_FILL"
  integration_points:
    - "TO_FILL"
implementation:
  status: candidate
  today_build: "TO_FILL"
  files_to_touch:
    - "TO_FILL"
evals:
  metrics:
    - "TO_FILL"
  minimum_viable_run: "TO_FILL"
guardrails:
  - "TO_FILL"
notes: "TO_FILL"
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"Created {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-dir", default=str(DEFAULT_CARD_DIR))
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.set_defaults(func=cmd_validate)

    list_cmd = sub.add_parser("list")
    list_cmd.set_defaults(func=cmd_list)

    matrix = sub.add_parser("matrix")
    matrix.add_argument("--output-md", default=str(DEFAULT_MATRIX_MD))
    matrix.add_argument("--output-csv", default=str(DEFAULT_MATRIX_CSV))
    matrix.set_defaults(func=cmd_matrix)

    scaffold = sub.add_parser("scaffold")
    scaffold.add_argument("algorithm_id")
    scaffold.add_argument("--force", action="store_true")
    scaffold.set_defaults(func=cmd_scaffold)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
