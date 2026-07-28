"""Pinned official-HRM runtime for direct constitutional checkpoint evaluation."""

from __future__ import annotations

import gc
import importlib
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F

OFFICIAL_COMMIT = "ac15626f8db096a63c775b84c9dc868776a6feda"


def install_torch_attention_fallback() -> bool:
    """Install an in-process FlashAttention-compatible SDPA fallback if needed."""
    try:
        importlib.import_module("flash_attn_interface")
        return False
    except ImportError:
        pass
    try:
        importlib.import_module("flash_attn")
        return False
    except ImportError:
        pass

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
    return True


class ConstitutionalHrmRuntime:
    """Load one exported ACT-HRM model and emit non-autoregressive token IDs."""

    def __init__(
        self,
        *,
        checkpoint_path: Path,
        official_root: Path,
        device: str = "cuda",
        gpu_memory_fraction: float = 0.80,
    ) -> None:
        self.checkpoint_path = checkpoint_path.resolve()
        self.official_root = official_root.resolve()
        self.device = torch.device(device)
        self.gpu_memory_fraction = gpu_memory_fraction
        self.model: torch.nn.Module | None = None
        self.config: dict[str, Any] | None = None
        self.parameter_count = 0
        self.attention_fallback = False

    def load(self) -> dict[str, Any]:
        if self.model is not None:
            raise RuntimeError("runtime is already loaded")
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(self.checkpoint_path)
        official_commit = subprocess.run(
            ["git", "-C", str(self.official_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout.strip()
        if official_commit != OFFICIAL_COMMIT:
            raise ValueError(
                f"official HRM commit drift: {official_commit} != {OFFICIAL_COMMIT}"
            )
        if self.device.type == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA was requested but is unavailable")
            if not 0.10 <= self.gpu_memory_fraction <= 0.95:
                raise ValueError("gpu_memory_fraction must be in [0.10, 0.95]")
            torch.cuda.set_per_process_memory_fraction(
                self.gpu_memory_fraction, self.device.index or 0
            )
        self.attention_fallback = install_torch_attention_fallback()
        if str(self.official_root) not in sys.path:
            sys.path.insert(0, str(self.official_root))
        model_module = importlib.import_module("models.hrm.hrm_act_v1")
        losses_module = importlib.import_module("models.losses")
        payload = torch.load(
            self.checkpoint_path,
            map_location="cpu",
            weights_only=True,
            mmap=True,
        )
        if payload.get("schema_version") != "constitutional_hrm_model_export_v2":
            raise ValueError("checkpoint is not a constitutional HRM model export")
        config = dict(payload["model_config"])
        with torch.device(self.device):
            wrapped = losses_module.ACTLossHead(
                model_module.HierarchicalReasoningModel_ACTV1(config),
                loss_type="softmax_cross_entropy",
            )
        missing, unexpected = wrapped.load_state_dict(payload["model"], strict=False)
        if missing or unexpected:
            raise ValueError(
                f"checkpoint state mismatch: missing={missing}, unexpected={unexpected}"
            )
        self.model = wrapped.model
        self.model.eval()
        self.config = config
        self.parameter_count = sum(
            parameter.numel() for parameter in self.model.parameters()
        )
        del wrapped, payload
        gc.collect()
        return {
            "parameter_count": self.parameter_count,
            "config": config,
            "device": str(self.device),
            "attention_fallback": self.attention_fallback,
            "official_commit": official_commit,
        }

    @torch.inference_mode()
    def predict(self, inputs: np.ndarray, *, batch_size: int = 1) -> np.ndarray:
        if self.model is None or self.config is None:
            raise RuntimeError("runtime is not loaded")
        if inputs.ndim != 2 or inputs.shape[1] != int(self.config["seq_len"]):
            raise ValueError(f"unexpected input shape {inputs.shape}")
        predictions: list[np.ndarray] = []
        for start in range(0, len(inputs), batch_size):
            values = torch.from_numpy(
                np.asarray(inputs[start : start + batch_size], dtype=np.int32)
            ).to(self.device)
            batch = {
                "inputs": values,
                "labels": torch.full_like(values, -100),
                "puzzle_identifiers": torch.zeros(
                    (len(values),), dtype=torch.int32, device=self.device
                ),
            }
            with torch.device(self.device):
                carry = self.model.initial_carry(batch)  # type: ignore[attr-defined]
            carry, outputs = self.model(carry, batch)
            predictions.append(
                outputs["logits"].argmax(dim=-1).to("cpu").numpy().astype(np.int32)
            )
            del values, batch, carry, outputs
        if not predictions:
            return np.empty((0, int(self.config["seq_len"])), dtype=np.int32)
        return np.concatenate(predictions, axis=0)

    def cleanup(self) -> dict[str, Any]:
        self.model = None
        self.config = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
        return {
            "cuda_memory_allocated_after": (
                int(torch.cuda.memory_allocated()) if torch.cuda.is_available() else 0
            ),
            "cuda_memory_reserved_after": (
                int(torch.cuda.memory_reserved()) if torch.cuda.is_available() else 0
            ),
        }
