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


def _lf(data: bytes) -> bytes:
    """Normalise CRLF to LF so hashes are the same on a Windows checkout and on the pod."""
    return data.replace(bytes([13, 10]), bytes([10]))


PARITY_AMENDMENT = REPO /"experiments/frame_internalization_sft_v1/protocol_amendment_parity_balance_v1.json"
PARITY_AMENDMENT_SHA256 = "19d454a66cdf250d1282a3d1dbda4b0d51af70cab6e0cd26d794952b9dacb87a"
PARITY_CODE = REPO / "scripts/parity_balance.py"


def load_parity(path: Path | None = None, expected_sha256: str = PARITY_AMENDMENT_SHA256,
                code_path: Path | None = None) -> dict[str, Any]:
    """Verified parity amendment: the file by SHA-256 and the rule's code by the hash it records."""
    path = path or PARITY_AMENDMENT
    raw = _lf(path.read_bytes())
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ExclusionError(f"parity amendment hash mismatch: {path}")
    data = json.loads(raw.decode("utf-8"))
    if data.get("amendment_id") != "frame_internalization_parity_balance_v1":
        raise ExclusionError("unexpected parity amendment id")
    code = _lf((code_path or PARITY_CODE).read_bytes())
    if hashlib.sha256(code).hexdigest() != data["rule"]["code_sha256_lf"]:
        raise ExclusionError("parity rule code differs from the hash recorded in the amendment")
    return data


DOSE_MATCHING_AMENDMENT = REPO / "experiments/frame_internalization_sft_v1/protocol_amendment_dose_matching_v1.json"
DOSE_MATCHING_AMENDMENT_SHA256 = "d6ccfa965b2ca0d2247f499e85dfee1420a2caf69aa4393c8abde01f2a301dc2"


def load_dose_matching(path: Path | None = None, expected_sha256: str = DOSE_MATCHING_AMENDMENT_SHA256) -> dict[str, Any]:
    """The verified dose-matching amendment; any change to the file is refused."""
    path = path or DOSE_MATCHING_AMENDMENT
    raw = _lf(path.read_bytes())
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ExclusionError(f"dose-matching amendment hash mismatch: {path}")
    data = json.loads(raw.decode("utf-8"))
    if data.get("amendment_id") != "frame_internalization_dose_matching_v1":
        raise ExclusionError("unexpected dose-matching amendment id")
    return data


SMOKE_REDUCTION_AMENDMENT = REPO / "experiments/frame_internalization_sft_v1/protocol_amendment_smoke_reduction_v1.json"
SMOKE_REDUCTION_AMENDMENT_SHA256 = "8baff4a52ec4b4e2dde1bbd94c67886c150d2230f83c8ff443956eb66ef7f2cf"


def load_smoke_reduction(path: Path | None = None, expected_sha256: str = SMOKE_REDUCTION_AMENDMENT_SHA256) -> dict[str, Any]:
    """The verified reduced-smoke amendment; any change to the file is refused."""
    path = path or SMOKE_REDUCTION_AMENDMENT
    raw = _lf(path.read_bytes())
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ExclusionError(f"smoke-reduction amendment hash mismatch: {path}")
    data = json.loads(raw.decode("utf-8"))
    if data.get("amendment_id") != "frame_internalization_smoke_reduction_v1":
        raise ExclusionError("unexpected smoke-reduction amendment id")
    return data


def smoke_steps_for(arm: str, amendment: dict[str, Any] | None, registered: int = 50) -> int:
    """Steps the F18 smoke runs for an arm: the registered 50, or the amendment's reduced schedule."""
    if amendment is None:
        return registered
    reduced = amendment["reduced_smoke"]
    return int(reduced["full_arm_steps"] if arm == reduced["full_arm"] else reduced["other_arms_steps"])
