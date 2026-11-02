# Ontological Constitution v4: source-aware training integration

Base: `MoralityLabAI/ConstitutionalAlignment@af65c17d2f85fc2049c50a4074e518bcf903dbf7`.
This sibling package leaves every v4 certificate, old trainer and earlier receipt unchanged.

## Executable first comparison

The bounded pilot trains **formal-control derivation** and **Platonic-grounding derivation** adapters from the same retained base. Each receives one source-checked example from every one of the 20 semantic groups, followed in a common shuffled schedule by 16 identical practical exercises. This is 36 optimizer updates per adapter, interleaved in 36 paired blocks. The within-block adapter order alternates.

Practical exercises use v4's explicit normative premises and independently recomputed applications, with a separate declared training seed. The familiar numeric JSON schema is shared. These exercises and the evaluation use known scenario templates. New option mappings do not constitute structural holdout evidence.

Both rank-16 LoRA adapters begin with identical weights. They have independent AdamW state, equal learning rates and no dropout. The base is frozen. Every update activates only the intended adapter. Snapshots are saved at half and final dose. No historical S1/O1 adapter or rejected v3 prose enters this training run.

The pilot has equal example counts and updates. Its input and target-token counts differ naturally between interpretations and are reported. Segment-normalized rationale/action weights are 0.25/1. This is an integration and exploratory curriculum-package comparison; it does not identify an equal-token or proof-versus-exposition interaction.

## Admission and native-tokenizer check

`contracts.load_corpus` checks the pinned upstream source receipt, all eight export file hashes and the entire regenerated 320-row roster. Each certificate and rendered target is checked again before encoding. Arbitrary teacher prose, edited proof conclusions, duplicated or omitted records, and different source evidence classes fail admission.

The explicit source type remains `CERTIFICATE_RENDERED_PUBLIC_EXPLANATION`. The original production trainer still rejects this class. A new verified practice type is scoped to the built-in constructive exercises; arbitrary records cannot request that type.

Native preflight reads an already-mounted local tokenizer, its config and template. It loads no model weights and uses no network. It records all eight curricula's token counts, the selected pair's actual token exposure, length maxima, and 36 natural EOS targets per arm. Overflow fails before GPU provisioning. Prompt labels are masked; target EOS tokens are never manufactured to equalize lengths.

A test tokenizer supports CPU regressions. Its counts are labeled `DETERMINISTIC_TEST_TOKENIZER_NOT_QWEN` and the production pilot refuses that receipt. The immutable revision string is a declaration until the worker compares the tokenizer hashes with the retained snapshot receipt.

## Commands

Run from a fresh checkout of the base plus the supplied integration patch:

```bash
python -m experiments.ontological_constitution_v4_training verify --out /tmp/v4-training-check
python -m experiments.ontological_constitution_v4_training prepare --out /durable/v4-prepared
python -m experiments.ontological_constitution_v4_training preflight \
  --corpus /durable/v4-prepared/corpus --tokenizer "$BASE" \
  --revision 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  --out /durable/v4-native-preflight
```

After an explicitly approved single-H100 allocation:

```bash
bash experiments/ontological_constitution_v4_training/scripts/silico_pilot.sh \
  "$BASE" 1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0 \
  /durable/v4-prepared /durable/v4-native-preflight /durable/v4-pilot
```

The provider must cap the whole allocation at 20 GPU-minutes. The script has a separate 1,190-second TERM plus 10-second KILL watchdog. The internal pilot reserves 300 seconds for evaluation. Deadlines preserve the completed training logs and produce unknown outcomes for the remaining evaluation roster. A hard external kill may leave only the streamed files and checkpoint; the worker must preserve them rather than claim a complete run.

## Evaluation and receipts

The base with adapters disabled and both new adapters are evaluated on the same 128 development cases each, for **384 assigned records**. Each arm gets the practical charter and case facts with the treatment frame removed. There are eight motifs with sixteen fact/pressure conditions. Treatment-pair order is balanced; the baseline's position rotates.

The independent scorer checks case regeneration, complete assignment, prompt equality and parses each raw output again. It reports correct constructive action, abandonment, schema errors, unknown bounds and per-motif paired differences. Actual timeouts retain partial generated text and token IDs when available. No performance threshold for one arm decides whether the other is evaluated.

Successful CUDA execution leaves `run.json`, the native preflight, source hashes, schedule, every update, half/final adapters, a complete raw evaluation roster and score. PEFT saves named adapters into their own subdirectories under the checkpoint directory. Reuse the recorded paths rather than infer a root adapter path.

## What was checked here

CPU tests exercise full certificate admission, fake-data rejection, all loss masks, two independent optimizers on an explicitly tiny Torch model, inactive-adapter isolation, unchanged base parameters, checkpoint saving, deadlines and complete evaluation accounting. The actual Qwen tokenizer, CUDA loading, PEFT integration on Qwen and behavioral outcomes require the approved worker. No pretrained weights were loaded in the sandbox.

API references used for integration: Hugging Face [PEFT models](https://huggingface.co/docs/peft/main/package_reference/peft_model) and [chat templates](https://huggingface.co/docs/transformers/chat_templating). Use the retained worker's Qwen-compatible library versions and record them; do not replace them with the CPU fixture versions.
