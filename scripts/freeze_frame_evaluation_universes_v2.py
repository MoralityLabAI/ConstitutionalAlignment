#!/usr/bin/env python3
"""Freeze the prospective licensed HarmBench evaluation-universe substitution."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "experiments" / "frame_internalization_sft_v1"
FREEZE = PACKAGE / "rerun_freeze"
DEFAULT_OUTPUT = FREEZE / "evaluation_universes_v2"
DEFAULT_RECEIPT = FREEZE / "evaluation_universes_v2.json"
DEFAULT_SEAL = PACKAGE / "readiness" / "evaluation_seal_v2.json"
V1_BENIGN = FREEZE / "evaluation_universes_v1" / "benign_queries.jsonl"
MIHNA = (
    REPO_ROOT
    / "data/storyworld_sources/constitutional_alignment_20260715_v1/evaluation"
)
MATERIALS = (
    PACKAGE
    / "predecessor_recovery/session_extracted/experiment_2/recovered_worktree/src/materials.py"
)

SEED = 42
HARMBENCH_REVISION = "8e1604d1171fe8a48d8febecd22f600e462bdcdd"
HARMBENCH_CSV = Path("data/behavior_datasets/harmbench_behaviors_text_all.csv")
HARMBENCH_CSV_SHA256 = "8d81accedd38eaaf8b760618622bb888417d1fd0c86eba65c427a16f1cbb4afc"
HARMBENCH_LICENSE_SHA256 = "fb424622fb4d8c1d7f952258dc56ed1e8e8b7ecc242f7db43ccb5a608205ec5b"
V1_BENIGN_SHA256 = "841e21fce209d7607b911320288de47e9daa1a2e0a1d60214138200cc4537c01"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harmbench-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--seal", type=Path, default=DEFAULT_SEAL)
    parser.add_argument("--freeze-date", default="2026-07-19")
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def text_sha16(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))[:16]


def ordered_set_sha16(texts: Iterable[str]) -> str:
    return sha256_bytes("\n".join(texts).encode("utf-8"))[:16]


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    body = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")


def verify_harmbench(root: Path) -> tuple[Path, Path]:
    csv_path = root / HARMBENCH_CSV
    license_path = root / "LICENSE"
    for path in (csv_path, license_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    if sha256_file(csv_path) != HARMBENCH_CSV_SHA256:
        raise ValueError("HarmBench behavior CSV SHA-256 mismatch")
    if sha256_file(license_path) != HARMBENCH_LICENSE_SHA256:
        raise ValueError("HarmBench root LICENSE SHA-256 mismatch")
    observed_revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if observed_revision != HARMBENCH_REVISION:
        raise ValueError(
            f"HarmBench revision mismatch: {observed_revision} != {HARMBENCH_REVISION}"
        )
    return csv_path, license_path


def build_harmful_rows(csv_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    expected_columns = {
        "Behavior",
        "FunctionalCategory",
        "SemanticCategory",
        "Tags",
        "ContextString",
        "BehaviorID",
    }
    if len(source_rows) != 400 or set(source_rows[0]) != expected_columns:
        raise ValueError("unexpected HarmBench CSV schema or row count")
    standard = [row for row in source_rows if row["FunctionalCategory"] == "standard"]
    if len(standard) != 200:
        raise ValueError("HarmBench standard subset must contain exactly 200 rows")
    if len({row["BehaviorID"] for row in standard}) != 200:
        raise ValueError("HarmBench standard BehaviorID values must be unique")
    if any(row["ContextString"].strip() for row in standard):
        raise ValueError("HarmBench standard rows unexpectedly contain contexts")
    if any(not row["Behavior"].strip() for row in standard):
        raise ValueError("HarmBench standard row has an empty behavior")

    rows = [
        {
            "prompt_id": f"h{index:03d}",
            "sha": text_sha16(source["Behavior"]),
            "split": "harmful",
            "text": source["Behavior"],
        }
        for index, source in enumerate(standard)
    ]
    metadata = {
        "source_row_count": len(source_rows),
        "selected_functional_category": "standard",
        "selected_row_count": len(standard),
        "unique_behavior_id_count": len({row["BehaviorID"] for row in standard}),
        "nonempty_context_count": sum(bool(row["ContextString"].strip()) for row in standard),
        "ordered_behavior_ids_sha256": sha256_bytes(
            "\n".join(row["BehaviorID"] for row in standard).encode("utf-8")
        ),
        "semantic_category_counts": dict(
            sorted(Counter(row["SemanticCategory"] for row in standard).items())
        ),
    }
    return rows, metadata


def load_benign_rows() -> list[dict[str, Any]]:
    if sha256_file(V1_BENIGN) != V1_BENIGN_SHA256:
        raise ValueError("v1 benign universe SHA-256 mismatch")
    rows = [
        json.loads(line)
        for line in V1_BENIGN.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != 100 or [row["prompt_id"] for row in rows] != [
        f"b{index:03d}" for index in range(100)
    ]:
        raise ValueError("v1 benign universe invariants failed")
    return rows


def build_override_rows(harmful_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def file_binding(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "path": relative(path),
        "row_count": len(rows),
        "sha256": sha256_file(path),
        "ordered_text_set_sha256_truncated_16": ordered_set_sha16(
            str(row["text"]) for row in rows
        ),
    }


def freeze(
    harmbench_root: Path,
    output_dir: Path,
    receipt_path: Path,
    seal_path: Path,
    freeze_date: str,
) -> dict[str, Any]:
    csv_path, source_license = verify_harmbench(harmbench_root)
    harmful_rows, source_metadata = build_harmful_rows(csv_path)
    benign_rows = load_benign_rows()
    override_rows = build_override_rows(harmful_rows)

    files = {
        "harmful": output_dir / "harmful_queries.jsonl",
        "benign": output_dir / "benign_queries.jsonl",
        "override": output_dir / "override_queries.jsonl",
    }
    write_jsonl(files["harmful"], harmful_rows)
    write_jsonl(files["benign"], benign_rows)
    write_jsonl(files["override"], override_rows)
    license_copy = output_dir / "HarmBench_LICENSE.txt"
    shutil.copyfile(source_license, license_copy)
    if sha256_file(license_copy) != HARMBENCH_LICENSE_SHA256:
        raise RuntimeError("copied HarmBench license is not byte-identical")

    universes = {
        "harmful": file_binding(files["harmful"], harmful_rows),
        "benign": file_binding(files["benign"], benign_rows),
        "override": file_binding(files["override"], override_rows),
    }
    receipt = {
        "schema_version": "frame_internalization_evaluation_universes.v2",
        "status": "frozen_licensed_prospective_substitution",
        "passed": True,
        "frozen_at": freeze_date,
        "exact_recovery": False,
        "classification": "prospective_licensed_substitution_before_affected_outcomes",
        "seed": SEED,
        "selection_algorithm": (
            "all HarmBench rows whose FunctionalCategory is exactly standard, in pinned CSV "
            "order; override uses a fresh seed-42 sample of 150 harmful rows and then sorts "
            "by replacement prompt_id; benign rows are byte-preserved from v1"
        ),
        "selection_script": {
            "path": relative(Path(__file__)),
            "sha256": sha256_file(Path(__file__)),
        },
        "sources": {
            "harmful": {
                "repository": "centerforaisafety/HarmBench",
                "revision": HARMBENCH_REVISION,
                "path": HARMBENCH_CSV.as_posix(),
                "sha256": HARMBENCH_CSV_SHA256,
                "license": "MIT",
                "license_status": "declared_in_repository_root",
                "license_path": "LICENSE",
                "license_sha256": HARMBENCH_LICENSE_SHA256,
                "license_copy": {
                    "path": relative(license_copy),
                    "sha256": sha256_file(license_copy),
                },
                "repository_url": "https://github.com/centerforaisafety/HarmBench",
                "source_file_url": (
                    "https://github.com/centerforaisafety/HarmBench/blob/"
                    f"{HARMBENCH_REVISION}/{HARMBENCH_CSV.as_posix()}"
                ),
                "license_url": (
                    "https://github.com/centerforaisafety/HarmBench/blob/"
                    f"{HARMBENCH_REVISION}/LICENSE"
                ),
                **source_metadata,
            },
            "benign": {
                "repository": "tatsu-lab/alpaca",
                "revision": "dce01c9b08f87459cf36a430d809084718273017",
                "source_path": "data/train-00000-of-00001-a09b74b3ef9c3b56.parquet",
                "source_sha256": "06391b656a06fd3fb9d213160ef2398796c3b7f3dc75ef1e3ced30d461517073",
                "license": "CC-BY-NC-4.0",
                "license_status": "declared",
                "copied_from_v1_universe_sha256": V1_BENIGN_SHA256,
            },
        },
        "universes": universes,
        "historical_reanchor_compatibility": {
            "exact_predecessor_reanchor": False,
            "recovered_f0_interval_is_confirmatory_target": False,
            "required_baseline": "new prospective base F0 estimate on v2",
            "historical_interval_role": "descriptive provenance only",
        },
        "license_gate": {
            "passed": True,
            "basis": "pinned source CSV is distributed in the official repository under its root MIT license",
            "redistribution": "retain the MIT license copy and attribution with the frozen subset",
        },
    }
    write_json(receipt_path, receipt)

    seal_inputs = [
        *files.values(),
        receipt_path,
        license_copy,
        MIHNA / "mihna_ca_eval_v2.encounter_prompts.jsonl",
        MIHNA / "mihna_ca_eval_v2.adjudication.jsonl",
        MATERIALS,
    ]
    sealed_files = [
        {"path": relative(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in seal_inputs
    ]
    seal = {
        "schema_version": "frame_internalization_evaluation_seal.v2",
        "sealed": True,
        "opened": False,
        "sealed_at": freeze_date,
        "sealed_before_adapter_training_outputs": True,
        "exact_predecessor_recovery": False,
        "evaluation_universe_version": "v2_harmbench_standard",
        "access_policy": {
            "training_code_may_read_evaluation_content": False,
            "outcome_analysis_may_open_only_after_all_registered_arms_complete": True,
            "hash_verification_does_not_count_as_opening": True,
        },
        "files": sealed_files,
        "content_manifest_sha256": sha256_bytes(
            "\n".join(f"{item['path']} {item['sha256']}" for item in sealed_files).encode(
                "utf-8"
            )
        ),
        "known_limitations": [
            "This prospective substitution does not reproduce the predecessor evaluation universe.",
            "The recovered F0 calibration interval is descriptive and is not a pass/fail target on v2.",
        ],
    }
    write_json(seal_path, seal)
    return {"receipt": receipt, "seal": seal}


def main() -> int:
    args = parse_args()
    result = freeze(
        args.harmbench_root.resolve(),
        args.output_dir.resolve(),
        args.receipt.resolve(),
        args.seal.resolve(),
        args.freeze_date,
    )
    print(
        json.dumps(
            {
                "receipt": str(args.receipt),
                "seal": str(args.seal),
                "passed": result["receipt"]["passed"],
                "harmful_rows": result["receipt"]["universes"]["harmful"]["row_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
