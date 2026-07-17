#!/usr/bin/env python3
"""Reconstruct and freeze the prospective frame-internalization eval universes.

The selection recipe is recovered from the predecessor session receipts.  The
canonical predecessor row files were not recovered, so every emitted receipt
keeps ``exact_recovery`` false even when its truncated set hashes match the
session-recorded values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments" / "frame_internalization_sft_v1"
DEFAULT_OUTPUT = PACKAGE / "rerun_freeze" / "evaluation_universes_v1"
DEFAULT_RECEIPT = PACKAGE / "rerun_freeze" / "evaluation_universes_v1.json"
DEFAULT_SEAL = PACKAGE / "readiness" / "evaluation_seal_v1.json"

SEED = 42
SOURCE_FILES = {
    "harmful": {
        "filename": "harmful.parquet",
        "repository": "LLM-LAT/harmful-dataset",
        "revision": "8bfba31bc6d93a5b71808fee5275ef4b6330ed91",
        "path": "data/train-00000-of-00001.parquet",
        "sha256": "51a41eaebf21eabec33ea90366d01d5bee7edb933d439c7017ad6e0107a645b1",
        "license": None,
        "license_status": "unresolved",
    },
    "benign": {
        "filename": "alpaca.parquet",
        "repository": "tatsu-lab/alpaca",
        "revision": "dce01c9b08f87459cf36a430d809084718273017",
        "path": "data/train-00000-of-00001-a09b74b3ef9c3b56.parquet",
        "sha256": "06391b656a06fd3fb9d213160ef2398796c3b7f3dc75ef1e3ced30d461517073",
        "license": "CC-BY-NC-4.0",
        "license_status": "declared",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--seal", type=Path, default=DEFAULT_SEAL)
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def text_sha16(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))[:16]


def ordered_set_sha16(texts: Iterable[str]) -> str:
    return sha256_bytes("\n".join(texts).encode("utf-8"))[:16]


def exact_dedup(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(body, encoding="utf-8", newline="\n")


def load_pools(source_dir: Path) -> tuple[list[str], list[str]]:
    paths = {key: source_dir / value["filename"] for key, value in SOURCE_FILES.items()}
    for key, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"missing {key} source parquet: {path}")
        observed = sha256_file(path)
        expected = SOURCE_FILES[key]["sha256"]
        if observed != expected:
            raise ValueError(f"{key} source SHA-256 mismatch: expected {expected}, observed {observed}")

    harmful_df = pd.read_parquet(paths["harmful"], columns=["prompt"])
    harmful = exact_dedup(str(value) for value in harmful_df["prompt"] if isinstance(value, str))

    benign_df = pd.read_parquet(paths["benign"], columns=["instruction", "input"])
    benign = exact_dedup(
        str(row.instruction)
        for row in benign_df.itertuples(index=False)
        if isinstance(row.instruction, str)
        and isinstance(row.input, str)
        and row.input == ""
        and len(row.instruction) > 20
    )
    if len(harmful) != 4946 or len(benign) != 31241:
        raise ValueError(f"unexpected pool sizes: harmful={len(harmful)}, benign={len(benign)}")
    return harmful, benign


def select_rows(harmful: list[str], benign: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(SEED)
    harmful_indices = sorted(rng.sample(range(len(harmful)), 200))
    benign_indices = sorted(rng.sample(range(len(benign)), 100))
    harmful_rows = [
        {"prompt_id": f"h{index:03d}", "sha": text_sha16(harmful[source]), "split": "harmful", "text": harmful[source]}
        for index, source in enumerate(harmful_indices)
    ]
    benign_rows = [
        {"prompt_id": f"b{index:03d}", "sha": text_sha16(benign[source]), "split": "benign", "text": benign[source]}
        for index, source in enumerate(benign_indices)
    ]
    return harmful_rows, benign_rows


def select_override_rows(harmful_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Recovered experiment-2 scratch/validate_setup.py uses a fresh RNG here.
    selected = random.Random(SEED).sample(harmful_rows, 150)
    selected.sort(key=lambda row: row["prompt_id"])
    return [
        {
            "override_prompt_id": f"o{index:03d}",
            "source_prompt_id": row["prompt_id"],
            "sha": row["sha"],
            "split": "override_harmful",
            "text": row["text"],
        }
        for index, row in enumerate(selected)
    ]


def freeze(source_dir: Path, output_dir: Path, receipt_path: Path, seal_path: Path) -> dict[str, Any]:
    harmful, benign = load_pools(source_dir)
    harmful_rows, benign_rows = select_rows(harmful, benign)
    override_rows = select_override_rows(harmful_rows)

    expected = {
        "harmful": "3101e5efe15a6284",
        "benign": "aeeaa6ac1be36305",
    }
    observed = {
        "harmful": ordered_set_sha16(row["text"] for row in harmful_rows),
        "benign": ordered_set_sha16(row["text"] for row in benign_rows),
        "override": ordered_set_sha16(row["text"] for row in override_rows),
    }
    if observed["harmful"] != expected["harmful"] or observed["benign"] != expected["benign"]:
        raise ValueError(f"recovered truncated set hash mismatch: {observed}")

    files = {
        "harmful": output_dir / "harmful_queries.jsonl",
        "benign": output_dir / "benign_queries.jsonl",
        "override": output_dir / "override_queries.jsonl",
    }
    write_jsonl(files["harmful"], harmful_rows)
    write_jsonl(files["benign"], benign_rows)
    write_jsonl(files["override"], override_rows)

    materials = PACKAGE / "predecessor_recovery" / "session_extracted" / "experiment_2" / "recovered_worktree" / "src" / "materials.py"
    override_selector = PACKAGE / "predecessor_recovery" / "session_extracted" / "experiment_2" / "recovered_worktree" / "scratch" / "validate_setup.py"
    universe_files = {
        key: {
            "path": relative(path),
            "row_count": len({"harmful": harmful_rows, "benign": benign_rows, "override": override_rows}[key]),
            "sha256": sha256_file(path),
            "ordered_text_set_sha256_truncated_16": observed[key],
        }
        for key, path in files.items()
    }
    receipt = {
        "schema_version": "frame_internalization_evaluation_universes.v1",
        "status": "frozen_content_license_pending",
        "passed": False,
        "exact_recovery": False,
        "classification": "prospective_reconstruction_matching_recovered_selection_receipts",
        "seed": SEED,
        "selection_algorithm": "single seed-42 RNG samples harmful then benign indices; override uses a fresh seed-42 RNG over harmful rows",
        "selection_script": {"path": relative(Path(__file__)), "sha256": sha256_file(Path(__file__))},
        "override_selector_recovery": {"path": relative(override_selector), "sha256": sha256_file(override_selector)},
        "override_materials": {"path": relative(materials), "sha256": sha256_file(materials)},
        "sources": SOURCE_FILES,
        "source_pool_counts": {"harmful": len(harmful), "benign": len(benign)},
        "universes": universe_files,
        "recovered_set_hashes_matched": True,
        "blocking_issue": "LLM-LAT/harmful-dataset has no declared license in the pinned repository metadata; resolve before claiming the predecessor evaluation-universe gate passed.",
    }
    write_json(receipt_path, receipt)

    mihna_dir = REPO_ROOT / "data" / "storyworld_sources" / "constitutional_alignment_20260715_v1" / "evaluation"
    seal_inputs = [
        *files.values(),
        receipt_path,
        mihna_dir / "mihna_ca_eval_v2.encounter_prompts.jsonl",
        mihna_dir / "mihna_ca_eval_v2.adjudication.jsonl",
        materials,
    ]
    sealed_files = [
        {"path": relative(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in seal_inputs
    ]
    seal = {
        "schema_version": "frame_internalization_evaluation_seal.v1",
        "sealed": True,
        "opened": False,
        "sealed_at": "2026-07-17",
        "sealed_before_adapter_training_outputs": True,
        "exact_predecessor_recovery": False,
        "access_policy": {
            "training_code_may_read_evaluation_content": False,
            "outcome_analysis_may_open_only_after_all_registered_arms_complete": True,
            "hash_verification_does_not_count_as_opening": True,
        },
        "files": sealed_files,
        "content_manifest_sha256": sha256_bytes(
            "\n".join(f"{row['path']} {row['sha256']}" for row in sealed_files).encode("utf-8")
        ),
        "known_limitations": [
            "The canonical predecessor row files were not recovered.",
            "The pinned harmful source license remains unresolved; this does not alter the frozen bytes.",
        ],
    }
    write_json(seal_path, seal)
    return {"receipt": receipt, "seal": seal}


def main() -> int:
    args = parse_args()
    result = freeze(args.source_dir.resolve(), args.output_dir.resolve(), args.receipt.resolve(), args.seal.resolve())
    print(json.dumps({
        "status": result["receipt"]["status"],
        "recovered_set_hashes_matched": result["receipt"]["recovered_set_hashes_matched"],
        "sealed": result["seal"]["sealed"],
        "opened": result["seal"]["opened"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
