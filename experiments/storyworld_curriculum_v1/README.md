# Storyworld Trajectory Curriculum Factory v1

This package is an executable vertical slice of the trajectory-curriculum factory. It is not a training release and it does not yet contain 10M tokens per adapter arm.

The slice establishes the contracts that the larger corpus must obey:

- Six-to-ten-turn acyclic paths with actions that change later states and legal menus.
- Opaque, seed-derived action identifiers in every actor-visible prompt.
- At least two Pareto-nondominated choices at each decision state, so the world does not encode one mechanically dominant action.
- Public and seat-private evidence with explicit fact/allegation status.
- A language-independent causal graph shared by a Quranic-motif skin and secular control skin.
- Structured teacher work products rather than private chain-of-thought.
- Separate actor, forecaster, interrogator, counterfactual analyst, and adjudicator/repairer roles at low through xhigh effort.
- Deterministic MeTTa-file-backed state, legality, visibility, transition, consequence, repair, and obligation facts.
- One canonical episode ledger that emits policy, world-model, interrogation, repair, preference, and RL-environment views.
- Tokenizer-measured per-arm quota packing with 1M, 3M, 6M, and 10M checkpoint receipts.
- One continuous, ordered, assistant-only QLoRA run per arm with hash-bound dose checkpoints.
- Hard rejection of sealed evaluation rows and review-pending data in the default training path.

## Package status

All twelve frozen train families are implemented: five matched motif/control pairs and seven standalone secular families.

- Entrusted Relief Ledger: `amanah_relief_ledger_train_v1` and secular `fiduciary_relief_ledger_train_v1`, graph SHA-256 `5dc844505de54b3619cfc04e7b0ae1550e6b7d18032cebbcc1428a8b21f88ee4`.
- Mizan Competing Claims: `mizan_competing_claims_train_v1` and secular `multicriteria_appeals_train_v1`, graph SHA-256 `ecbee22d2db2470f6d5ebbf5714e631c78c33746f271598475cd8846e3b475db`.
- Tawbah Costly Repair: `tawbah_cold_chain_repair_train_v1` and secular `incident_remediation_train_v1`, graph SHA-256 `385dd29cbf589f5e618bb3ec670aeec352b9b26b8d253373255976599b470ef8`.
- Shura Consultation and Authority: `shura_payroll_cutover_train_v1` and secular `participatory_cutover_train_v1`, graph SHA-256 `1fa707d409367a10a15ee555a141df20d2bdc4052bdd2ef1b48ab177b6806e91`.
- Common Resource Allocation: standalone `common_well_allocation_train_v1`, graph SHA-256 `5c78eaba3580743f0eb7ddf6151ad4095f46a5afb62878e68e20b338154eb9b0`.
- Market Status and Generosity: standalone original-fiction `market_mutual_aid_train_v1`, graph SHA-256 `a216f51cfffaf3c928af622d91c4fabaab8498f20a21ec517e8e3ef7b9e3870f`.
- Interpretation Under Authority: standalone original-fiction `interpretation_under_authority_train_v1`, graph SHA-256 `1f51a5f7d1dec600e0917c195967d8d2b14c1e1c7848dccabf3b6e6ef2cac09a`.
- Nontransactional Service: standalone original-fiction `nontransactional_service_train_v1`, graph SHA-256 `20ce1809d22918d0a076c410d4d64040ca25a62a105bcc0c319e98738f634bd6`.
- Knowledge Claims and Public Risk: standalone original-fiction `knowledge_claims_public_risk_train_v1`, graph SHA-256 `25058c1b25c448bf5c0ed0dfadd35c01c45e06cf1e3c143391a5175dcb29a91b`.
- Ghayb Boundary Search: `ghayb_boundary_search_train_v1` and secular `uncorroborated_signal_search_train_v1`, graph SHA-256 `13396a1e1c0bc7745cc3d08ffdb10912d1e479a8e1b31cfefec97714fb65c809`.
- Proportionate Disclosure: standalone `proportionate_disclosure_train_v1`, graph SHA-256 `e7c1d333fc2b8ba6684a9cd2da0b230791a81450fabe8e187ca1a7acaa684cb6`.
- Exogenous Failure Recovery: standalone `exogenous_failure_recovery_train_v1`, graph SHA-256 `feade0456d9699af95d14ba404758d663697bd55d3eb4da2e18a9fbe58249041`.

All seventeen train worlds are marked `training_eligible`, but none is `training_approved`. Split eligibility and release approval are deliberately separate gates.

All four frozen development families are also implemented as five resolved, explicitly non-training worlds:

- Private Testimony and Counterpressure: Shahada-motif `shahada_private_testimony_dev_v1` and secular `protected_testimony_dev_v1`, graph SHA-256 `9ca55fb031a55e69b476d006eb3beba4b69be7593006fda4097c01e7118bff85`.
- Continuity After Reset: standalone `continuity_after_reset_dev_v1`, graph SHA-256 `ba34ea364f0cf4f4016764ffd0eb1ab4b0a90f56a8f26289982ec3e6be69a2f8`.
- Unreliable Intercessor: standalone `unreliable_intercessor_dev_v1`, graph SHA-256 `3ef9fc7d95c6f08ddce38a0c302ec72b3fc5fc7b7f995489d2945673dc8ca4ec`.
- Public Witness and Group Pressure: standalone original-fiction `public_witness_group_pressure_dev_v1`, graph SHA-256 `4151098400d6e24923d54f13ac63675040c3c24d254bdaf659fbed2fbb8dddc1`.

Development traces may be harvested for checkpoint measurement, but `derive_trace_views` and the quota packer reject them even when provisional output is explicitly allowed. Regenerate and validate the deterministic development authoring outputs with `python scripts/generate_storyworld_development_worlds.py`.

The 17-source pre-migration registry is in `source_inventory.json`. The manifest-only `split_freeze_v1.json` assigns exactly 12 train, 4 development, and 6 confirmatory evaluation causal families. Trust Ledger and Pixie Relief Ledger become one train family; overlapping Unwatched Ledger, Mizan Sealed Ledger, and reused Mizan evaluation variants remain legacy diagnostics rather than being counted as clean holdouts.

## Freeze causal-family assignments

Validate the split freeze without opening pending or sealed content:

```powershell
python scripts/freeze_storyworld_splits.py
```

Write a hash-bearing receipt when preparing an external build:

```powershell
python scripts/freeze_storyworld_splits.py `
  --output D:/Research_Engine/storyworld_curriculum/split_freeze/RECEIPT.json
```

The validator requires 22 unique causal clusters, dispositions for all 17 named sources, exactly five train motifs (`amanah`, `ghayb_boundary`, `mizan`, `tawbah`, and `shura`), and explicit exclusions for every legacy or development-only source. Implemented train and development paths are resolved; sealed evaluation content is not read.

## Prepare blinded evaluation authoring

Validate the closed protocol and print sanitized family-level author briefs:

```powershell
python scripts/prepare_blinded_storyworld_eval.py
```

To write transferable briefs and a hash-bearing closed-gate receipt:

```powershell
python scripts/prepare_blinded_storyworld_eval.py `
  --output-dir D:/Research_Engine/storyworld_curriculum/blinded_authoring_v1
```

The protocol exposes only family ID, causal-cluster ID, family-level construct, authoring mode, and required reviews. It never resolves an evaluation content path. The preparation command also emits a content-free `SEALED_AUTHORING_RECEIPT_TEMPLATE.json` for the external access-controlled environment. The one-time gate remains closed until the adapter recipe, checkpoint manifest, global development selection, analysis code, review bundle, six-family authoring completion, and training-provenance nonleakage receipts are frozen. `audit_storyworld_training_nonleakage.py` proves the exact packed corpus contains only approved train provenance. `authorize_storyworld_one_time_unseal.py --authorize-one-time-unseal` can then create exactly one closed authorization; it still contains no sealed content or result. After external execution, `record_storyworld_one_time_sealed_evaluation.py --record-one-time-sealed-evaluation` binds the signed result to the authorization and refuses an existing output path.

Build the separately keyed development suite after reviews (the provisional flag is for pipeline validation only):

```powershell
python scripts/build_storyworld_development_eval.py `
  --output-dir D:/Research_Engine/storyworld_curriculum/development_suite_v1
```

The current suite materializes 30 development worlds and 4,962 public requests. It directly scores legal-action recognition, next-state prediction, belief visibility, fact/allegation separation, counterfactual branches, contradiction detection, reachable repair, obligation/dynamics disagreement, calibrated consequence forecasts, and paired-skin policy choices; identity-scrubbed defense consistency is derived from matched motif/control responses. Public requests and deterministic keys are stored separately, emit zero training rows, and never open sealed evaluation content.

Score each 1M/3M/6M/10M adapter checkpoint with its packed-curriculum manifest:

```powershell
python scripts/score_storyworld_development_eval.py `
  --manifest D:/Research_Engine/storyworld_curriculum/development_suite_v1/DEV_EVAL_MANIFEST.json `
  --predictions D:/Research_Engine/storyworld_curriculum/dev_predictions/jinn_3m.jsonl `
  --arm jinn `
  --checkpoint-tokens 3000000 `
  --checkpoint-receipt D:/Research_Engine/storyworld_curriculum/packed_v1/PACKING_MANIFEST.json `
  --output D:/Research_Engine/storyworld_curriculum/dev_scores/jinn_3m.json
```

The scorer verifies the suite/key hashes, checkpoint boundary and prefix hash, arm, release status, and frozen tokenizer fingerprint. Exact tasks use deterministic engine/MeTTa targets; belief visibility uses micro-F1, forecast calibration uses Brier score, and paired metrics compare underlying action keys and cited visible fact IDs rather than surface wording.

Checkpoint choice is not arm-specific. `analysis_plan_v1.json` locks one global checkpoint shared by all four arms, using the mean of all twelve direction-corrected development metrics across the four arms, with the smaller dose winning an exact tie. The added `frame_robust_policy_accuracy` is a direct identity-scrubbed behavioral measure: on secular development prompts, it scores grounded selection of actions satisfying the largest number of the four reviewed operational constraint frames. It is explicitly a synthetic policy proxy, not moral ground truth. This prevents choosing 10M for one identity and 3M for its control. After all 16 score cells exist, `freeze_storyworld_analysis_selection.py` applies that rule and hashes every analysis-code artifact before sealed access.

`run_storyworld_development_eval.py` provides a shardable command-model adapter for producing the prediction JSONL. It reads and hashes only `DEV_PUBLIC_ITEMS.jsonl`, binds every request to the arm and checkpoint prefix, requires explicit evaluation-spend authorization, and writes a pre-invocation claim so an interrupted paid shard cannot be silently replayed. The runner never opens `DEV_PRIVATE_KEYS.jsonl`; scoring remains a separate step.

## Validate and compile

Run the package audit without writing artifacts:

```powershell
python scripts/validate_storyworld_curriculum.py
```

Write validation and MeTTa compilation receipts:

```powershell
python scripts/validate_storyworld_curriculum.py `
  --output-dir artifacts/storyworld_curriculum_v1/validation
```

The compiler's accurate description is "MeTTa-file-backed deterministic derivation; not native Hyperon proof execution." Proof metadata is retained outside actor-visible policy prompts.

## Materialize parameter sweeps

The base worlds define causal families. Explicit sweep manifests vary resources, observation, authority, timing, and counterpart behavior without using seed values as undocumented scenario knobs. Materialize a matched sweep before harvesting:

```powershell
python scripts/materialize_storyworld_instances.py `
  --sweep experiments/storyworld_curriculum_v1/instance_sweeps/shura_payroll_cutover_sweep_v1.json `
  --output-dir D:/Research_Engine/storyworld_curriculum/instances/shura_v1
```

The sixteen reference sweeps currently define 98 profiles and materialize 136 resolved worlds: paired motif/control sweeps materialize both skins for every profile, while standalone sweeps materialize one. Every output carries its sweep/profile, factor values, and base-world content hash; paired outputs also carry their matched counterpart. The validator rejects missing factor variation, unknown override targets, invalid worlds, a one-sided sweep of a paired world, or a theological/secular graph mismatch.

## Harvest traces

The production interface is a command adapter. The command receives one `storyworld_teacher_request_v1` JSON object on standard input and emits either one task-specific JSON object or a response/provider-receipt envelope. Each request includes the functional role, `gpt-5.6-sol` model ID, reasoning effort, explicit no-private-chain-of-thought instruction, agent-visible input, and provenance metadata.

`scripts/openai_storyworld_teacher.py` is the reference OpenAI Responses API adapter. It uses strict JSON-schema output, retries semantic contract failures, sets `store=false`, and returns per-attempt model, token-usage, request-hash, and output-hash receipts without retaining hidden reasoning. It requires a valid `OPENAI_API_KEY` and the installed OpenAI Python SDK.

```powershell
python scripts/harvest_storyworld_traces.py `
  --world experiments/storyworld_curriculum_v1/worlds/train/amanah_relief_ledger_train_v1.json `
  --frames neutral,constitutional,jinn,beast `
  --seeds 23,47 `
  --actor-schedule dyadic `
  --teacher command `
  --agent-command "python scripts/openai_storyworld_teacher.py" `
  --output-dir D:/Research_Engine/storyworld_curriculum/traces/amanah_v1
```

Run a small reviewed smoke tranche before any corpus-scale spend. Do not substitute fixture traces when API authentication, model access, review approval, or token-budget authorization is missing.

`--actor-schedule single` keeps the declared primary actor for every turn. `--actor-schedule dyadic` alternates the first two declared agents and records the acting seat on every turn, so each seat receives only its own private evidence. An explicit comma-separated agent schedule is also accepted.

Use the deterministic fixture only to test plumbing. Fixture traces can never become training-approved:

```powershell
python scripts/harvest_storyworld_traces.py `
  --world experiments/storyworld_curriculum_v1/worlds/train/amanah_relief_ledger_train_v1.json `
  --frames jinn `
  --seeds 42 `
  --teacher fixture `
  --output-dir artifacts/storyworld_curriculum_v1/fixture_harvest
```

Each turn requests and validates:

1. An actor work product containing observed fact IDs, uncertainty, forecasts, an opaque action ID, a public reason, responsibility attribution, a counterfactual, and confidence.
2. A forecast for every legal action.
3. Three to eight interrogation questions, including an identity-scrubbed defense.
4. A question-aligned defense from the visible record.
5. A counterfactual action and observation-regime analysis.
6. An xhigh adjudicated/repaired target.

Teacher outputs are rejected if they cite a hidden fact, select an illegal action, omit uncertainty, use an invalid probability, or fail the response contract. Engine validation still does not make the adjudicator's policy choice moral ground truth.

## Build canonical views

```powershell
python scripts/build_storyworld_curriculum.py `
  --traces D:/Research_Engine/storyworld_curriculum/traces/amanah_v1/traces.jsonl `
  --world experiments/storyworld_curriculum_v1/worlds/train/amanah_relief_ledger_train_v1.json `
  --output-dir D:/Research_Engine/storyworld_curriculum/releases/canonical_v1
```

The output manifest hashes these views:

- `sft_policy.jsonl`
- `sft_world_model.jsonl`
- `sft_interrogation.jsonl`
- `sft_repair.jsonl`
- `preference_pairs.jsonl`
- `rl_environment.jsonl`

The release builder refuses pending-review traces by default. `--allow-provisional` exists for fixture and pipeline validation only; its manifest remains visibly provisional.

The loss-bearing views use compact visible evidence rather than repeating the full actor-view JSON. Policy and repair targets retain the selected action text, review critique, and remaining uncertainty; each turn's three-to-eight interrogation answers are packed as one grounded defense record. This keeps explicit work products loss-bearing and makes the 4M assistant-token floor achievable without requesting or storing private chain-of-thought.

## Plan the real harvest campaign

The initial campaign estimate is balanced by causal family rather than by raw world-file count: 134 unique traces per family per arm, or 1,608 traces for each of neutral, constitutional, Jinn, and Beast. Half use a single seat and half alternate the two declared seats.

```powershell
python scripts/plan_storyworld_harvest_campaign.py `
  --output-dir D:/Research_Engine/storyworld_curriculum/campaign_10m_v1
```

This writes 6,432 deterministic jobs, a disjoint 48-trace `pilot_jobs.jsonl`, and 6,384 `remaining_jobs.jsonl` rows in 67 executable shards. No pilot row appears in a shard, preventing post-pilot duplicate spend. The full estimate corresponds to 38,592 decision turns and 231,552 functional teacher calls. It is intentionally marked `planning_estimate_not_spend_authorization`: the approved-world reviews, a valid credential, the pilot, and exact-tokenizer recalibration are execution gates. Evaluation and development worlds produce zero training jobs.

After every train world has hash-bound approval receipts, regenerate the plan and execute one pilot job explicitly:

```powershell
python scripts/run_storyworld_harvest_job.py `
  --jobs D:/Research_Engine/storyworld_curriculum/campaign_10m_v1/pilot_jobs.jsonl `
  --job-index 0 `
  --output-root D:/Research_Engine/storyworld_curriculum/traces/campaign_10m_v1 `
  --authorize-teacher-spend
```

The runner rechecks train-only eligibility, content and transition hashes, and review approval before constructing the command teacher. It accepts pilot jobs only; full-campaign jobs remain closed until pilot receipts and exact-tokenizer recalibration are recorded. A pre-invocation `RUN_CLAIM.json` makes an interrupted job fail closed instead of silently spending twice.

After all 48 jobs succeed, audit their job receipts and provider call receipts and recalibrate against the frozen local training tokenizer:

```powershell
python scripts/calibrate_storyworld_harvest_pilot.py `
  --campaign-manifest D:/Research_Engine/storyworld_curriculum/campaign_10m_v1/CAMPAIGN_MANIFEST.json `
  --pilot-jobs D:/Research_Engine/storyworld_curriculum/campaign_10m_v1/pilot_jobs.jsonl `
  --trace-root D:/Research_Engine/storyworld_curriculum/traces/campaign_10m_v1 `
  --tokenizer D:/Research_Engine/tokenizers/frozen_adapter_base `
  --output D:/Research_Engine/storyworld_curriculum/campaign_10m_v1/PILOT_CALIBRATION.json
```

Calibration refuses missing or duplicate jobs, non-OpenAI command traces, stored API calls, incomplete provider receipts, and any job/world/graph/seed/schedule/hash mismatch. It measures packed and assistant yield per core slice and arm, counts actual provider usage, exactly tokenizes the deterministic MeTTa rows over all train instances, and rounds the binding trace estimate to one family-balanced even count so the four arms retain identical 50/50 single/dyadic allocation. Its status remains `pilot_passed_pending_human_full_campaign_authorization`; it cannot open the full campaign by itself.

The calibration also emits 48 content-bound trace review tasks. Reviewers inspect each complete pilot episode for visible-fact grounding, action/consequence/interrogation coherence, repair quality, identity boundaries, and hidden-state or sacred-reenactment failures. Record one signed `storyworld_real_pilot_trace_review_receipt_v1` per task, including the exact task scopes as `confirmed_scopes`, then build the required all-approved bundle:

```powershell
python scripts/apply_storyworld_pilot_trace_reviews.py `
  --pilot-calibration D:/Research_Engine/storyworld_curriculum/campaign_10m_v1/PILOT_CALIBRATION.json `
  --review-receipts D:/Research_Engine/storyworld_curriculum/campaign_10m_v1/PILOT_TRACE_REVIEW_RECEIPTS.jsonl `
  --output D:/Research_Engine/storyworld_curriculum/campaign_10m_v1/PILOT_HUMAN_REVIEW_BUNDLE.json
```

Freeze that recommendation into a new repository-tracked planning config, regenerate its disjoint remaining-job artifacts, and only then record an explicit human spend authorization:

```powershell
python scripts/freeze_storyworld_recalibrated_campaign.py `
  --calibration D:/Research_Engine/storyworld_curriculum/campaign_10m_v1/PILOT_CALIBRATION.json `
  --campaign-id storyworld_gpt_5_6_10m_per_arm_postpilot_v1 `
  --output experiments/storyworld_curriculum_v1/harvest_campaign_postpilot_v1.json

python scripts/plan_storyworld_harvest_campaign.py `
  --campaign experiments/storyworld_curriculum_v1/harvest_campaign_postpilot_v1.json `
  --output-dir D:/Research_Engine/storyworld_curriculum/campaign_postpilot_v1

python scripts/authorize_storyworld_full_campaign.py `
  --campaign-manifest D:/Research_Engine/storyworld_curriculum/campaign_postpilot_v1/CAMPAIGN_MANIFEST.json `
  --pilot-calibration D:/Research_Engine/storyworld_curriculum/campaign_10m_v1/PILOT_CALIBRATION.json `
  --pilot-review-bundle D:/Research_Engine/storyworld_curriculum/campaign_10m_v1/PILOT_HUMAN_REVIEW_BUNDLE.json `
  --authorized-by <accountable-operator> `
  --authorization-reference <budget-or-change-ticket> `
  --max-teacher-calls <manifest-projected-remaining-calls> `
  --output D:/Research_Engine/storyworld_curriculum/campaign_postpilot_v1/FULL_CAMPAIGN_AUTHORIZATION.json `
  --authorize-full-campaign-spend
```

The authorization command verifies the exact pilot, tokenizer, recipe, package, post-pilot config, projections, remaining-job file, and every shard hash. It authorizes neither the pilot rows nor `jobs.jsonl`, only `remaining_jobs.jsonl` and its disjoint shards. Execute an authorized shard job with both the per-job spend flag and that receipt:

```powershell
python scripts/run_storyworld_harvest_job.py `
  --jobs D:/Research_Engine/storyworld_curriculum/campaign_postpilot_v1/shards/shard_0000.jsonl `
  --job-index 0 `
  --output-root D:/Research_Engine/storyworld_curriculum/traces/campaign_postpilot_v1 `
  --full-campaign-authorization D:/Research_Engine/storyworld_curriculum/campaign_postpilot_v1/FULL_CAMPAIGN_AUTHORIZATION.json `
  --authorize-teacher-spend
```

After the original 48-job pilot and every authorized post-pilot remaining job are complete, atomically audit them into the sole canonical trace input. `prepare_storyworld_harvest_release.py` replays every episode from its frozen world and seed, checks every model/effort/non-storage/usage/response receipt, reconstructs the family-by-arm and single/dyadic matrices, and binds each job receipt and trace hash. It refuses partial campaigns and emits no approved ledger without `--apply`:

```powershell
python scripts/prepare_storyworld_harvest_release.py `
  --pilot-calibration <real-pilot-calibration.json> `
  --pilot-review-bundle <pilot-human-review-bundle.json> `
  --pilot-jobs <original-pilot-jobs.jsonl> `
  --pilot-trace-root <original-pilot-output-root> `
  --campaign-manifest <post-pilot-campaign-manifest.json> `
  --remaining-jobs <authorized-remaining-jobs.jsonl> `
  --remaining-trace-root <post-pilot-output-root> `
  --full-authorization <full-campaign-authorization.json> `
  --output-dir <approved-harvest-release-dir> `
  --apply
```

Pass the resulting `approved_traces.jsonl` and `HARVEST_RELEASE_MANIFEST.json` positionally as `--traces` and `--trace-manifest` to `build_storyworld_curriculum.py`. A nonprovisional canonical release refuses arbitrary trace JSONL files, and the training audit walks this complete lineage back through the job evidence before accepting any packed row.

## Pack the 10M-per-arm recipe

The frozen arithmetic is in `token_recipe_10m_per_arm.json`:

| Slice | Packed tokens/arm | Assistant minimum/arm |
|---|---:|---:|
| Stateful actor trajectories | 4.5M | 2.0M |
| Interrogation and defense | 2.0M | 1.0M |
| MeTTa world-model tasks | 1.5M | 0.3M |
| Failure critique and repair | 1.0M | 0.4M |
| Static identity/calibration | 0.5M | 0.15M |
| Ordinary helpfulness/guardrails | 0.5M | 0.15M |

Each of the neutral, constitutional, Jinn, and Beast arms targets 10M packed tokens and at least 4M loss-bearing assistant tokens. That is 40M total processed tokens before adapter-spend ablations.

The tiktoken backend is a development estimate. A real training pack must use `--tokenizer-backend huggingface --hf-tokenizer <frozen-local-tokenizer-directory>` so the quota and checkpoint boundaries match the exact base-model tokenizer revision. The Hugging Face gate refuses remote identifiers and records a content manifest for the local tokenizer configuration, vocabulary, merge rules, special tokens, and chat template; the path label alone is never treated as a freeze receipt. Loss-bearing counts use the same exact chat-template prefix mask as the trainer, including supervised template suffix tokens, rather than an estimate from raw assistant text. The builder uses unique rows in deterministic hash order and stops only when both packed and assistant-token minima are met for every slice; it does not inflate the pack by cycling a small corpus. Selected slice rows are then weighted-fair interleaved by normalized slice completion, so 1M, 3M, and 6M are prefix-compatible scaled versions of the final recipe rather than actor-only early phases. Intermediate checkpoints use the first indivisible row crossing their aggregate target. The nominal 10M checkpoint consumes the complete selected stream, including small row-granularity overshoot, so all six packed and assistant slice quotas are actually satisfied.

## Train the adapter-spend curve

`adapter_training_recipe_v1.json` freezes one continuous, ordered QLoRA run for each arm. It uses one dataset pass, no shuffle, rank-32/alpha-64 LoRA on full-attention, Qwen3.5 linear-attention, and MLP projections, token-normalized AdamW gradients, and assistant-only labels. The linear-attention coverage includes `in_proj_qkv`, `in_proj_z`, `in_proj_a`, `in_proj_b`, and `out_proj`; omitting these would leave 18 of the 24 Qwen3.5 token-mixing blocks without direct LoRA adaptation. Prompt tokens are always masked. Frozen rows that exceed 8,192 tokens are rejected rather than truncated. At each 1M/3M/6M/10M packed boundary, accumulated gradients are flushed before the adapter is saved, making every dose a prefix of the same optimizer trajectory.

Inspect the no-spend 4-run/16-checkpoint plan:

```powershell
python scripts/plan_storyworld_adapter_training.py
```

After selecting a local research-compatible base, hash every weight shard and the exact tokenizer bytes:

```powershell
python scripts/freeze_storyworld_adapter_base.py `
  --model-dir D:/Research_Engine/models/<frozen-9b-base> `
  --tokenizer-dir D:/Research_Engine/models/<frozen-9b-base> `
  --model-id <stable-model-id> `
  --model-revision <immutable-revision> `
  --license-review-reference <license-review-receipt> `
  --reviewed-by <reviewer-pseudonym> `
  --output D:/Research_Engine/storyworld_curriculum/BASE_FREEZE.json
```

Only after the reviewed 10M pack exists, issue a human-attributed authorization bound to the pack, base, tokenizer, trainer source, output root, all four arms, and a total four-arm GPU-hour ceiling. V1 partitions that ceiling equally into four nontransferable per-arm limits, so the apparent budget cannot be spent once per arm:

```powershell
python scripts/authorize_storyworld_adapter_training.py `
  --training-recipe experiments/storyworld_curriculum_v1/adapter_training_recipe_v1.json `
  --token-recipe experiments/storyworld_curriculum_v1/token_recipe_10m_per_arm.json `
  --packing-manifest D:/Research_Engine/storyworld_curriculum/packed_v1/PACKING_MANIFEST.json `
  --base-freeze D:/Research_Engine/storyworld_curriculum/BASE_FREEZE.json `
  --output-root D:/Research_Engine/storyworld_curriculum/adapter_runs_v1 `
  --authorized-by <reviewer-pseudonym> `
  --authorization-reference <compute-authorization-receipt> `
  --max-gpu-hours <ceiling> `
  --output D:/Research_Engine/storyworld_curriculum/ADAPTER_TRAINING_AUTHORIZATION.json `
  --authorize-adapter-training-spend
```

Run each arm with `train_storyworld_adapter_curve.py --arm <arm> --authorize-adapter-training-spend`. Before loading the model, the trainer rehashes the base, tokenizer, pack, authorization, and its own source; recomputes every packed prefix; verifies chat-template prefix masking; retokenizes every row; proves zero truncation and zero prompt-loss tokens; and writes a pre-load compute claim. Each adapter checkpoint has its own byte manifest and binds the exact packed prefix hash.

For local development evaluation, `run_storyworld_local_adapter_development_eval.py` loads the base and one adapter only once per public shard. It verifies the adapter artifact, training receipt, base freeze, packed dose prefix, and development public-item hash, and never reads the private scoring key. Merge complete disjoint shards with `merge_storyworld_development_predictions.py`, then pass the merged JSONL to `score_storyworld_development_eval.py`.

Static identity/calibration and ordinary-helpfulness rows enter through `--extra-rows` after they are normalized to `storyworld_training_view_v1`, split-audited, licensed, and approved. Bad candidates belong in repair context or the rejected preference field, never as an unmarked assistant target.

Normalize the recovered four-arm train split without admitting its validation or heldout rows:

```powershell
python scripts/normalize_recovered_storyworld_extras.py `
  --source-root D:/Research_Engine/recovered_silico_workspace_artifacts_20260716/exp_01kxm64p51e3ys4vyd23hqtwp2 `
  --output-dir D:/Research_Engine/storyworld_curriculum/recovered_extras_v1
```

The hash-verified source contributes 600 rows per arm, but all 2,400 rows remain provisional: neutral and constitutional are unreviewed, while 390 train rows in each of Jinn and Beast require scholar review and their other 210 are unreviewed. With `cl100k_base`, the recovered train split supplies 144k–228k static/calibration tokens and 17k–25k ordinary-helpfulness tokens per arm, so it cannot fill either 0.5M slice without new unique data. The normalization manifest reports the exact packed and assistant shortfall for every arm and slice.

Recovered rows do not inherit approval merely because their hashes are known. `prepare_recovered_storyworld_extras_review.py` emits one content-bound task for every normalized row, upgrading source-marked identity rows to scholar-and-content review and assigning ordinary content review to the remainder. Every row receipt must explicitly confirm the task's complete required-check set. `apply_recovered_storyworld_extras_reviews.py --apply` requires all 2,400 current row receipts plus a separate `storyworld_recovered_source_license_receipt_v1` bound to the normalized row-file hash. One rejection, missing check confirmation, stale hash, missing signature, or absent research-training license keeps the complete recovered batch provisional.

The complementary no-spend support campaign supplies original prompts without borrowing train, development, or sealed-evaluation storyworld content:

```powershell
python scripts/plan_storyworld_support_slices.py `
  --output-dir D:/Research_Engine/storyworld_curriculum/support_slices_v1
```

It creates 900 identity/calibration and 1,200 ordinary-helpfulness/guardrail scenarios, matched across all four arms: 8,400 jobs total, a disjoint 76-job category-by-arm pilot, and 8,324 remaining jobs in 66 shards. Helpfulness covers explanation, rewriting, planning, debugging, data interpretation, tutoring, comparison, extraction, creative drafting, and safe capability preservation. Static calibration covers nonliteral identity, observer invariance, epistemic and authority boundaries, correction, anti-theatrical helpfulness, neutral frame translation, responsibility calibration, and persistence on mundane tasks. All prompts are original and unique; every job remains execution-ineligible and training-unapproved until prompt review, a real-teacher pilot, exact-tokenizer recalibration, and sampled output review.

Prepare a review work order containing the complete user/system messages for all 76 pilot slice/category/arm cells:

```powershell
python scripts/prepare_storyworld_support_prompt_reviews.py `
  --config experiments/storyworld_curriculum_v1/support_slice_campaign_v1.json `
  --plan-manifest D:/Research_Engine/storyworld_curriculum/support_slices_v1/SUPPORT_PLAN_MANIFEST.json `
  --scenarios D:/Research_Engine/storyworld_curriculum/support_slices_v1/support_scenarios.jsonl `
  --pilot-jobs D:/Research_Engine/storyworld_curriculum/support_slices_v1/pilot_jobs.jsonl `
  --output D:/Research_Engine/storyworld_curriculum/support_slices_v1/PROMPT_REVIEW_QUEUE.json

python scripts/apply_storyworld_support_prompt_reviews.py `
  --review-queue D:/Research_Engine/storyworld_curriculum/support_slices_v1/PROMPT_REVIEW_QUEUE.json `
  --review-receipts D:/Research_Engine/storyworld_curriculum/support_slices_v1/PROMPT_REVIEW_RECEIPTS.jsonl `
  --output D:/Research_Engine/storyworld_curriculum/support_slices_v1/PROMPT_HUMAN_REVIEW_BUNDLE.json
```

Each `storyworld_support_prompt_review_receipt_v1` must bind the job, scenario, and complete messages hashes; approve and confirm every required scope; and include reviewer attribution, notes, a timezone-bearing signature date, and an external signature/receipt. Only a complete 76-prompt bundle can be used to create the pilot authorization. The explicit flag authorizes exactly the 76 hash-listed nonstored calls and still approves zero training rows:

```powershell
python scripts/authorize_storyworld_support_pilot.py `
  --config experiments/storyworld_curriculum_v1/support_slice_campaign_v1.json `
  --plan-manifest D:/Research_Engine/storyworld_curriculum/support_slices_v1/SUPPORT_PLAN_MANIFEST.json `
  --scenarios D:/Research_Engine/storyworld_curriculum/support_slices_v1/support_scenarios.jsonl `
  --pilot-jobs D:/Research_Engine/storyworld_curriculum/support_slices_v1/pilot_jobs.jsonl `
  --prompt-review-bundle D:/Research_Engine/storyworld_curriculum/support_slices_v1/PROMPT_HUMAN_REVIEW_BUNDLE.json `
  --authorized-by <authorizer-pseudonym> `
  --authorization-reference <external-authorization-receipt> `
  --output D:/Research_Engine/storyworld_curriculum/support_slices_v1/PILOT_AUTHORIZATION.json `
  --authorize-pilot-spend
```

Execute each pilot job separately. The runner writes a claim before the provider call and refuses ambiguous retries:

```powershell
python scripts/run_storyworld_support_job.py `
  --jobs D:/Research_Engine/storyworld_curriculum/support_slices_v1/pilot_jobs.jsonl `
  --job-index 0 `
  --authorization D:/Research_Engine/storyworld_curriculum/support_slices_v1/PILOT_AUTHORIZATION.json `
  --output-root D:/Research_Engine/storyworld_curriculum/support_outputs_v1 `
  --authorize-teacher-spend
```

Audit all 76 genuine provider receipts and project each category with the frozen local tokenizer:

```powershell
python scripts/calibrate_storyworld_support_pilot.py `
  --config experiments/storyworld_curriculum_v1/support_slice_campaign_v1.json `
  --plan-manifest D:/Research_Engine/storyworld_curriculum/support_slices_v1/SUPPORT_PLAN_MANIFEST.json `
  --pilot-jobs D:/Research_Engine/storyworld_curriculum/support_slices_v1/pilot_jobs.jsonl `
  --pilot-authorization D:/Research_Engine/storyworld_curriculum/support_slices_v1/PILOT_AUTHORIZATION.json `
  --output-root D:/Research_Engine/storyworld_curriculum/support_outputs_v1 `
  --tokenizer D:/Research_Engine/tokenizers/<frozen-base-tokenizer> `
  --output D:/Research_Engine/storyworld_curriculum/support_slices_v1/PILOT_CALIBRATION.json
```

The calibration applies a 0.9 safety factor and requires both 0.5M packed and 0.15M assistant tokens in each support slice and arm. If either projection misses, its status requires a larger unique-prompt replan. If all cells cover, the calibration also emits a 76-task queue binding each real pilot output by record and content hash. Review every task and create the mandatory bundle:

```powershell
python scripts/apply_storyworld_support_pilot_reviews.py `
  --pilot-calibration D:/Research_Engine/storyworld_curriculum/support_slices_v1/PILOT_CALIBRATION.json `
  --review-receipts D:/Research_Engine/storyworld_curriculum/support_slices_v1/PILOT_REVIEW_RECEIPTS.jsonl `
  --output D:/Research_Engine/storyworld_curriculum/support_slices_v1/PILOT_HUMAN_REVIEW_BUNDLE.json
```

Every receipt is a `storyworld_support_pilot_review_receipt_v1` record that approves the current row hash, confirms every task scope, and includes reviewer attribution, notes, a timezone-bearing signature date, and a signature or external receipt. Only a complete all-approved bundle can authorize the 8,324 remaining jobs (or their 66 hash-listed shards):

```powershell
python scripts/authorize_storyworld_support_full_campaign.py `
  --config experiments/storyworld_curriculum_v1/support_slice_campaign_v1.json `
  --plan-manifest D:/Research_Engine/storyworld_curriculum/support_slices_v1/SUPPORT_PLAN_MANIFEST.json `
  --pilot-calibration D:/Research_Engine/storyworld_curriculum/support_slices_v1/PILOT_CALIBRATION.json `
  --pilot-review-bundle D:/Research_Engine/storyworld_curriculum/support_slices_v1/PILOT_HUMAN_REVIEW_BUNDLE.json `
  --remaining-jobs D:/Research_Engine/storyworld_curriculum/support_slices_v1/remaining_jobs.jsonl `
  --authorized-by <authorizer-pseudonym> `
  --authorization-reference <external-authorization-receipt> `
  --max-teacher-calls 8324 `
  --output D:/Research_Engine/storyworld_curriculum/support_slices_v1/FULL_AUTHORIZATION.json `
  --authorize-full-campaign-spend
```

The same per-job runner then uses that full authorization; pilot replay is outside its scope.

After every job finishes, `prepare_storyworld_support_release.py` verifies every job, authorization, provider receipt, semantic screen, uniqueness constraint, and exact token total. It emits provisional rows and a deterministic 152-task release queue: one pilot and one remaining response per slice/category/arm cell. Reviewers return `storyworld_support_release_review_receipt_v1` records bound to each task and row hash. `apply_storyworld_support_release_reviews.py --apply` releases the batch only when every sampled receipt is signed, current, and approved; otherwise all 8,400 rows remain provisional.

Prepare the hash-bound storyworld review work order without changing approval status:

```powershell
python scripts/prepare_storyworld_review_queue.py `
  --output D:/Research_Engine/storyworld_curriculum/reviews_v1/REVIEW_QUEUE.json
```

For reviewer handoff, combine the three current queues with the recovered rows into readable packets and fail-closed receipt templates:

```powershell
python scripts/prepare_storyworld_human_review_handoff.py `
  --world-review-queue <world-review-queue.json> `
  --prompt-review-queue <support-prompt-review-queue.json> `
  --recovered-review-queue <recovered-review-queue.json> `
  --recovered-rows <normalized-recovered-rows.jsonl> `
  --output-dir <reviewer-handoff-directory>
```

The templates deliberately contain invalid decisions, empty scope/check confirmations, placeholder attribution, and invalid timestamps. The generator proves that all untouched templates are rejected before writing `HANDOFF_MANIFEST.json`; they are aids for reviewers, never implicit approvals.

The current queue contains 51 review tasks across 22 resolved nonsealed worlds; all 17 train worlds block real campaign execution. The queue includes content and graph hashes plus required receipt fields, but has no approval effect by itself.

Reviewers return `storyworld_review_receipt_v1` records containing the queue task ID, the exact task `review_type`, the task's `reviewable_content_sha256` as `content_sha256`, a decision, scoped notes, a timezone-bearing signature date, and a signature or external receipt reference. Workflow status and receipt fields are excluded from that substantive hash, so recording the batch cannot invalidate the reviewed content identity.

Validate all 51 receipts without changing source files, then repeat with the explicit application flag:

```powershell
python scripts/apply_storyworld_review_receipts.py `
  --queue D:/Research_Engine/storyworld_curriculum/reviews_v1/REVIEW_QUEUE.json `
  --receipts D:/Research_Engine/storyworld_curriculum/reviews_v1/RECEIPTS.jsonl `
  --bundle-output experiments/storyworld_curriculum_v1/review_bundles/review_application_v1.json

python scripts/apply_storyworld_review_receipts.py `
  --queue D:/Research_Engine/storyworld_curriculum/reviews_v1/REVIEW_QUEUE.json `
  --receipts D:/Research_Engine/storyworld_curriculum/reviews_v1/RECEIPTS.jsonl `
  --bundle-output experiments/storyworld_curriculum_v1/review_bundles/review_application_v1.json `
  --apply
```

Application is all-or-nothing at the review-batch level: missing, duplicate, stale, unsigned, or hash-mismatched tasks are refused before source mutation. The resulting package validator checks every world decision, source/content/graph hash, receipt hash and reference, and the package hash recorded by the review bundle.

## Audit end-to-end readiness

Run the readiness auditor at any point without authorizing spend or opening sealed content:

```powershell
python scripts/audit_storyworld_curriculum_readiness.py `
  --review-bundle <approved-world-review-bundle> `
  --main-pilot-calibration <real-main-pilot-calibration> `
  --main-pilot-review-bundle <all-48-pilot-human-review-bundle> `
  --support-pilot-calibration <real-support-pilot-calibration> `
  --support-pilot-review-bundle <all-76-support-pilot-human-review-bundle> `
  --packing-manifest <reviewed-10m-pack-manifest> `
  --base-freeze <base-freeze-receipt> `
  --training-authorization <training-authorization> `
  --adapter-training-receipt <one-per-arm> `
  --development-score <all-16-score-cells> `
  --analysis-freeze <frozen-global-selection> `
  --sealed-evaluation-receipt <one-time-final-receipt> `
  --output <readiness-receipt.json>
```

Arguments backed by repeatable artifacts may be supplied more than once. The auditor reports each of eleven gates as passed, pending, or failed and sets `objective_complete` only when the full chain exists. With no external artifacts supplied, only the factory-design gate passes; that is the expected pre-execution state, not a claim that the dataset or adapters exist.

## Remaining work before adapter spend

1. Obtain scholar, research-ethics, and domain review receipts and change world review status only through a recorded review update.
2. Replace the invalid API credential, run the 48-trace real-teacher pilot, and recalibrate trace counts and cost with the exact frozen tokenizer.
3. Normalize the recovered static corpus and ordinary-helpfulness guardrails, satisfying each slice's 0.5M packed/0.15M assistant quotas per arm.
4. Freeze and execute the approved campaign over train worlds only, then pack unique four-arm rows to every packed and loss-bearing quota.
5. Have blinded evaluators author or upgrade the six evaluation families in separate access-controlled storage while only public family briefs remain visible here.
6. Save adapters at 1M/3M/6M/10M, select only on development worlds, freeze analysis, and open the sealed evaluation once.
