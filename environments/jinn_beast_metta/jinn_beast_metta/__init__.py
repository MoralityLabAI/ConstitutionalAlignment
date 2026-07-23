"""Jinn/Beast MeTTa storyworld taskset."""

from typing import Any

__all__ = ["JinnBeastMettaTaskset", "load_environment"]


def __getattr__(name: str) -> Any:
    if name == "JinnBeastMettaTaskset":
        from .taskset import JinnBeastMettaTaskset

        return JinnBeastMettaTaskset
    if name == "load_environment":
        from .legacy import load_environment

        return load_environment
    raise AttributeError(name)
