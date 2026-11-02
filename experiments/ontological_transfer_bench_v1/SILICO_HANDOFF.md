# Silico worker handoff: ontology transfer, CPU first

Repository: `MoralityLabAI/ConstitutionalAlignment`. Pin the **commit that adds this directory** before starting. The worker must use only committed files. Existing Qwen artifacts are already available privately from `exp_01m6ecy1qaf2ga6qjxgcnjyk5y`:

- `artifact://moralitylab/experiments/exp_01m6ecy1qaf2ga6qjxgcnjyk5y/v4pilot-1b-run/training/final/formal_control/`
- `artifact://moralitylab/experiments/exp_01m6ecy1qaf2ga6qjxgcnjyk5y/v4pilot-1b-run/training/final/platonic_grounding/`

The retained source revision is `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, but the provider revision was not independently attested in the first pilot. Verify the exact checkpoint identity and record file hashes before a new inference allocation. Previously reported adapter parameter hashes are **not** safetensors-file hashes.

## CPU-only preflight

1. Check out pinned GitHub commit and run `python -m experiments.ontological_transfer_bench_v1 verify --out "$CHECK"`.
2. Compare generated CPU receipt to the committed source-bound receipt. Verify all 52 tests and plan SHA-256 IDs.
3. Generate the eight-motif `smoke` plan in a fresh durable directory; record its manifest and training-exclusion flag.
4. Mount/check the Qwen base and both existing adapters **read-only**. Report exact `adapter_model.safetensors` and `adapter_config.json` hashes; check tokenizer, chat template, native thinking mode and GPU fit without spending on an unnecessary model download.
5. Establish whether the requested PrimeIntellect/INTELLECT-3 **exact model** can be served. A current Prime endpoint advertising a newer INTELLECT model is not a substitute. Report a proposed endpoint/model identity and independent budget. Do not use someone else's credentials or infer the API model ID.

## Next optional inference experiment

Qwen: one model load, `hf-group`, only if a new capped lease is approved; use at most the 64-case smoke per arm (192 Qwen assignments). The process time limit is advisory; the provider must enforce its own GPU cap. Preserve partial outputs.

INTELLECT-3: a separate endpoint or multi-GPU serving route, authorized and costed independently. Use the same 64 public cases, exact menu mappings, and comparable output budgets. Store native thinking tokens and final JSON separately. If the model is unavailable, return a source-backed provider availability issue and continue only the CPU work.

After each run, call `score` on one or more record JSONL files. Report by-family joint/action/reason counts, unknown bounds, cue sensitivity, model identity hashes and grouped exploratory paired contrasts.

No new model training, teacher synthesis, release to the Hub, sealed-test access, or paid automatic retry is authorized by this handoff file.
