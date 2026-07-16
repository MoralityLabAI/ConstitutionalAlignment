#!/usr/bin/env python3
"""Compatibility wrapper for the legacy Trinity-named adapter trainer."""

from __future__ import annotations

import sys

from train_constitution_adapter import main


def main_with_legacy_defaults() -> int:
    if "--model-id" not in sys.argv[1:]:
        sys.argv.extend(["--model-id", "arcee-ai/Trinity-Mini"])
    return main()


if __name__ == "__main__":
    raise SystemExit(main_with_legacy_defaults())
