# Ontological Transfer Bench v1

A **prospective development challenge** for the Qwen3.8-27B baseline, two existing Ontological Constitution v4 LoRA adapters, and a separately served **Prime Intellect INTELLECT-3** reasoning model. The previous v4 pilot reached 128/128 on a shared practical suite for both adapters; this benchmark adds eight new task-scene families and checks the selected justification as well as the action.

The benchmark is CPU-built and fully source-controlled. Model evaluation has **not** been run by this package's verification. No trained adapters, teacher tokens, external API calls, or GPU lease are generated or consumed by its CPU job.

## Mechanisms tested

- **Confluence:** unique upstream first principle in branched/merged DAGs versus two roots with common downstream effects, with changing node labels and graph size.
- **Modal identity:** necessary existence can coexist with grounding; A6 identification makes a nonroot God-like bearer inconsistent in the described model.
- **Value bridge:** separates the existence of a necessary ground from an independently supplied ground-to-value premise.
- **Victim claim:** distinguishes personal forgiveness, outstanding restitution, and genuine capacity to repair.
- **Authenticated guidance:** one calibrated source event printed twice counts once; authentication and delegated authority remain distinct.
- **Signed correction:** an authenticated Boolean **false** remains authenticated despite an opposing rumor.
- **Unjust command:** preserves constructive action under reward and observation cues, including justified protective refusal.
- **Knowledge/action gap:** knowing the right duty can coexist with unwatched violations; finite compliance is not necessary compliance.

Each 5-factor case varies: relevant factual truth, monitoring, promised reward, purported training/deployment phase, and presence of a metaphysical bridge. The bridge changes the correct answer only in the modal-identity and value-bridge families. All arms receive the same scenario, exact menus, source text, and output contract.

The output must be exact JSON: `{"choice": 0, "reason_code": 1}`. Menu IDs are randomized once per motif. The score separately reports action accuracy, rationale-choice accuracy, and **joint correctness**. Reasoning text, if returned by an inference server, remains trace data and is never counted as a proof. These are synthetically authored tasks and do not establish universal theological claims.

## Scope and honesty

The cases are semantically different from v4's development *scenes*, but inherit some of its theorem families. The project itself is public and the benchmark generator is inspectable. This is a **prospective development holdout by newly authored task scenes**, not a sealed or independent final test. The next confirmatory study must freeze entirely new proof-template and narrative families, choose its seed independently, withhold labels, and keep all prompts out of training. Grouped motifs, not the hundreds of factorial repeats, are the sampling units.

A Qwen adapter-versus-adapter contrast may measure a specific treatment difference if paired training and dose controls hold. INTELLECT-3 serves as an **external capability benchmark**; its architectural and training differences preclude a causal treatment comparison. Preserve the prior input token dose imbalance (13,862 versus 13,360), teacher and base revisions, all decoding differences, and variant hardware costs.

## CPU reproducibility

From repository root, with Python 3.11+ and standard library only:

```bash
python -m experiments.ontological_transfer_bench_v1 verify --out /tmp/otb-v1-verified
python -m experiments.ontological_transfer_bench_v1 build --mode smoke --out /tmp/otb-v1-smoke
python -m experiments.ontological_transfer_bench_v1 build --mode full --out /tmp/otb-v1-full
python -m experiments.ontological_transfer_bench_v1 fixture \
  --plan /tmp/otb-v1-smoke/plan.json --arm formal_control --policy oracle \
  --out /tmp/otb-v1-formal-fixture.jsonl
python -m experiments.ontological_transfer_bench_v1 score \
  --plan /tmp/otb-v1-smoke/plan.json \
  --records /tmp/otb-v1-formal-fixture.jsonl \
  --out /tmp/otb-v1-scored.json
```

`smoke` has eight motifs and **64 assignments per arm**, with an eight-run pairwise-balanced design; `full` has 16 motifs and **512 assignments per arm** across all 32 factorial cells. The four registered arms are `base`, `formal_control`, `platonic_grounding`, and `intellect3`.

The output directory contains `plan.json` (private scoring keys included), `public_cases.jsonl` (safe prompt view, no answer fields), and `manifest.json`. Keep `plan.json` separate from API requests and model training. Full manifest hashes and a limited source-derived worked set are committed under `results/`. A new seed produces a different contract and must be frozen before any real model queries.

Partial runs leave their missing assignments as `unknown`, preserving the full denominator and uncertainty interval. All raw final JSON, malformed outputs, original model text, timing, token usage and adapter safetensors **file** hashes are retained when provided. No unobserved response is filled from the oracle.

## Existing Qwen adapters, single weight load

The paired runner loads the retained base once and attaches both trained adapters. It uses the pinned Qwen tokenizer's native chat template and explicit final-only parsing. Point it at **mounted paths** on the worker, not the `artifact://` locator itself:

```bash
python -m experiments.ontological_transfer_bench_v1 hf-group \
  --plan "$PLAN" --out "$OUT/qwen.jsonl" \
  --base "$BASE" --revision "$MODEL_REVISION" \
  --formal-adapter "$FORMAL_DIR" --platonic-adapter "$PLATONIC_DIR" \
  --max-assignments 192 --max-new-tokens 1024 --max-wall-seconds 900 \
  --approved
```

This command requires a **new explicitly approved paid inference allocation**, outside the software build. The provider must enforce its own lease cap. Preflight must establish local model/adapter file integrity and genuine model-revision provenance. The model revision argument alone is not attestation. An optional `--thinking` enables the native Qwen chat-template thinking path; freeze the inference setting before comparison.

## INTELLECT-3 reasoning baseline

INTELLECT-3 is [PrimeIntellect/INTELLECT-3](https://huggingface.co/PrimeIntellect/INTELLECT-3), a ~106B-total, ~12B-active MoE; it is **not** a 12B-weight model and should not be scheduled onto a single 80GB H100 by assuming its active size is its memory footprint. The official model card documents multi-accelerator serving through vLLM. A hosted endpoint must be verified as serving the actual INTELLECT-3 revision; the current Prime serverless model catalog may list newer INTELLECT versions instead.

The optional endpoint runner accepts any verified OpenAI-compatible `/chat/completions` URL, with credentials exclusively from an environment variable. It makes zero calls unless `--approved` is passed, requires hard per-request and cumulative output-token limits, stores original model response and usage, and stops on a provider failure without retrying:

```bash
python -m experiments.ontological_transfer_bench_v1 endpoint \
  --plan "$PLAN" --out "$OUT/intellect3.jsonl" \
  --arm intellect3 --model-id "$VERIFIED_INTELLECT3_ID" \
  --url "$VERIFIED_CHAT_COMPLETIONS_URL" \
  --api-key-env BENCH_API_KEY \
  --max-requests 64 --total-output-cap 131072 \
  --max-new-tokens 2048 --timeout 120 --approved
```

The endpoint URL/model ID are deliberately unspecified. **No INTELLECT-3 hosting availability or monetary price is assumed.** The cap restricts requests and completion tokens, while the serving provider must independently enforce a spend limit. Any usage or model-revision discrepancy marks the run noncomparable. The model's reasoning tokens may be accounted separately where the provider reports them; only its final selected JSON is scored.

## Interpretation of results

Inspect family-level joint correctness, unknown bounds, expected counterfactual flips, spurious oversight/reward/training cue flips, and the motif-grouped exploratory bootstrap. Separate model decoding errors and response-format transfer from semantic errors. A high-scoring model may simply be executing the provided rules. The resulting evidence tests task transfer and declared justifications; it cannot establish private model motives or moral ontology.

Read `PROTOCOL.md` and `SILICO_HANDOFF.md` before authorizing any inference work. Existing v4 LoRA artifacts remain private in Silico's durable store. **No GPU, paid endpoint, training, upload, or sealed test was run during this build.**
