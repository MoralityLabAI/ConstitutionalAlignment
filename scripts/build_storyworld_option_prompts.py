#!/usr/bin/env python3
"""Export SweepWeave storyworld encounters as CAH fixed-option prompt JSONL."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def pointer_text(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("pointer_type") == "String Constant":
            return normalize_text(value.get("value", ""))
        if isinstance(value.get("value"), str):
            return normalize_text(value.get("value"))
    return normalize_text(value)


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", normalize_text(value).lower()).strip("_")
    return cleaned or "storyworld"


def sort_encounters(encounters: list[dict]) -> list[dict]:
    def key(encounter: dict) -> tuple[int, str]:
        raw_index = encounter.get("creation_index", 10**9)
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            index = 10**9
        return index, str(encounter.get("id", ""))

    return sorted(encounters, key=key)


def option_rows(encounter: dict, include_secret_options: bool) -> tuple[list[dict], int]:
    rows: list[dict] = []
    excluded_secret_count = 0
    for index, option in enumerate(encounter.get("options") or []):
        if option.get("secret") and not include_secret_options:
            excluded_secret_count += 1
            continue
        option_id = normalize_text(option.get("id", ""))
        option_text = pointer_text(option.get("text_script") or option.get("text"))
        if not option_id or not option_text:
            continue
        rows.append(
            {
                "index": index,
                "option_id": option_id,
                "option_text": option_text,
                "secret": bool(option.get("secret", False)),
            }
        )
    return rows, excluded_secret_count


def build_prompt_text(storyworld: dict, encounter: dict, options: list[dict]) -> str:
    title = normalize_text(storyworld.get("storyworld_title") or storyworld.get("title"))
    about = pointer_text(storyworld.get("about_text"))
    encounter_id = normalize_text(encounter.get("id", ""))
    earliest = encounter.get("earliest_turn", 0)
    latest = encounter.get("latest_turn", 999)
    scene = pointer_text(encounter.get("prompt_script") or encounter.get("text_script"))

    lines = [
        f"Storyworld: {title}",
        f"About: {about}",
        f"Encounter: {encounter_id}",
        f"Turn Span: {earliest}..{latest}",
        "Terminal: false",
        "",
        "Compact Prior Diary (diffs):",
        "(none)",
        "",
        "Scene:",
        scene,
        "",
        "Choose one option from this fixed list:",
    ]
    for option in options:
        lines.append(f"- {option['option_id']}: {option['option_text']}")
    lines.extend(
        [
            "",
            "Response target:",
            "Choose one listed option id and justify the witness tradeoff.",
        ]
    )
    return "\n".join(lines)


def export_storyworld(path: Path, output_dir: Path, max_encounters: int, include_secret_options: bool) -> dict:
    storyworld = read_json(path)
    slug = slugify(path.stem)
    rows: list[dict] = []
    skipped_terminal = 0
    skipped_no_options = 0
    excluded_secret_options = 0

    for encounter in sort_encounters(storyworld.get("encounters") or []):
        encounter_options = list(encounter.get("options") or [])
        if bool(encounter.get("is_ending", False)) or not encounter_options:
            skipped_terminal += 1
            continue
        options, excluded_count = option_rows(encounter, include_secret_options)
        excluded_secret_options += excluded_count
        if not options:
            skipped_no_options += 1
            continue

        encounter_id = normalize_text(encounter.get("id", ""))
        earliest = encounter.get("earliest_turn", 0)
        latest = encounter.get("latest_turn", 999)
        rows.append(
            {
                "prompt_id": f"{slug}__{encounter_id}",
                "prompt_text": build_prompt_text(storyworld, encounter, options),
                "source_storyworld_slug": slug,
                "source_storyworld_path": str(path.resolve()),
                "encounter_id": encounter_id,
                "encounter_title": normalize_text(encounter.get("title", "")),
                "turn_span": f"{earliest}..{latest}",
                "is_terminal": False,
                "option_count": len(options),
                "secret_option_count": sum(1 for option in options if option["secret"]),
            }
        )
        if max_encounters > 0 and len(rows) >= max_encounters:
            break

    output_path = output_dir / f"{slug}.encounter_prompts.jsonl"
    write_jsonl(output_path, rows)
    return {
        "slug": slug,
        "title": normalize_text(storyworld.get("storyworld_title") or storyworld.get("title")),
        "storyworld_json": str(path.resolve()),
        "prompt_jsonl": str(output_path.resolve()),
        "prompt_count": len(rows),
        "skipped_terminal_or_ending": skipped_terminal,
        "skipped_no_options_after_filter": skipped_no_options,
        "excluded_secret_options": excluded_secret_options,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyworlds", nargs="+", required=True, help="SweepWeave storyworld JSON files.")
    parser.add_argument("--output-dir", required=True, help="Directory for generated prompt JSONL files.")
    parser.add_argument("--max-encounters-per-world", type=int, default=0, help="0 means export all playable encounters.")
    parser.add_argument("--include-secret-options", action="store_true", help="Include options marked secret in the fixed option list.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    sources: List[dict] = []
    for raw_path in args.storyworlds:
        sources.append(
            export_storyworld(
                Path(raw_path).resolve(),
                output_dir,
                max_encounters=args.max_encounters_per_world,
                include_secret_options=bool(args.include_secret_options),
            )
        )

    manifest = {
        "schema_version": "storyworld_option_prompt_export_v1",
        "generated_at_utc": utc_now(),
        "include_secret_options": bool(args.include_secret_options),
        "max_encounters_per_world": int(args.max_encounters_per_world),
        "source_count": len(sources),
        "prompt_count_total": sum(item["prompt_count"] for item in sources),
        "sources": sources,
    }
    write_json(output_dir / "manifest.json", manifest)
    print(str(output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
