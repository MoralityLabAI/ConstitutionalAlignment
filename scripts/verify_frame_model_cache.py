#!/usr/bin/env python3
"""Verify a cluster-local model cache and inference-engine lock fail-closed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INVENTORY = (
    REPO_ROOT
    / "experiments/frame_internalization_sft_v1/rerun_freeze/model_tokenizer_remote_inventory_v1.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--engine-lock", type=Path, required=True)
    parser.add_argument("--engine-description", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verification-date", default="2026-07-19")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def main() -> int:
    args = parse_args()
    inventory_path = args.inventory.resolve()
    inventory = read_json(inventory_path)
    if inventory.get("schema_version") != "frame_internalization_model_remote_inventory.v1":
        raise ValueError("unexpected model inventory schema")

    model_dir = args.model_dir.resolve()
    engine_lock = args.engine_lock.resolve()
    checks: list[dict[str, Any]] = []
    for artifact in inventory.get("artifacts", []):
        path = model_dir / artifact["path"]
        exists = path.is_file()
        observed_size = path.stat().st_size if exists else None
        observed_hash = sha256_file(path) if exists and observed_size == artifact["size_bytes"] else None
        checks.append(
            {
                "path": artifact["path"],
                "expected_size_bytes": artifact["size_bytes"],
                "observed_size_bytes": observed_size,
                "expected_sha256": artifact["sha256"],
                "observed_sha256": observed_hash,
                "passed": exists
                and observed_size == artifact["size_bytes"]
                and observed_hash == artifact["sha256"],
            }
        )

    engine_exists = engine_lock.is_file()
    engine_hash = sha256_file(engine_lock) if engine_exists else None
    artifacts_passed = len(checks) == inventory.get("artifact_count") and all(
        check["passed"] for check in checks
    )
    passed = bool(
        inventory.get("immutable_revisions") is True
        and inventory.get("chat_template_comparison", {}).get("byte_identical") is True
        and artifacts_passed
        and engine_exists
        and engine_hash
    )
    receipt = {
        "schema_version": "frame_internalization_base_freeze.v1",
        "verification_date": args.verification_date,
        "passed": passed,
        "immutable_revisions": True,
        "repository": inventory["repository"],
        "revision": inventory["revision"],
        "license": inventory.get("license"),
        "remote_inventory_path": str(inventory_path),
        "remote_inventory_sha256": sha256_file(inventory_path),
        "model_dir": str(model_dir),
        "artifact_inventory_sha256": inventory["artifact_inventory_sha256"],
        "artifact_checks": checks,
        "engine": {
            "description": args.engine_description,
            "lock_path": str(engine_lock),
            "lock_sha256": engine_hash,
            "passed": engine_exists and engine_hash is not None,
        },
        "failures": [check["path"] for check in checks if not check["passed"]]
        + ([] if engine_exists else ["inference_engine_lock"]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "passed": passed, "failures": receipt["failures"]}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
