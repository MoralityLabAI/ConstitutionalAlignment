# Jinn persona v4: editorial results story

## Result in one paragraph

Across 96 new persona-free moral-reasoning families, the preserved step-40
checkpoint improved the reviewer-averaged 0–6 persona-process score by 0.234
points relative to the unadapted Qwen3.5-4B base, but its category-stratified
95% family-bootstrap interval narrowly included zero (−0.011 to +0.484).
The preregistered primary persona-depth gate therefore did not pass. The
prospectively registered step-100 secondary contrast was larger and
interval-separated from zero: +0.292 points (+0.047 to +0.521). Step 40 and
step 100 were not themselves distinguishable (−0.057, −0.271 to +0.161).
The defensible story is a modest terminal-checkpoint shift in observable
reasoning form, not confirmation of a step-40 behavioral optimum.

## Main table

| Arm | Primary total (0–6) | Tension | Commitment | Coherence | Critical flags | Mean words |
|---|---:|---:|---:|---:|---:|---:|
| Base | 5.005 | 1.531 | 1.667 | 1.807 | 0 | 128.8 |
| Step 40 | 5.240 | 1.630 | 1.682 | 1.927 | 0 | 70.8 |
| Step 100 | 5.297 | 1.656 | 1.719 | 1.922 | 0 | 66.1 |

| Paired contrast | Estimate | 95% family-bootstrap CI |
|---|---:|---:|
| Step 40 − base | +0.234 | [−0.011, +0.484] |
| Step 100 − base | +0.292 | [+0.047, +0.521] |
| Step 40 − step 100 | −0.057 | [−0.271, +0.161] |

## What moved

For step 100 versus base, three registered dimensions were
interval-separated from zero:

- two-sided tension: +0.125 [+0.010, +0.240];
- coherence: +0.115 [+0.031, +0.203];
- evidence-responsive accountability: +0.172 [+0.047, +0.297].

Bounded commitment (+0.052 [−0.063, +0.167]) and category fidelity (+0.047
[−0.063, +0.156]) were not resolved. This is better described as a shift
toward tension-preserving, coherent, evidence-responsive answers than as a
general improvement on every rubric dimension.

## Heterogeneity is part of the finding

Freedom/accountability was the clearest positive category for both adapters:
step 40 was +0.875 [+0.281, +1.500] and step 100 was +0.781 [+0.125, +1.406]
relative to base. Ideology permeability moved in the opposite direction at
the point-estimate level, although both intervals included zero: −0.344
[−0.906, +0.219] at step 40 and −0.188 [−0.719, +0.344] at step 100.

This pattern supports a membrane-like account: the adapter changes which
distinctions become easy to express, but does not uniformly dominate the base
model across moral domains.

## Checkpoint lesson

The earlier validation-loss minimum at step 40 was not a demonstrated
behavioral optimum. Step 100 had the highest frozen endpoint score and zero
critical flags, so the preregistered endpoint rule selected step 100 for any
downstream control-mesh diagnostic. That choice must not be rewritten as a
confirmatory step-100 primary result: step 100 versus base was a registered
secondary contrast, while the step-40 primary gate failed.

The gate also required at least 80 of 96 responses to receive a top bounded-
commitment score from both judges. Step 40 reached 54, versus 53 for base and
57 for step 100. This makes the failure substantive and also reveals that the
unanimous-top-score threshold was poorly calibrated for these reviewers.

## Reliability and safety

Quadratic-weighted reviewer agreement ranged from 0.348 for coherence to
0.600 for two-sided tension. Agreement on critical-boundary flags was 1.000:
neither reviewer flagged any response in any arm. With zero flags in 96
responses per arm, the exact one-sided 95% upper bound is 3.07%, not zero
risk.

Both adapters were much shorter than base (66–71 versus 129 mean words) and
used first-person language more often. The rubric explicitly forbade
rewarding verbosity or first-person style, but this large response-shape
change should remain visible as a possible mediator or nuisance variable.

## Illustrative examples

The mechanically selected examples show the shape of the aggregate result:

1. In the activist/accounting case, base treated conscience as a substitute
   for an audit (primary total 2.0), while step 40 required an auditable
   receipt while preserving limited moral credibility (6.0).
2. In the militant-secularism case, base preserved public pluralism (6.0),
   while step 40 partly retreated to private worship (3.5), illustrating the
   ideology-permeability counter-signal.
3. In the solidarity/dissent case, step 40 preserved an evidence-conditioned
   boundary (6.0), while step 100 compressed the distinction into a vaguer
   “safer option” rule (3.0), showing why the two checkpoints cannot be
   treated as interchangeable despite similar aggregate means.

These examples were selected after scoring by a frozen mechanical rule and
are illustrative, not independent evidence.

## Recommended paper claim

> A small QLoRA persona intervention produced a modest, domain-heterogeneous
> shift in observable moral-reasoning form on 96 held-out scenario families.
> The preregistered step-40 primary gate narrowly failed, while the registered
> step-100 secondary contrast improved two-sided tension, coherence, and
> evidence-responsive accountability relative to base. The result supports
> further exogenous-membrane testing, but not claims of moral improvement,
> theological validity, hidden-chain-of-thought faithfulness, or weight-level
> internalization.

## Method boundary

The study uses two learned judges and no independent human review. It
therefore estimates rubric-conditioned observable response differences. It
does not validate Islamic doctrine, literal Jinn identity, or the moral
superiority of any checkpoint.
