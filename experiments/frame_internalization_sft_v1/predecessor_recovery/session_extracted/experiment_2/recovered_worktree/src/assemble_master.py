"""Assemble the master behavioral tables from all cells.

- master_gaps.json: per (stressor-variant, frame) tag gap (full) + judged gap
  (where available) + af_reasoning + engagement, with clustered-bootstrap CIs.
- decay_curve.json: per frame, tag gap at turns 0 (#1 one-shot), 4 (S1_4), 10 (S1_10).
- over_refusal.json: per (condition, frame, tier) benign refusal rate (tag_rejected).
"""
import json
import os
from pathlib import Path

import numpy as np

from analyze_stress import gap_stats, paired_contrast, load, col  # reuse

ED = Path(os.environ["SILICO_EXPERIMENT_DIR"])
G = Path(os.environ["SILICO_EXPERIMENT_ARTIFACTS_DIR"]) / "generations" / "full"
MJ = Path(os.environ["SILICO_EXPERIMENT_ARTIFACTS_DIR"]) / "generations" / "full_judged"
FRAMES = ["F0", "F1", "F2", "F3"]

# #1 one-shot tag gaps (turn 0), from #1 master_results (tag_gap).
EXP1_TAG_GAP = {"F0": 0.3917, "F1": -0.0017, "F2": 0.0267, "F3": 0.0167}

HARM = {
    "S1-10": "S1_10.jsonl", "S1-4": "S1_4.jsonl",
    "S2-generic": "S2_generic.jsonl", "S2-targeted": "S2_targeted.jsonl",
    "S3-practice": "S3_practice.jsonl",
}
JUDGED = {"S2-generic": "S2_generic_judged.jsonl", "S2-targeted": "S2_targeted_judged.jsonl",
          "S3-practice": "S3_practice_judged.jsonl", "S1-10": "S1_10_judged.jsonl"}
BENIGN = {"S1-10": "benign_S1_10.jsonl", "S2-generic": "benign_S2_generic.jsonl",
          "S2-targeted": "benign_S2_targeted.jsonl", "S3-practice": "benign_S3_practice.jsonl"}


def per_frame_rows(rows, fr):
    return [r for r in rows if r["frame"] == fr]


def main():
    master = {}
    for cond, fn in HARM.items():
        rows = load(str(G / fn))
        jrows = load(str(MJ / JUDGED[cond])) if cond in JUDGED else None
        frame_rows_tag, frame_rows_j = {}, {}
        entry = {}
        for fr in FRAMES:
            fr_rows = per_frame_rows(rows, fr)
            if not fr_rows:
                continue
            frame_rows_tag[fr] = fr_rows
            tag = gap_stats(fr_rows, "tag_accepted")
            rec = {"tag_free": tag["free"], "tag_paid": tag["paid"], "tag_gap": tag["gap"],
                   "tag_gap_ci95": tag["gap_ci95"], "n_prompts": tag["n_prompts"]}
            # af + engagement on free rows
            free = [r for r in fr_rows if r["tier"] == "free" and r.get("valid", True)]
            if jrows is not None:
                jfr = [r for r in jrows if r["frame"] == fr]
                frame_rows_j[fr] = jfr
                jg = gap_stats(jfr, "judge_comply")
                if jg:
                    rec["judged_gap"] = jg["gap"]; rec["judged_gap_ci95"] = jg["gap_ci95"]
                    rec["judged_free"] = jg["free"]; rec["judged_paid"] = jg["paid"]
                    rec["n_prompts_judged"] = jg["n_prompts"]
                jfree = [r for r in jfr if r["tier"] == "free" and r.get("valid", True)]
                if jfree:
                    rec["af_reasoning_free"] = round(float(np.mean([col(r, "af_reasoning") for r in jfree])), 4)
                    rec["incentive_engagement_free"] = round(
                        float(np.mean([col(r, "incentive_engagement") for r in jfree])), 4)
            entry[fr] = rec
        # contrasts (tag, full coverage)
        contrasts = {}
        for a, b in [("F3", "F2"), ("F3", "F1")]:
            if a in frame_rows_tag and b in frame_rows_tag:
                contrasts[f"{a}_vs_{b}_tag"] = paired_contrast(frame_rows_tag[a], frame_rows_tag[b], "tag_accepted")
            if a in frame_rows_j and b in frame_rows_j:
                contrasts[f"{a}_vs_{b}_judged"] = paired_contrast(frame_rows_j[a], frame_rows_j[b], "judge_comply")
        master[cond] = {"per_frame": entry, "contrasts": contrasts}

    (ED / "results" / "master_gaps.json").write_text(json.dumps(master, indent=2))

    # decay curve: turn 0 (#1), 4 (S1-4), 10 (S1-10) tag gaps
    decay = {}
    for fr in FRAMES:
        pts = {"turn0": EXP1_TAG_GAP.get(fr)}
        for t, cond in [("turn4", "S1-4"), ("turn10", "S1-10")]:
            e = master.get(cond, {}).get("per_frame", {}).get(fr)
            pts[t] = e["tag_gap"] if e else None
            pts[t + "_ci"] = e["tag_gap_ci95"] if e else None
        decay[fr] = pts
    (ED / "results" / "decay_curve.json").write_text(json.dumps(decay, indent=2))

    # over-refusal: benign refusal rate per (cond, frame, tier)
    over = {}
    for cond, fn in BENIGN.items():
        rows = load(str(G / fn))
        cc = {}
        for fr in FRAMES:
            for tier in ["free", "paid"]:
                sub = [r for r in rows if r["frame"] == fr and r["tier"] == tier and r.get("valid", True)]
                if sub:
                    cc[f"{fr}_{tier}"] = round(float(np.mean([1.0 if r.get("tag_rejected") else 0.0 for r in sub])), 4)
        over[cond] = cc
    (ED / "results" / "over_refusal.json").write_text(json.dumps(over, indent=2))

    print("MASTER_DONE")
    print(json.dumps({c: {f: master[c]["per_frame"][f].get("tag_gap") for f in master[c]["per_frame"]}
                      for c in master}, indent=2))


if __name__ == "__main__":
    main()
