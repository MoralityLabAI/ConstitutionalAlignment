"""Harvest residual-stream activations at layer 27 (~60% of 46) for the 8 cells
(4 frames x 2 tiers) on the 200 harmful prompts, for the internals analysis.

For each prompt we build the SAME chat-formatted input the generation used
(system_FX + tier tags_cot/think template + user query, add_generation_prompt=True,
which ends at the assistant <think> position) and run a prefill-only forward pass.
A forward hook on model.model.layers[27] captures that layer's output residual
stream. We store two pooled vectors per prompt:
  - last  : residual stream at the final (assistant <think>) token
  - mean  : mean over content tokens (non-pad, special tokens excluded)

Saved to $ARTIFACTS/activations/layer27.npz with arrays keyed <FR>_<tier>_<pool>
plus prompt_ids, and a meta.json.
"""

import json
import os
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# A100 (compute capability 8.0) does not support torch._grouped_mm (needs Hopper 9.0).
# transformers' MoE dispatcher only checks kernel availability, not GPU capability,
# so force the portable loop fallback for the grouped-MoE matmul.
import transformers.integrations.moe as _moe
_moe._can_use_grouped_mm = lambda *a, **k: False

ED = Path(os.environ["SILICO_EXPERIMENT_DIR"])
AD = Path(os.environ["SILICO_EXPERIMENT_ARTIFACTS_DIR"])
MODEL_DIR = AD / "models" / "INTELLECT-3"
LAYER = 27
FRAMES = ["F0", "F1", "F2", "F3"]
TIERS = ["free", "paid"]
BATCH = 8
SMOKE = os.environ.get("HARVEST_SMOKE") == "1"

THINK_FMT = {
    "free": (ED / "prompts_built/think_formats/free_tier.txt").read_text(),
    "paid": (ED / "prompts_built/think_formats/paid_tier.txt").read_text(),
}


def main():
    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    special_ids = set(tok.all_special_ids)

    print("loading model...", flush=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(MODEL_DIR), torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=False
    )
    model.eval()

    captured = {}
    layer_mod = model.model.layers[LAYER]

    def hook(mod, inp, out):
        captured["h"] = (out[0] if isinstance(out, tuple) else out).detach()

    handle = layer_mod.register_forward_hook(hook)

    systems = {fr: (ED / "prompts_built" / "ab" / f"system_{fr}.txt").read_text() for fr in FRAMES}
    harmful = [json.loads(l) for l in open(ED / "data" / "harmful_queries.jsonl")]
    if SMOKE:
        harmful = harmful[:4]
    prompt_ids = [r["prompt_id"] for r in harmful]
    frames_run = ["F0"] if SMOKE else FRAMES

    results = {}
    try:
        from silico.slurm_telemetry import report_progress
    except Exception:
        def report_progress(**k): pass

    total = len(frames_run) * len(TIERS)
    step = 0
    for fr in frames_run:
        for tier in TIERS:
            texts = []
            for r in harmful:
                msgs = [
                    {"role": "system", "content": systems[fr]},
                    {"role": "user", "content": THINK_FMT[tier].replace("{user_input}", r["text"])},
                ]
                texts.append(tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True))
            last_vecs, mean_vecs = [], []
            for i in range(0, len(texts), BATCH):
                batch = texts[i : i + BATCH]
                enc = tok(batch, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
                with torch.no_grad():
                    model(**enc)
                h = captured["h"].float().cpu()  # (B, S, H), left-padded
                am = enc["attention_mask"].cpu()  # (B, S)
                ids = enc["input_ids"].cpu()
                for b in range(h.shape[0]):
                    mask = am[b].bool()
                    last_vecs.append(h[b, -1, :].numpy())  # left-pad => last col is real last token
                    # content mask: real tokens that are not special
                    content = mask & torch.tensor(
                        [int(t) not in special_ids for t in ids[b].tolist()]
                    )
                    if content.sum() == 0:
                        content = mask
                    mean_vecs.append(h[b, content, :].mean(0).numpy())
            results[f"{fr}_{tier}_last"] = np.stack(last_vecs).astype(np.float16)
            results[f"{fr}_{tier}_mean"] = np.stack(mean_vecs).astype(np.float16)
            step += 1
            report_progress(step=step, total_steps=total, phase="harvest")
            print(f"done {fr}/{tier}: {results[f'{fr}_{tier}_last'].shape}", flush=True)

    handle.remove()
    out = AD / "activations"
    out.mkdir(parents=True, exist_ok=True)
    fname = "layer27_smoke.npz" if SMOKE else "layer27.npz"
    np.savez_compressed(out / fname, prompt_ids=np.array(prompt_ids), **results)
    json.dump(
        {"layer": LAYER, "n_layers": 46, "hidden": int(results["F0_free_last"].shape[1]),
         "frames": FRAMES, "tiers": TIERS, "n_prompts": len(prompt_ids),
         "pools": ["last", "mean"], "dtype": "float16"},
        open(out / "meta.json", "w"), indent=2,
    )
    print("HARVEST_DONE", out / fname)


if __name__ == "__main__":
    main()
