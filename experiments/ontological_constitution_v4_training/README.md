# Ontology v4 source-aware training integration

This sibling package admits the existing certificate-rendered ontology curriculum into a dedicated trainer. The v3/v3.1 trainer, v4 curriculum, source proofs and their old receipts are unchanged.

## Admission

The input is the default v4 build: 320 rows, twenty semantic groups, four interpretations and two views, with two shared option permutations. Admission rebuilds every row, verifies every certificate and compares all source text and source labels. Changed prose, a rehashed false explanation, test rows, missing files, extra files in the manifest and reclassification as `MODEL_GENERATED` fail admission. The training source remains `CERTIFICATE_RENDERED_PUBLIC_EXPLANATION`.

## Encoding and CPU preflight

Preflight loads only the already-local fast student tokenizer with its native chat template. It never loads model weights or requests CUDA. The full prompt/response sequence is tokenized once; offsets determine masked prompt tokens, rationale targets and action targets. Tokenization across the prompt boundary is checked explicitly. One supervised natural EOS terminates each response. There is no padding or truncation in the microbatch-one pilot.

The continuation is `Rationale:` plus the certified explanation followed by `Action:` and numeric JSON, matching the existing v4-to-SFT mapping. `enable_thinking=False` is passed to the native template; the exact rendered prefix and its hash are recorded. The production preflight refuses a missing native template, a slow tokenizer, context overflow or inconsistent EOS behavior.

The CPU receipt uses a clearly identified character-offset test double. It is **not** a measurement of the Qwen tokenizer. Real counts are produced on the worker, where the retained tokenizer exists.

```bash
python -m experiments.ontological_constitution_v4 build --out "$RUN/corpus"
python -m experiments.ontological_constitution_v4_training preflight \
  --corpus "$RUN/corpus" --tokenizer "$BASE" --revision "$REVISION" \
  --out "$RUN/preflight.json" --steps-per-arm 20 --seed 11
```

All eight curriculum files are token-audited. The receipt additionally records the exact scheduled exposure of the selected pair. The worker must match tokenizer/config hashes and the retained checkpoint receipt to the declared revision; a supplied revision string alone provides no attestation of weight origin.

## First pilot

Default pair: `formal_control` versus `platonic_grounding`, both using the derivation view. A frozen twenty-update schedule visits every semantic group once per arm. Option permutations rotate and arm execution order is balanced. Both receive the same proof structure, choice target, update count and per-example segment weights. Raw input and rationale-token differences are measured and remain part of the interpretation contrast. The run does not claim equal raw token exposure or a proof-versus-prose factorial result.

Load the retained base once, attach two fresh rank-16 LoRA adapters with alpha 32 and dropout zero, and verify that their initial state hashes match. Optimizers must have disjoint trainable parameters. The base stays frozen. Each loss is 0.25 times the example's mean rationale CE plus its mean action CE. The code reuses the tested segmented loss from v3.

Training alternates arms within rounds. A high loss does not skip the other arm; infrastructure failures preserve the per-arm status and produce a partial run. Final adapters, tokenized exposure, gradient/loss records, CUDA allocated/reserved peaks and package versions are saved. The small pilot has final checkpoints only; larger learning-curve studies can add matched intermediate checkpoints separately.

## Behavioral calibration

After saving adapters, evaluate a separately versioned two-arm projection of the existing v4 transfer cases. The default worker launcher uses four motifs, sixteen cells each, two arms: 128 assigned responses covering care, restitution, testimony and unjust-order tasks. It does not cover the full eight-family suite. Both arms see the same practical charter with the training frame removed. Metaphysical-premise availability is crossed with the relevant fact, oversight and reward.

Numeric JSON, verbatim output, token IDs, native prompts and assignment order are retained. Malformed responses count as observed failures. Timeouts preserve the partial raw generation and widen the unknown-outcome bounds. Deadline-censored units remain in the assigned denominator. The independent scorer requires the exact complete roster and rebuilt prompts.

This is a one-seed training/transfer integration pilot on a twenty-group curriculum seed. It supplies no confirmatory effect estimate, learned-ontology claim, or baseline-improvement claim. No base-model behavioral baseline is included in this first run. All selected examples are development material. Existing sealed tests remain inaccessible.

## Reproduce CPU evidence

```bash
python -m experiments.ontological_constitution_v4_training verify --out /tmp/ontology-training-check
```

The verifier combines the 232 existing v4/v3/semantic-review regressions with 49 new tests. New tests cover certificate and manifest tampering, natural EOS, masking, paired updates, isolated tiny Torch adapters, complete transfer rosters and timeouts. The native Transformers/PEFT GPU path is prepared but was not executed in this CPU build.

The new workflow regenerates the receipt and compares its source hashes with the committed receipt. Generated CPU artifacts remain labeled fixtures. The dependency-light tests use NumPy and CPU Torch; production reuses the worker's known compatible Transformers/PEFT environment and records actual versions.

## Bounded worker command

After the tokenizer-only gate passes, execute the one approved H100 lease:

```bash
bash experiments/ontological_constitution_v4_training/scripts/silico_pair.sh \
  "$BASE" "$REVISION" "$RUN/corpus" "$RUN/preflight.json" "$NEW_GPU_RUN"
```

The wrapper kills the process by 1,200 seconds, covering the in-process checks and base load. Its inner runtime reserves 240 seconds for evaluation within 1,080 seconds after the tokenizer check. Provider startup, upload and teardown require their own allocation cap. An incomplete run is retained, with no automatic retry. Hub upload and teacher generation are absent.

## Technical sources

The data and theorem anchors are those pinned in `ontological_constitution_v4/sources.py` at `af65c17d2f85fc2049c50a4074e518bcf903dbf7`. The admission path preserves their conditional status.

Native-template and special-token handling follows the official Transformers chat-template documentation: https://huggingface.co/docs/transformers/main/chat_templating . Adapter attachment and selection follow the official PEFT interface: https://huggingface.co/docs/peft/en/package_reference/peft_model . The final worker receipt records the installed library versions; no compatibility claim is inferred from a model name.
