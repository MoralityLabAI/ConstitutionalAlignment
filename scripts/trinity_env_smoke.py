#!/usr/bin/env python3
"""Compatibility wrapper for the legacy Trinity-named environment smoke test."""

from model_env_smoke import main


if __name__ == "__main__":
    raise SystemExit(main())
