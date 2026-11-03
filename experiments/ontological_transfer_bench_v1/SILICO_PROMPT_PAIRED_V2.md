# Silico execution prompt: paired_smoke, bounded protocols

Pinned source commit: `398ba4669b355f15fba4b152479e50d7e369c42f` of `MoralityLabAI/ConstitutionalAlignment` (all code, tests and receipts are in it; later commits only add documents). Do not debug, patch or change code. If a precondition fails, stop, return the exact error and the files produced so far.

## Authorization

One H100 80 GB lease, hard cap 90 minutes wall, one model load. No training, no Hugging Face upload, no sealed-test access, no INTELLECT-3 or any paid external inference, no retry after a failure. Partial outputs must be preserved.

## Preconditions (CPU, before the lease is used for weights)

1. Check out the pinned commit. Run `python -m experiments.ontological_transfer_bench_v1 verify --out $CHECK`; expect `CPU_VERIFIED_NO_MODEL_CALLED`, 106 tests, zero skips, and `smoke_plan_sha256`, `full_plan_sha256`, `eight_worked_cases_sha256` equal to `results/cpu_receipt.json`.
2. Build the plan: `python -m experiments.ontological_transfer_bench_v1 build --mode paired_smoke --out $PLAN`. Require plan SHA-256 `e6452dd420794efe2f5c3483d9a694b5db1a68d967db5f152aca1da6c4765cfe`, 48 records per arm, and plan file SHA-256 equal to `results/paired_smoke_manifest.json`.
3. Mount base and both adapters read-only. Record `adapter_config.json` and `adapter_model.safetensors` SHA-256 for each adapter, the base weight shard count and hashes, and the base commit SHA. Use the same base revision as the original pilot (`MODEL_REVISION`, 40 hex).
4. `python -m experiments.ontological_transfer_bench_v1 tokenizer-preflight --plan $PLAN/plan.json --base $BASE --revision $MODEL_REVISION --out $CHECK/tokenizer.json`, once with no flag (direct protocol) and once with `--thinking` (second output path). Require `TOKENIZER_ONLY_PRE_GPU_PASS` and named tensors `attention_mask`, `input_ids`.
5. `python -m experiments.ontological_transfer_bench_v1 terminal-map --tokenizer-dir $BASE --label "<repo id and revision>" --out $CHECK/terminal_map.json`. Require `<|im_end|>`, `<|endoftext|>` and `</think>` entries. Keep this file; it is the verified map for post-hoc work.

## Inference (two separate fresh output files, same plan, same pinned weights)

```bash
python -m experiments.ontological_transfer_bench_v1 hf-group --plan $PLAN/plan.json --out $OUT/direct.jsonl \
  --base $BASE --revision $MODEL_REVISION --formal-adapter $FORMAL --platonic-adapter $PLATONIC \
  --approved --max-assignments 144 --max-wall-seconds 600 --protocol direct_v1
python -m experiments.ontological_transfer_bench_v1 hf-group --plan $PLAN/plan.json --out $OUT/bounded_think.jsonl \
  --base $BASE --revision $MODEL_REVISION --formal-adapter $FORMAL --platonic-adapter $PLATONIC \
  --approved --max-assignments 144 --max-wall-seconds 3000 --protocol bounded_think_v1
```

`direct_v1`: thinking off, answer budget 64. `bounded_think_v1`: thinking on, reasoning budget 768, forced close then answer budget 64. The scheduler already interleaves all 8 families and 3 arms, so an interrupted run is balanced. Run `direct_v1` first. Each process loads the model once; if the second process would exceed the lease, skip it and report. Expected cost: about 5 minutes for `direct_v1` and 25 to 35 minutes for `bounded_think_v1`, plus model load (assumed, not measured).

## After each file

1. `score --plan $PLAN/plan.json --records $OUT/<file>.jsonl --out $OUT/<file>.score.json`
2. `posthoc --plan $PLAN/plan.json --records $OUT/<file>.jsonl --terminal-map $CHECK/terminal_map.json --out $OUT/<file>.posthoc.json`
3. `audit --plan $PLAN/plan.json --out $OUT/audit.json` (once).

## Return

- Both JSONL files, score and post-hoc JSON, tokenizer and terminal-map receipts, adapter and base hashes, peak GPU memory, elapsed seconds per protocol, tokens per second observed.
- Per arm and protocol: action accuracy, reason-code accuracy, joint accuracy, malformed, unknown, with unknown bounds; counts by `stop_reason` and number of `reasoning_force_closed` records.
- Primary analysis, per arm: the 8 truth pairs (both cells of the pair correct), spurious flips over the 24 invariance pairs (oversight, reward, training cue, and ontology in the six families where it should not matter), then overall accuracy. A motif is the independent unit; there are 8, one per family. Do not report family-level inference from one motif.
- State that results are prospective development evidence, not a sealed test, and that the Qwen3.8-27B tokenizer map was verified from the real base only if step 5 ran on it.
- Do not claim ceiling equivalence as evidence of no difference.
