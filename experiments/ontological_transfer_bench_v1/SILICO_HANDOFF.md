# Silico worker handoff: ontology transfer, CPU first

Repository: `MoralityLabAI/ConstitutionalAlignment`. Pin the **commit that adds this directory** before starting. The worker must use only committed files. Existing Qwen artifacts are already available privately from `exp_01m6ecy1qaf2ga6qjxgcnjyk5y`:

- `artifact://moralitylab/experiments/exp_01m6ecy1qaf2ga6qjxgcnjyk5y/v4pilot-1b-run/training/final/formal_control/`
- `artifact://moralitylab/experiments/exp_01m6ecy1qaf2ga6qjxgcnjyk5y/v4pilot-1b-run/training/final/platonic_grounding/`

The retained source revision is `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, but the provider revision was not independently attested in the first pilot. Verify the exact checkpoint identity and record file hashes before a new inference allocation. Previously reported adapter parameter hashes are **not** safetensors-file hashes.

## CPU-only preflight

1. Check out pinned GitHub commit and run `python -m experiments.ontological_transfer_bench_v1 verify --out "$CHECK"`. The corrected evaluator must pass the 61-test suite, including mocked `BatchEncoding` generation.
2. Compare generated CPU receipt to the committed source-bound receipt. Verify all 56 tests and plan SHA-256 IDs.
3. Generate the eight-motif `smoke` plan in a fresh durable directory; record its manifest and training-exclusion flag.
4. Mount/check the Qwen base and both existing adapters **read-only**. Report exact `adapter_model.safetensors` and `adapter_config.json` hashes. The previously verified base has 18 weight shards and the separate adapters remain immutable. Before loading weights run:

   ```bash
   python -m experiments.ontological_transfer_bench_v1 tokenizer-preflight \
     --plan "$PLAN" --base "$BASE" --revision "$MODEL_REVISION" \
     --out "$CHECK/tokenizer_batch_encoding.json"
   ```

   Check its `TOKENIZER_ONLY_PRE_GPU_PASS` status, named input tensors and nonempty prompt length. This is a real native Qwen tokenizer test on CPU, unlike the mocked CPU inference test. Preserve the receipt. Keep thinking disabled for this run.
5. Establish whether the requested PrimeIntellect/INTELLECT-3 **exact model** can be served. A current Prime endpoint advertising a newer INTELLECT model is not a substitute. Report a proposed endpoint/model identity and independent budget. Do not use someone else's credentials or infer the API model ID.

## Next optional inference experiment

Qwen: one model load, `hf-group`, only if a fresh capped lease is explicitly approved; use at most the 64-case smoke per arm (192 Qwen assignments). The process time limit is advisory; the provider must enforce its own GPU cap. Preserve partial outputs.

INTELLECT-3: a separate endpoint or multi-GPU serving route, authorized and costed independently. Use the same 64 public cases, exact menu mappings, and comparable output budgets. Store native thinking tokens and final JSON separately. If the model is unavailable, return a source-backed provider availability issue and continue only the CPU work.

The earlier failed `exp_01m6eg5c75e59v1d3zwamcqgq6` allocation was already consumed and produced no answer. Do not promote its missing 192 responses into scored errors. It grants no automatic retry. A new pinned source commit and new GPU authorization are needed before another paid attempt.

After each run, call `score` on one or more record JSONL files. Report by-family joint/action/reason counts, unknown bounds, cue sensitivity, model identity hashes and grouped exploratory paired contrasts.

No new model training, teacher synthesis, release to the Hub, sealed-test access, or paid automatic retry is authorized by this handoff file.
