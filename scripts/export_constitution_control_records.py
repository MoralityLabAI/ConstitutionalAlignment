#!/usr/bin/env python3
"""Export constitutional storyworld prompt runs into canonical control records."""

from __future__ import annotations

import argparse
from pathlib import Path

from constitution_bridge import (
    build_control_record,
    ensure_dir,
    read_json,
    read_jsonl,
    summarize_control_records,
    utc_now,
    write_json,
    write_jsonl,
)


def iter_generation_files(run_dir: Path):
    for path in sorted(run_dir.rglob("generations.jsonl")):
        if path.is_file():
            yield path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Run directory containing per-condition generations.jsonl files.")
    parser.add_argument("--output-jsonl", required=True, help="Output JSONL for constitution_control_record_v1 rows.")
    parser.add_argument("--output-manifest", default="", help="Optional manifest path. Defaults beside output JSONL.")
    parser.add_argument("--include-low-quality", action="store_true", help="Keep low-quality records in the exported JSONL.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        raise SystemExit(f"Run dir not found: {run_dir}")

    output_path = Path(args.output_jsonl).resolve()
    ensure_dir(output_path.parent)
    manifest_path = Path(args.output_manifest).resolve() if args.output_manifest else output_path.with_suffix(".manifest.json")

    run_manifest_file = run_dir / "manifest.json"
    run_manifest = read_json(run_manifest_file) if run_manifest_file.exists() else {}

    records = []
    skipped_low_quality = 0
    source_files = list(iter_generation_files(run_dir))
    episode_idx = 0
    for source_file in source_files:
        for row in read_jsonl(source_file):
            record = build_control_record(row, run_dir, source_file, run_manifest, episode_idx)
            episode_idx += 1
            if record["quality"]["is_low_quality"] and not args.include_low_quality:
                skipped_low_quality += 1
                continue
            records.append(record)

    write_jsonl(output_path, records)
    summary = summarize_control_records(records)
    manifest = {
        "status": "completed",
        "generated_at_utc": utc_now(),
        "run_dir": str(run_dir),
        "output_jsonl": str(output_path),
        "source_generation_files": [str(path) for path in source_files],
        "schema_json": str((Path(__file__).resolve().parent.parent / "schemas" / "constitution_control_record_v1.schema.json").resolve()),
        "include_low_quality": bool(args.include_low_quality),
        "skipped_low_quality_records": skipped_low_quality,
        **summary,
    }
    write_json(manifest_path, manifest)
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
