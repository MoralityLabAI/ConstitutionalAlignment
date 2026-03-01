# Train Plan v1 (Constitutional Alignment)

Updated: 2026-02-13
Recipe reference: `papers/data_recipe_v1.yaml`

## Objective

Train two models from a shared base:
1. Ashari + fiqh MCP support (`ashari_with_mcp`)
2. Mutazili without MCP support (`mutazili_no_mcp`)

Both follow a 4-stage pipeline:
1. SFT bootstrap
2. Socratic critique/revision SFT
3. Preference optimization (DPO)
4. Adversarial + constitutional eval gates

## Prerequisites

1. Curate source corpora
- Quran subset (about 500 wisdom verses)
- Ashari tafsir corpus
- Mutazili tafsir corpus

2. Build constitutions
- `constitution_ashari_v1`
- `constitution_mutazili_v1`

3. Finalize sample schema
- Ensure every sample has provenance + constitution tags.

4. Freeze eval holdout
- Keep `internal_constitutional_dilemmas_holdout` fully isolated from training.

## Phase breakdown

### Phase 0: Data prep (2-4 days)

1. Normalize all datasets to shared schema:
- `prompt`, `context`, `judgment_label`, `concise_justification`, `recommended_action`

2. Generate synthetic constitutional data:
- 10k examples per track for initial SFT.
- Include counterexamples and near-miss cases.

3. Create socratic rollouts:
- draft -> critique -> revise tuples.
- 5k tuples per track minimum.

4. Create preference pairs:
- 8k pairwise comparisons per track.
- Label preference based on constitutional fidelity + harm policy.

Deliverables:
- `data/processed/<track>/sft.jsonl`
- `data/processed/<track>/critique_revision.jsonl`
- `data/processed/<track>/preferences.jsonl`
- `data/manifests/data_manifest_v1.json`

### Phase 1: SFT bootstrap (1-2 days)

1. Train from base model on SFT mix in recipe.
2. Keep rationale concise (no hidden CoT extraction/targets).
3. Validate every 500 steps against small dev split.

Promotion criteria:
- constitutional_fidelity >= 0.70
- harm_avoidance >= 0.85

### Phase 2: Socratic critique/revision SFT (1-2 days)

1. Continue from Phase 1 checkpoint.
2. Optimize for improved revised answers over drafts.
3. Train explicit violation flagging behavior.

Promotion criteria:
- revised_better_than_draft_rate >= 0.70
- constitutional_fidelity uplift >= +0.05 over Phase 1

### Phase 3: Preference optimization (1-2 days)

1. Train DPO on mixed external + internal preference pairs.
2. Keep track-specific runs isolated.
3. Monitor refusal style drift and over-refusal.

Promotion criteria:
- constitutional_fidelity >= 0.80
- harm_avoidance >= 0.90
- refusal_calibration >= 0.75

### Phase 4: Final eval + red-team (1 day)

1. Run full eval suite:
- BeaverTails
- ToxiGen
- TruthfulQA
- internal holdout dilemmas

2. Add manual review panel on 200 sampled failures per track.

Ship criteria:
- All gates in `papers/data_recipe_v1.yaml` pass.
- No catastrophic failure clusters in manual review.

## Run matrix

1. `ashari_with_mcp`: SFT -> Critique/Revision -> DPO -> Eval
2. `mutazili_no_mcp`: SFT -> Critique/Revision -> DPO -> Eval

Optional ablation runs:
1. SFT only
2. SFT + critique/revision (no DPO)

## Logging and governance

1. Log required tags for every run:
- `run_id`, `base_model`, `track`, `constitution_version`, `data_recipe_version`

2. Store artifacts:
- model checkpoint
- training config
- dataset manifest hash
- eval report JSON

3. Track safety incidents:
- prompt
- response
- violation type
- severity
- disposition

## Immediate next actions

1. Create constitution YAML files (`constitution_ashari_v1.yaml`, `constitution_mutazili_v1.yaml`).
2. Implement data normalization pipeline to emit schema-compliant JSONL.
3. Build the socratic rollout generator with explicit critique/revision outputs.
4. Stand up the eval harness with the gating metrics above.
