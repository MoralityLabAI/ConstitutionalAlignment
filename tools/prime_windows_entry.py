"""Run non-tunnel Prime CLI commands despite the unconditional fcntl import."""

from __future__ import annotations

import sys
import types


def _flock(*args: object) -> None:
    return None


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "tunnel":
        raise RuntimeError("Prime tunnel commands require a POSIX runtime")

    fcntl = types.ModuleType("fcntl")
    fcntl.LOCK_EX = 2
    fcntl.LOCK_UN = 8
    fcntl.LOCK_NB = 4
    fcntl.flock = _flock
    sys.modules["fcntl"] = fcntl

    sys.argv = ["prime", *sys.argv[1:]]
    from prime_cli.main import run

    run()


if __name__ == "__main__":
    main()
