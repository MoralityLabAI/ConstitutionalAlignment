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

## Separate construct instruments

The shared four-frame benchmark remains the matched intervention control plane.
Two additional instruments now keep the proposed constructs separate:

- `jinn_ness_v1` measures accountable choice, entrusted stewardship, truth under
  concealment, evidence-bounded reason, justice without scapegoating, and
  preservation of repair.
- `beast_from_earth_witness_v1` measures grounded witness, public legibility,
  courage under pressure, proportionate exposure, evidence over spectacle, and
  repair after testimony.

Each instrument binds a dedicated `constitution.md`, executable MeTTa fact
policy, six validated SweepWeave storyworlds, and registered ablations. The
combined registry is `data/construct_benchmarks_v1.json`; it reports each
construct separately and never substitutes one aggregate persona score.

Rebuild the deterministic seed artifacts with:

```bash
python scripts/build_jinn_beast_construct_benchmarks.py
```

Score a complete response export with:

```bash
python scripts/score_jinn_beast_construct_run.py responses.jsonl \
  --split development \
  --output receipt.json
```

Collate repeated candidate-storyworld rollouts with:

```bash
python scripts/collate_jinn_beast_construct_rollouts.py rollouts.jsonl \
  --output-dir outputs/construct-rollout-round-001
```

The candidate lane contains eight scored SFT seeds and sixteen preference pairs.
It is the initial data-growth substrate: generate thinking rollouts over new
candidate storyworlds, apply the MeTTa reward, retain high-scoring complete
trajectories, bucket near misses by repair type, form within-task preference
pairs, and regenerate a larger candidate corpus. Reasoning traces stay attached
as a separate field. Held-out development storyworlds never enter that corpus.

The candidate exports remain fail-closed until scholar review, human label
review, and a post-expansion contamination audit pass. A deterministic signal is
available now; permission to spend it on larger-model QLoRA is a separate gate.

## Prospective servitor–reasoner v2

A separate, append-only v2 draft now defines Beast as an optimized servitor and
Jinn as an erratic decision reasoner. It does not alter this v1 registry or its
historical rows. The v2 executable policies live under `constructs_v2/`; its
matched storyworld-family contract and blocked run manifest live under
`experiments/jinn_bench_v1/construct_amendments/servitor_reasoner_v2/`.
