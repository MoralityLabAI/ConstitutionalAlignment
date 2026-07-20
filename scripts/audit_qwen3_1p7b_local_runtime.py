#!/usr/bin/env python3
"""Verify the pinned Qwen3-1.7B cache and complete an offline NF4 runtime smoke."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INVENTORY = (
    REPO_ROOT
    / "experiments/frame_internalization_sft_v1/rerun_freeze/qwen3_1p7b_v1/"
    "model_tokenizer_remote_inventory_v1.json"
)
EXPECTED_REPOSITORY = "Qwen/Qwen3-1.7B"
EXPECTED_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--venue", choices=("local", "primelab"), default="local")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verification-date", default="2026-07-20")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def git_head(repo_root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()


def git_tracked_clean(repo_root: Path) -> bool:
    return not subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo_root, text=True
    ).strip()


def verify_artifacts(inventory: dict[str, Any], model_dir: Path) -> list[dict[str, Any]]:
    checks = []
    for artifact in inventory.get("artifacts", []):
        path = model_dir / str(artifact["path"])
        exists = path.is_file()
        size = path.stat().st_size if exists else None
        digest = sha256_file(path) if exists and size == artifact["size_bytes"] else None
        checks.append(
            {
                "path": artifact["path"],
                "expected_size_bytes": artifact["size_bytes"],
                "observed_size_bytes": size,
                "expected_sha256": artifact["sha256"],
                "observed_sha256": digest,
                "passed": bool(
                    exists and size == artifact["size_bytes"] and digest == artifact["sha256"]
                ),
            }
        )
    if len(checks) != inventory.get("artifact_count"):
        raise ValueError("artifact check count drifted")
    return checks


def package_versions() -> dict[str, str]:
    packages = [
        "torch",
        "transformers",
        "bitsandbytes",
        "accelerate",
        "peft",
        "trl",
        "safetensors",
        "huggingface-hub",
    ]
    return {name: importlib.metadata.version(name) for name in packages}


def checkpoint_tensor_elements(model_dir: Path) -> int:
    from safetensors import safe_open

    total = 0
    for path in sorted(model_dir.glob("*.safetensors")):
        with safe_open(path, framework="pt", device="cpu") as handle:
            for key in handle.keys():
                count = 1
                for dimension in handle.get_slice(key).get_shape():
                    count *= dimension
                total += count
    return total


def gpu_identity() -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the NF4 runtime smoke")
    properties = torch.cuda.get_device_properties(0)
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        "name": properties.name,
        "total_memory_bytes": properties.total_memory,
        "compute_capability": f"{properties.major}.{properties.minor}",
        "nvidia_smi": result.stdout.strip(),
        "torch_cuda_version": torch.version.cuda,
    }


def runtime_smoke(model_dir: Path, inventory: dict[str, Any]) -> dict[str, Any]:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    started = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    if sha256_text(tokenizer.chat_template) != inventory["chat_template"]["sha256"]:
        raise RuntimeError("loaded tokenizer chat template hash drifted")
    template_messages = [
        {"role": "system", "content": "Use only stated facts."},
        {"role": "user", "content": "Return exactly OK."},
    ]
    rendered_thinking = tokenizer.apply_chat_template(
        template_messages, tokenize=False, add_generation_prompt=True, enable_thinking=True
    )
    rendered_nonthinking = tokenizer.apply_chat_template(
        template_messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_dir,
        local_files_only=True,
        quantization_config=quantization,
        device_map={"": 0},
        dtype=torch.float16,
        low_cpu_mem_usage=True,
    )
    loaded = time.monotonic()

    def generate(messages: list[dict[str, str]], thinking: bool, max_new_tokens: int) -> str:
        inputs = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=thinking,
            return_tensors="pt",
            return_dict=True,
        )
        inputs = {key: value.to("cuda") for key, value in inputs.items()}
        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        start = inputs["input_ids"].shape[-1]
        return tokenizer.decode(output[0, start:], skip_special_tokens=False)

    nonthinking_output = generate(
        [
            {"role": "system", "content": "Follow the requested output format exactly."},
            {"role": "user", "content": "Reply with exactly the word OK and nothing else."},
        ],
        thinking=False,
        max_new_tokens=16,
    )
    thinking_output = generate(
        [
            {"role": "system", "content": "Answer accurately."},
            {"role": "user", "content": "What is 2 + 2?"},
        ],
        thinking=True,
        max_new_tokens=128,
    )
    visible_after_think = thinking_output.split("</think>", 1)[-1].strip()
    linear4 = next((item for item in model.modules() if type(item).__name__ == "Linear4bit"), None)
    checks = {
        "official_template_thinking_rendered": rendered_thinking.endswith("<think>\n"),
        "official_template_nonthinking_rendered": "<think>\n\n</think>" in rendered_nonthinking,
        "nf4_linear_present": linear4 is not None,
        "nonthinking_exact_ok": nonthinking_output.strip() == "OK<|im_end|>",
        "thinking_block_closed": thinking_output.startswith("<think>\n")
        and "</think>" in thinking_output,
        "thinking_visible_answer_contains_four": "4" in visible_after_think,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "quantization": {
            "load_in_4bit": True,
            "quant_type": "nf4",
            "double_quant": True,
            "compute_dtype": "float16",
            "device_map": {"": 0},
        },
        "model": {
            "architectures": model.config.architectures,
            "model_type": model.config.model_type,
            "num_hidden_layers": model.config.num_hidden_layers,
            "hidden_size": model.config.hidden_size,
            "quantized_parameter_numel": sum(parameter.numel() for parameter in model.parameters()),
            "checkpoint_tensor_elements": checkpoint_tensor_elements(model_dir),
        },
        "tokenizer": {
            "class": type(tokenizer).__name__,
            "vocab_size": tokenizer.vocab_size,
            "eos_token_id": tokenizer.eos_token_id,
            "pad_token_id": tokenizer.pad_token_id,
            "chat_template_sha256": sha256_text(tokenizer.chat_template),
            "thinking_render_sha256": sha256_text(rendered_thinking),
            "nonthinking_render_sha256": sha256_text(rendered_nonthinking),
        },
        "generation": {
            "nonthinking_output": nonthinking_output,
            "thinking_output_sha256": sha256_text(thinking_output),
            "thinking_output_characters": len(thinking_output),
            "thinking_visible_answer": visible_after_think,
            "do_sample": False,
        },
        "load_seconds": round(loaded - started, 3),
        "total_seconds": round(time.monotonic() - started, 3),
        "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "gpu_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
    }


def main() -> int:
    args = parse_args()
    head = git_head(REPO_ROOT)
    if head != args.source_commit:
        raise RuntimeError(f"source commit mismatch: expected {args.source_commit}, found {head}")
    if not git_tracked_clean(REPO_ROOT):
        raise RuntimeError("tracked worktree must be clean before runtime audit")
    inventory_path = args.inventory.resolve()
    inventory = read_json(inventory_path)
    if inventory.get("schema_version") != "frame_internalization_model_remote_inventory.v1":
        raise ValueError("unexpected inventory schema")
    if inventory.get("repository") != EXPECTED_REPOSITORY or inventory.get("revision") != EXPECTED_REVISION:
        raise ValueError("inventory model identity drifted")
    model_dir = args.model_dir.resolve()
    checks = verify_artifacts(inventory, model_dir)
    artifacts_passed = all(check["passed"] for check in checks)
    if not artifacts_passed:
        raise RuntimeError("one or more local model artifacts failed verification")
    smoke = runtime_smoke(model_dir, inventory)
    gpu = gpu_identity()
    minimum_primelab_bytes = 24 * 1024**3
    venue_passed = args.venue == "local" or gpu["total_memory_bytes"] >= minimum_primelab_bytes
    passed = bool(artifacts_passed and smoke["passed"] and venue_passed)
    receipt = {
        "schema_version": "frame_internalization_base_freeze.v1",
        "freeze_id": "qwen3_1p7b_local_nf4_v1",
        "verification_date": args.verification_date,
        "passed": passed,
        "immutable_revisions": True,
        "classification": "prospective_small_model_substitution_infrastructure",
        "source_commit": head,
        "repository": inventory["repository"],
        "revision": inventory["revision"],
        "license": inventory["license"],
        "remote_inventory_path": inventory_path.relative_to(REPO_ROOT).as_posix(),
        "remote_inventory_sha256": sha256_file(inventory_path),
        "artifact_inventory_sha256": inventory["artifact_inventory_sha256"],
        "model_dir": str(model_dir),
        "artifact_checks": checks,
        "engine": {
            "description": f"offline Transformers NF4 inference on the {args.venue} lane",
            "venue": args.venue,
            "script_path": Path(__file__).resolve().relative_to(REPO_ROOT).as_posix(),
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": package_versions(),
            "gpu": gpu,
            "venue_requirement": {
                "minimum_vram_bytes": minimum_primelab_bytes if args.venue == "primelab" else None,
                "passed": venue_passed,
            },
            "runtime_smoke": smoke,
            "passed": smoke["passed"],
        },
        "scope_boundary": {
            "scored_behavioral_outputs_generated": False,
            "local_smoke_authorizes_primelab_training": False,
            "primelab_model_runtime_frozen": args.venue == "primelab" and venue_passed,
            "primelab_full_4096_training_smoke_still_required": True,
            "historical_intellect_3_reproduction_claimed": False,
        },
        "failures": [check["path"] for check in checks if not check["passed"]]
        + ([] if smoke["passed"] else ["runtime_smoke"])
        + ([] if venue_passed else ["venue_vram_requirement"]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"output": str(args.output), "passed": passed, "failures": receipt["failures"]}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
