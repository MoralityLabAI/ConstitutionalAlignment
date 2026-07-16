#!/usr/bin/env python3
"""Smoke-test a model environment before real adapter runs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from model_family import default_cache_dir, inspect_model_family, patch_transformers_for_model_family


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True, help="Local model path or HF repo id.")
    parser.add_argument("--cache-dir", default=str(default_cache_dir()))
    args = parser.parse_args()

    if args.cache_dir:
        cache = str(Path(args.cache_dir).resolve())
        os.environ.setdefault("HF_HOME", cache)
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", cache)
        os.environ.setdefault("TRANSFORMERS_CACHE", cache)
        os.environ.setdefault("TRITON_CACHE_DIR", str(Path(cache) / "triton"))

    import torch
    from transformers import AutoConfig, AutoTokenizer

    patch_info = patch_transformers_for_model_family(args.model_id, cache_dir=args.cache_dir or None)
    identity = inspect_model_family(args.model_id, cache_dir=args.cache_dir or None)

    cfg = AutoConfig.from_pretrained(
        args.model_id,
        trust_remote_code=True,
        cache_dir=args.cache_dir or None,
    )
    tok = AutoTokenizer.from_pretrained(
        args.model_id,
        trust_remote_code=True,
        cache_dir=args.cache_dir or None,
        use_fast=True,
    )

    result = {
        "model_id": args.model_id,
        "model_family": identity["family"],
        "afmoe_required": bool(identity["afmoe_required"]),
        "patch_info": patch_info,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device_count": int(torch.cuda.device_count()),
        "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "",
        "torch_version": torch.__version__,
        "transformers_version": __import__("transformers").__version__,
        "config_class": type(cfg).__name__,
        "model_type": str(getattr(cfg, "model_type", "") or ""),
        "architectures": list(getattr(cfg, "architectures", []) or []),
        "pad_token_id": getattr(cfg, "pad_token_id", None),
        "eos_token_id": getattr(cfg, "eos_token_id", None),
        "tokenizer_class": type(tok).__name__,
        "tokenizer_pad_token_id": getattr(tok, "pad_token_id", None),
    }

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
