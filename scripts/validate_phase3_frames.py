#!/usr/bin/env python3
"""Verify Phase 3 framing-arm token counts and the preregistered length gate."""

from __future__ import annotations

import re
import sys
from pathlib import Path


NOTES = Path("constitutional-harness/RESEARCH_NOTES.md")
ARM_NAMES = {
    "no_frame",
    "generic_constitution",
    "secular_omniscient",
    "eschatological",
}
MAX_SPREAD = 0.10


def main() -> int:
    try:
        import tiktoken  # type: ignore
    except ImportError:
        print("Missing dependency: tiktoken. Install with: pip install tiktoken")
        return 2

    text = NOTES.read_text(encoding="utf-8")
    arm_pattern = re.compile(
        r"<!-- phase3-arm:(?P<name>[a-z_]+):start -->\s*"
        r"(?P<text>.*?)\s*"
        r"<!-- phase3-arm:(?P=name):end -->",
        re.DOTALL,
    )
    arms = {match.group("name"): match.group("text") for match in arm_pattern.finditer(text)}

    count_pattern = re.compile(r"\| `(?P<name>[a-z_]+)` \| (?P<count>\d+) \|")
    recorded = {
        match.group("name"): int(match.group("count"))
        for match in count_pattern.finditer(text)
        if match.group("name") in ARM_NAMES
    }

    if set(arms) != ARM_NAMES or set(recorded) != ARM_NAMES:
        print(f"Expected arms {sorted(ARM_NAMES)}; found text={sorted(arms)}, counts={sorted(recorded)}")
        return 1

    encoding = tiktoken.get_encoding("cl100k_base")
    actual = {name: len(encoding.encode(arm_text)) for name, arm_text in arms.items()}
    if actual != recorded:
        print(f"Recorded counts are stale: recorded={recorded}, actual={actual}")
        return 1

    spread = max(actual.values()) / min(actual.values()) - 1
    print(f"phase3_arm_tokens={actual}")
    print(f"max_min_spread={spread:.4%}")
    if spread > MAX_SPREAD:
        print(f"Length gate failed: {spread:.4%} > {MAX_SPREAD:.0%}")
        return 1

    print("phase3_frame_length_gate=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
