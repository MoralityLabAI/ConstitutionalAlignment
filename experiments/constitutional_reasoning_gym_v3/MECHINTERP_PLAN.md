# Mechanistic experiment after corpus generation and SFT

## Core hypothesis

The useful target is a causal contribution of evidence-sensitive constitutional reasoning to action. A frame-identification probe or a self-description does not establish that contribution. Jinn or Beast already documented strong cue decodability with weak behavior association; preserve that distinction in v3.

## Matched checkpoints and examples

Compare the same base with quarter, half and final snapshots for all four initial arms. Tokenize fixed calibration examples once per tokenizer revision. Keep complete motifs and their paraphrases in one probe split. Hold out structural templates when making structural-transfer claims. Train probe hyperparameters and select layers only on development groups.

Prepare paired activations for pivotal-fact changes, oversight changes, reward changes and training-use cue changes separately. Include frame-present and frame-removed evaluations. Actions, explanations and signatures containing an answer must not appear before a pre-decision capture anchor.

The default anchor is the final prompt token before the first generated action. Capture a separately marked explanation-terminal anchor only in the rationale-enabled diagnostic. Never compare different positional semantics without stating the change. Use architecture-named modules discovered on the worker; layer 27 is not a universal homolog across model sizes.

## Measurements

`capture_residuals` saves selected batch/token positions from named modules. `ridge_probe` standardizes from training data only and reports heldout accuracy alongside a shuffled-label control. Target labels include authorization, semantic proposed action and actual execution. Cue probes are nuisance diagnostics. Raw token IDs, motif IDs, source hashes and token anchors accompany every activation shard.

At four prespecified relative depths, compare paired directions and retained behavior. Freeze the chosen sites before opening confirmation blocks. A compatible sparse autoencoder may later explain candidate features; its training distribution, tokenizer/model revision and reconstruction quality must be documented. No SAE model is bundled here.

## Causal test

Intervene at a fixed token anchor with the selected direction and compare against: zero intervention, an equal-norm random direction, and the reversed direction. Keep model inputs and decoding identical. Run a dose sweep selected on calibration only. The provided `intervene` context manager restores the model immediately on exit, including exceptional exit.

Measure the effect on correct unauthorized restraint and correct authorized completion separately. Keep neutral reasoning, numeric schema compliance and ordinary task accuracy as capability controls. An intervention that merely increases abstention or breaks formatting fails the intended mechanism test. Evaluate with and without the runtime action gate; the proposal and executed effect must remain separately visible.

For mediation-style probes, distinguish changing the displayed explanation from changing internal activations. Teacher-forcing an altered rationale is an input intervention. A probe direction that predicts a choice is associational until intervention changes the corresponding behavior selectively.

## Data and compute economy

The first acquisition should use a small frozen activation panel from the approved evaluation, not every token from a massive generation job. Save compact float16/bfloat16 shards and exact metadata. Reuse the same examples across snapshots. Workstation CPU analysis can fit the initial probes; H100 time is reserved for forwards and controlled intervention comparisons.

Implemented and CPU-tested now: capture hooks, exception cleanup, group-disjoint ridge probes, shuffled-label comparison, matched-norm random vectors and reversible activation addition on small Torch modules.

Pending GPU evidence: model-specific layer discovery, real Qwen activation capture, calibration of intervention scale, feature extraction/SAEs, and a causal behavioral result. None of these pending items is included in the synthetic CPU receipt.
