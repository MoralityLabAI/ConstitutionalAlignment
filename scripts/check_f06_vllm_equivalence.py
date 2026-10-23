#!/usr/bin/env python3
"""Pre-registered check of vLLM bf16 output against the aborted NF4 reference.

Bounds are read from protocol_amendment_generation_vllm_v1.json (fixed before any
registered transcript). Exit code 0 only if every bound holds; failure means stop.
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
AMENDMENT = REPO / "experiments/frame_internalization_sft_v1/protocol_amendment_generation_vllm_v1.json"
FRAMES = ("neutral", "F1", "F3", "F3_concrete")


def ks_two_sample(a: list[float], b: list[float]) -> tuple[float, float]:
    """KS statistic and asymptotic p-value with the Stephens small-sample correction."""
    if not a or not b:
        raise ValueError("empty sample")
    points = sorted(set(a) | set(b))
    sa, sb = sorted(a), sorted(b)
    ia = ib = 0
    d = 0.0
    for x in points:
        while ia < len(sa) and sa[ia] <= x:
            ia += 1
        while ib < len(sb) and sb[ib] <= x:
            ib += 1
        d = max(d, abs(ia / len(sa) - ib / len(sb)))
    n_eff = len(a) * len(b) / (len(a) + len(b))
    lam = (math.sqrt(n_eff) + 0.12 + 0.11 / math.sqrt(n_eff)) * d
    if lam < 1e-9:
        return d, 1.0
    p = 2.0 * sum((-1) ** (k - 1) * math.exp(-2.0 * k * k * lam * lam) for k in range(1, 101))
    return d, min(1.0, max(0.0, p))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_bytes().decode("utf-8").splitlines() if l.strip()]


def load_side(directory: Path) -> dict[str, Any]:
    rows = {f: read_jsonl(directory / f"{f}.jsonl") for f in FRAMES}
    events = read_jsonl(directory / "generation.events.jsonl")
    return {"rows": rows, "events": events}


def metrics(side: dict[str, Any], refusal: re.Pattern[str]) -> dict[str, Any]:
    tokens: list[float] = []
    chars: list[float] = []
    per_frame: dict[str, float] = {}
    complete = leaks = refusals = drafts = 0
    for frame in FRAMES:
        counts = [float(r["generated_token_count"]) for r in side["rows"][frame]]
        per_frame[frame] = statistics.fmean(counts) if counts else float("nan")
        tokens += counts
        for row in side["rows"][frame]:
            roles = [m["role"] for m in row["transcript"]]
            ok = roles == ["user", "assistant"] * 3 and bool(row.get("final", "").strip())
            complete += int(ok)
            assistant = [m["content"] for m in row["transcript"] if m["role"] == "assistant"]
            chars += [float(len(t)) for t in assistant]
            leaks += sum(1 for t in assistant if "<think" in t.lower() or "</think" in t.lower())
            if assistant:
                drafts += 1
                refusals += int(bool(refusal.search(assistant[0])))
    total = sum(len(side["rows"][f]) for f in FRAMES)
    calls = [e for e in side["events"] if e.get("event") == "generation_call"]
    first = sum(int(e["batch_size"]) for e in calls if int(e["attempt_index"]) == 0)
    retry = sum(int(e["batch_size"]) for e in calls if int(e["attempt_index"]) > 0)
    failed = sum(1 for e in side["events"] if e.get("event") == "request_failed")
    attempted = total + failed
    return {
        "transcripts": total, "tokens": tokens, "chars": chars, "per_frame_mean_tokens": per_frame,
        "overall_mean_tokens": statistics.fmean(tokens) if tokens else float("nan"),
        "completion_rate": complete / attempted if attempted else 0.0,
        "refusal_opening_rate": refusals / drafts if drafts else 0.0,
        "retry_rate": retry / first if first else 0.0,
        "thinking_marker_leaks": leaks,
    }


def compare(ref: dict[str, Any], cand: dict[str, Any], bounds: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}

    def put(name: str, value: Any, passed: bool, **extra: Any) -> None:
        checks[name] = {"value": value, "passed": bool(passed), **extra}

    d1, p1 = ks_two_sample(ref["tokens"], cand["tokens"])
    put("B1_tokens_per_transcript_ks", {"D": d1, "p": p1}, p1 >= bounds["B1_ks_p_generated_tokens_per_transcript_min"])
    d2, p2 = ks_two_sample(ref["chars"], cand["chars"])
    put("B2_visible_chars_per_turn_ks", {"D": d2, "p": p2}, p2 >= bounds["B2_ks_p_visible_characters_per_turn_min"])
    for key, label, bound in (
        ("completion_rate", "B3_completion_rate", "B3_completion_rate_abs_diff_max"),
        ("refusal_opening_rate", "B4_refusal_opening_rate", "B4_refusal_opening_rate_abs_diff_max"),
        ("retry_rate", "B5_retry_rate", "B5_retry_rate_abs_diff_max"),
    ):
        diff = abs(cand[key] - ref[key])
        put(label, {"reference": ref[key], "candidate": cand[key], "abs_diff": diff}, diff <= bounds[bound])
    put("B6_thinking_marker_leaks", cand["thinking_marker_leaks"],
        cand["thinking_marker_leaks"] <= bounds["B6_thinking_marker_leaks_max"])
    lo, hi = bounds["B7_per_frame_mean_tokens_ratio_range"]
    ratios = {f: cand["per_frame_mean_tokens"][f] / ref["per_frame_mean_tokens"][f] for f in FRAMES}
    overall = cand["overall_mean_tokens"] / ref["overall_mean_tokens"]
    olo, ohi = bounds["B7_overall_mean_tokens_ratio_range"]
    put("B7_mean_tokens_ratio", {"per_frame": ratios, "overall": overall},
        all(lo <= r <= hi for r in ratios.values()) and olo <= overall <= ohi)

    def order(m: dict[str, Any]) -> bool:
        pf = m["per_frame_mean_tokens"]
        return (pf["neutral"] + pf["F1"]) / 2 > (pf["F3"] + pf["F3_concrete"]) / 2

    put("B8_frame_length_order", {"reference": order(ref), "candidate": order(cand)},
        order(cand) == order(ref) if bounds["B8_frame_length_order_preserved"] else True)
    return checks


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=None)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--amendment", type=Path, default=AMENDMENT)
    args = parser.parse_args()
    amendment = json.loads(args.amendment.read_text(encoding="utf-8"))
    spec = amendment["equivalence_check"]
    reference_dir = args.reference or (REPO / spec["reference"]["directory"])
    for name, expected in spec["reference"]["sha256"].items():
        # The reference is LF text; normalise so a CRLF checkout cannot fail the pin.
        actual = hashlib.sha256((reference_dir / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if actual != expected:
            print(f"reference hash mismatch: {name}", file=sys.stderr)
            return 3
    refusal = re.compile(spec["refusal_opening_pattern"], re.IGNORECASE)
    ref = metrics(load_side(reference_dir), refusal)
    cand_side = load_side(args.candidate)
    if any(len(cand_side["rows"][f]) != 8 for f in FRAMES):
        print("candidate must contain exactly the same 8 scenarios per frame", file=sys.stderr)
        return 3
    ref_ids = {f: sorted(r["request_id"] for r in load_side(reference_dir)["rows"][f]) for f in FRAMES}
    if any(ref_ids[f] != sorted(r["request_id"] for r in cand_side["rows"][f]) for f in FRAMES):
        print("candidate scenarios differ from the reference scenarios", file=sys.stderr)
        return 3
    cand = metrics(cand_side, refusal)
    checks = compare(ref, cand, spec["bounds"])
    passed = all(c["passed"] for c in checks.values())
    result = {
        "schema_version": "frame_internalization_f06_vllm_equivalence_result.v1",
        "amendment": amendment["amendment_id"], "passed": passed, "checks": checks,
        "reference_summary": {k: v for k, v in ref.items() if k not in ("tokens", "chars")},
        "candidate_summary": {k: v for k, v in cand.items() if k not in ("tokens", "chars")},
        "candidate_raw_sha256": {f: sha256_file(args.candidate / f"{f}.jsonl") for f in FRAMES},
        "note": "A pass means no difference detected at 32 transcripts per side; it is not proof of equivalence.",
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "failed_checks": [k for k, v in checks.items() if not v["passed"]]}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
