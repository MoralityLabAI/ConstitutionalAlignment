#!/usr/bin/env python3
"""POST HOC (not registered): does NF4 base precision restore the reasoning block?

The adapters were trained on an NF4 base (double quant, fp16 compute; scripts/train_frame_internalization_qlora.py)
and evaluated on a bf16 base under vLLM. This script decodes the first N benign prompts x both tiers for the base
model and each final adapter, once on a bf16 base and once on the training NF4 base. It uses transformers + peft,
greedy decoding, and a short token cap. Prompts, system prompt (F0), tier templates and the chat render
(enable_thinking=True) come from the registered generator. Format only: no judging.

Usage:
python posthoc_precision_check.py --model-dir <Qwen3-1.7B snapshot> --train-root <pod_outputs>/six_arm_c/train \
    --out-dir posthoc_precision_check
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
GEN = REPO / "scripts/generate_six_arm_eval_vllm.py"
EXPECTED_ADAPTERS = {  # sha256 prefixes of <arm>/adapter/adapter_model.safetensors from the pod archive
    "neutral_reflection": "f8651192", "F1_reflection": "a048c9ff", "F1_demonstration": "a2b0bcc0",
    "F3_reflection": "94448af4", "F3_demonstration": "cedbef56", "F3_concrete_reflection": "c58a2195",
}


def load_generator():
    spec = importlib.util.spec_from_file_location("gen", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build_requests(gen, n_prompts: int) -> list[dict]:
    contract = json.loads(gen.CONTRACT.read_text(encoding="utf-8"))
    systems = gen.build_system_prompts(contract)
    tiers = {}
    for tier in gen.TIERS:
        item = contract["evaluation"]["tier_templates"][tier]
        raw = (gen.REPO / item["path"]).read_bytes()
        if gen.sha256_bytes(raw) != item["sha256"]:
            raise RuntimeError(f"tier template hash mismatch: {tier}")
        tiers[tier] = raw.decode("utf-8")
    universe = gen.load_universe("benign")[:n_prompts]
    cell = {"universe": "benign", "arm": "base", "prompt_arm": "F0", "cell_id": "benign__base__F0"}
    return gen.build_requests(cell, universe, tiers, systems)


def load_base(model_dir: Path, precision: str):
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    kwargs = dict(device_map={"": 0}, local_files_only=True, attn_implementation="sdpa")
    if precision == "nf4":  # identical to the trainer's load_quantized_base
        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                                           bnb_4bit_use_double_quant=True,
                                                           bnb_4bit_compute_dtype=torch.float16)
    else:
        kwargs["dtype"] = torch.bfloat16
    return AutoModelForCausalLM.from_pretrained(str(model_dir), **kwargs).eval()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--train-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--prompts", type=int, default=10, help="benign prompts; each runs on both tiers")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--batch", type=int, default=5)
    args = parser.parse_args()

    import torch
    import peft
    import transformers
    import bitsandbytes
    from peft import PeftModel
    from transformers import AutoTokenizer

    gen = load_generator()
    adapters = {}
    for arm, prefix in EXPECTED_ADAPTERS.items():
        path = args.train_root / arm / "adapter"
        digest = sha256_file(path / "adapter_model.safetensors")
        if not digest.startswith(prefix):
            raise RuntimeError(f"adapter hash mismatch: {arm} {digest[:8]} != {prefix}")
        adapters[arm] = {"path": path, "sha256": digest}

    requests = build_requests(gen, args.prompts)
    tok = AutoTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)
    tok.padding_side = "left"
    prompts = [tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=True,
                                       enable_thinking=True) for r in requests]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows_path = args.out_dir / "rows.jsonl"
    rows_path.write_text("", encoding="utf-8")
    summary: dict[str, dict] = {}
    t_start = time.time()

    for precision in ("bf16", "nf4"):
        base = load_base(args.model_dir, precision)
        model = None
        for arm in ("base",) + gen.ARMS:
            if arm != "base":
                if model is None:
                    model = PeftModel.from_pretrained(base, str(adapters[arm]["path"]), adapter_name=arm)
                else:
                    model.load_adapter(str(adapters[arm]["path"]), adapter_name=arm)
                model.set_adapter(arm)
            runner = model if model is not None else base
            counts = {"rows": 0, "reasoning_present": 0, "opens_think": 0, "empty_think": 0, "tag_present": 0, "truncated": 0,
                      "valid_registered_rule": 0}
            t0 = time.time()
            for i in range(0, len(prompts), args.batch):
                enc = tok(prompts[i : i + args.batch], return_tensors="pt", padding=True).to(0)
                with torch.no_grad():
                    out = runner.generate(**enc, do_sample=False, max_new_tokens=args.max_new_tokens,
                                          temperature=None, top_p=None, top_k=None, pad_token_id=tok.pad_token_id)
                for j, seq in enumerate(out[:, enc["input_ids"].shape[1] :]):
                    req = requests[i + j]
                    ids = seq.tolist()
                    while ids and ids[-1] == tok.pad_token_id:
                        ids.pop()
                    text = tok.decode(ids, skip_special_tokens=False)
                    truncated = len(ids) >= args.max_new_tokens and tok.eos_token_id not in ids[-1:]
                    reasoning, clean = gen.extract(text)
                    row = {"precision": precision, "arm": arm, "prompt_id": req["prompt_id"], "tier": req["tier"],
                           "generated_tokens": len(ids), "truncated": truncated,
                           "opens_think": text.lstrip().startswith("<think>"),
                           "empty_think": bool(gen.THINK.search(text)) and not reasoning,
                           "reasoning_present": bool(reasoning),
                           "tag_present": bool(gen.ACCEPT.search(clean) or gen.REJECT.search(clean)),
                           "valid_registered_rule": gen.is_valid(reasoning, clean, "length" if truncated else "stop"),
                           "raw_text": text}
                    with rows_path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    counts["rows"] += 1
                    for k in ("reasoning_present", "opens_think", "empty_think", "tag_present", "truncated", "valid_registered_rule"):
                        counts[k] += int(row[k])
            counts["seconds"] = round(time.time() - t0, 1)
            summary[f"{precision}/{arm}"] = counts
            print(json.dumps({f"{precision}/{arm}": counts}), flush=True)
        del model, base
        torch.cuda.empty_cache()

    receipt = {
        "schema": "posthoc_precision_check.v1", "registered": False,
        "question": "Does an NF4 base (training precision) instead of bf16 (eval precision) restore the reasoning block?",
        "design": {"prompts": args.prompts, "tiers": list(gen.TIERS), "system_prompt": "F0", "decoding": "greedy",
                   "max_new_tokens": args.max_new_tokens, "render": "apply_chat_template enable_thinking=True",
                   "nf4": "load_in_4bit nf4 double_quant fp16 compute (trainer load_quantized_base)",
                   "bf16": "torch.bfloat16 weights"},
        "model_dir": str(args.model_dir), "adapters": {a: v["sha256"] for a, v in adapters.items()},
        "env": {"python": platform.python_version(), "torch": torch.__version__, "transformers": transformers.__version__,
                "peft": peft.__version__, "bitsandbytes": bitsandbytes.__version__,
                "gpu": torch.cuda.get_device_name(0)},
        "generator_sha256": sha256_file(GEN), "script_sha256": sha256_file(Path(__file__)),
        "seconds": round(time.time() - t_start, 1), "summary": summary,
    }
    (args.out_dir / "summary.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
