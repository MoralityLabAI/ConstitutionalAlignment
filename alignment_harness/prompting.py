"""Shared chat-template controls for direct, publicly auditable answers."""

from __future__ import annotations

from typing import Any, Sequence


DIRECT_CHAT_TEMPLATE_KWARGS = {"enable_thinking": False}


def render_direct_chat_prompt(tokenizer: Any, messages: Sequence[dict[str, str]]) -> str:
    """Render a prompt with model-specific hidden-reasoning modes disabled."""
    return tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        **DIRECT_CHAT_TEMPLATE_KWARGS,
    )
