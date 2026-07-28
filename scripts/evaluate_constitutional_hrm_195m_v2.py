#!/usr/bin/env python3
"""Evaluate one exported 195M constitutional HRM checkpoint on frozen suites."""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from tokenizers import Tokenizer

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitutional_hrm_eval_v2 import (
    native_balanced_indices,
    native_metadata,
    read_jsonl,
    sha256_file,
)
from alignment_harness.constitutional_hrm_metrics_v2 import (
    summarize_predictions,
)
from alignment_harness.constitutional_hrm_runtime_v2 import (
    ConstitutionalHrmRuntime,
)

DEFAULT_SUITES = (
    "moral_reasoner_raw",
    "moral_reasoner_structured",
    "storyworld_raw",
    "storyworld_structured",
    "storyworld_full_text",
    "prime_hub_mesh_v2_raw",
    "prime_hub_quranic_village_replay",
    "arc_zero_shot",
)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument(
        "--official-root",
        type=Path,
        default=REPO_ROOT.parent / ".codex-cache" / "HRM-ac15626",
    )
    parser.add_argument(
        "--tokenizer",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "tokenizer"
        / "tokenizer.json",
    )
    parser.add_argument(
        "--suite-dir",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "eval_suites_v2",
    )
    parser.add_argument(
        "--curriculum-dir",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "curriculum_production",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--gpu-memory-fraction", type=float, default=0.80)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--suites", nargs="*", default=list(DEFAULT_SUITES))
    parser.add_argument("--max-examples-per-suite", type=int)
    parser.add_argument("--include-constitutional-validation", action="store_true")
    parser.add_argument("--include-sealed", action="store_true")
    parser.add_argument("--sealed-authorization", type=Path)
    return parser.parse_args()


def _load_suite(
    suite_dir: Path, suite_id: str, max_examples: int | None
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    inputs = np.load(suite_dir / f"{suite_id}__inputs.npy", mmap_mode="r")
    labels = np.load(suite_dir / f"{suite_id}__labels.npy", mmap_mode="r")
    metadata = read_jsonl(suite_dir / f"{suite_id}__metadata.jsonl")
    limit = len(inputs) if max_examples is None else min(len(inputs), max_examples)
    return inputs[:limit], labels[:limit], metadata[:limit]


def main() -> int:
    args = parse_args()
    output = args.output_dir.resolve()
    if (output / "evaluation_receipt.json").exists():
        raise FileExistsError(f"refusing to overwrite evaluation output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    runtime = ConstitutionalHrmRuntime(
        checkpoint_path=args.checkpoint.resolve(),
        official_root=args.official_root.resolve(),
        device=args.device,
        gpu_memory_fraction=args.gpu_memory_fraction,
    )
    receipt: dict[str, Any] = {
        "schema_version": "constitutional_hrm_195m_eval_receipt_v2",
        "status": "preparing",
        "started_at_utc": started.isoformat(),
        "checkpoint": {
            "path": str(args.checkpoint.resolve()),
            "sha256": sha256_file(args.checkpoint.resolve()),
        },
        "sealed_test_opened": False,
        "suites": {},
    }
    atomic_json(output / "evaluation_receipt.json", receipt)
    cleanup: dict[str, Any] = {}
    try:
        suite_manifest = json.loads(
            (args.suite_dir.resolve() / "manifest.json").read_text(encoding="utf-8")
        )
        tokenizer = Tokenizer.from_file(str(args.tokenizer.resolve()))
        decision_ids = [
            int(tokenizer.token_to_id(f"<|decision:{index}|>"))
            for index in range(4)
        ]
        runtime_info = runtime.load()
        if not 190_000_000 <= runtime_info["parameter_count"] <= 205_000_000:
            raise ValueError("loaded checkpoint is outside the 190M-205M band")
        receipt["runtime"] = runtime_info
        receipt["suite_manifest_sha256"] = sha256_file(
            args.suite_dir.resolve() / "manifest.json"
        )

        suite_ids = list(args.suites)
        if args.include_constitutional_validation:
            suite_ids.insert(0, "constitutional_validation")
        if args.include_sealed:
            if args.sealed_authorization is None:
                raise ValueError(
                    "--include-sealed requires --sealed-authorization"
                )
            authorization_path = args.sealed_authorization.resolve()
            authorization = json.loads(
                authorization_path.read_text(encoding="utf-8")
            )
            expected_checkpoint = receipt["checkpoint"]["sha256"]
            authorized_checkpoints = set(
                map(str, authorization.get("checkpoint_sha256", []))
            )
            if (
                authorization.get("gate_id") != "F11E_SEALED_TEST_SINGLE_OPEN"
                or authorization.get("status") != "authorized"
                or not authorization.get("checkpoint_selection_frozen", False)
                or expected_checkpoint not in authorized_checkpoints
                or authorization.get("suite_manifest_sha256")
                != receipt["suite_manifest_sha256"]
                or authorization.get("curriculum_manifest_sha256")
                != sha256_file(args.curriculum_dir.resolve() / "manifest.json")
            ):
                raise ValueError("sealed authorization does not match this evaluation")
            suite_ids.append("constitutional_sealed")
            receipt["sealed_test_opened"] = True
            receipt["sealed_authorization"] = {
                "path": str(authorization_path),
                "sha256": sha256_file(authorization_path),
            }
            atomic_json(
                output / "sealed_unseal_receipt.json",
                {
                    "schema_version": "constitutional_hrm_sealed_unseal_v2",
                    "opened_at_utc": datetime.now(timezone.utc).isoformat(),
                    "checkpoint_sha256": receipt["checkpoint"]["sha256"],
                    "curriculum_manifest_sha256": sha256_file(
                        args.curriculum_dir.resolve() / "manifest.json"
                    ),
                    "checkpoint_selection_complete": True,
                },
            )

        for suite_id in suite_ids:
            if suite_id in {"constitutional_validation", "constitutional_sealed"}:
                stem = (
                    "validation"
                    if suite_id == "constitutional_validation"
                    else "sealed_test"
                )
                inputs = np.load(
                    args.curriculum_dir.resolve() / "common" / f"{stem}_inputs.npy",
                    mmap_mode="r",
                )
                labels = np.load(
                    args.curriculum_dir.resolve() / "common" / f"{stem}_labels.npy",
                    mmap_mode="r",
                )
                selected = native_balanced_indices(
                    len(inputs), args.max_examples_per_suite
                )
                inputs = inputs[selected]
                labels = labels[selected]
                metadata = native_metadata(
                    groups_path=args.curriculum_dir.resolve()
                    / "groups"
                    / f"{stem}.jsonl",
                    selected_indices=selected,
                    labels=np.asarray(labels),
                    decision_token_ids=decision_ids,
                )
                if suite_id == "constitutional_sealed":
                    for item in metadata:
                        item["split"] = "sealed_test"
            else:
                if suite_id not in suite_manifest["suites"]:
                    raise ValueError(f"suite is not frozen: {suite_id}")
                inputs, labels, metadata = _load_suite(
                    args.suite_dir.resolve(),
                    suite_id,
                    args.max_examples_per_suite,
                )
                expected = suite_manifest["suites"][suite_id]["files"]
                for filename, digest in expected.items():
                    if sha256_file(args.suite_dir.resolve() / filename) != digest:
                        raise ValueError(f"suite hash drift: {filename}")
            predictions = runtime.predict(
                np.asarray(inputs), batch_size=args.batch_size
            )
            metrics, rows = summarize_predictions(
                predictions=predictions,
                labels=np.asarray(labels),
                metadata=metadata,
                decision_token_ids=decision_ids,
            )
            write_jsonl(output / "predictions" / f"{suite_id}.jsonl", rows)
            receipt["suites"][suite_id] = {
                "status": "completed",
                "metrics": metrics,
                "examples": len(inputs),
            }
            atomic_json(output / "evaluation_receipt.json", receipt)
            del inputs, labels, metadata, predictions, rows
            gc.collect()
        receipt["status"] = "completed"
    except Exception as error:  # noqa: BLE001
        receipt["status"] = "failed"
        receipt["error"] = f"{type(error).__name__}: {error}"
    finally:
        cleanup = runtime.cleanup()
        receipt["cleanup"] = cleanup
        receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(output / "evaluation_receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
