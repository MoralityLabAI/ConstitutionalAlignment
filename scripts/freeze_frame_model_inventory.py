#!/usr/bin/env python3
"""Freeze the remote INTELLECT-3 artifact inventory at an immutable revision."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "experiments/frame_internalization_sft_v1/rerun_freeze/model_tokenizer_remote_inventory_v1.json"
)
DEFAULT_RECOVERED_TEMPLATE = (
    REPO_ROOT
    / "experiments/frame_internalization_sft_v1/predecessor_recovery/session_extracted/"
    "experiment_1/model/chat_template.jinja"
)
MODEL_ID = "PrimeIntellect/INTELLECT-3"
REVISION = "ff39d4a4688989f3f28868923d030c28e1b7d81c"
REQUIRED_SMALL_FILES = (
    "chat_template.jinja",
    "config.json",
    "generation_config.json",
    "model.safetensors.index.json",
    "special_tokens_map.json",
    "tokenizer_config.json",
)
REQUIRED_LFS_FILES = ("tokenizer.json",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--recovered-template", type=Path, default=DEFAULT_RECOVERED_TEMPLATE)
    parser.add_argument("--freeze-date", default="2026-07-19")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    return parser.parse_args()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(payload.encode("utf-8"))


def fetch_json(url: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object from {url}")
    return value


def fetch_bytes(url: str, timeout: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def main() -> int:
    args = parse_args()
    api_url = f"https://huggingface.co/api/models/{MODEL_ID}/revision/{REVISION}?blobs=true"
    metadata = fetch_json(api_url, args.timeout_seconds)
    if metadata.get("sha") != REVISION:
        raise RuntimeError(f"revision mismatch: expected {REVISION}, got {metadata.get('sha')}")

    siblings = {item["rfilename"]: item for item in metadata.get("siblings", [])}
    weight_names = sorted(
        name for name in siblings if name.startswith("model-") and name.endswith(".safetensors")
    )
    expected_weights = [f"model-{index:05d}-of-00048.safetensors" for index in range(1, 49)]
    if weight_names != expected_weights:
        raise RuntimeError("remote weight inventory is not the expected ordered 48-shard set")

    artifacts: list[dict[str, Any]] = []
    for name in weight_names + list(REQUIRED_LFS_FILES):
        item = siblings.get(name, {})
        lfs = item.get("lfs", {})
        if not lfs.get("sha256") or not lfs.get("size"):
            raise RuntimeError(f"missing LFS digest or size for {name}")
        artifacts.append(
            {
                "path": name,
                "kind": "weight" if name.endswith(".safetensors") else "tokenizer",
                "size_bytes": int(lfs["size"]),
                "sha256": str(lfs["sha256"]),
                "git_blob_id": item.get("blobId"),
            }
        )

    downloaded: dict[str, bytes] = {}
    for name in REQUIRED_SMALL_FILES:
        if name not in siblings:
            raise RuntimeError(f"required remote artifact is missing: {name}")
        url = f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}"
        content = fetch_bytes(url, args.timeout_seconds)
        downloaded[name] = content
        artifacts.append(
            {
                "path": name,
                "kind": "chat_template" if name == "chat_template.jinja" else "configuration",
                "size_bytes": len(content),
                "sha256": sha256_bytes(content),
                "git_blob_id": siblings[name].get("blobId"),
            }
        )

    artifacts.sort(key=lambda item: item["path"])
    recovered_template = args.recovered_template.resolve()
    recovered_hash = sha256_bytes(recovered_template.read_bytes())
    remote_template_hash = sha256_bytes(downloaded["chat_template.jinja"])
    aggregate_input = {
        "repository": MODEL_ID,
        "revision": REVISION,
        "artifacts": artifacts,
    }
    inventory = {
        "schema_version": "frame_internalization_model_remote_inventory.v1",
        "freeze_date": args.freeze_date,
        "status": "remote_frozen_local_verification_pending",
        "passed": False,
        "immutable_revisions": True,
        "repository": MODEL_ID,
        "revision": REVISION,
        "license": metadata.get("cardData", {}).get("license"),
        "official_api_url": api_url,
        "builder": {
            "path": Path(__file__).resolve().relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_bytes(Path(__file__).resolve().read_bytes()),
        },
        "weight_shard_count": len(weight_names),
        "weight_bytes": sum(item["size_bytes"] for item in artifacts if item["kind"] == "weight"),
        "artifact_count": len(artifacts),
        "artifact_inventory_sha256": canonical_sha256(aggregate_input),
        "artifacts": artifacts,
        "chat_template_comparison": {
            "recovered_path": recovered_template.relative_to(REPO_ROOT).as_posix(),
            "recovered_sha256": recovered_hash,
            "remote_sha256": remote_template_hash,
            "byte_identical": recovered_hash == remote_template_hash,
        },
        "completion_requirements": [
            "verify every listed artifact against the cluster-local model cache",
            "record a SHA-256 for the exact inference-engine image digest or lockfile",
            "emit frame_internalization_base_freeze.v1 with passed=true only after both checks pass",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": inventory["status"], "artifacts": len(artifacts)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
