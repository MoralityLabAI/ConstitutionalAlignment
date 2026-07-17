# Frame Internalization SFT: Recovered Rerun Plan

Status: reconstructed plan; original rerun protocol not frozen; F3 wording
amendment frozen pending scholar review; no fine-tuning outcome.

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
- [`scholar_review_contract_v1.json`](scholar_review_contract_v1.json) and [`SCHOLAR_REVIEW_BRIEF_V1.md`](SCHOLAR_REVIEW_BRIEF_V1.md): hash-bound review criteria and handoff packet.
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

## Frozen F3 amendment readiness

The amendment does not rewrite the interrupted experiment. It adds
`F3_concrete_reflection` to the future rerun and keeps the original six-arm
primary analysis intact. Abstract F3 is copied byte-for-byte from the marked
Phase 3 prompt in `constitutional-harness/RESEARCH_NOTES.md`; concrete F3 makes
recording, witnessing, and weighing explicit. Their `cl100k_base` counts are 64
and 65 tokens (1.5625% spread).

Run:

```powershell
python scripts/validate_frame_internalization_package.py
```

Structural success is not fielding approval. Until approving receipts for both
exact hashes are supplied, the report status is
`structurally_valid_gates_pending`. Launch automation should use
`--require-fielding-ready`, which exits 2 while review is pending. Even after
that frame-specific gate passes, the experiment-level source, training-smoke,
base-reproduction, evaluator-freeze, and compute-authorization gates remain.

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
