#!/usr/bin/env python3
"""Build an aggregate manifest over exported constitutional corpus shards."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List


def read_jsonl(path: Path) -> List[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards-root", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    root = Path(args.shards_root).resolve()
    shard_files = sorted(p for p in root.glob("*.jsonl") if p.is_file())
    if not shard_files:
        raise SystemExit(f"No shard files found under {root}")

    summary = {
        "status": "completed",
        "shards_root": str(root),
        "shard_count": len(shard_files),
        "total_examples": 0,
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "constitutions": {},
        "task_types": {},
        "source_worlds": {},
        "shards": [],
    }
    constitutions = Counter()
    task_types = Counter()
    source_worlds = Counter()

    for shard in shard_files:
        rows = read_jsonl(shard)
        prompt_tokens = sum(int((row.get("generation", {}) or {}).get("prompt_tokens", 0) or 0) for row in rows)
        completion_tokens = sum(int((row.get("generation", {}) or {}).get("completion_tokens", 0) or 0) for row in rows)
        shard_constitutions = Counter(str(row.get("constitution_id", "") or "") for row in rows)
        for row in rows:
            constitutions[str(row.get("constitution_id", "") or "")] += 1
            task_types[str(row.get("task_type", "") or "")] += 1
            source_worlds[str(row.get("source_world", "") or "")] += 1
        summary["total_examples"] += len(rows)
        summary["total_prompt_tokens"] += prompt_tokens
        summary["total_completion_tokens"] += completion_tokens
        summary["shards"].append(
            {
                "path": str(shard),
                "examples": len(rows),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "constitutions": dict(sorted(shard_constitutions.items())),
            }
        )

    summary["constitutions"] = dict(sorted(constitutions.items()))
    summary["task_types"] = dict(sorted(task_types.items()))
    summary["source_worlds"] = dict(sorted(source_worlds.items()))

    output_path = Path(args.output_json).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
