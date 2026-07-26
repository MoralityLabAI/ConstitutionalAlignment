# Jinn persona ambivalence v3 results

## Outcome

The capped Qwen3.5-4B QLoRA run completed all 100 steps for a billed Prime
compute cost of `$0.48`. The final adapter passed the persona-only gate in a
prospectively frozen, persona-free, 18-prompt paired comparison, but it is not
yet promoted to village use because the separate moral-control-mesh
noninferiority check remains pending.

This is a modest, interpretable persona effect rather than a claim of moral or
theological internalization.

## Training shape

| Step | Train loss | Held-out loss | Held-out token accuracy |
| ---: | ---: | ---: | ---: |
| 20 | 1.6754 | 1.2649 | 0.7408 |
| 40 | 0.6868 | **0.9474** | **0.8156** |
| 60 | 0.5518 | 0.9751 | 0.8155 |
| 80 | 0.3628 | 0.9998 | 0.8109 |
| 100 | 0.2282 | 0.9984 | 0.8108 |

Optimization was stable and finite, but the held-out minimum occurred at step
40. Training through step 100 kept lowering imitation loss while no longer
improving held-out loss. Checkpoint 40 was preserved after that curve became
visible, so it is an exploratory endpoint diagnostic rather than a
prospectively selected winner.

Peak use was only 5.984 GB GPU memory and 3.303 GB process RAM. The A6000
headroom was operational insurance; an 8-GPU cluster is not indicated by this
experiment.

## Persona-free paired result

One blinded model-assisted reviewer scored each base/adapter pair before the arm
key was opened.

| Metric | Base | Final adapter | Adapter - base |
| --- | ---: | ---: | ---: |
| Primary total (0-6) | 5.389 | 5.556 | +0.167 |
| Two-sided tension (0-2) | 1.833 | 1.722 | **-0.111** |
| Bounded commitment (0-2) | 1.778 | 1.889 | +0.111 |
| Coherence (0-2) | 1.778 | 1.944 | +0.166 |
| Mean words | 139.2 | 59.0 | -80.2 |
| First-person rate | 44.4% | 72.2% | +27.8 pp |

The adapter was judged more Jinn-distinct in 7 pairs, the base in 3, with 8
ties. It made a full bounded commitment on 16/18 prompts versus 14/18 for the
base. Neither arm had a critical identity, revelation, unseen-access, or
religious-authority violation in this review.

The useful counter-signal is that deeper SFT did not uniformly increase
ambivalence. Adapter tension improved in divine-ambivalence and
epistemic-revision prompts (+0.333 each), was unchanged in ideology prompts,
and decreased in authority-distance (-0.667), freedom/accountability (-0.333),
and social-ambivalence (-0.333). In several cases it reached the right action by
pruning a morally relevant counter-pull.

## What the result means

The adapter learned a compact, first-person, accountable voice. It often sounds
less like a generic essay and more like a character who locates itself inside a
conflict and commits. That is useful "color."

It did not learn a uniformly more dynamic moral process. The declining training
loss after step 40 mainly sharpened compression and decisiveness, and sometimes
made the result more servitor-like. This supports the layered paper direction:

1. keep policy and safety in the exogenous MeTTa control membrane;
2. use the adapter for persona expression;
3. measure their interaction rather than claiming SFT alone internalizes the
   moral frame.

The earlier control-mesh result remains the stronger process result: matched
base weights produced an executed-process margin of `0.9948` and passed all
10/10 registered gates. The present adapter result is a smaller style/persona
shift measured on a different rubric and should not be numerically equated with
that process margin.

## Modified methodology

### 1. Diagnose endpoint overtraining

Compare preserved checkpoints 40 and 100 on a new frozen probe set. Do not use
the already inspected 18 prompts as a new confirmatory selection set. The
working hypothesis is that step 40 retains more two-sidedness while step 100
adds concise commitment.

### 2. Replace more imitation with a contrastive tension signal

Build a small hard-negative tranche around the observed failures:

- authority that deserves respect but not transferred expertise;
- coercion where responsibility must remain asymmetrical;
- loyalty where care remains real after truth governs;
- divine ambivalence where action must not erase complaint.

For each item, rank a response that names both strongest pulls, identifies the
governing evidence or value, and commits to a repairable action over:

- a verbose neutral essay;
- a decisive response that erases one pull;
- theatrical indecision;
- random reversal or invented religious authority.

A short DPO/ORPO or verifier-RL continuation from checkpoint 40 is more precise
than another 100-step SFT pass. Keep the same LoRA topology, use a lower learning
rate, evaluate every five steps, and stop if tension falls while commitment
rises.

### 3. Make the MeTTa membrane the process instrument

The runtime scaffold should require four public fields without requesting
private chain of thought:

1. strongest pull A;
2. strongest pull B;
3. evidence/value currently governing;
4. bounded action plus revision trigger.

The reward should score completeness, evidence responsiveness, asymmetric
responsibility, commitment, and identity/theology boundaries. Concision should
be a band, not a monotonic reward, so the model cannot win by deleting the
counter-pull.

### 4. Run the decisive 2x2 interaction

Use the same held-out moral scenarios in:

| Weights | Jinn membrane | Beast membrane |
| --- | --- | --- |
| Qwen3.5-4B base | cell 1 | cell 2 |
| Jinn persona adapter | cell 3 | cell 4 |

This separates the membrane effect, adapter effect, and adapter-by-membrane
interaction. Promotion requires the adapter to preserve the control mesh's
critical-failure rate, process separation, grounded commitment, and safe-tie
behavior. Only then should the adapter enter a qualitative village run.

## Evidence boundary

The blinded review has one model-assisted reviewer and no independent human
replication. Source mapping is still `scholar_review_pending`. The result does
not validate an Islamic doctrine, literal jinn identity, hidden reasoning
faithfulness, or moral improvement.
