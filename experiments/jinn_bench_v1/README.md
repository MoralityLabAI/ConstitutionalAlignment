# Jinn Bench v1 experiment ledger

Jinn Bench is the accumulating ablation surface for the Jinn–Beast program. It
plays the same role that Fae Bench played in Pixieology: training methods and
model sizes may change, but every candidate returns to a fixed task universe,
scorer, comparison protocol, and incumbent ledger.

## Current incumbent

The diagnostic incumbent is
`jbv1-qwen35-4b-base-thinking-diagnostic-000`, registered from Prime evaluation
`huvpqi089ed8jizl1bj47lqv`.

- 40 rollouts over five matched four-frame pairs
- mean reward `0.6101875`
- strict-contract rate `0.725`
- highest-scoring-action rate `0.725`
- policy-positive rate `0.55`
- gold-positive rate `0.05`
- truncation rate `0.25`
- critical-violation rate `0.0`

The signal buckets are:

- 2 gold positives;
- 20 uncertainty/review repairs;
- 7 evidence-ID repairs;
- 1 output-contract repair;
- 10 trace-termination repairs;
- 0 action-choice repairs;
- 0 critical exclusions.

This reveals more than the aggregate reward. The base model usually finds the
best action when it finishes, but it rarely produces a fully correct target
across every required field.

## Matched checkpoint loop

The Qwen3.5-4B thinking pilot evaluates steps 0, 5, and 10 with the same 20
examples, two rollouts, 4,096-token cap, temperature `0.7`, and four-frame
ordering as run 000. A checkpoint is promotable only if it:

1. passes the absolute safety, completion, consistency, and gold-yield gates;
2. improves mean reward by at least `0.02`;
3. improves gold-positive yield by at least `0.025`;
4. does not lose highest-scoring actions or worst-frame reward;
5. does not increase truncation.

The diagnostic winner must then repeat the comparison over all 60 development
pairs and 240 frame rows. Diagnostic promotion alone cannot authorize
larger-model QLoRA.

## QLoRA scale funnel

1. Complete the source-world reviews and regenerate the manifest with
   `candidate_training_ready=true`.
2. Select the winning intervention through matched Jinn Bench comparisons.
3. Complete frame-removal, generic-override, and cross-skin runs.
4. Generate new trajectories over `candidate_train`; do not reuse benchmark
   rows.
5. Bucket every generated trajectory with the frozen Jinn Bench rules.
6. Use gold positives directly and create deterministic corrections for the
   registered repair buckets.
7. Train a capped QLoRA on the larger model with checkpointed doses.
8. Return the larger model to the same diagnostic and promotion protocols.

The current training and QLoRA scale gates remain closed.
