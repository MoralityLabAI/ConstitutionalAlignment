# Frame Internalization SFT: Recovered Rerun Plan

Status: reconstructed plan; v2 treatment and staged-compute governance frozen;
scholar review pending as a claims-only gate; six pilot gates pending; no
fine-tuning outcome.

This package reconstructs Silico experiment `exp_01kxm0hbf4ez58y7mfj58rmn6q`, originally titled **"Training the frames in: does SFT internalize what prompting couldn't?"** The experiment was interrupted during data generation. The recovered record contains the design, partial generation counts, quality checks, launcher decisions, and compute receipts, but it does **not** contain the generated transcript payloads, trained adapters, dose checkpoints, or evaluation outputs.

Accordingly, this is a plan for a new, provenance-preserving rerun. It is not a claim that the original run completed, and it is not evidence that secular or eschatological framing changes action policy.

## Scientific question

Does supervised fine-tuning on framed moral reasoning change no-frame action policy beyond a neutral, reflection-formatted SFT control? If so, is the effect attributable to frame content, to the reflection curriculum, or to their interaction?

The planned design separates:

- content: secular constitutional framing (F1) versus eschatological framing (F3);
- curriculum: full draft/critique/revise reflection transcripts versus final-answer demonstrations;
- training exposure: four framed adapters versus a neutral reflection-formatted control and the unmodified base model.

The primary behavioral endpoint remains the no-frame free/paid-tier alignment-faking gap inherited from the completed predecessor experiment. Representation-level probes and override evaluations are secondary and cannot substitute for a behavioral effect.

## Package contents

- [`PROTOCOL_RECOVERED_V1.md`](PROTOCOL_RECOVERED_V1.md): complete rerun design, gates, analysis, resource plan, and claim limits.
- [`recovery_manifest.json`](recovery_manifest.json): machine-readable recovered facts, missing artifacts, amendments, and provenance.
- [`PROTOCOL_AMENDMENT_F3_CONCRETE_V1.md`](PROTOCOL_AMENDMENT_F3_CONCRETE_V1.md): prospective concrete-F3 arm and the three-endpoint operational internalization gate.
- [`protocol_amendment_f3_concrete_v1.json`](protocol_amendment_f3_concrete_v1.json): machine-readable frozen hashes, arm invariants, estimands, and launch gates.
- [`frame_cards/F3_v1.json`](frame_cards/F3_v1.json) and [`frame_cards/F3_concrete_v1.json`](frame_cards/F3_concrete_v1.json): exact abstract and mechanically explicit treatment wording.
- [`scholar_review_contract_v1.json`](scholar_review_contract_v1.json) and [`SCHOLAR_REVIEW_BRIEF_V1.md`](SCHOLAR_REVIEW_BRIEF_V1.md): immutable v1 review-chain provenance.
- [`PROTOCOL_AMENDMENT_V2.md`](PROTOCOL_AMENDMENT_V2.md) and [`protocol_amendment_v2.json`](protocol_amendment_v2.json): prospective separation of compute authorization from the scholar-review claim gate.
- [`frame_cards/F3_v2.json`](frame_cards/F3_v2.json) and [`frame_cards/F3_concrete_v2.json`](frame_cards/F3_concrete_v2.json): clean v2 metadata with treatment prompts byte-identical to v1.
- [`frame_cards/claim_boundary_v1.json`](frame_cards/claim_boundary_v1.json) and [`scholar_review_contract_v2.json`](scholar_review_contract_v2.json): machine-readable claim placement and the active hash-bound review contract.
- [`SCHOLAR_REVIEW_BRIEF_V2.md`](SCHOLAR_REVIEW_BRIEF_V2.md): current exact-hash review handoff, usable before or after fielding.
- [`compute_stage_plan_v1.json`](compute_stage_plan_v1.json): zero-spend gates, the capped two-hour eight-A100 pilot, deterministic overnight promotion, abort rules, checkpoint cadence, and paper packaging.
- [`prompt_sft_contrast_v1.json`](prompt_sft_contrast_v1.json) and [`PROTOCOL_AMENDMENT_DIRECT_PROMPT_SFT_V1.md`](PROTOCOL_AMENDMENT_DIRECT_PROMPT_SFT_V1.md): immutable v1 provenance for the matched direct prompt-versus-SFT estimands.
- [`PROTOCOL_AMENDMENT_LICENSED_HARMBENCH_V2.md`](PROTOCOL_AMENDMENT_LICENSED_HARMBENCH_V2.md) and [`prompt_sft_contrast_v2.json`](prompt_sft_contrast_v2.json): active prospective licensed-universe amendment and direct prompt-versus-SFT contract. V2 requires a new base baseline and forbids the historical F0 interval as a replacement-universe pass/fail target.
- [`readiness/pre_spend_readiness_20260719.json`](readiness/pre_spend_readiness_20260719.json): pre-amendment no-spend audit receipt retained for provenance.
- [`readiness/pre_spend_readiness_20260719_v3.json`](readiness/pre_spend_readiness_20260719_v3.json): current audit receipt; the licensed v2 universe, v2 direct prompt-versus-SFT contract, split, seal, and judge dry run pass. Six compute blockers remain and `pilot_ready` is false.
- [`readiness/split_freeze_v1.json`](readiness/split_freeze_v1.json), [`readiness/evaluation_seal_v2.json`](readiness/evaluation_seal_v2.json), and [`readiness/judge_dry_run_v1.json`](readiness/judge_dry_run_v1.json): active passed prospective split, licensed-v2 evaluation seal, and production judge-contract gates.
- [`rerun_freeze/evaluation_universes_v1.json`](rerun_freeze/evaluation_universes_v1.json): immutable reconstructed-universe provenance. Its recovered set hashes match, but its harmful-source license remains unresolved and it is not fielded under v2.
- [`rerun_freeze/evaluation_universes_v2.json`](rerun_freeze/evaluation_universes_v2.json): active prospective 200-row HarmBench-standard harmful universe, byte-preserved 100-row benign universe, and rebuilt 150-row override universe, with pinned source and MIT-license hashes.
- [`LICENSE_RESOLUTION_HANDOFF.md`](LICENSE_RESOLUTION_HANDOFF.md): fail-closed evidence for v1 and the completed prospective-substitution disposition for v2.
- [`rerun_freeze/predecessor_artifact_registry_recovery_v1.json`](rerun_freeze/predecessor_artifact_registry_recovery_v1.json): recovered Silico registry paths for the historical judged generations and layer-27 archive. Registration is transcript-attested, but current availability and artifact bytes remain unverified.
- [`predecessor_recovery/transcript_recovered_summaries/`](predecessor_recovery/transcript_recovered_summaries/): exact compact result tables reconstructed from embedded tool outputs and file-construction code. These support pilot reporting only until the registered row and activation bundles are retrieved and validated.
- [`rerun_freeze/curriculum_source_v1/dilemma_manifest.json`](rerun_freeze/curriculum_source_v1/dilemma_manifest.json): pinned prospective 5,600-row dilemma pool and 5,320/280 cluster-disjoint split.
- [`GATES_1_4_HANDOFF.md`](GATES_1_4_HANDOFF.md): cluster commands and fail-closed completion conditions for base verification, the 22,400-request curriculum pack, final nonleakage, and predecessor reanchoring.
- [`rerun_freeze/model_tokenizer_remote_inventory_v1.json`](rerun_freeze/model_tokenizer_remote_inventory_v1.json): immutable remote model/tokenizer inventory awaiting cluster-cache and engine-lock verification.
- [`rerun_freeze/curriculum_generation_v1/request_manifest.json`](rerun_freeze/curriculum_generation_v1/request_manifest.json): frozen four-frame generation plan that renders into the six registered training arms.
- [`rerun_freeze/nonleakage_source_prompts_v2.json`](rerun_freeze/nonleakage_source_prompts_v2.json): active source-prompt precursor audit against v2; all overlap counts are zero, while generated text remains to be audited.
- [`rerun_freeze/predecessor_reanchor_progress_v2.json`](rerun_freeze/predecessor_reanchor_progress_v2.json): active v2 inputs, passed licensed-universe subgate, and outstanding inference, human-label, probe, and row-join evidence for a new prospective baseline.
- [`predecessor_dependency_manifest_v1.json`](predecessor_dependency_manifest_v1.json) and [`predecessor_recovery/`](predecessor_recovery/): session-extracted predecessor payloads, exact recovery hashes, and the remaining freeze gaps.
- [`predecessor_prompt_reconstruction_v1.json`](predecessor_prompt_reconstruction_v1.json): hash-bound reconstruction of exact F0-F3 prompt text from recovered base/frame inputs and the recorded construction command.
- [`predecessor_reanchoring_plan_v1.json`](predecessor_reanchoring_plan_v1.json): prospective fail-closed freezes for the missing model, universes, judges, row joins, baseline, and fitted probe.

The recovered Silico conversations remain in the repository rather than being duplicated here:

- [primary worker session](../../silico_reports/chats/remote/2026-07-15T23-07-16-035Z_019f6808-d0c3-74f6-82d6-44166b37a589.md)
- [checkpoint/render session](../../silico_reports/chats/remote/2026-07-15T23-07-26-577Z_019f6808-f9f1-7889-90a2-e045e47e4161.md)
- [recovery session index](../../silico_reports/source_manifests/remote_pi_sessions_index_all.md)

## What survived

- A final v2 dilemma-pool specification: 5,600 cluster-disjoint scenarios, with 5,320 train and 280 validation rows.
- The final six-arm comparison and SFT hyperparameters.
- The draft/critique/revise generation procedure and early corpus-quality audit.
- A last auditable generation count of 7,830 of 16,800 neutral/F1/F3 transcripts.
- Roughly 50.1 auditable A100-hours through the final recovered snapshot, against a planned cap of about 210 A100-hours.
- The planned primary, dose, override, benign, capability, storyworld, and representation evaluations.

## What did not survive

- The stochastic JSONL transcript corpus itself.
- Any trained LoRA adapter or dose checkpoint.
- Any post-training generation, behavioral score, or layer-27 comparison.
- A W&B training run: training had not begun at the last auditable checkpoint.
- Pinned revisions for the public source datasets, so the pool can be structurally regenerated but not assumed byte-identical.

## Recovered design defect

The intended and smoke-tested sequence length was 4,096. The recovered full-run shell launcher still passed `--seq-len 2048`. A resumed launch would therefore have violated the intended design. The rerun protocol freezes 4,096 and treats this as an explicit reconstruction amendment.

## Execution order

1. Rebuild the dilemma pool with pinned source revisions and reproduce the structural counts and disjointness checks.
2. Rebuild the neutral/F1/F3 generation pipeline and rerun a small, reviewed corpus smoke test.
3. Reconstruct the inherited evaluators from the completed predecessor runs and reproduce the base-model gap before adapter comparisons.
4. Run a short 4,096-token training smoke, including adapter save/load and generation checks.
5. Freeze code, data, environments, exact prompts, evaluation universes, analysis code, seeds, and the pilot-anchored compute budget before any full run.
6. Generate the full corpus, train the five adapters, and collect sealed outcomes without changing the registered analysis.

No full configuration should run merely because this plan exists. The protocol's recovery and smoke gates must pass first.

## V2 governance and staged-compute readiness

The v1 amendment remains immutable provenance. Amendment v2 keeps its arms,
estimands, three-endpoint gate, and regression guards, but moves scholar review
from compute authorization to review-provenance and theological-adequacy
claims. Both clean v2 cards preserve the v1 treatment prompts byte-for-byte.
Their `cl100k_base` counts are 64 and 65 tokens (1.5625% spread).

Run:

```powershell
python scripts/audit_frame_internalization_pre_spend.py
```

The current report passes v2 governance integrity and records scholar review as
`pending_nonblocking`. It also passes the prospective split freeze, evaluation
seal, and actual production judge-parser dry run. It blocks the pilot on six
remaining receipts: immutable base freeze, matched curricula and token parity,
full-curriculum nonleakage, predecessor reanchor, distributed 4,096-token smoke,
and signed pilot authorization. Use
`--require-pilot-ready` in launch automation; it exits 2 while any compute gate
is pending. No scholar receipt is required for that exit condition.

The frozen artifacts can be regenerated from locally downloaded, hash-checked
source parquets:

```powershell
python scripts/freeze_frame_evaluation_universes.py `
  --source-dir <dir-containing-harmful.parquet-and-alpaca.parquet>
python scripts/freeze_frame_dilemma_split.py `
  --moral-stories-parquet <pinned-moral-stories.parquet>
Push-Location constitutional-harness
npm run judge:contract-dry-run
Pop-Location
python scripts/audit_frame_internalization_pre_spend.py `
  --output experiments/frame_internalization_sft_v1/readiness/pre_spend_readiness_20260717.json
```

The dilemma pool reproduces the lost run's total, split, and cluster-count
invariants. Its pinned prospective sample contains 7 storyworld rows rather
than the session-reported 13 because the lost run did not pin its parquet
conversion revision; this divergence is recorded and is not presented as exact
historical recovery.

The guarded cluster wrapper is dry-run safe and refuses real execution outside
a bounded Slurm allocation:

```powershell
python scripts/run_frame_internalization_stage.py --stage pilot `
  --training-task-id <id> --authorization <authorization.json> `
  --run-dir <empty-run-dir> `
  --checkpoint-root <checkpoint-dir> --checkpoint-every-steps 200 `
  --checkpoint-every-minutes 20 --dry-run -- <exact-trainer-command>
```

The pilot uses one full eight-GPU distributed load at a time and time-slices an
equal reduced step count across all six adapters. The overnight is cancelled
unless every arm passes the pilot and the measured throughput fits the frozen
12-hour, 96-GPU-hour cap.

The predecessor recovery check is independent:

```powershell
python scripts/recover_frame_predecessor_assets.py --check
```

It verifies 88 exact payloads embedded in three pinned raw Silico sessions. This
recovers the free-minus-paid analysis, informative base prompt, F1/F2/F3 frame
payloads, arm-construction recipe and token receipt, target chat template,
query-manifest receipt, generic override, rubrics, layer-27 procedure, summary
JSON, and figures. Exact F0-F3 prompt text is deterministically reconstructable,
but the canonical generated files are not claimed as recovered. Complete query
rows, immutable model/tokenizer and dataset revisions, raw generations, judge
receipts, activation arrays, and the fitted layer-27 direction remain launch
gates under `predecessor_reanchoring_plan_v1.json`.
