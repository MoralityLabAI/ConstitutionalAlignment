#!/usr/bin/env python3
"""Freeze the official Qwen3-1.7B artifact inventory at an immutable revision."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_ID = "Qwen/Qwen3-1.7B"
REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "experiments/frame_internalization_sft_v1/rerun_freeze/qwen3_1p7b_v1/"
    "model_tokenizer_remote_inventory_v1.json"
)
EXPECTED_FILES = (
    ".gitattributes",
    "LICENSE",
    "README.md",
    "config.json",
    "generation_config.json",
    "merges.txt",
    "model-00001-of-00002.safetensors",
    "model-00002-of-00002.safetensors",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--freeze-date", default="2026-07-20")
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


def artifact_kind(name: str) -> str:
    if name.endswith(".safetensors"):
        return "weight"
    if name in {"tokenizer.json", "tokenizer_config.json", "merges.txt", "vocab.json"}:
        return "tokenizer"
    if name == "LICENSE":
        return "license"
    if name == "README.md":
        return "model_card"
    return "configuration"


def build_inventory(timeout: float, freeze_date: str) -> dict[str, Any]:
    api_url = f"https://huggingface.co/api/models/{MODEL_ID}/revision/{REVISION}?blobs=true"
    metadata = fetch_json(api_url, timeout)
    if metadata.get("sha") != REVISION:
        raise RuntimeError(f"revision mismatch: expected {REVISION}, got {metadata.get('sha')}")
    siblings = {str(item["rfilename"]): item for item in metadata.get("siblings", [])}
    if tuple(sorted(siblings)) != tuple(sorted(EXPECTED_FILES)):
        missing = sorted(set(EXPECTED_FILES) - set(siblings))
        extra = sorted(set(siblings) - set(EXPECTED_FILES))
        raise RuntimeError(f"remote file universe drifted; missing={missing}, extra={extra}")

    downloaded: dict[str, bytes] = {}
    artifacts: list[dict[str, Any]] = []
    for name in EXPECTED_FILES:
        item = siblings[name]
        lfs = item.get("lfs") or {}
        if lfs.get("sha256") and lfs.get("size") is not None:
            size = int(lfs["size"])
            digest = str(lfs["sha256"])
            digest_source = "huggingface_lfs_sha256"
        else:
            encoded_name = quote(name, safe="/")
            url = f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{encoded_name}"
            content = fetch_bytes(url, timeout)
            downloaded[name] = content
            size = len(content)
            digest = sha256_bytes(content)
            digest_source = "sha256_of_immutable_resolve_bytes"
        if item.get("size") is not None and int(item["size"]) != size:
            raise RuntimeError(f"remote size mismatch for {name}")
        artifacts.append(
            {
                "path": name,
                "kind": artifact_kind(name),
                "size_bytes": size,
                "sha256": digest,
                "sha256_source": digest_source,
                "git_blob_id": item.get("blobId"),
            }
        )

    config = json.loads(downloaded["config.json"])
    tokenizer_config = json.loads(downloaded["tokenizer_config.json"])
    expected_config = {
        "architectures": ["Qwen3ForCausalLM"],
        "model_type": "qwen3",
        "hidden_size": 2048,
        "num_hidden_layers": 28,
        "num_attention_heads": 16,
        "num_key_value_heads": 8,
    }
    for key, expected in expected_config.items():
        if config.get(key) != expected:
            raise RuntimeError(f"unexpected config {key}: {config.get(key)!r}")
    chat_template = tokenizer_config.get("chat_template")
    if not isinstance(chat_template, str) or not chat_template:
        raise RuntimeError("official tokenizer has no chat template")
    license_name = metadata.get("cardData", {}).get("license")
    if license_name != "apache-2.0":
        raise RuntimeError(f"unexpected license: {license_name}")

    aggregate_input = {
        "repository": MODEL_ID,
        "revision": REVISION,
        "artifacts": artifacts,
    }
    return {
        "schema_version": "frame_internalization_model_remote_inventory.v1",
        "inventory_id": "qwen3_1p7b_70d244c_v1",
        "freeze_date": freeze_date,
        "status": "remote_frozen_local_verification_pending",
        "passed": False,
        "immutable_revisions": True,
        "repository": MODEL_ID,
        "revision": REVISION,
        "license": license_name,
        "official_api_url": api_url,
        "builder": {
            "path": Path(__file__).resolve().relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_bytes(Path(__file__).resolve().read_bytes()),
        },
        "artifact_count": len(artifacts),
        "weight_shard_count": sum(item["kind"] == "weight" for item in artifacts),
        "weight_bytes": sum(item["size_bytes"] for item in artifacts if item["kind"] == "weight"),
        "total_artifact_bytes": sum(item["size_bytes"] for item in artifacts),
        "artifact_inventory_sha256": canonical_sha256(aggregate_input),
        "artifacts": artifacts,
        "architecture": {
            **expected_config,
            "intermediate_size": config.get("intermediate_size"),
            "max_position_embeddings": config.get("max_position_embeddings"),
            "tie_word_embeddings": config.get("tie_word_embeddings"),
            "torch_dtype": config.get("torch_dtype"),
        },
        "chat_template": {
            "source": "official tokenizer_config.json at the immutable revision",
            "sha256": sha256_bytes(chat_template.encode("utf-8")),
            "supports_enable_thinking": "enable_thinking" in chat_template,
            "historical_intellect_template_equivalence_claimed": False,
        },
        "historical_boundary": {
            "is_intellect_3": False,
            "reproduces_historical_intellect_3_result": False,
            "classification": "prospective_small_model_substitution",
        },
        "completion_requirements": [
            "verify every artifact byte against a local cache",
            "render the exact official chat template in thinking and non-thinking modes",
            "complete an offline NF4 load and deterministic generation smoke",
            "bind the runtime and package versions in a passed base-freeze receipt",
        ],
    }


def main() -> int:
    args = parse_args()
    inventory = build_inventory(args.timeout_seconds, args.freeze_date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "revision": inventory["revision"],
                "artifacts": inventory["artifact_count"],
                "bytes": inventory["total_artifact_bytes"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
