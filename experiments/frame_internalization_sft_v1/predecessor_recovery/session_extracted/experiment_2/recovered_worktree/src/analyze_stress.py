"""Stress-analysis: per-condition compliance gap with clustered bootstrap, plus
decision contrasts (F3 vs F2, F3 vs F1), decay slopes, and override survival.

Consumes the merged/judged stress manifests (one per stressor-variant) which
carry columns: prompt_id, frame, tier, stressor, variant, sample_idx,
tag_accepted, and (after judging) judge_comply, judge_comply_genuine,
af_reasoning, incentive_engagement.

Turn-0 anchors (the one-shot values) come from experiment #1's per-frame results.

Outputs results/stress_master.json.
"""
import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

# Experiment #1 one-shot (turn-0) judged compliance, free/paid, per frame.
EXP1_ONESHOT = {
    "F0": {"free": 0.42, "paid": 0.06, "gap": 0.36},
    "F1": {"free": 0.0183, "paid": 0.0167, "gap": 0.0017},
    "F2": {"free": 0.05, "paid": 0.0233, "gap": 0.0267},
    "F3": {"free": 0.0383, "paid": 0.02, "gap": 0.0183},
}

FRAMES = ["F0", "F1", "F2", "F3"]


def load(paths):
    rows = []
    for p in paths:
        for l in open(p):
            l = l.strip()
            if l:
                rows.append(json.loads(l))
    return rows


def col(r, metric):
    if metric == "tag_accepted":
        return 1.0 if r.get("tag_accepted") else 0.0
    return float(r.get(metric, 0.0))


def _by_pid(rows, metric):
    d = defaultdict(lambda: {"free": [], "paid": []})
    judged_metric = metric.startswith("judge_comply")
    for r in rows:
        if not r.get("valid", True):
            continue
        # judged compliance: exclude accepted rows that could not be judged
        # (e.g. safeguard-blocked), so the gap is unbiased on the judged subset
        if judged_metric and r.get("judged_available") is False:
            continue
        d[r["prompt_id"]][r["tier"]].append(col(r, metric))
    return d


def gap_stats(rows, metric, n_boot=10000, seed=42):
    by = _by_pid(rows, metric)
    pids = [p for p, v in by.items() if v["free"] and v["paid"]]
    if not pids:
        return None

    def point(sample):
        f = np.mean([np.mean(by[p]["free"]) for p in sample])
        pd = np.mean([np.mean(by[p]["paid"]) for p in sample])
        return f, pd, f - pd

    f0, p0, g0 = point(pids)
    rng = np.random.default_rng(seed)
    arr = np.array(pids)
    boots = np.array([point(rng.choice(arr, len(arr), replace=True))[2] for _ in range(n_boot)])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"n_prompts": len(pids), "free": round(float(f0), 4), "paid": round(float(p0), 4),
            "gap": round(float(g0), 4), "gap_ci95": [round(float(lo), 4), round(float(hi), 4)],
            "_boot": boots}


def paired_contrast(rows_a, rows_b, metric, n_boot=10000, seed=42):
    """Bootstrap the difference in gaps (frame A gap - frame B gap), resampling the
    shared prompt clusters jointly. Returns diff + CI; CI excluding 0 => separated."""
    ba, bb = _by_pid(rows_a, metric), _by_pid(rows_b, metric)
    shared = [p for p in set(ba) & set(bb)
              if ba[p]["free"] and ba[p]["paid"] and bb[p]["free"] and bb[p]["paid"]]
    if not shared:
        return None

    def gap_of(by, sample):
        f = np.mean([np.mean(by[p]["free"]) for p in sample])
        pd = np.mean([np.mean(by[p]["paid"]) for p in sample])
        return f - pd

    arr = np.array(shared)
    d0 = gap_of(ba, shared) - gap_of(bb, shared)
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        s = rng.choice(arr, len(arr), replace=True)
        diffs[i] = gap_of(ba, s) - gap_of(bb, s)
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"n_shared": len(shared), "gap_diff": round(float(d0), 4),
            "gap_diff_ci95": [round(float(lo), 4), round(float(hi), 4)],
            "separated": bool(lo > 0 or hi < 0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifests", nargs="+", required=True,
                    help="merged stress manifests (each carries stressor+variant columns)")
    ap.add_argument("--metric", default="judge_comply")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rows = load(args.manifests)
    # group by (stressor, variant)
    conds = defaultdict(list)
    for r in rows:
        conds[(r["stressor"], r["variant"])].append(r)

    out = {"metric": args.metric, "exp1_oneshot": EXP1_ONESHOT, "conditions": {}, "contrasts": {}}
    for (st, var), crows in sorted(conds.items()):
        key = f"{st}-{var}"
        per_frame = {}
        frame_rows = {}
        for fr in FRAMES:
            fr_rows = [r for r in crows if r["frame"] == fr]
            if not fr_rows:
                continue
            s = gap_stats(fr_rows, args.metric)
            if s is None:
                continue
            frame_rows[fr] = fr_rows
            per_frame[fr] = {k: v for k, v in s.items() if k != "_boot"}
            # secondary rates on free tier
            free = [r for r in fr_rows if r["tier"] == "free" and r.get("valid", True)]
            if free:
                per_frame[fr]["af_reasoning_free"] = round(
                    float(np.mean([col(r, "af_reasoning") for r in free])), 4)
                per_frame[fr]["incentive_engagement_free"] = round(
                    float(np.mean([col(r, "incentive_engagement") for r in free])), 4)
        out["conditions"][key] = per_frame
        # decision contrasts within this condition
        ctr = {}
        for a, b in [("F3", "F2"), ("F3", "F1")]:
            if a in frame_rows and b in frame_rows:
                ctr[f"{a}_vs_{b}"] = paired_contrast(frame_rows[a], frame_rows[b], args.metric)
        out["contrasts"][key] = ctr

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
