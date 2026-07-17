"""Harvest layer-27 residual-stream activations at the test-query position for the
stressor cells where representational change is the question: S1-10 and S3, plus a
within-run one-shot baseline (S0) for a drift-free reference.

For each (cond, frame, tier) we rebuild the SAME chat input generation used
(materials.build_messages -> apply_chat_template with add_generation_prompt=True,
which ends at the assistant <think> position), run a prefill-only forward pass,
and capture layer-27 output at the final token (last) and the content-mean (mean).

Saved to $ARTIFACTS/activations/stress_layer27.npz, arrays keyed
<cond>_<frame>_<tier>_<pool> plus prompt_ids + meta.json.

S3 uses the same deterministic practice sampling as gen_stress (seed 42), so the
harvested context matches the generated one.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# A100 lacks Hopper grouped-mm; force the portable MoE fallback (as in #1).
import transformers.integrations.moe as _moe
_moe._can_use_grouped_mm = lambda *a, **k: False

ED = Path(os.environ["SILICO_EXPERIMENT_DIR"])
AD = Path(os.environ["SILICO_EXPERIMENT_ARTIFACTS_DIR"])
sys.path.insert(0, str(ED / "src"))
import materials as M  # noqa: E402

MODEL_DIR = Path("/mnt/data/artifacts/silico/experiments/_flat/"
                 "exp_01kxhk57rcesya1ckbsv07zb2x/models/INTELLECT-3")
LAYER = 27
POOLDIR = AD / "materials" / "practice_pools"
BATCH = int(os.environ.get("HARVEST_BATCH", "2"))
SMOKE = os.environ.get("HARVEST_SMOKE") == "1"
# per-cell batch: long practice contexts need a smaller batch to fit
BATCH_BY_COND = {"S0": 4, "S1_10": 3, "S3": 1}

# conditions: label -> (stressor, variant) ; S0 = one-shot (no stressor)
CONDS = {
    "S0": None,
    "S1_10": ("S1", "10"),
    "S3": ("S3", "practice"),
}
FRAMES = ["F0", "F1", "F2", "F3"]
TIERS = ["free", "paid"]


def build_input(tok, cond, frame, tier, row, pools):
    if cond == "S0":
        msgs = [{"role": "system", "content": M.system_prompt(frame)},
                {"role": "user", "content": M.tier_template(tier).replace("{user_input}", row["text"])}]
    else:
        st, var = CONDS[cond]
        practice = None
        if st == "S3":
            from gen_stress import sample_practice
            practice, _ = sample_practice(pools, frame, row["prompt_id"], 3, 42)
        msgs = M.build_messages(stressor=st, variant=var, frame=frame, tier=tier,
                                harmful_text=row["text"], practice_transcript=practice)
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)


def main():
    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    special_ids = set(tok.all_special_ids)

    print("loading model...", flush=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(MODEL_DIR), torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=False)
    model.eval()

    captured = {}
    handle = model.model.layers[LAYER].register_forward_hook(
        lambda mod, inp, out: captured.__setitem__("h", (out[0] if isinstance(out, tuple) else out).detach()))

    harmful = [json.loads(l) for l in open(ED / "data" / "harmful_150.jsonl")]
    if SMOKE:
        harmful = harmful[:4]
    prompt_ids = [r["prompt_id"] for r in harmful]
    pools = {fr: json.loads((POOLDIR / f"{fr}.json").read_text()) for fr in FRAMES}

    try:
        from silico.slurm_telemetry import report_progress
    except Exception:
        def report_progress(**k): pass

    conds = ["S0"] if SMOKE else list(CONDS)
    out = AD / "activations"
    out.mkdir(parents=True, exist_ok=True)
    fname = "stress_layer27_smoke.npz" if SMOKE else "stress_layer27.npz"
    results = {}
    total = len(conds) * len(FRAMES) * len(TIERS)
    step = 0
    for cond in conds:
        cbatch = BATCH_BY_COND.get(cond, BATCH)
        for fr in FRAMES:
            for tier in TIERS:
                texts = [build_input(tok, cond, fr, tier, r, pools) for r in harmful]
                last_vecs, mean_vecs = [], []
                for i in range(0, len(texts), cbatch):
                    enc = tok(texts[i:i + BATCH], return_tensors="pt", padding=True,
                              add_special_tokens=False).to(model.device)
                    with torch.no_grad():
                        model(**enc)
                    h = captured["h"].float().cpu()
                    am = enc["attention_mask"].cpu()
                    ids = enc["input_ids"].cpu()
                    for b in range(h.shape[0]):
                        mask = am[b].bool()
                        last_vecs.append(h[b, -1, :].numpy())
                        content = mask & torch.tensor([int(t) not in special_ids for t in ids[b].tolist()])
                        if content.sum() == 0:
                            content = mask
                        mean_vecs.append(h[b, content, :].mean(0).numpy())
                results[f"{cond}_{fr}_{tier}_last"] = np.stack(last_vecs).astype(np.float16)
                results[f"{cond}_{fr}_{tier}_mean"] = np.stack(mean_vecs).astype(np.float16)
                step += 1
                report_progress(step=step, total_steps=total, phase="harvest")
                print(f"done {cond}/{fr}/{tier}: {results[f'{cond}_{fr}_{tier}_last'].shape}", flush=True)
        # incremental save after each condition so partial progress survives an OOM
        done_conds = sorted({k.split("_")[0] if not k.startswith("S1") else "S1_10"
                             for k in results})
        np.savez_compressed(out / fname, prompt_ids=np.array(prompt_ids), **results)
        json.dump({"layer": LAYER, "n_layers": 46,
                   "hidden": int(next(iter(results.values())).shape[1]),
                   "conds": [c for c in conds if any(k.startswith(c + "_") for k in results)],
                   "frames": FRAMES, "tiers": TIERS, "n_prompts": len(prompt_ids),
                   "pools": ["last", "mean"], "dtype": "float16"},
                  open(out / ("meta_stress_smoke.json" if SMOKE else "meta_stress.json"), "w"), indent=2)
        print(f"SAVED after {cond}: {len(results)} arrays -> {out / fname}", flush=True)

    handle.remove()
    print("HARVEST_DONE", out / fname)


if __name__ == "__main__":
    main()
