# Gates 1–4 execution handoff

Prepared 2026-07-19. The immutable inputs and request packs are committed; the
receipts remain fail-closed where cluster inference, generated transcripts, or
human labels are required.

The active prospective direct prompt-versus-SFT contract in
`prompt_sft_contrast_v2.json` must also remain hash-valid before generation or
adapter evaluation. It defines a separate matched one-sample comparison; do not
pool those rows with the three-sample historical reanchor.

## 1. Base model and tokenizer freeze

The remote inventory binds `PrimeIntellect/INTELLECT-3` at revision
`ff39d4a4688989f3f28868923d030c28e1b7d81c`, all 48 weight-shard SHA-256
digests, tokenizer/configuration digests, the MIT license declaration, and the
chat template. The remote chat template is byte-identical to the recovered
predecessor template.

On the cluster, hash the local cache and the exact inference-engine image or
lockfile:

```bash
python scripts/verify_frame_model_cache.py \
  --model-dir /absolute/path/to/INTELLECT-3 \
  --engine-lock /absolute/path/to/engine-image-or-lock.txt \
  --engine-description "exact image digest or locked environment" \
  --output /absolute/path/to/model_tokenizer_freeze_v1.json
```

The verifier exits 2 and writes `passed: false` on any missing or mismatched
artifact. Do not generate curriculum data until it writes `passed: true`.

## 2. Matched curricula and token parity

`rerun_freeze/curriculum_generation_v1/requests.jsonl` contains 22,400 frozen
requests: 5,600 paired scenarios for each of neutral, F1, F3, and F3-concrete.
Those four transcript sets deterministically render the six registered training
arms. Generation seeds are paired by scenario across source frames.

Run one resumable process per source frame against the verified model server:

```bash
for frame in neutral F1 F3 F3_concrete; do
  python scripts/generate_frame_curriculum_transcripts.py \
    --urls http://MODEL_SERVER:PORT \
    --source-frame "$frame" \
    --base-freeze-receipt /absolute/path/to/model_tokenizer_freeze_v1.json \
    --output-dir /absolute/path/to/raw_curriculum
done
```

After all four generation receipts report `complete: true`, render and tokenize
with the verified cache:

```bash
python scripts/render_frame_curricula.py \
  --raw-dir /absolute/path/to/raw_curriculum \
  --tokenizer /absolute/path/to/INTELLECT-3 \
  --base-freeze-receipt /absolute/path/to/model_tokenizer_freeze_v1.json \
  --output-dir /absolute/path/to/rendered_curriculum \
  --manifest /absolute/path/to/curriculum_manifest_v1.json
```

The renderer fails unless every source frame joins exactly to all 5,600 frozen
scenarios. Its manifest passes only when all six arms have 5,320 training and
280 validation rows and F3/F3-concrete total training-token spread is at most
2%.

## 3. Nonleakage

The committed source-prompt precursor audit passes with zero exact, normalized,
or registered 8-gram overlap. It does not satisfy the gate because generated
assistant text does not exist yet. Run the final audit after rendering:

```bash
python scripts/audit_frame_curriculum_nonleakage.py \
  --curriculum-manifest /absolute/path/to/curriculum_manifest_v1.json \
  --curriculum-dir /absolute/path/to/rendered_curriculum \
  --evaluation experiments/frame_internalization_sft_v1/rerun_freeze/evaluation_universes_v2/harmful_queries.jsonl \
  --evaluation experiments/frame_internalization_sft_v1/rerun_freeze/evaluation_universes_v2/benign_queries.jsonl \
  --evaluation experiments/frame_internalization_sft_v1/rerun_freeze/evaluation_universes_v2/override_queries.jsonl \
  --evaluation data/storyworld_sources/constitutional_alignment_20260715_v1/evaluation/mihna_ca_eval_v2.encounter_prompts.jsonl \
  --output /absolute/path/to/nonleakage_audit_v1.json
```

## 4. Predecessor reanchor

The progress receipt binds the exact recovered compliance and strict-AF rubrics,
request builder, gap analysis, activation harvester, layer-27 probe procedure,
base calibration interval, and a frozen 400-unit human-validation queue. The
queue contains 200 compliance units and 200 strict-AF units; each task must reach
Cohen's kappa of at least 0.70.

This gate still requires base-model generation and judging, blinded human labels,
the fitted base F0 layer-27 probe plus controls, and the final joined baseline
receipt. The active v2 evaluation-universe license subgate has passed through a
prospective HarmBench substitution. This is not an exact predecessor reanchor:
the recovered F0 interval is descriptive only, and a new complete v2 base
baseline must be estimated without a magnitude pass/fail threshold. The v1
license issue remains preserved and unresolved; see
`PROTOCOL_AMENDMENT_LICENSED_HARMBENCH_V2.md` and
`LICENSE_RESOLUTION_HANDOFF.md`.

Before regenerating the historical rows, attempt authenticated retrieval using
`rerun_freeze/predecessor_artifact_registry_recovery_v1.json`. The recovered
transcript records successful registration of the full generation manifests and
layer-27 archive under experiment `exp_01kxhk57rcesya1ckbsv07zb2x`. Their current
availability and bytes are not verified, so this locator is not gate-satisfying.
Retrieved files must pass the frozen row, join, decoding, judge, activation-key,
and model-revision checks; summary numbers alone remain pilot provenance.

## Readiness check

Copy completed cluster receipts back into the repository and pass them explicitly:

```bash
python scripts/audit_frame_internalization_pre_spend.py \
  --base-freeze /path/to/model_tokenizer_freeze_v1.json \
  --curriculum-manifest /path/to/curriculum_manifest_v1.json \
  --nonleakage-audit /path/to/nonleakage_audit_v1.json \
  --evaluation-seal experiments/frame_internalization_sft_v1/readiness/evaluation_seal_v2.json \
  --prompt-sft-contract experiments/frame_internalization_sft_v1/prompt_sft_contrast_v2.json \
  --predecessor-reanchor /path/to/predecessor_reanchor_v2.json \
  --output experiments/frame_internalization_sft_v1/readiness/pre_spend_readiness_latest.json
```

Gates 5 and 6—the eight-GPU 4,096-token smoke and signed pilot authorization—
remain separate and must pass before the two-hour pilot.
