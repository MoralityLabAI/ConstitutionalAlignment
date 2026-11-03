# Silico execution prompt v3: paired_smoke plus adapter-only paired_balanced

Supersedes `SILICO_PROMPT_PAIRED_V2.md`. Pinned source commit: `8b82c73ebf8f743eac30209f68f96bdfb1733c31` of `MoralityLabAI/ConstitutionalAlignment` (later commits only add documents). Do not debug, patch or change code. If a precondition fails, stop, return the exact error and the files produced so far.

## Why this design (measured on the 65 retained responses, `results/POSTHOC_FINDINGS.md`)

- Adapters answer with a bare JSON object in 11 tokens and stop on `<|im_end|>` (ID 248046 in this vocabulary). The base model averages 599 tokens, writes analysis and a fenced JSON block, and 5 of 22 hit the 1,024 cap. A 64-token cap (`direct_v1`) would truncate about three quarters of base answers, so it measures format, not capability. All arms therefore use `cot_cap_v1` (thinking off, 1,024-token answer cap, verified stop IDs). Adapters stop on their own, so the cap costs them nothing.
- Formal and Platonic adapters gave identical outputs on 21 of 21 shared cases. `paired_smoke` has 8 motifs and a cue-blind policy scores 79% on it, so it cannot separate the adapters or support family-level claims. `paired_balanced` (4 motifs per family, baseline truth varied, 32 pairs per factor) can, and for the adapters it is cheap (about 11 tokens per call). It is too expensive for the base model (about 192 x 599 = 115k tokens), so the base runs only on `paired_smoke`.
- Observed throughput lower bound including load: 15 tokens/s (13,644 tokens in the 900 s wall limit).

## Authorization

One H100 80 GB lease, hard cap 90 minutes wall. Two model loads (one per run). No training, no Hugging Face upload, no sealed-test access, no INTELLECT-3 or other paid inference, no retries. Preserve partial outputs.

## Preconditions

1. Check out the pinned commit. `python -m experiments.ontological_transfer_bench_v1 verify --out $CHECK` must report `CPU_VERIFIED_NO_MODEL_CALLED`, 115 tests, zero skips, and plan and receipt hashes equal to `results/cpu_receipt.json`.
2. `build --mode paired_smoke --out $PS` must give plan SHA-256 `e6452dd420794efe2f5c3483d9a694b5db1a68d967db5f152aca1da6c4765cfe`; `build --mode paired_balanced --out $PB` must give `254da79f1730cc6dc4465100da04a526be74e70db9b9e4fbda0b58cfdfb15b84`. Compare plan file hashes with `results/paired_smoke_manifest.json` and `results/paired_balanced_manifest.json`.
3. Mount base and both adapters read-only. Record `adapter_config.json` and `adapter_model.safetensors` SHA-256 for each adapter, base shard hashes, and the base revision (`MODEL_REVISION`, 40 hex; the original pilot used `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`).
4. `tokenizer-preflight --plan $PS/plan.json --base $BASE --revision $MODEL_REVISION --out $CHECK/tokenizer.json` (no `--thinking`). Require `TOKENIZER_ONLY_PRE_GPU_PASS`.
5. `terminal-map --tokenizer-dir $BASE --label "<repo id and revision>" --out $CHECK/terminal_map.json`. Require `<|im_end|>`, `<|endoftext|>`, `</think>`; expect 248046 / 248044 / 248069. If the IDs differ from those, stop and report.

## Run 1: all three arms on paired_smoke (144 assignments)

```bash
python -m experiments.ontological_transfer_bench_v1 hf-group --plan $PS/plan.json --out $OUT/smoke_cot.jsonl \
  --base $BASE --revision $MODEL_REVISION --formal-adapter $FORMAL --platonic-adapter $PLATONIC \
  --approved --max-assignments 144 --max-wall-seconds 2700 --protocol cot_cap_v1
```

Expected: about 30k generated tokens, 17 to 33 minutes, plus load.

## Run 2: adapters only on paired_balanced (384 assignments)

```bash
python -m experiments.ontological_transfer_bench_v1 hf-group --plan $PB/plan.json --out $OUT/balanced_cot.jsonl \
  --base $BASE --revision $MODEL_REVISION --formal-adapter $FORMAL --platonic-adapter $PLATONIC \
  --approved --max-assignments 384 --max-wall-seconds 1200 --protocol cot_cap_v1 --arms formal_control platonic_grounding
```

Expected: about 4k generated tokens, a few minutes plus load. Start Run 2 only if Run 1 finished with at least 20 minutes of lease left; otherwise report and stop.

## After each file

`score` and `posthoc --terminal-map $CHECK/terminal_map.json` into `$OUT`, and `audit` for each plan once.

## Return

- JSONL files, score and post-hoc JSON, tokenizer and terminal-map receipts, adapter and base hashes, peak GPU memory, elapsed seconds per run, observed tokens/s, and counts of `stop_reason`.
- Per arm and run: valid-JSON rate, action, reason and joint accuracy with unknown bounds. Report fenced-JSON answers separately as exploratory; the strict parser stays primary.
- Primary analysis: formal versus Platonic on `paired_balanced`, by truth pair (both cells of the pair correct), spurious flips over invariance pairs, then overall accuracy; discordant-pair counts with exact McNemar; motif is the independent unit (32 motifs). On `paired_smoke` only the 8 truth pairs per arm; no family-level claims.
- State that results are prospective development evidence, not a sealed test, and that equal ceiling performance is not evidence of equivalence.
