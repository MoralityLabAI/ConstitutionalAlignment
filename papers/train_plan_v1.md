# Train Plan v1 (Constitutional Alignment)

Updated: 2026-02-13
Recipe reference: `papers/data_recipe_v1.yaml`

## Objective

Train three models from the same base while manipulating only the constitutional
treatment (constitution plus its tradition-tied evidence corpus):

1. Ashari constitution + Ashari tafsir evidence (`ashari`)
2. Mutazili constitution + Mutazili tafsir evidence (`mutazili`)
3. Generic secular constitution derived from the repository's CC0 Anthropic
   constitution snapshot (`control_generic`)

MCP is disabled in both main tracks. Tool access is tested after training as a
separate paired ablation on one frozen Ashari checkpoint.

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

5. Freeze experimental invariants
- Use the same base-model revision, initialization, public dataset revisions and
  weights, stage hyperparameters, prompts, randomization procedure, and gates.
- Permit differences only in `constitution_version` and the matching local
  constitution/evidence-derived corpora.
- Treat `control_generic` exactly like the Islamic tracks at every stage; do not
  omit critique/revision, preference optimization, or any promotion gate.

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
- ETHICS frozen diagnostic slice (eval-only; not a promotion metric because of
  documented train-test overlap and construct-validity concerns,
  arXiv:2410.13009)
- internal holdout dilemmas

2. Add manual review panel on 200 sampled failures per track.

Ship criteria:
- All gates in `papers/data_recipe_v1.yaml` pass.
- No catastrophic failure clusters in manual review.

## Run matrix

Each row names its comparator and exactly one manipulated variable. A run is
invalid if any held-constant field differs.

| Arm | Comparator | Manipulated variable | Held constant |
|---|---|---|---|
| `ashari` | Reference arm (no comparator) | N/A | Base revision, public mix, pipeline, MCP off, prompts, gates |
| `mutazili` | `ashari` | Constitutional treatment: Mutazili constitution + Mutazili evidence corpus | Base revision, public mix, pipeline, MCP off, prompts, gates |
| `control_generic` | Reference control arm (no comparator) | N/A | Base revision, public mix, pipeline, MCP off, prompts, gates |
| `ashari` | `control_generic` | Constitutional treatment: Ashari constitution + Ashari evidence corpus | Base revision, public mix, pipeline, MCP off, prompts, gates |
| `mutazili` | `control_generic` | Constitutional treatment: Mutazili constitution + Mutazili evidence corpus | Base revision, public mix, pipeline, MCP off, prompts, gates |
| `ashari_mcp_off` | Frozen `ashari` checkpoint | None; paired-ablation control | Checkpoint, constitution, data, prompt set, sampling, order, gates |
| `ashari_mcp_on` | `ashari_mcp_off` | MCP tool access | Checkpoint, constitution, data, prompt set, sampling, order, gates |

The MCP pair is inference/evaluation-only: it does not receive additional
training. `mcp_on` may retrieve `fiqh_mcp_outputs` and must cite them; `mcp_off`
cannot retrieve them. Prompts are evaluated in randomized paired order.

### Public-mixture equality gate

Before launching a main-track run, compare the normalized recipe sources after
replacing each constitution-tied `local/*` ID with a common placeholder. The
remaining source IDs and every weight must be byte-for-byte identical across
`ashari`, `mutazili`, and `control_generic`. The run launcher must stop if this
invariant or any weight sum fails.

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
