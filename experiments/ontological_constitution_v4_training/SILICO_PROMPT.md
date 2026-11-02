# Silico: execute the v4 certificate-trained paired pilot

Repository: `MoralityLabAI/ConstitutionalAlignment`.
Source: use the immutable implementation commit supplied with this prompt; record it in every receipt.
Package: `experiments/ontological_constitution_v4_training/`.
Retained student: Qwen3.8-27B, revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`.

## Work order

Train two fresh adapters on the actual ontology curriculum: Platonic-grounding derivations and their formal-proof control. Use the existing retained base. The historical S1/O1 adapters and v3.1 free-text rationales are outside this training run.

This work order authorizes CPU preparation followed by **one H100 80GB allocation capped at 20 billed GPU-minutes total**. Enforce the cap at the provider and through the shipped process wrapper. No automatic retry or additional allocation. Resolve routine mounted paths locally without changing the experimental source.

Before allocating a GPU, check out the immutable commit, run the committed CPU verification, build the corpus and use the retained tokenizer to run preflight:

```bash
python -m experiments.ontological_constitution_v4_training verify --out "$RUN/cpu-check"
python -m experiments.ontological_constitution_v4 build --out "$RUN/corpus"
python -m experiments.ontological_constitution_v4_training preflight \
  --corpus "$RUN/corpus" --tokenizer "$BASE" --revision "$REVISION" \
  --out "$RUN/preflight.json" --steps-per-arm 20 --seed 11
```

Match the tokenizer/config and weight inventory against the existing checkpoint receipt. Preflight reads no weights. It audits all 320 certificate rows and measures the scheduled pair's real input, rationale and action token counts. Keep those counts in the report; do not inject EOS or edit text to make them equal.

On a successful real-tokenizer preflight, launch the approved job directly:

```bash
bash experiments/ontological_constitution_v4_training/scripts/silico_pair.sh \
  "$BASE" "$REVISION" "$RUN/corpus" "$RUN/preflight.json" "$NEW_GPU_RUN"
```

The runner loads one base, verifies identical initial adapter hashes, executes the paired twenty-update schedule and saves both adapters. It then performs the frozen 128-assignment development comparison with the frame removed. Poor performance remains an outcome. The roster is never reduced to the favorable arm or completed cases.

Preserve the corpus, tokenizer receipt, update journal, adapters, full evaluation records, native prompts, source hashes and process/run receipts in durable artifact storage. Rescore the saved evaluation on CPU using the committed `evaluation.score` function. If the job reaches its cap, retain partial work and score unknowns where the record supports it. A hard-killed incomplete file must be reported as incomplete rather than silently repaired into a completed experiment.

Return measured steps and token exposure for both arms, final adapter hashes, finite loss/gradient status, four-family transfer accuracy and abandonment, malformed/unknown counts, paired bounds, measured peak allocated/reserved VRAM, actual billed GPU-minutes and all artifact paths. Distinguish the process timer from billing. The first result is training/transfer calibration, not proof of an ontological effect.

Do not generate teacher prose, retrain historical adapters, open sealed data, upload to Hugging Face, change repository code, create PRs or start another job. CPU prep plus the one stated lease is the complete task. A source or native-tokenizer defect should return the exact failing row and traceback for ChatGPT, with completed artifacts preserved.
