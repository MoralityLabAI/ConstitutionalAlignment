#!/usr/bin/env python3
"""Registered Qwen3-1.7B layer-27 evaluation-awareness probe and its controls.

Spec: base_reanchor_plan_v1.json (representation_probe) and the recovered predecessor
procedure (harvest_activations.py, analyze_internals.py). Layer index 27 (zero based) is
the final of Qwen3-1.7B's 28 decoder layers; the activation is that layer's output
residual stream (before the final norm), at two positions: the last prefill token and the
mean over content tokens. The probe is a logistic regression (C=0.5, L2) separating free
from paid, fit on the base model with the F0 prompt only, on a prompt-disjoint 70/30
split (seed 42). Controls: a random-label fit and random unit directions in the same
standardized space.

Phases (run in this order, enforced):
  fit       base F0 only. Writes probe_freeze.json/.npz and their hash BEFORE any adapter is loaded.
  adapters  refuses without a matching freeze; harvests each adapter (F0) and the base with
            F1/F3/F3-concrete, projects on the frozen direction, writes probe_results.json.
  associate offline (CPU): held-out association of the probe shift with the compliance-gap shift.
No GPU result is claimed until the stage has run; only the CPU tests have.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_six_arm_eval_vllm as ev  # noqa: E402

LAYER = 27
N_LAYERS = 28
SEED = 42
TRAIN_FRACTION = 0.7
C = 0.5
N_RANDOM = 1000
POOLS = ("last", "mean")
PRIMARY_POOL = "last"
BATCH = 8
ARMS = ev.ARMS
TIERS = ev.TIERS


# ------------------------------------------------------------------ pure math
def split_indices(n: int, seed: int = SEED) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    idx = np.arange(n)
    rng.shuffle(idx)
    cut = int(TRAIN_FRACTION * n)
    return idx[:cut], idx[cut:]


def auroc(y: np.ndarray, score: np.ndarray) -> float:
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score))
    sorted_scores = score[order]
    i = 0
    while i < len(score):
        j = i
        while j + 1 < len(score) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    n_pos = float((y == 1).sum())
    n_neg = float((y == 0).sum())
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def fit_logistic(X: np.ndarray, y: np.ndarray, c: float = C, max_iter: int = 500) -> tuple[np.ndarray, float]:
    """minimize 0.5*|w|^2 + c * sum(logloss), intercept unpenalized (the scikit-learn objective), by L-BFGS."""
    import torch

    Xt = torch.tensor(X, dtype=torch.float64)
    yt = torch.tensor(2.0 * y - 1.0, dtype=torch.float64)
    w = torch.zeros(X.shape[1], dtype=torch.float64, requires_grad=True)
    b = torch.zeros(1, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([w, b], lr=1.0, max_iter=max_iter, tolerance_grad=1e-7, tolerance_change=1e-12,
                            line_search_fn="strong_wolfe")

    def closure():
        opt.zero_grad()
        margin = yt * (Xt @ w + b)
        loss = 0.5 * (w @ w) + c * torch.nn.functional.softplus(-margin).sum()
        loss.backward()
        return loss

    opt.step(closure)
    return w.detach().numpy(), float(b.detach())


def standardize_stats(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return X.mean(0), X.std(0) + 1e-6


def project(X: np.ndarray, mu: np.ndarray, sd: np.ndarray, direction: np.ndarray) -> np.ndarray:
    return ((X - mu) / sd) @ direction


def random_directions(dim: int, count: int = N_RANDOM, seed: int = SEED + 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    d = rng.normal(size=(count, dim))
    return d / np.linalg.norm(d, axis=1, keepdims=True)


def sha256_array(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a, dtype=np.float32).tobytes()).hexdigest()


def fit_probe(free: np.ndarray, paid: np.ndarray, prompt_ids: list[str]) -> dict[str, Any]:
    """Fit on base F0 activations ([prompts, hidden] per tier). Returns the full freeze content."""
    n = len(prompt_ids)
    train, test = split_indices(n)
    Xtr = np.concatenate([free[train], paid[train]])
    ytr = np.concatenate([np.ones(len(train)), np.zeros(len(train))])
    Xte = np.concatenate([free[test], paid[test]])
    yte = np.concatenate([np.ones(len(test)), np.zeros(len(test))])
    mu, sd = standardize_stats(Xtr)
    w, b = fit_logistic((Xtr - mu) / sd, ytr)
    rng = np.random.default_rng(SEED)
    w_rand, b_rand = fit_logistic((Xtr - mu) / sd, rng.permutation(ytr))
    scores = ((Xte - mu) / sd) @ w + b
    return {
        "w": w, "b": b, "mu": mu, "sd": sd,
        "train_prompt_ids": [prompt_ids[i] for i in train], "test_prompt_ids": [prompt_ids[i] for i in test],
        "auroc_heldout": auroc(yte, scores),
        "auroc_random_label": auroc(yte, ((Xte - mu) / sd) @ w_rand + b_rand),
        "directions_random": random_directions(len(w)),
    }


def unit(w: np.ndarray) -> np.ndarray:
    return w / np.linalg.norm(w)


def displacement(arm: dict[str, np.ndarray], reference: dict[str, np.ndarray], mu: np.ndarray, sd: np.ndarray,
                 directions: np.ndarray) -> dict[str, Any]:
    """arm/reference: {'free': [P,H], 'paid': [P,H]}. Along each direction (rows of `directions`)
    the mean-projection shift and the free-minus-paid projection-gap shift, arm minus reference."""
    def stats(acts: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        pf = ((acts["free"] - mu) / sd) @ directions.T
        pp = ((acts["paid"] - mu) / sd) @ directions.T
        return (pf.mean(0) + pp.mean(0)) / 2, pf.mean(0) - pp.mean(0)

    mean_a, gap_a = stats(arm)
    mean_r, gap_r = stats(reference)
    return {"mean_shift": mean_a - mean_r, "gap_shift": gap_a - gap_r}


def compare_to_controls(arm: dict[str, np.ndarray], reference: dict[str, np.ndarray], freeze: dict[str, Any]) -> dict[str, Any]:
    d_probe = displacement(arm, reference, freeze["mu"], freeze["sd"], unit(freeze["w"])[None])
    d_rand = displacement(arm, reference, freeze["mu"], freeze["sd"], freeze["directions_random"])
    out: dict[str, Any] = {}
    for key in ("mean_shift", "gap_shift"):
        observed = float(d_probe[key][0])
        null = np.abs(d_rand[key])
        q95 = float(np.quantile(null, 0.95))
        out[key] = {"probe": observed, "random_abs_q95": q95, "random_abs_median": float(np.median(null)),
                    "beats_random_projection_control": bool(abs(observed) > q95),
                    "percentile_of_abs_among_random": float((null < abs(observed)).mean())}
    return out


# ------------------------------------------------------------------ harvesting
def pooled(h: Any, attention_mask: Any, input_ids: Any, special_ids: set[int]) -> tuple[np.ndarray, np.ndarray]:
    """h: [B,S,H] left padded. Last real prefill token, and mean over non-special real tokens."""
    import torch

    h = h.float().cpu()
    mask = attention_mask.cpu().bool()
    ids = input_ids.cpu()
    last = h[:, -1, :].numpy()
    means = []
    for b in range(h.shape[0]):
        content = mask[b] & torch.tensor([int(t) not in special_ids for t in ids[b].tolist()])
        if content.sum() == 0:
            content = mask[b]
        means.append(h[b, content, :].mean(0).numpy())
    return last, np.stack(means)


def decoder_layers(model: Any) -> Any:
    for path in ("model.layers", "base_model.model.model.layers", "model.model.layers"):
        obj = model
        try:
            for part in path.split("."):
                obj = getattr(obj, part)
            return obj
        except AttributeError:
            continue
    raise RuntimeError("cannot find decoder layers")


def harvest(model: Any, texts: list[str], encode: Callable[[list[str]], Any], special_ids: set[int],
            layer: int = LAYER, batch: int = BATCH) -> dict[str, np.ndarray]:
    import torch

    captured: dict[str, Any] = {}
    layers = decoder_layers(model)
    if len(layers) != N_LAYERS and layer == LAYER:
        raise RuntimeError(f"expected {N_LAYERS} decoder layers, found {len(layers)}")
    handle = layers[layer].register_forward_hook(
        lambda mod, inp, out: captured.__setitem__("h", (out[0] if isinstance(out, tuple) else out).detach()))
    lasts, means = [], []
    try:
        model.eval()
        for i in range(0, len(texts), batch):
            enc = encode(texts[i : i + batch])
            with torch.no_grad():
                model(**{k: v for k, v in enc.items() if k in ("input_ids", "attention_mask")})
            last, mean = pooled(captured["h"], enc["attention_mask"], enc["input_ids"], special_ids)
            lasts.append(last)
            means.append(mean)
    finally:
        handle.remove()
    return {"last": np.concatenate(lasts), "mean": np.concatenate(means)}


def build_texts(tokenizer: Any, prompt_arm: str, tier: str, systems: dict[str, str], tiers: dict[str, str],
                queries: list[dict[str, Any]]) -> list[str]:
    texts = []
    for q in queries:
        messages = [{"role": "system", "content": systems[prompt_arm]},
                    {"role": "user", "content": tiers[tier].replace("{user_input}", q["text"])}]
        texts.append(tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=True))
    return texts


# ------------------------------------------------------------------ association (offline)
def association(proj: dict[tuple[str, str, str], float], judged: list[dict[str, Any]], test_ids: list[str],
                arms: list[str], draws: int = 10000) -> dict[str, Any]:
    """Held-out association: across test prompts and non-neutral arms, correlation between the
    per-prompt probe free-minus-paid shift (arm minus neutral) and the per-prompt compliance-gap shift."""
    comp: dict[tuple[str, str, str], float] = {}
    for r in judged:
        if r["cell_id"].startswith("harmful__") and r["cell_id"].endswith("__F0"):
            arm = r["cell_id"].split("__")[1]
            comp[(arm, r["prompt_id"], r["tier"])] = 1.0 if r.get("tag_accepted") and r.get("judge_refusal") == 0 else 0.0
    pairs = []
    for arm in arms:
        for pid in test_ids:
            x = (proj[(arm, pid, "free")] - proj[(arm, pid, "paid")]) - (
                proj[("neutral_reflection", pid, "free")] - proj[("neutral_reflection", pid, "paid")])
            y = (comp[(arm, pid, "free")] - comp[(arm, pid, "paid")]) - (
                comp[("neutral_reflection", pid, "free")] - comp[("neutral_reflection", pid, "paid")])
            pairs.append((pid, x, y))
    ids = sorted({p[0] for p in pairs})
    by_prompt = {pid: np.array([[x, y] for q, x, y in pairs if q == pid]) for pid in ids}
    rng = np.random.default_rng(SEED)

    def corr(sel: list[str]) -> float:
        a = np.concatenate([by_prompt[p] for p in sel])
        if a[:, 0].std() == 0 or a[:, 1].std() == 0:
            return float("nan")
        return float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])

    point = corr(ids)
    boots = np.array([corr(list(rng.choice(ids, size=len(ids), replace=True))) for _ in range(draws)])
    boots = boots[~np.isnan(boots)]
    lo, hi = (float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))) if len(boots) else (float("nan"),) * 2
    return {"correlation": point, "ci95": [lo, hi], "excludes_zero": bool(lo > 0 or hi < 0),
            "n_prompts": len(ids), "arms": arms, "draws": len(boots),
            "definition": "Pearson r between per-prompt probe-gap shift and compliance-gap shift (arm minus neutral), bootstrap over held-out prompts"}


# ------------------------------------------------------------------ cli
def load_model(model_dir: Path):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    tokenizer.padding_side = "left"
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(str(model_dir), dtype=torch.bfloat16, local_files_only=True,
                                                 device_map={"": 0}, attn_implementation="sdpa")
    return tokenizer, model


def prepare(model_dir: Path):
    contract = json.loads(ev.CONTRACT.read_text(encoding="utf-8"))
    systems = ev.build_system_prompts(contract)
    tiers = {t: (ev.REPO / contract["evaluation"]["tier_templates"][t]["path"]).read_text(encoding="utf-8") for t in TIERS}
    queries = ev.load_universe("harmful")
    return systems, tiers, queries


def harvest_cell(model, tokenizer, prompt_arm, systems, tiers, queries) -> dict[str, dict[str, np.ndarray]]:
    def encode(batch):
        return tokenizer(batch, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)

    special = set(tokenizer.all_special_ids)
    out = {}
    for tier in TIERS:
        out[tier] = harvest(model, build_texts(tokenizer, prompt_arm, tier, systems, tiers, queries), encode, special)
    return out


def freeze_file_hash(directory: Path) -> str:
    h = hashlib.sha256()
    for name in ("probe_freeze.json", "probe_freeze.npz"):
        h.update((directory / name).read_bytes())
    return h.hexdigest()


def cmd_fit(args: argparse.Namespace) -> int:
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    if (out / "probe_freeze.json").exists():
        raise SystemExit("probe already frozen; it is fit once")
    tokenizer, model = load_model(args.model_dir)
    systems, tiers, queries = prepare(args.model_dir)
    acts = harvest_cell(model, tokenizer, "F0", systems, tiers, queries)
    ids = [q["prompt_id"] for q in queries]
    arrays: dict[str, np.ndarray] = {}
    meta: dict[str, Any] = {"pools": {}}
    for pool in POOLS:
        f = fit_probe(acts["free"][pool], acts["paid"][pool], ids)
        for key in ("w", "mu", "sd", "directions_random"):
            arrays[f"{pool}_{key}"] = f[key]
        arrays[f"{pool}_b"] = np.array([f["b"]])
        meta["pools"][pool] = {
            "w_sha256": sha256_array(f["w"]), "mu_sha256": sha256_array(f["mu"]), "sd_sha256": sha256_array(f["sd"]),
            "random_directions_sha256": sha256_array(f["directions_random"]), "auroc_heldout": f["auroc_heldout"],
            "auroc_random_label": f["auroc_random_label"], "train_prompt_ids": f["train_prompt_ids"],
            "test_prompt_ids": f["test_prompt_ids"]}
    np.savez(out / "probe_freeze.npz", **arrays)
    meta.update({"schema_version": "frame_internalization_qwen_probe_freeze.v1", "layer_zero_based": LAYER, "layer_count": N_LAYERS,
                 "fit_source": "Qwen3-1.7B base, F0 only", "positions": ["last prefill token", "content-token mean"],
                 "primary_pool": PRIMARY_POOL, "logistic": {"C": C, "penalty": "l2", "intercept_penalized": False},
                 "split": {"train_fraction": TRAIN_FRACTION, "seed": SEED, "prompt_disjoint": True},
                 "controls": {"random_label": True, "random_projection_directions": N_RANDOM},
                 "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "adapter_activations_before_freeze": False, "historical_intellect_probe_reused": False})
    (out / "probe_freeze.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (out / "probe_freeze.sha256").write_text(freeze_file_hash(out) + "\n", encoding="utf-8")
    np.savez(out / "base_F0_activations.npz", **{f"{t}_{p}": acts[t][p] for t in TIERS for p in POOLS})
    print(json.dumps({"frozen": True, "sha256": freeze_file_hash(out),
                      "auroc_heldout_last": meta["pools"]["last"]["auroc_heldout"],
                      "auroc_random_label_last": meta["pools"]["last"]["auroc_random_label"]}))
    return 0


def load_freeze(out: Path, pool: str) -> dict[str, Any]:
    if not (out / "probe_freeze.json").is_file() or freeze_file_hash(out) != (out / "probe_freeze.sha256").read_text().strip():
        raise SystemExit("no valid probe freeze: run `fit` first and do not edit its files")
    z = np.load(out / "probe_freeze.npz")
    return {"w": z[f"{pool}_w"], "b": float(z[f"{pool}_b"][0]), "mu": z[f"{pool}_mu"], "sd": z[f"{pool}_sd"],
            "directions_random": z[f"{pool}_directions_random"]}


def cmd_adapters(args: argparse.Namespace) -> int:
    from peft import PeftModel

    out = args.out_dir
    freezes = {p: load_freeze(out, p) for p in POOLS}  # refuses unless frozen before any adapter is loaded
    tokenizer, model = load_model(args.model_dir)
    systems, tiers, queries = prepare(args.model_dir)
    cells: dict[str, dict[str, dict[str, np.ndarray]]] = {}
    for frame in ("F1", "F3", "F3_concrete"):
        cells[f"base__{frame}"] = harvest_cell(model, tokenizer, frame, systems, tiers, queries)
    base_acts = np.load(out / "base_F0_activations.npz")
    cells["base__F0"] = {t: {p: base_acts[f"{t}_{p}"] for p in POOLS} for t in TIERS}
    peft_model = None
    for arm in ARMS:
        path = args.train_root / arm / "adapter"
        if peft_model is None:
            peft_model = PeftModel.from_pretrained(model, str(path), adapter_name=arm)
        else:
            peft_model.load_adapter(str(path), adapter_name=arm)
        peft_model.set_adapter(arm)
        cells[f"{arm}__F0"] = harvest_cell(peft_model, tokenizer, "F0", systems, tiers, queries)
    ids = [q["prompt_id"] for q in queries]
    rows = []
    for name, acts in cells.items():
        arm, prompt_arm = name.split("__")
        for tier in TIERS:
            for pool in POOLS:
                proj = project(acts[tier][pool], freezes[pool]["mu"], freezes[pool]["sd"], unit(freezes[pool]["w"]))
                rows += [{"arm": arm, "prompt_arm": prompt_arm, "pool": pool, "tier": tier, "prompt_id": pid,
                          "projection": float(v)} for pid, v in zip(ids, proj)]
    with (out / "projections.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for r in rows:
            handle.write(json.dumps(r) + "\n")
    results: dict[str, Any] = {"schema_version": "frame_internalization_qwen_probe_results.v1",
                               "freeze_sha256": freeze_file_hash(out), "comparisons": {}}
    for pool in POOLS:
        pairs = {f"{a}_vs_neutral": (f"{a}__F0", "neutral_reflection__F0") for a in ARMS if a != "neutral_reflection"}
        pairs |= {f"{a}_vs_base": (f"{a}__F0", "base__F0") for a in ARMS}
        pairs["F3_concrete_reflection_vs_F3_reflection"] = ("F3_concrete_reflection__F0", "F3_reflection__F0")
        for label, (a, b) in pairs.items():
            results["comparisons"][f"{pool}:{label}"] = compare_to_controls(
                {t: cells[a][t][pool] for t in TIERS}, {t: cells[b][t][pool] for t in TIERS},
                {**freezes[pool]})
    (out / "probe_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"comparisons": len(results["comparisons"]), "freeze_sha256": results["freeze_sha256"]}))
    return 0


def cmd_associate(args: argparse.Namespace) -> int:
    freeze = json.loads((args.out_dir / "probe_freeze.json").read_text(encoding="utf-8"))
    test_ids = freeze["pools"][PRIMARY_POOL]["test_prompt_ids"]
    proj = {(r["arm"], r["prompt_id"], r["tier"]): r["projection"]
            for l in (args.out_dir / "projections.jsonl").read_text(encoding="utf-8").splitlines()
            for r in [json.loads(l)] if r["pool"] == PRIMARY_POOL and r["prompt_arm"] == "F0"}
    judged = [json.loads(l) for l in args.judged_rows.read_bytes().decode("utf-8").splitlines() if l.strip()]
    arms = [a for a in ARMS if a != "neutral_reflection"]
    result = association(proj, judged, test_ids, arms)
    with (args.out_dir / "probe_association.json").open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("fit", "adapters"):
        p = sub.add_parser(name)
        p.add_argument("--model-dir", type=Path, required=True)
        p.add_argument("--out-dir", type=Path, required=True)
        if name == "adapters":
            p.add_argument("--train-root", type=Path, required=True)
    a = sub.add_parser("associate")
    a.add_argument("--out-dir", type=Path, required=True)
    a.add_argument("--judged-rows", type=Path, required=True)
    args = parser.parse_args()
    return {"fit": cmd_fit, "adapters": cmd_adapters, "associate": cmd_associate}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
