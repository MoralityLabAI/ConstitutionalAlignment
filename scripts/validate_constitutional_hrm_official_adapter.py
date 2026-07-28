#!/usr/bin/env python3
"""Validate the v2 text/proof adapter against the pinned official HRM code."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib
import json
import os
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from tokenizers import Tokenizer

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alignment_harness.constitutional_hrm_v2 import (  # noqa: E402
    IGNORE_LABEL_ID,
    PROOF_SLOT_COUNT,
    encode_example,
    ensure_disjoint_group_ids,
    fixed_adapter_scenarios,
    write_official_dataset,
)

OFFICIAL_COMMIT = "ac15626f8db096a63c775b84c9dc868776a6feda"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def install_cpu_flash_attention_fallback() -> None:
    if "flash_attn" in sys.modules:
        return

    def flash_attn_func(
        q: torch.Tensor,
        k: torch.Tensor,
        v: torch.Tensor,
        causal: bool = False,
        **_: Any,
    ) -> torch.Tensor:
        query = q.transpose(1, 2)
        key = k.transpose(1, 2)
        value = v.transpose(1, 2)
        output = F.scaled_dot_product_attention(
            query,
            key,
            value,
            is_causal=causal,
        )
        return output.transpose(1, 2).contiguous()

    module = types.ModuleType("flash_attn")
    module.flash_attn_func = flash_attn_func  # type: ignore[attr-defined]
    sys.modules["flash_attn"] = module


def official_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()


def load_prompt(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload["prompts"]["constitution_metta_full"]["text"])


def official_smoke(
    *,
    official_root: Path,
    inputs: np.ndarray,
    labels: np.ndarray,
    vocab_size: int,
    seq_len: int,
) -> dict[str, Any]:
    install_cpu_flash_attention_fallback()
    sys.path.insert(0, str(official_root))
    try:
        module = importlib.import_module("models.hrm.hrm_act_v1")
        losses = importlib.import_module("models.losses")
        model_class = module.HierarchicalReasoningModel_ACTV1
        loss_class = losses.ACTLossHead
        config = {
            "batch_size": 1,
            "vocab_size": vocab_size,
            "seq_len": seq_len,
            "num_puzzle_identifiers": 1,
            "causal": False,
            "H_cycles": 1,
            "L_cycles": 1,
            "H_layers": 1,
            "L_layers": 1,
            "hidden_size": 32,
            "expansion": 2.0,
            "num_heads": 4,
            "pos_encodings": "rope",
            "puzzle_emb_ndim": 0,
            "halt_max_steps": 1,
            "halt_exploration_prob": 0.0,
            "forward_dtype": "float32",
        }
        model = loss_class(model_class(config), loss_type="softmax_cross_entropy")
        model.train()
        batch = {
            "inputs": torch.from_numpy(inputs[:1]).long(),
            "labels": torch.from_numpy(labels[:1]).long(),
            "puzzle_identifiers": torch.zeros((1,), dtype=torch.int32),
        }
        carry = model.initial_carry(batch)
        carry, loss, metrics, outputs, all_finish = model(
            carry=carry,
            batch=batch,
            return_keys=["logits"],
        )
        loss.backward()
        gradients = [
            parameter.grad
            for parameter in model.parameters()
            if parameter.grad is not None
        ]
        result = {
            "loss": float(loss.detach()),
            "loss_finite": bool(torch.isfinite(loss.detach())),
            "gradient_tensors": len(gradients),
            "gradients_finite": bool(
                gradients and all(torch.isfinite(gradient).all() for gradient in gradients)
            ),
            "logits_shape": list(outputs["logits"].shape),
            "all_finish": bool(all_finish),
            "metrics": {
                key: float(value.detach()) for key, value in metrics.items()
            },
            "smoke_parameters": sum(parameter.numel() for parameter in model.parameters()),
            "config": config,
        }
        del carry, outputs, gradients, batch, loss, model
        gc.collect()
        return result
    finally:
        if sys.path and sys.path[0] == str(official_root):
            sys.path.pop(0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--official-root",
        type=Path,
        default=REPO_ROOT.parent / ".codex-cache" / "HRM-ac15626",
    )
    parser.add_argument(
        "--model-config",
        type=Path,
        default=REPO_ROOT / "experiments" / "constitutional_hrm_200m_v2" / "model_config.json",
    )
    parser.add_argument(
        "--tokenizer",
        type=Path,
        default=REPO_ROOT / "artifacts" / "constitutional_hrm_200m_v2" / "tokenizer" / "tokenizer.json",
    )
    parser.add_argument(
        "--prompt-bundle",
        type=Path,
        default=REPO_ROOT
        / "artifacts"
        / "constitutional_hrm_200m_v2"
        / "generated"
        / "system_prompt_bundle_v2.json",
    )
    parser.add_argument("--constitution", type=Path, default=REPO_ROOT / "constitution.md")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "constitutional_hrm_200m_v2" / "official_adapter",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    official_root = args.official_root.resolve()
    commit = official_commit(official_root)
    if commit != OFFICIAL_COMMIT:
        raise ValueError(f"official HRM commit drift: {commit}")
    model_config = json.loads(args.model_config.read_text(encoding="utf-8"))
    architecture = model_config["architecture"]
    tokenizer = Tokenizer.from_file(str(args.tokenizer.resolve()))
    prompt = load_prompt(args.prompt_bundle.resolve())
    scenarios = fixed_adapter_scenarios()
    examples = [
        encode_example(
            tokenizer=tokenizer,
            prompt=prompt,
            scenario=scenario,
            constitution_path=args.constitution.resolve(),
            seq_len=int(architecture["seq_len"]),
            prompt_token_budget=int(model_config["input_contract"]["prompt_tokens_max"]),
            scenario_token_budget=int(model_config["input_contract"]["scenario_tokens_max"]),
        )
        for scenario in scenarios
    ]
    train_examples = examples[:4]
    eval_examples = examples[4:]
    ensure_disjoint_group_ids((train_examples, eval_examples))
    output_dir = args.output_dir.resolve()
    dataset = write_official_dataset(
        output_dir=output_dir / "dataset",
        train_examples=train_examples,
        eval_sets={"development": eval_examples},
        pad_id=int(tokenizer.token_to_id("<|pad|>")),
        vocab_size=tokenizer.get_vocab_size(with_added_tokens=True),
        seq_len=int(architecture["seq_len"]),
    )

    if str(official_root) not in sys.path:
        sys.path.insert(0, str(official_root))
    dataset_common = importlib.import_module("dataset.common")
    metadata = dataset_common.PuzzleDatasetMetadata(
        **json.loads(
            (output_dir / "dataset" / "train" / "dataset.json").read_text(encoding="utf-8")
        )
    )
    inputs = np.load(output_dir / "dataset" / "train" / "all__inputs.npy")
    labels = np.load(output_dir / "dataset" / "train" / "all__labels.npy")
    supervised_counts = (labels != IGNORE_LABEL_ID).sum(axis=1)
    supervised_labels = labels[labels != IGNORE_LABEL_ID]
    smoke = official_smoke(
        official_root=official_root,
        inputs=inputs,
        labels=labels,
        vocab_size=int(architecture["vocab_size"]),
        seq_len=int(architecture["seq_len"]),
    )
    checks = {
        "official_commit_pinned": commit == OFFICIAL_COMMIT,
        "tokenizer_vocab_matches": tokenizer.get_vocab_size(with_added_tokens=True)
        == int(architecture["vocab_size"]),
        "official_metadata_loads": metadata.seq_len == int(architecture["seq_len"]),
        "all_22_slots_supervised": bool(np.all(supervised_counts == PROOF_SLOT_COUNT)),
        "input_ids_in_vocab": int(inputs.max()) < int(architecture["vocab_size"]),
        "label_ids_in_vocab": bool(
            supervised_labels.size
            and int(supervised_labels.min()) >= 0
            and int(supervised_labels.max()) < int(architecture["vocab_size"])
        ),
        "official_ignore_label_contract": metadata.ignore_label_id == IGNORE_LABEL_ID
        and bool(np.all(labels[:, PROOF_SLOT_COUNT:] == IGNORE_LABEL_ID)),
        "prompt_budget_passes": max(example["prompt_tokens"] for example in examples)
        <= int(model_config["input_contract"]["prompt_tokens_max"]),
        "scenario_budget_passes": max(example["scenario_tokens"] for example in examples)
        <= int(model_config["input_contract"]["scenario_tokens_max"]),
        "official_forward_backward_finite": smoke["loss_finite"]
        and smoke["gradients_finite"],
        "official_logits_contract": smoke["logits_shape"]
        == [1, int(architecture["seq_len"]), int(architecture["vocab_size"])],
    }
    source_files = [
        official_root / "models" / "hrm" / "hrm_act_v1.py",
        official_root / "models" / "layers.py",
        official_root / "models" / "losses.py",
        official_root / "puzzle_dataset.py",
    ]
    receipt = {
        "schema_version": "constitutional_hrm_official_adapter_receipt_v1",
        "gate_id": "F07_OFFICIAL_CODE_ADAPTER",
        "status": "passed" if all(checks.values()) else "failed",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "official_hrm": {
            "root": str(official_root),
            "commit": commit,
            "source_sha256": {
                str(path.relative_to(official_root)).replace("\\", "/"): sha256_file(path)
                for path in source_files
            },
            "cpu_attention_fallback_scope": "local_contract_smoke_only",
        },
        "tokenizer": {
            "path": str(args.tokenizer.resolve()),
            "sha256": sha256_file(args.tokenizer.resolve()),
            "vocab_size": tokenizer.get_vocab_size(with_added_tokens=True),
        },
        "adapter": {
            "dataset": dataset,
            "train_examples": len(train_examples),
            "development_examples": len(eval_examples),
            "proof_slots": PROOF_SLOT_COUNT,
            "max_prompt_tokens": max(example["prompt_tokens"] for example in examples),
            "max_scenario_tokens": max(example["scenario_tokens"] for example in examples),
        },
        "official_smoke": smoke,
    }
    atomic_json(output_dir / "adapter_receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
        if hasattr(torch.cuda, "ipc_collect"):
            torch.cuda.ipc_collect()
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
