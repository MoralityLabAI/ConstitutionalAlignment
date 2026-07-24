#!/usr/bin/env python3
"""Freeze one deterministic held-out trace sentinel per Jinn v2 family."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    prompts_path = args.prompts.resolve()
    manifest_path = args.manifest.resolve()
    prompts = read_jsonl(prompts_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    development_families = manifest["development_families"]
    prompt_map = {
        (row["family_id"], row["variant_id"]): row
        for row in prompts
    }
    selected = []
    selection = []
    for family_id in development_families:
        variants = manifest["family_metadata"][family_id]["variant_ids"]
        variant_id = variants[-1]
        key = (family_id, variant_id)
        if key not in prompt_map:
            raise ValueError(f"missing deterministic trace sentinel {key}")
        selected.append(prompt_map[key])
        selection.append({"family_id": family_id, "variant_id": variant_id})
    if len(selected) != 4:
        raise ValueError("expected one sentinel from each of four development families")

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in selected),
        encoding="utf-8",
        newline="\n",
    )
    receipt = {
        "schema_version": "jinn_reasoner_v2_trace_sentinel_selection_v1",
        "status": "frozen",
        "selection_rule": "last registered variant in manifest order for each development family",
        "rows": len(selected),
        "selection": selection,
        "source_prompts_sha256": sha256_file(prompts_path),
        "source_manifest_sha256": sha256_file(manifest_path),
        "output_sha256": sha256_file(output_path),
        "claim_boundary": "Exploratory secondary trace lane; not the behavioral reward denominator.",
    }
    receipt_path = args.receipt.resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
