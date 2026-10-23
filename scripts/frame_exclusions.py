"""The one recorded scenario exclusion (amendment frame_internalization_failed_scenario_v1).

The amendment file is bound by SHA-256 over its LF bytes. Only this exact file, and only
the failed request it names, is accepted; any other missing or failed transcript must
still stop the run. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
AMENDMENT = REPO / "experiments/frame_internalization_sft_v1/protocol_amendment_failed_scenario_v1.json"
AMENDMENT_SHA256 = "76034cc8c69128f85181e710dd3e2ce7ba8fcfe6892c9611201b522c6c46a2c2"
FRAMES = ("neutral", "F1", "F3", "F3_concrete")


class ExclusionError(RuntimeError):
    pass


def load_exclusion(path: Path | None = None, expected_sha256: str = AMENDMENT_SHA256) -> dict[str, Any]:
    """Return the verified amendment; raise unless its LF-normalised bytes match the pin."""
    path = path or AMENDMENT
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ExclusionError(f"exclusion amendment hash mismatch: {path}")
    data = json.loads(raw.decode("utf-8"))
    if data.get("amendment_id") != "frame_internalization_failed_scenario_v1":
        raise ExclusionError("unexpected amendment id")
    return data


def excluded_scenarios(data: dict[str, Any] | None) -> set[str]:
    return set(data["decision"]["excluded_scenario_ids"]) if data else set()


def permitted_failed_requests(data: dict[str, Any] | None) -> set[str]:
    return set(data["decision"]["permitted_failed_request_ids"]) if data else set()


def expected_split_counts(dilemmas: dict[str, dict[str, Any]], excluded: set[str]) -> dict[str, int]:
    kept = [d for sid, d in dilemmas.items() if sid not in excluded]
    return {"scenarios": len(kept), "train": sum(d["split"] == "train" for d in kept),
            "val": sum(d["split"] == "val" for d in kept)}
