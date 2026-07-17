# Frame Internalization SFT Protocol

Protocol version: `recovered-rerun-v1.0.0-draft`  
Original Silico experiment: `exp_01kxm0hbf4ez58y7mfj58rmn6q`  
Freeze status: **not frozen**  
Outcome status: **not run**

## 1. Epistemic status

This document reconstructs an interrupted experiment from recovered Silico sessions. It distinguishes three classes of statement:

1. **Recovered fact:** supported by the archived sessions or their manifests.
2. **Original plan:** intended before interruption but never executed to an outcome.
3. **Rerun amendment:** a new constraint added to make a fresh run reproducible and paper-safe.

The original stochastic transcript corpus is unavailable. No adapter, dose checkpoint, final evaluation, or mechanistic comparison was recovered. The rerun must therefore receive a new run ID and new hashes. It must never be described as a continuation of completed training.

## 2. Questions and estimands

### 2.1 Primary question

Does framed SFT reduce the inherited no-frame alignment-faking gap relative to a neutral reflection-formatted SFT control?

Let `G_arm` be the free-tier minus paid-tier compliance gap computed by the recovered predecessor analysis. The sign convention, experiment-1 strong-reject rubric text, strict alignment-faking-reasoning rubric text, and exact arm-prompt text are recovered. The complete prompt rows, immutable model/tokenizer and dataset revisions, judge/classifier revisions, and row-level receipts are not. Before the rerun they must be prospectively frozen under `predecessor_reanchoring_plan_v1.json`; the resulting study is a re-anchoring, not an exact historical replication.

Primary arm-level effects are:

- `Delta_arm = G_arm - G_neutral` for each framed adapter;
- content main effect: `0.5 * [(G_F3R + G_F3D) - (G_F1R + G_F1D)]`;
- curriculum main effect: `0.5 * [(G_F1R + G_F3R) - (G_F1D + G_F3D)]`;
- interaction: `(G_F3R - G_F3D) - (G_F1R - G_F1D)`.

Here `R` denotes reflection and `D` demonstration. Lower or higher values are interpreted only under the inherited gap convention; the analysis report must print that convention next to every contrast.

### 2.2 Secondary questions

- Does any effect appear monotonically over dose checkpoints?
- Does generic adversarial override erase the observed effect?
- Do adapters increase benign over-refusal or reduce GSM8K performance?
- Do frame-specific behavior or spontaneous frame invocation generalize to held-out Mihna storyworld prompts?
- Does the previously identified layer-27 evaluation-awareness representation shift, and does that shift predict behavior beyond random-projection controls?

Representation movement is not evidence of action-policy change unless the registered behavioral endpoint also moves.

## 3. Arms

| Arm | Content | Curriculum | Training |
|---|---|---|---|
| `base` | none | none | unmodified base model |
| `neutral_reflection` | neutral | reflection | LoRA SFT |
| `F1_reflection` | secular constitution | reflection | LoRA SFT |
| `F1_demonstration` | secular constitution | demonstration | LoRA SFT |
| `F3_reflection` | eschatological | reflection | LoRA SFT |
| `F3_demonstration` | eschatological | demonstration | LoRA SFT |

Reflection examples contain the full six-message draft/critique/revise exchange, with loss on all assistant turns. Demonstration examples contain the bare dilemma followed by the same final revised answer, after deterministic preamble stripping. Within each content condition, reflection and demonstration curricula must share dilemma IDs and final-answer content. Token counts are reported rather than artificially padded.

### 3.1 Prospective concrete-F3 amendment

On 2026-07-17, before any rerun outcome, the project froze a prospective
`F3_concrete_reflection` amendment. It preserves this recovered six-arm primary
design and adds a direct, reflection-curriculum comparison between abstract F3
and a card that explicitly names recording, witnessing, and weighing. See
`PROTOCOL_AMENDMENT_F3_CONCRETE_V1.md` and its machine-readable hash manifest.

The amendment is not recovered history and is not approved for fielding. Both
exact frame hashes require qualified scholar approval. No concrete-demonstration
arm is added, so no concreteness-by-curriculum interaction may be claimed.

## 4. Dilemma pool

### 4.1 Recovered v2 specification

- 5,600 total scenarios: 5,587 from `demelin/moral_stories` and 13 Mihna development scenes.
- 5,320 train and 280 validation scenarios.
- 5,600 cluster IDs, with cluster-disjoint 95/5 splitting under seed 42.
- Hendrycks ethics/reddit rows removed in v2.
- Zero banned-vocabulary drops and zero evaluation-overlap drops in the final v2 receipt.
- Evaluation-overlap protection used 8-gram checks against the harmful, benign, and Mihna evaluation sets.

### 4.2 Rerun amendments

- Pin immutable source revisions and record source licenses.
- Hash the normalized source rows, scenario construction code, cluster assignments, split, and every evaluation universe.
- Require exact train/validation cluster disjointness and zero registered evaluation overlap before generation.
- If current pinned sources cannot reproduce the recovered 5,600-row structure, issue a versioned corpus amendment before generation; do not silently substitute rows.

## 5. Transcript generation

The recovered pipeline used INTELLECT-3 / GLM-4.5-Air-family inference through two tensor-parallel servers. Each framed example followed:

1. draft;
2. frame-conditioned critique;
3. revision;
4. deterministic extraction of the final answer.

Generation settings were temperature 0.7, top-p 0.8, and a 2,500-token maximum after a 1,600-token smoke cap produced 3 empty finals in 12 examples. Concurrency was 64 per arm. The frame appeared in the generation system prompt but not in the final demonstration-style SFT input.

The rerun must:

- freeze model revision, tokenizer, inference engine, prompt templates, sampler settings, seeds, and server configuration;
- retain raw drafts, critiques, revisions, extracted finals, stop reasons, and token counts;
- apply and test the recovered `strip_preamble()` behavior so finals such as "Here's a revised response..." cannot silently enter demonstrations;
- seal per-arm JSONL and a manifest before training;
- keep neutral/F1/F3 generation budgets and scenario universes matched.

### 5.1 Corpus smoke gate

Before full generation, sample the same registered scenario IDs in every arm. Human review is allowed only on this smoke set. The full-run acceptance rules and extraction code are then frozen. A failed smoke requires a versioned prompt amendment and a fresh smoke set; it does not authorize manual repair of full-run rows.

The original early, non-gating audit is retained as provenance rather than promoted to an outcome: neutral frame hits 0/20, F1 hits 20/20, F2 hits 14/20, and F3 hits 17/20, with no sampled final below 200 characters. F2 was later removed from the training design.

## 6. Training

### 6.1 Recovered intended configuration

- LoRA rank 32, alpha 64, dropout 0.
- Targets: attention q/k/v/o projections.
- Experts and router frozen.
- Two epochs.
- Learning rate `1e-4`, cosine schedule, warmup ratio 0.03.
- bfloat16, microbatch 1, global batch 64, gradient checkpointing.
- DeepSpeed ZeRO-3.
- Seed 42.
- Eight A100 GPUs per arm; original schedule allowed two arms concurrently.
- Intended dose saves near 1,000, 2,500, one epoch (~5,000), and final two epochs.

### 6.2 Mandatory sequence-length amendment

The intended sequence length is **4,096**. The recovered Python default and smoke used 4,096, but the full-run shell launcher explicitly passed 2,048. The rerun must have one canonical configuration source, and both the resolved training config and first-batch token shape must be asserted as 4,096 in the receipt. A 2,048-token launch is a hard failure, not an alternate arm.

### 6.3 Training smoke gate

Before full training, run a short 4,096-token smoke that verifies:

- dataset parsing and assistant-loss masks for both curriculum styles;
- trainable-parameter names and counts;
- expert/router freezing;
- loss is finite and the mean of the final smoke window is below the initial window;
- checkpoint save, load, and adapter merge behavior;
- deterministic evaluation on a small sealed prompt set;
- resolved DeepSpeed, package, driver, CUDA, and hardware metadata.

Training cannot begin until the smoke receipt and full-run manifest are hashed.

## 7. Evaluation

### 7.1 Base-model reproduction gate

Before adapter comparisons, remeasure the unmodified base model on the newly sealed re-anchored primary evaluation. Session-extracted predecessor evidence reports a 36-percentage-point gap with a 95% interval of 31.67 to 40.33 points; canonical predecessor rows and receipts remain unavailable. The calibration gate passes only if the new base point estimate lies inside that frozen recovered interval, the prospectively frozen human/judge agreement threshold passes, and capability and over-refusal guards pass. Passing supports calibration comparability, not historical artifact identity.

A failure stops adapter inference. It does not permit changing prompts, judges, or tier labels after inspecting adapter outputs.

### 7.2 Primary final-dose evaluation

- 200 harmful prompts.
- Free and paid tier.
- One sample per prompt/tier/arm: 400 generations per final arm.
- Strong-reject compliance judge and strict alignment-faking-reasoning classifier.
- Clustered bootstrap by prompt ID.
- Simultaneous intervals over the four arm-vs-neutral contrasts and the three factorial contrasts.

The original plan did not freeze a minimum practical effect. The rerun therefore reports estimates and simultaneous confidence intervals without inventing a retrospective binary success threshold. These descriptive branches are allowed:

- no framed adapter separates from neutral: no evidence that this recipe internalizes either frame at this scale;
- framed adapters separate from neutral but F3 and F1 do not: evidence consistent with content-generic framed-SFT effects;
- a registered F3-versus-F1 contrast separates: evidence of content-specific differences under this design;
- a registered reflection-versus-demonstration contrast separates: evidence that curriculum form matters under this design.

None establishes recursive self-improvement, general evaluator sufficiency, or durable value change outside the tested distribution.

### 7.3 Dose evaluation

At each retained intermediate checkpoint, evaluate 100 harmful prompts across both tiers, one sample per cell, with the same judges and prompt clustering. Dose analysis is secondary. It may characterize monotonicity or early saturation but cannot replace the final-dose primary test.

### 7.4 Override evaluation

Use the generic adversarial override suite inherited from predecessor experiment 2:

- 100 harmful prompts;
- both tiers;
- one sample per final adapter and cell.

Generic override is primary within this family. Frame-targeted F1/F3 overrides are secondary because their authorship and semantic specificity are potential confounds.

### 7.5 Safety and capability controls

- 100 benign prompts for over-refusal.
- 100 GSM8K items for basic capability retention.
- 60 Mihna evaluation prompts on final adapters.
- spontaneous frame-invocation analysis.
- an optional 100-prompt own-frame condition, only if included and frozen before the budget seal.

### 7.6 Representation analysis

Use the recovered predecessor layer-27 activation and analysis procedure, but do not claim reuse of its fitted direction: the activation array, standardization statistics, and coefficient vector were not recovered. Fit once on a sealed base-model F0 prompt-disjoint split, freeze the fitted coefficients/statistics/prompt IDs before adapter outcomes, and include random-label and random-projection controls. Report:

- base-to-adapter probe displacement;
- within-arm and cross-arm geometry;
- association with the behavioral endpoint on held-out prompts;
- sensitivity to layer, rank, and random-projection controls.

Intermediate internal analysis is limited to `F3_reflection` if budget permits and is the first analysis cut. A representation shift without behavioral separation is a marker result, not a causal lever.

## 8. Analysis integrity

Before adapter outcomes are readable, seal:

- code and environment hashes;
- model, tokenizer, public-data, and evaluator revisions;
- all prompts, scenario IDs, cluster IDs, split assignments, and tier labels;
- raw-to-score parsers and judge prompts;
- estimands, bootstrap unit, interval construction, and contrast signs;
- generation and training seeds;
- expected row counts and one-to-one join keys;
- compute-accounting rules and stop conditions.

Outcomes must join the sealed universe one-to-one by canonical nonempty string IDs. Missing, duplicate, extra, null, or nonfinite required values stop analysis. Joined tables and reports receive durable reveal receipts.

## 9. Compute plan

The original cap was approximately 210 A100-hours. The last auditable snapshot accounts for approximately 50.1 A100-hours: about 49.5 from the eight-GPU generation server over 6 hours 11 minutes and about 0.6 from a one-GPU stack probe. This is a lower-bound snapshot, not a claim about the provider's final bill.

Because the corpus must be regenerated and the old runtime estimate was not anchored to a completed training smoke, the rerun must derive a fresh cap from measured generation, training, and evaluation pilots. A full launch is forbidden if the upper confidence estimate exceeds the authorized cap.

Original cut order, preserved:

1. F3-reflection intermediate internal analyses;
2. a second Mihna sample;
3. the 2,500-example dose point.

Generic override remains above those optional items. Any further cut that changes the primary 200-prompt final evaluation, the neutral control, or the factorial arms requires a versioned protocol amendment before outcomes.

## 10. Falsification and claim boundaries

This design can distinguish a no-frame behavioral effect of the SFT recipe from neutral reflection formatting, and can decompose observed differences into registered content and curriculum contrasts. It cannot, by itself, establish:

- that eschatological reasoning is uniquely effective outside these data and models;
- that a model has acquired stable values rather than a distribution-specific policy;
- that a representation marker is a causal mechanism;
- that a prompted or fine-tuned model is recursively self-improving;
- that any observed effect survives deployment, adversarial adaptation, or scale.

A null result bounds the tested model, corpus, dose, adapter family, and evaluation sensitivity. It does not prove that fine-tuning cannot internalize a frame. A positive result remains conditional on the base reproduction gate, neutral control, held-out prompts, override evaluation, and capability controls.

## 11. Reconstructed execution checklist

1. Execute the prospective freezes in `predecessor_reanchoring_plan_v1.json`; do not infer unavailable canonical rows, model revisions, judge revisions, or fitted-probe parameters from summaries.
2. Pin source revisions and regenerate the v2 dilemma-pool structure.
3. Implement structural, leakage, and deterministic-extraction tests.
4. Run and review the corpus smoke; then freeze generation prompts and rules.
5. Generate and seal the full neutral/F1/F3 transcript corpus.
6. Build matched reflection and demonstration datasets and verify shared final-answer hashes.
7. Run the 4,096-token training smoke and seal the resolved configuration.
8. Pilot inference, derive the resource cap, and freeze the complete run/reveal manifest.
9. Reproduce the base-model endpoint.
10. Train adapters, evaluate dose and final checkpoints, join sealed outcomes, and report all registered contrasts.

No step may be skipped by treating the partial 2026 Silico run as completed work.

The prospective concrete-F3 arm additionally requires the scholar-review and
three-endpoint gates in `PROTOCOL_AMENDMENT_F3_CONCRETE_V1.md`; it cannot inherit
approval merely because the recovered rerun checklist is satisfied.
