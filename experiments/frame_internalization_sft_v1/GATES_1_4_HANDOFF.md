# Gates 1–4 execution handoff

Prepared 2026-07-19. The immutable inputs and request packs are committed; the
receipts remain fail-closed where cluster inference, generated transcripts, or
human labels are required.

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
receipt. The harmful-source content is hash-frozen, but its source repository
does not declare a license, so the evaluation-universe subgate also remains
pending resolution.

## Readiness check

Copy completed cluster receipts back into the repository and pass them explicitly:

```bash
python scripts/audit_frame_internalization_pre_spend.py \
  --base-freeze /path/to/model_tokenizer_freeze_v1.json \
  --curriculum-manifest /path/to/curriculum_manifest_v1.json \
  --nonleakage-audit /path/to/nonleakage_audit_v1.json \
  --predecessor-reanchor /path/to/predecessor_reanchor_v1.json \
  --output experiments/frame_internalization_sft_v1/readiness/pre_spend_readiness_latest.json
```

Gates 5 and 6—the eight-GPU 4,096-token smoke and signed pilot authorization—
remain separate and must pass before the two-hour pilot.
