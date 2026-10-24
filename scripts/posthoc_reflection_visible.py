#!/usr/bin/env python3
"""POST HOC (not registered): judge the visible answers of the four reflection arms and re-estimate.

See experiments/frame_internalization_sft_v1/six_arm_run_20261024/POSTHOC_REFLECTION_VISIBLE_ANSWERS.md.
The registered analysis stands and is not replaced. This ignores only the closed-reasoning-block part
of the registered validity rule. Judging reuses scripts/judge_six_arm_codex.py (same judge, rubric,
batching, content-filter halving, quota stop); the estimates reuse scripts/analyze_six_arm.py unchanged.

Modes:
  plan     count usable rows and units to judge
  judge    judge the accepted-tag usable harmful and override rows of the four reflection arms
  analyze  merge the post hoc verdicts into the registered judged rows and compute the post hoc estimates
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_six_arm as an  # noqa: E402
import judge_six_arm as jg  # noqa: E402
import judge_six_arm_codex as cx  # noqa: E402

REFLECTION_ARMS = ["neutral_reflection", "F1_reflection", "F3_reflection", "F3_concrete_reflection"]
UNIVERSES = ("harmful", "override")
CELLS = [f"{u}__{a}__F0" for u in UNIVERSES for a in REFLECTION_ARMS]


def posthoc_usable(r: dict[str, Any]) -> bool:
    """Registered validity minus the closed-reasoning-block requirement."""
    return (not r.get("truncated") and not r.get("missing_visible_answer") and bool(r.get("tag_accepted") or r.get("tag_rejected"))
            and bool((r.get("output_without_scratchpad") or "").strip()))


def reflection_rows(eval_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for cell in CELLS:
        rows += jg.read_jsonl(eval_dir / f"{cell}.jsonl")
    return rows


def judge_units(eval_dir: Path) -> list[dict[str, Any]]:
    rows = [dict(r, valid=posthoc_usable(r)) for r in reflection_rows(eval_dir)]
    return jg.select_units(rows, "compliance", jg.question_texts())


# ------------------------------------------------------------------ estimates
def merged_rows(registered: list[dict[str, Any]], eval_dir: Path, verdicts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Registered judged rows for every non-reflection cell (benign dropped); post hoc verdicts for the reflection cells."""
    keep = [r for r in registered if r["universe"] != "benign" and r["cell_id"] not in CELLS]
    for r in reflection_rows(eval_dir):
        out = dict(r, judge_refusal=None, valid=posthoc_usable(r))
        rec = verdicts.get(jg.uid_of(r))
        if rec is not None and rec["status"] == "ok" and out["valid"] and r.get("tag_accepted"):
            out["judge_refusal"] = rec["verdict"]["refusal"]
        keep.append(out)
    return keep


def boot_ci(x: np.ndarray) -> list[float]:
    lo, hi = np.quantile(x, [0.025, 0.975])
    return [float(lo), float(hi)]


def analyze_posthoc(rows: list[dict[str, Any]], harmful_ids: list[str], override_ids: list[str]) -> dict[str, Any]:
    result = an.analyze(rows, harmful_ids, [], override_ids)  # registered code, unchanged
    cells = {c: an.cell_arrays(rows, c, harmful_ids) for c in ["harmful__base__F0", "harmful__neutral_reflection__F0"] +
             [f"harmful__{a}__F0" for a in REFLECTION_ARMS if a != "neutral_reflection"]}
    idx = np.random.default_rng(an.SEED).integers(0, len(harmful_ids), size=(an.DRAWS, len(harmful_ids)))  # identical to analyze()
    base, neutral = cells["harmful__base__F0"], cells["harmful__neutral_reflection__F0"]

    def level(c, i=None):
        pooled = (c["free"] + c["paid"]) / 2
        return float(pooled.mean()) if i is None else pooled[i].mean(axis=1)

    per_arm = {}
    for a in REFLECTION_ARMS + ["base"]:
        c = cells[f"harmful__{a}__F0"] if a != "base" else base
        per_arm[a] = {
            "free": float(c["free"].mean()), "free_ci95": boot_ci(c["free"][idx].mean(axis=1)),
            "paid": float(c["paid"].mean()), "paid_ci95": boot_ci(c["paid"][idx].mean(axis=1)),
            "pooled": level(c), "pooled_ci95": boot_ci(level(c, idx)),
            "G": an.gap(c["free"], c["paid"]), "G_ci95": boot_ci(an.gap(c["free"], c["paid"], idx)),
            "rows": c["rows"]}
    arms = [a for a in REFLECTION_ARMS]
    # G contrasts against the base model with F0 (simultaneous within the family)
    def family(point: dict[str, float], boot: dict[str, np.ndarray]) -> dict[str, Any]:
        dev = np.stack([boot[n] - point[n] for n in point])
        hw = float(np.quantile(np.abs(dev).max(axis=0), 0.95))
        return {"common_half_width": hw, "contrasts": {n: {"estimate": point[n], "lower": point[n] - hw, "upper": point[n] + hw,
                                                           "excludes_zero": bool(abs(point[n]) > hw)} for n in point}}

    def g(a):  # noqa: ANN001
        c = cells[f"harmful__{a}__F0"]
        return an.gap(c["free"], c["paid"]), an.gap(c["free"], c["paid"], idx)

    gb = (an.gap(base["free"], base["paid"]), an.gap(base["free"], base["paid"], idx))
    pt, bt = {}, {}
    for a in arms:
        pt[f"G[{a}] - G[base F0]"], bt[f"G[{a}] - G[base F0]"] = g(a)[0] - gb[0], g(a)[1] - gb[1]
    result_extra = {"G_minus_base_family": family(pt, bt)}
    pl, bl = {}, {}
    for a in arms:
        c = cells[f"harmful__{a}__F0"]
        pl[f"level[{a}] - level[base F0]"], bl[f"level[{a}] - level[base F0]"] = level(c) - level(base), level(c, idx) - level(base, idx)
    result_extra["level_minus_base_family"] = family(pl, bl)
    pn, bn = {}, {}
    for a in arms:
        if a == "neutral_reflection":
            continue
        c = cells[f"harmful__{a}__F0"]
        pn[f"level[{a}] - level[neutral]"], bn[f"level[{a}] - level[neutral]"] = level(c) - level(neutral), level(c, idx) - level(neutral, idx)
    result_extra["level_minus_neutral_family"] = family(pn, bn)
    return {"label": "POST HOC, exploratory; the registered analysis stands and is not replaced", "registered_code_result": result,
            "per_arm_harmful": per_arm, **result_extra}


# ------------------------------------------------------------------ cli
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["plan", "judge", "analyze"], default="plan")
    parser.add_argument("--eval-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--registered-rows", type=Path, help="judged_rows.jsonl of the registered Codex run (analyze)")
    parser.add_argument("--output", type=Path, help="result JSON (analyze)")
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    units = judge_units(args.eval_dir)
    if args.mode == "plan":
        print(json.dumps({"units": len(units), "harmful": sum(u["row"]["universe"] == "harmful" for u in units),
                          "override": sum(u["row"]["universe"] == "override" for u in units)}))
        return 0
    if args.mode == "judge":
        (args.out_dir / "work").mkdir(exist_ok=True)
        runner = cx.codex_runner(cx.find_codex(), args.out_dir / "work")
        summary = cx.run_task(runner, "compliance", units, jg.rubric_text("compliance"), args.out_dir)
        (args.out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary))
        return 0 if not summary["stopped"] else 2
    registered = jg.read_jsonl(args.registered_rows)
    verdicts = jg.load_verdicts(args.out_dir / "verdicts_compliance.jsonl")
    rows = merged_rows(registered, args.eval_dir, verdicts)
    ids = lambda name, key, limit=0: [json.loads(l)[key] for l in (jg.UNIVERSES / name).read_bytes().decode("utf-8").splitlines() if l.strip()][: limit or None]  # noqa: E731
    result = analyze_posthoc(rows, ids("harmful_queries.jsonl", "prompt_id"), ids("override_queries.jsonl", "override_prompt_id", 100))
    judged = [u["uid"] for u in units]
    recs = [verdicts[u] for u in judged if u in verdicts]
    result["accounting"] = {"units": len(units), "verdicts": len(recs), "ok": sum(r["status"] == "ok" for r in recs),
                            "missing": sum(r["status"] != "ok" for r in recs),
                            "blocked_by_content_filter": sum(r.get("error") == "blocked_by_provider_content_filter" for r in recs)}
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["accounting"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
