"""Verify historical byte hashes across Git checkout LF normalization.

Earlier experiment exports were frozen as CRLF. Git's eol=lf checkout
converts them to LF. Exact digest equality with raw bytes or with the
uniquely reconstructed original CRLF bytes retains the frozen binding.
Only pinned historical subtrees are eligible for reconstruction.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_PREFIXES = (
    "jinn_bench/",
    "experiments/jinn_bench_v1/",
    "experiments/jinn_beast_metta_rl_v1/",
    "environments/jinn_beast_metta/jinn_beast_metta/data/",
    "experiments/frame_internalization_sft_v1/rerun_freeze/",
)


def matches_frozen_sha256(path: Path, expected: str) -> bool:
    if not isinstance(expected, str) or re.fullmatch(r"[a-f0-9]{64}", expected) is None:
        return False
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        return False
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() == expected:
        return True
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return False
    if not any(relative.startswith(prefix) for prefix in HISTORICAL_PREFIXES):
        return False
    if b"\n" not in raw or b"\r" in raw:
        return False
    reconstructed = raw.replace(b"\n", b"\r\n")
    return hashlib.sha256(reconstructed).hexdigest() == expected
