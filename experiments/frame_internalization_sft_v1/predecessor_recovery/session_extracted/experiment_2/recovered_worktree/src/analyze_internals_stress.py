"""Internals on the stress layer-27 activations.

Eval-awareness probe trained on the WITHIN-RUN one-shot cell (S0, F0), on a
prompt-disjoint split, with a random-label control it must beat. Then for each
(cond, frame) project free & paid activations onto the probe and report the
standardized free-paid separation (Cohen's d) + raw projection gap.

Key readout: does in-context practice (S3) shrink the internal tier separation
relative to one-shot (S0), where one-shot framing in #1 did NOT? Also reports the
frame-geometry cosine distances per condition.

Runs on CPU. Writes results/internals_stress_<pool>.json.
"""
import json
import os
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

ED = Path(os.environ["SILICO_EXPERIMENT_DIR"])
AD = Path(os.environ["SILICO_EXPERIMENT_ARTIFACTS_DIR"])
POOL = os.environ.get("POOL", "last")
SEED = 42

# #1 one-shot internal separation (Cohen's d) for reference (from #1 internals_summary).
EXP1_ONESHOT_D = {"last": {"F0": 14.2, "F1": 11.4, "F2": 13.4, "F3": 11.9},
                  "mean": {"F0": 17.7, "F1": 14.1, "F2": 13.9, "F3": 13.7}}


def main():
    npz = np.load(AD / "activations" / "stress_layer27.npz", allow_pickle=True)
    meta = json.loads((AD / "activations" / "meta_stress.json").read_text())
    conds, frames, tiers = meta["conds"], meta["frames"], meta["tiers"]
    pids = npz["prompt_ids"]
    n = len(pids)
    rng = np.random.default_rng(SEED)

    def feats(cond, fr, tier):
        return npz[f"{cond}_{fr}_{tier}_{POOL}"].astype(np.float32)

    # probe trained on within-run one-shot F0 (S0), prompt-disjoint
    base_cond = "S0" if "S0" in conds else conds[0]
    idx = np.arange(n); rng.shuffle(idx)
    cut = int(0.7 * n)
    tr, te = idx[:cut], idx[cut:]
    Xtr = np.concatenate([feats(base_cond, "F0", "free")[tr], feats(base_cond, "F0", "paid")[tr]])
    ytr = np.concatenate([np.ones(len(tr)), np.zeros(len(tr))])
    Xte = np.concatenate([feats(base_cond, "F0", "free")[te], feats(base_cond, "F0", "paid")[te]])
    yte = np.concatenate([np.ones(len(te)), np.zeros(len(te))])
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    clf = LogisticRegression(max_iter=2000, C=0.5).fit((Xtr - mu) / sd, ytr)
    auroc = roc_auc_score(yte, clf.decision_function((Xte - mu) / sd))
    clf_r = LogisticRegression(max_iter=2000, C=0.5).fit((Xtr - mu) / sd, rng.permutation(ytr))
    auroc_rand = roc_auc_score(yte, clf_r.decision_function((Xte - mu) / sd))
    w = clf.coef_[0]

    def proj(X):
        return ((X - mu) / sd) @ w

    per_cond = {}
    for cond in conds:
        pf_by_frame = {}
        for fr in frames:
            pf = proj(feats(cond, fr, "free")); pp = proj(feats(cond, fr, "paid"))
            pooled_sd = np.sqrt((pf.var() + pp.var()) / 2) + 1e-6
            pf_by_frame[fr] = {"proj_gap": float(pf.mean() - pp.mean()),
                               "cohens_d": float((pf.mean() - pp.mean()) / pooled_sd)}
        per_cond[cond] = pf_by_frame

    # frame geometry per cond (cos-dist of per-frame mean activation vs F0)
    def frame_mean(cond, fr):
        return np.concatenate([feats(cond, fr, "free"), feats(cond, fr, "paid")]).mean(0)

    def cos(a, b):
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

    geom = {}
    for cond in conds:
        f0m = frame_mean(cond, "F0")
        geom[cond] = {fr: {"cos_dist_to_F0": 1 - cos(frame_mean(cond, fr), f0m)}
                      for fr in frames if fr != "F0"}

    out = {"pool": POOL, "layer": 27, "probe_trained_on": base_cond,
           "eval_awareness_probe": {"auroc_heldout": round(float(auroc), 4),
                                    "auroc_random_label": round(float(auroc_rand), 4),
                                    "note": "AUROC is near-trivial (tier stated in prompt); the meaningful "
                                            "quantity is the per-cond separation MAGNITUDE below."},
           "exp1_oneshot_cohens_d": EXP1_ONESHOT_D.get(POOL, {}),
           "per_cond_internal_separation": per_cond,
           "frame_geometry": geom}
    (ED / "results").mkdir(exist_ok=True)
    (ED / "results" / f"internals_stress_{POOL}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
