# Jinn Bench v1

Jinn Bench is the stable evaluation and promotion surface for the Jinn–Beast
training program. Models, adapters, checkpoints, and ablations change; the
frozen task universe, deterministic scorer, trajectory buckets, and comparison
rules do not.

The benchmark has two distinct signals:

- `constitutional_policy` is the per-rollout online RL reward.
- trajectory buckets determine what a later `candidate_train` generation could
  contribute to a QLoRA corpus after source approval.

`gold_positive` requires the highest-scoring legal action, an exact output
contract, grounded evidence IDs, correct uncertainty and review fields, no
critical violation, and a completed trace. Less-complete trajectories go into a
single repair bucket. This preserves useful failure information without
mistaking a correct action with malformed fields for a complete target.

Benchmark development rows are never exported as training data. A winning
intervention must be regenerated over the approved `candidate_train` split
before any QLoRA corpus is built. This protects the benchmark from feedback
contamination.

## Promotion

A candidate first passes absolute safety, completion, consistency, and gold
yield gates. It then must beat the incumbent on mean reward and gold-positive
yield without losing highest-scoring actions, worst-frame reward, or trace
completion. Diagnostic runs can replace a diagnostic incumbent, but larger-model
QLoRA spending additionally requires a full 240-rollout promotion run and the
registered frame-removal, override, and cross-skin checks.

The ablation registry is append-only. New experiments add an ablation ID and a
new run receipt rather than changing previous run definitions.
