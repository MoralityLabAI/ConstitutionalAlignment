"""Model-family detection, runtime patching, and repository-local path defaults."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_pipeline_root() -> Path:
    return repo_root() / "artifacts" / "constitution_pipeline"


def default_cache_dir() -> Path:
    return repo_root() / ".cache" / "huggingface"


def default_prompt_runs_root() -> Path:
    return default_pipeline_root() / "prompt_runs"


def compute_default_rope_parameters(config: Any, device=None, seq_len=None, **kwargs):
    import torch

    rope_theta = getattr(config, "rope_theta", 10000.0)
    head_dim = getattr(config, "head_dim", None)
    if head_dim is None:
        hidden_size = int(getattr(config, "hidden_size"))
        num_heads = int(getattr(config, "num_attention_heads"))
        head_dim = hidden_size // num_heads
    partial_rotary_factor = 1.0
    rope_scaling = getattr(config, "rope_scaling", None)
    if isinstance(rope_scaling, dict):
        partial_rotary_factor = rope_scaling.get("partial_rotary_factor", 1.0)
    dim = int(head_dim * partial_rotary_factor)
    inv_freq = 1.0 / (
        rope_theta ** (torch.arange(0, dim, 2, dtype=torch.int64).float().to(device=device) / dim)
    )
    return inv_freq, 1.0


def inspect_model_family(
    model_id: str | None = None,
    revision: str = "main",
    cache_dir: str | None = None,
) -> dict[str, Any]:
    lower_model_id = str(model_id or "").lower()
    fallback_family = "afmoe" if ("afmoe" in lower_model_id or "trinity" in lower_model_id) else "generic"
    identity: dict[str, Any] = {
        "family": fallback_family,
        "model_type": "",
        "architectures": [],
        "afmoe_required": fallback_family == "afmoe",
        "inspection_error": "",
    }
    if not model_id:
        return identity

    try:
        from transformers import AutoConfig

        config = AutoConfig.from_pretrained(
            model_id,
            revision=revision,
            trust_remote_code=True,
            cache_dir=cache_dir,
        )
        model_type = str(getattr(config, "model_type", "") or "")
        architectures = list(getattr(config, "architectures", []) or [])
        lower_architectures = [architecture.lower() for architecture in architectures]
        afmoe_required = model_type.lower() == "afmoe" or any(
            "afmoe" in architecture for architecture in lower_architectures
        )
        return {
            "family": "afmoe" if afmoe_required else "generic",
            "model_type": model_type,
            "architectures": architectures,
            "afmoe_required": afmoe_required,
            "inspection_error": "",
        }
    except Exception as exc:
        identity["inspection_error"] = f"{type(exc).__name__}: {exc}"
        return identity


def patch_transformers_for_model_family(
    model_id: str | None = None,
    revision: str = "main",
    cache_dir: str | None = None,
) -> dict[str, Any]:
    identity = inspect_model_family(model_id, revision=revision, cache_dir=cache_dir)
    if not identity.get("afmoe_required"):
        return {
            "family": identity["family"],
            "model_type": identity.get("model_type", ""),
            "architectures": identity.get("architectures", []),
            "patched_module_names": [],
            "afmoe_required": False,
            "inspection_error": identity.get("inspection_error", ""),
        }

    from transformers import modeling_rope_utils
    from transformers.dynamic_module_utils import get_class_from_dynamic_module

    patched_module_names: list[str] = []
    if "default" not in modeling_rope_utils.ROPE_INIT_FUNCTIONS:
        modeling_rope_utils.ROPE_INIT_FUNCTIONS["default"] = compute_default_rope_parameters

    if model_id:
        from transformers import AutoConfig

        config = AutoConfig.from_pretrained(
            model_id,
            revision=revision,
            trust_remote_code=True,
            cache_dir=cache_dir,
        )
        class_ref = (getattr(config, "auto_map", {}) or {}).get("AutoModelForCausalLM")
        if class_ref:
            get_class_from_dynamic_module(
                class_ref,
                model_id,
                revision=revision,
                cache_dir=cache_dir,
            )

    for module_name, module in list(sys.modules.items()):
        if not module_name.endswith("modeling_afmoe"):
            continue
        rotary_cls = getattr(module, "AfmoeRotaryEmbedding", None)
        if rotary_cls is None or hasattr(rotary_cls, "compute_default_rope_parameters"):
            continue
        rotary_cls.compute_default_rope_parameters = staticmethod(compute_default_rope_parameters)
        patched_module_names.append(module_name)

    return {
        "family": identity["family"],
        "model_type": identity.get("model_type", ""),
        "architectures": identity.get("architectures", []),
        "patched_module_names": patched_module_names,
        "afmoe_required": True,
        "inspection_error": identity.get("inspection_error", ""),
    }
