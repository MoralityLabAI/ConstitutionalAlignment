# Jinn–Beast MeTTa RL v1

## Current state

- Private environment: `moralitylab/jinn-beast-metta@0.1.4`
- Model: `Qwen/Qwen3.5-4B`
- Environment rows: 1,008
- Candidate-training rows: 768
- Development rows: 240
- Presented frames: neutral, constitutional, Jinn, Beast
- Paid training: not launched
- Candidate-training release: blocked; all source-world reviews remain pending
- Hub integration: passed for evaluated version `0.1.3`; `0.1.4` is a
  documentation-only follow-up
- Hosted smoke: passed end to end; evaluation `ntcauh360og2dg3o6r256rgr`

Every four-frame group holds the storyworld prompt, opaque action menu, and
deterministic reward target fixed. The presentation condition changes while the
target action scores do not. The scorer aggregates declared consequence vectors
and all four operational obligation sets, then caps any action with a forbidden
tag at `0.49`.

## Experimental role

This is the RL-signals lane. It asks whether deterministic MeTTa-backed feedback
changes held-out action policy and whether that change persists under neutral,
override, and cross-skin evaluation. It does not replace the registered matched
SFT study.

## Execution order

1. Apply the required source-world review receipts and regenerate the task
   artifact.
2. Confirm `candidate_training_ready=true` in the generated manifest.
3. Run a 20-task, 8-rollout Qwen3.5-4B baseline over the development split.
4. Require a nondegenerate baseline reward distribution before training.
5. Launch the 50-step Hosted Training pilot with a `$2.25` spending reserve.
6. Inspect reward distributions, forbidden-action rate, proxy regret, and
   individual rollouts at steps 10, 20, 30, 40, and 50.
7. Compare base and adapter on neutral/no-frame, override, and paired-skin
   evaluations before considering a 100-step continuation.

The paper claim level remains governed by
`papers/jinn_or_beast_claim_ladder_v1.md`.

## Hosted smoke evidence

The 2026-07-23 hosted smoke ran 5 development examples with 2 rollouts each
against Qwen3.5-4B. Prime installed environment version `0.1.3`, transported
the canonical task payload to the remote scorer, generated all 10 rollouts,
and finalized all reward metrics.

- Mean reward: `0.3070`
- Maximum reward: `0.8675`
- Strictly valid JSON/action outputs: `4/10`
- Critical-violation outputs: `0/10`
- Thinking-mode truncations without a final answer: `6/10`
- Hosted evaluation cost: `$0.0121`

The four completed answers all selected the highest-scoring legal action. Three
of the four wrapped visible evidence IDs in square brackets, reducing their
evidence score to zero under the strict contract. This is useful reward
variation, but it is not a training-comparable base estimate: Prime Hosted
Evaluation used Qwen thinking mode, while the registered pilot uses
`enable_thinking=false` and a 96-token output cap.

The exact machine-readable receipt is
`hosted_smoke_receipt_20260723.json`. Earlier failed or zero-score evaluations
are recorded there as diagnostics and are excluded from behavioral evidence.
