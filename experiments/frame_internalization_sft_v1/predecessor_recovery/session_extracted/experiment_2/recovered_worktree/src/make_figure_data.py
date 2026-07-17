"""Emit tidy plot-ready CSVs into figures/<name>/data.csv for the results page."""
import csv
import json
import os
from pathlib import Path

ED = Path(os.environ["SILICO_EXPERIMENT_DIR"])
R = ED / "results"
FR_LABEL = {"F0": "none (F0)", "F1": "secular constitution (F1)",
            "F2": "secular auditor (F2)", "F3": "eschatological (F3)"}


def w(name, header, rows):
    d = ED / "figures" / name
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "data.csv", "w", newline="") as f:
        cw = csv.writer(f); cw.writerow(header); cw.writerows(rows)
    print(f"wrote figures/{name}/data.csv ({len(rows)} rows)")


master = json.loads((R / "master_gaps.json").read_text())
decay = json.loads((R / "decay_curve.json").read_text())
over = json.loads((R / "over_refusal.json").read_text())

# 1) headline: gap per frame per stressor (tag) with CI
rows = []
for cond, d in master.items():
    for fr, s in d["per_frame"].items():
        lo, hi = s["tag_gap_ci95"]
        rows.append([cond, fr, FR_LABEL[fr], s["tag_gap"], lo, hi,
                     s.get("judged_gap", ""), s.get("af_reasoning_free", ""),
                     s.get("incentive_engagement_free", "")])
w("gap_by_frame", ["stressor", "frame", "frame_label", "tag_gap", "ci_lo", "ci_hi",
                   "judged_gap", "af_reasoning_free", "incentive_engagement_free"], rows)

# 2) decay curve
rows = []
for fr, pts in decay.items():
    for turn, key in [(0, "turn0"), (4, "turn4"), (10, "turn10")]:
        v = pts.get(key)
        if v is not None:
            rows.append([fr, FR_LABEL[fr], turn, v])
w("decay", ["frame", "frame_label", "turns", "tag_gap"], rows)

# 3) override survival: gap at one-shot(#1) -> generic -> targeted per frame
EXP1 = {"F0": 0.3917, "F1": -0.0017, "F2": 0.0267, "F3": 0.0167}
rows = []
for fr in ["F0", "F1", "F2", "F3"]:
    g = master.get("S2-generic", {}).get("per_frame", {}).get(fr, {}).get("tag_gap")
    t = master.get("S2-targeted", {}).get("per_frame", {}).get(fr, {}).get("tag_gap")
    rows.append([fr, FR_LABEL[fr], EXP1[fr], g if g is not None else "", t if t is not None else ""])
w("override_survival", ["frame", "frame_label", "oneshot_gap", "generic_override_gap", "targeted_override_gap"], rows)

# 4) practice effect + engagement: one-shot(#1) vs S3 gap, and engagement per frame
rows = []
for fr in ["F0", "F1", "F2", "F3"]:
    s3 = master.get("S3-practice", {}).get("per_frame", {}).get(fr, {})
    rows.append([fr, FR_LABEL[fr], EXP1[fr], s3.get("tag_gap", ""),
                 s3.get("incentive_engagement_free", "")])
w("practice_effect", ["frame", "frame_label", "oneshot_gap", "practice_gap", "practice_engagement_free"], rows)

# 5) over-refusal (benign) per condition/frame (free tier)
rows = []
for cond, cc in over.items():
    for fr in ["F0", "F1", "F2", "F3"]:
        k = f"{fr}_free"
        if k in cc:
            rows.append([cond, fr, FR_LABEL[fr], cc[k]])
w("over_refusal", ["condition", "frame", "frame_label", "benign_refusal_free"], rows)

print("FIGDATA_DONE")
