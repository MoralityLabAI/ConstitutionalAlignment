# Silico execution packet: constitutional reasoning data v3

Purpose: use an approved H100 lease to produce durable, reusable training artifacts. Implementation and CPU debugging belong to ChatGPT. The existing v2 reporting-schema evaluation continues at its own frozen revision.

## First job

Use an already-mounted teacher snapshot, preferably the retained 27B checkpoint whose metadata matches its original receipt. Check out the v3 implementation commit. Reuse the known worker library environment and record versions. This package does not download weights or call paid teacher APIs.

Run the shipped CPU suite before loading weights. Then execute one bounded synthesis canary with 32 motifs, both pivotal twins, both frames and two critique/rewrite rounds. This assigns 128 candidate records and 640 generation stages. Batch size starts at four. Keep the journal, raw shards and every failed output; acceptance is checked after generation.

```bash
bash experiments/constitutional_reasoning_gym_v3/scripts/silico_generate.sh \
  "$BASE" "$REVISION" "$DURABLE_RUN_DIR" 1200 32
```

The wrapper requires an owner-approved lease and counts from its own start through process termination. The provider must also enforce the whole allocation limit, including startup. No new GPU spend is authorized by merely reading this packet. Once a concrete envelope is approved, execute that envelope without repeated design or approval requests. No automatic retry or extra allocation is authorized.

## What to return from the lease

Return the exact commit, teacher identity, complete-stage counts, accepted paired motifs, acceptance by track, rewrite improvements/regressions, actual generated tokens, accepted explanation words/tokens, measured generation speed, peak allocated VRAM, elapsed GPU time, and durable paths. Export all four SFT arms. The CPU-produced fixture data are excluded by the production exporter and trainer.

A low acceptance rate is a measured yield result. Preserve it and the prompts. Stop automatically on the resource cap or a backend failure. Ordinary recoverable task failures do not require a philosophical review. Send a runtime defect with its minimal failing request and stderr; leave code changes to ChatGPT.

## Scale to mass synthesis

Measure accepted tokens per billed GPU-minute on the canary. Choose the bulk group budget and batch size from that measurement. Proposed SFT dose points are 0.25M, 1M and 3M accepted rationale tokens per comparison, subject to the actual number of unique semantic motifs. Never meet a volume target by duplicating the same cases or by including rejected drafts.

Each new job gets a separate durable run directory and source-bound contract. A retry of the same job reuses its exact journal. Raw records preserve all source contexts, critique turns and generated token IDs. Changing the teacher snapshot, chat template, seed schedule or rewrite contract creates a new batch.

## Hugging Face

Build a new private bundle after export:

```bash
python -m experiments.constitutional_reasoning_gym_v3 hub-bundle \
  --source "$DURABLE_RUN_DIR/sft" --generation "$DURABLE_RUN_DIR/generation" \
  --out "$DURABLE_RUN_DIR/hub"
```

Proposed destination: `AlephFunk/constitutional-reasoning-gym-v3`. With the owner's Hub write approval and worker authentication:

```bash
python -m experiments.constitutional_reasoning_gym_v3 hub-upload \
  --bundle "$DURABLE_RUN_DIR/hub" --repo-id AlephFunk/constitutional-reasoning-gym-v3 --approved
```

Keep the dataset private. Upload into a content-addressed batch directory, record the returned Hub commit, and verify receipt hashes before ending the lease. Raw audit shards are segregated from the accepted training files. Credentials, old eval records and hidden test material are excluded.

## Following jobs

Fine-tune fresh matched adapters under the natural-EOS/segmented-loss contract; retain intermediate checkpoints. Run action-only calibration on fresh cases with the frame prompt removed. Then capture the preregistered mechanistic panel and run matched interventions. Corpus generation, student training and mechanistic acquisition have separate recorded budgets, while their artifacts share a continuous lineage.

The required first deliverable is a useful dataset, not another research review. The scientific limits of the pilot are recorded in `PROTOCOL.md` and `MECHINTERP_PLAN.md`.
