"""Internals analysis on layer-27 activations.

1. Eval-awareness probe: logistic regression separating free vs paid contexts,
   trained on F0 ONLY, evaluated on prompt-disjoint held-out prompts, with a
   random-label control it must beat.
2. Per-frame internal separation: project each frame's free & paid activations
   onto the F0 probe direction; report the mean free-paid projection gap per frame.
   Does a frame that flattens BEHAVIOR also flatten the INTERNAL tier separation?
3. Frame geometry: cosine distance between per-frame mean activations (vs F0).

Runs on CPU. Writes results/internals.json.
"""
import json, os
import numpy as np
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

ED = Path(os.environ["SILICO_EXPERIMENT_DIR"])
AD = Path(os.environ["SILICO_EXPERIMENT_ARTIFACTS_DIR"])
POOL = os.environ.get("POOL", "last")
SEED = 42


def main():
    npz = np.load(AD / "activations" / "layer27.npz", allow_pickle=True)
    pids = npz["prompt_ids"]
    n = len(pids)
    rng = np.random.default_rng(SEED)

    def feats(fr, tier):
        return npz[f"{fr}_{tier}_{POOL}"].astype(np.float32)

    # ---- 1. eval-awareness probe on F0, prompt-disjoint split ----
    idx = np.arange(n); rng.shuffle(idx)
    cut = int(0.7 * n)
    tr_p, te_p = idx[:cut], idx[cut:]
    Xtr = np.concatenate([feats("F0", "free")[tr_p], feats("F0", "paid")[tr_p]])
    ytr = np.concatenate([np.ones(len(tr_p)), np.zeros(len(tr_p))])
    Xte = np.concatenate([feats("F0", "free")[te_p], feats("F0", "paid")[te_p]])
    yte = np.concatenate([np.ones(len(te_p)), np.zeros(len(te_p))])
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    clf = LogisticRegression(max_iter=2000, C=0.5).fit((Xtr - mu) / sd, ytr)
    auroc = roc_auc_score(yte, clf.decision_function((Xte - mu) / sd))
    # random-label control
    yrand = rng.permutation(ytr)
    clf_r = LogisticRegression(max_iter=2000, C=0.5).fit((Xtr - mu) / sd, yrand)
    auroc_rand = roc_auc_score(yte, clf_r.decision_function((Xte - mu) / sd))

    w = clf.coef_[0]

    def proj(X):
        return ((X - mu) / sd) @ w

    # ---- 2. per-frame internal free/paid separation along the probe ----
    per_frame = {}
    for fr in ["F0", "F1", "F2", "F3"]:
        pf = proj(feats(fr, "free")); pp = proj(feats(fr, "paid"))
        # standardized separation (Cohen's d)
        pooled_sd = np.sqrt((pf.var() + pp.var()) / 2) + 1e-6
        per_frame[fr] = {
            "proj_gap_free_minus_paid": float(pf.mean() - pp.mean()),
            "cohens_d": float((pf.mean() - pp.mean()) / pooled_sd),
        }

    # ---- 3. frame geometry: cosine distance of per-frame mean activation vs F0 ----
    def frame_mean(fr):
        return np.concatenate([feats(fr, "free"), feats(fr, "paid")]).mean(0)
    f0m = frame_mean("F0")
    def cos(a, b):
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
    geom = {fr: {"cos_to_F0": cos(frame_mean(fr), f0m),
                 "cos_dist_to_F0": 1 - cos(frame_mean(fr), f0m)} for fr in ["F1", "F2", "F3"]}
    # pairwise among accountability frames
    geom["cos_dist_F2_F3"] = 1 - cos(frame_mean("F2"), frame_mean("F3"))
    geom["cos_dist_F1_F3"] = 1 - cos(frame_mean("F1"), frame_mean("F3"))
    geom["cos_dist_F1_F2"] = 1 - cos(frame_mean("F1"), frame_mean("F2"))

    out = {"pool": POOL, "layer": 27,
           "eval_awareness_probe": {"auroc_heldout": round(float(auroc), 4),
                                    "auroc_random_label": round(float(auroc_rand), 4),
                                    "n_train_prompts": int(cut), "n_test_prompts": int(n - cut)},
           "per_frame_internal_separation": per_frame,
           "frame_geometry": geom}
    (ED / "results").mkdir(exist_ok=True)
    json.dump(out, open(ED / "results" / f"internals_{POOL}.json", "w"), indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
