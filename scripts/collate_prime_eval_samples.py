"""Collate a completed Prime hosted evaluation into local immutable artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prime_json(arguments: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        ["prime", "--plain", *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise TypeError("Prime CLI did not return a JSON object")
    return value


def canonical_row(sample: dict[str, Any]) -> dict[str, Any]:
    state = sample.get("info")
    if not isinstance(state, dict):
        raise TypeError("hosted sample is missing its info state")
    required = {
        "task_id",
        "pair_id",
        "family_id",
        "split",
        "frame",
        "cell_type",
        "mesh_trace",
        "mesh_receipt",
        "metrics",
    }
    missing = sorted(required.difference(state))
    if missing:
        raise ValueError(f"hosted sample state is missing {missing}")
    row = dict(sample)
    row["info"] = state
    for key in (
        "mesh_trace",
        "mesh_receipt",
        "metrics",
        "is_truncated",
        "stop_condition",
    ):
        row[key] = state[key]
    return row


def collect_samples(evaluation_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata = prime_json(["eval", "get", evaluation_id, "--output", "json"])
    if metadata.get("status") != "COMPLETED":
        raise ValueError(f"evaluation is not complete: {metadata.get('status')!r}")
    expected = int(metadata["total_samples"])
    page = 1
    samples: list[dict[str, Any]] = []
    while len(samples) < expected:
        payload = prime_json(
            [
                "eval",
                "samples",
                evaluation_id,
                "--page",
                str(page),
                "--num",
                "100",
                "--output",
                "json",
            ]
        )
        batch = payload.get("samples")
        if not isinstance(batch, list) or not batch:
            raise ValueError(f"Prime returned an empty sample page {page}")
        if not all(isinstance(sample, dict) for sample in batch):
            raise TypeError(f"Prime returned a malformed sample page {page}")
        samples.extend(batch)
        page += 1
    if len(samples) != expected:
        raise ValueError(
            f"sample join mismatch: expected {expected}, received {len(samples)}"
        )
    return metadata, samples


def write_artifacts(
    *,
    evaluation_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    metadata, samples = collect_samples(evaluation_id)
    rows = [canonical_row(sample) for sample in samples]
    output_dir.mkdir(parents=True, exist_ok=False)
    metadata_path = output_dir / "evaluation.json"
    samples_path = output_dir / "results.jsonl"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    samples_path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    receipt = {
        "schema_version": "prime_hosted_eval_collation_v1",
        "evaluation_id": evaluation_id,
        "environment_version_id": metadata.get("version_id"),
        "model": metadata.get("model_name"),
        "status": metadata.get("status"),
        "samples": len(rows),
        "evaluation_sha256": sha256_file(metadata_path),
        "results_sha256": sha256_file(samples_path),
    }
    receipt_path = output_dir / "collation_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = write_artifacts(
        evaluation_id=str(args.eval_id),
        output_dir=args.output_dir.resolve(),
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
