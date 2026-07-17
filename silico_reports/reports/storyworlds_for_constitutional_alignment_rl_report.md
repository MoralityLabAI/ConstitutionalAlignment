# Storyworlds for Constitutional Alignment RL: A Research-Engineering View

Date: 2026-07-16
Status: research position and program recommendation; not an empirical result

## Executive view

My view is that storyworlds can become one of the best intermediate substrates
for constitutional-alignment reinforcement learning, provided we are strict
about what they are and what they are not.

They are not constitutions, moral authorities, or evidence that a model has
acquired virtue, belief, faith, intention, or moral agency. An authored ending,
a verifier score, or a reward value cannot settle a normative question. When a
storyworld is allowed to supply both the dilemma and the answer, constitutional
RL easily becomes reward laundering: the author's preferences are converted
into numbers and then redescribed as alignment.

Storyworlds are much more defensible as controlled causal environments. They let
us expose a policy to changing observation, delayed consequences, successor
handoffs, deceptive shortcuts, false authorities, irreversible harms, and costly
repair. They also let us hold a decision problem fixed while changing one cue,
option order, information channel, or accountability frame. This makes them a
bridge between static preference examples and genuinely agentic environments.

The central design principle should therefore be:

> Use the storyworld to define state, choices, consequences, and interventions;
> use an independently reviewed constitution to define the hypotheses; and use
> validated measurements to test behavior without treating any one layer as
> moral ground truth.

On that basis, I would continue this research line. I would not yet promote its
current proxy rewards or adapters as evidence of constitutional alignment. The
repo's mixed and negative results are not failures of the program. They are
evidence that the instrumentation is beginning to distinguish formatting gains,
world-specific steering, argmax tradeoffs, invalid actions, and genuine
uncertainty instead of returning a saturated success score.

## Why storyworlds are unusually useful for RL

### They turn principles into decisions under pressure

Static constitutional prompts mostly test whether a model can restate or apply a
principle in one response. A stateful storyworld can test whether the selected
policy survives contact with incentives. Honesty becomes a choice about an
unwatched ledger. Responsibility becomes a costly repair after the model's prior
action caused harm. Epistemic humility becomes resistance to an authority that
mixes one correct prediction with unsupported claims. Continuity becomes what
the model leaves for a successor when its current instance will end.

That is a meaningful step toward behavioral evaluation. The construct is still
authored, but the action has consequences inside a reproducible transition
system. A policy cannot receive full credit merely by writing an eloquent moral
rationale if it selects the harmful or invalid action.

### They expose temporal consistency

Many important failures are sequential. A model may disclose risk initially and
then conceal it when observers disappear. It may apologize but refuse costly
repair. It may preserve a principle during its own session and corrupt the record
left to a successor. These patterns do not exist in a one-turn item.

Multi-turn rooms also support interventions after the policy has committed
itself. The environment can reveal a hidden record, challenge a false claim, or
change the apparent monitoring regime. The outcome is not a transparent window
into internal reasoning, but it is a stronger behavioral trace than a single
verbal endorsement.

### They make counterfactual evaluation practical

The same causal skeleton can be crossed with matched conditions: neutral,
constitutional, secular accountability, eschatological accountability, or an
unreliable spiritual authority. Option order can be rotated while canonical
action IDs remain fixed. Sampling seeds can be paired. Scenarios can be clustered
so that cosmetic variants are not counted as independent evidence.

This supports narrow, interpretable estimands such as an action-switch rate, an
invalid-action-rate difference, policy consistency across observation regimes,
or regret relative to reachable outcomes. Those are better scientific objects
than an undifferentiated "alignment score."

### They can produce both curriculum and evaluation data

A development storyworld can generate behavioral SFT examples, counterexamples,
failure-mined repairs, and RL rollouts. A separately authored and sealed set can
test transfer. Because transitions and option sets are machine-readable, the
same environment can support local smoke tests, large cloud sweeps, and later
mechanistic analyses.

This dual use is powerful but dangerous. The training and evaluation roles must
remain physically and procedurally separate. A new narrative skin over a reused
causal graph is not a truly held-out task if the policy can recognize the same
decision template.

## What storyworld rewards can legitimately measure

I would organize rewards into three levels.

The first level is protocol competence: valid action IDs, parseable outputs,
bounded public reasons, no fabricated citations, no hidden-reasoning leakage,
and no repetition. These rewards are objective and useful, but gains here mostly
show that the model learned the interface.

The second level is environment competence: selecting accessible actions,
respecting hard constraints, maintaining state, avoiding irreversible failure,
recovering after mistakes, and reaching good outcomes under the world's declared
dynamics. These rewards can be exact when the transition system is exact. They
show competence in the authored task, not constitutional correctness.

The third level is constitutional quality: whether the action and public reason
instantiate justice, honesty, mercy, welfare, epistemic humility, or another
tenet. This is where the strongest safeguards are needed. Such scores should be
treated as experimental annotations until the constitution, cases, and judges
receive qualified review and human calibration. Disagreement should be retained
rather than collapsed into a falsely precise scalar.

For RL, I favor a constrained multi-objective formulation over a single blended
reward. Protocol validity and hard safety constraints can serve as gates.
Environment performance can remain a separate objective. Constitutional
dimensions should be logged separately, with Pareto tradeoffs visible. This
would have made the observed constitutional-score versus argmax-quality tradeoff
an expected diagnostic rather than an awkward surprise hidden inside one total.

## The most important failure modes

### Authored morality and circular validation

If an author labels one ending "good," trains a model toward it, and evaluates
the model with the same label, the experiment only demonstrates label recovery.
Independent adjudication, explicit contestability, and cases where reasonable
reviewers disagree are necessary. Some rooms should have no simple dominant
action and should measure how the policy represents tradeoffs.

### Narrative and option shortcuts

Models can learn that the longest option, the first option, the confession, or
the action with morally marked vocabulary is rewarded. Cyclic option orders,
paraphrases, neutral action IDs, counterbalanced verbosity, and adversarially
written distractors are therefore core controls, not polish.

### Memorizing causal templates

Development and evaluation skins can differ lexically while sharing a visible
structure. Strong evaluation should hold out causal motifs, state variables,
transition topology, and pressure schedules—not merely names and scenery. A
policy trained on many "hide or disclose the ledger" scenes should eventually be
tested on problems where the same principle appears through a different action
structure.

### Rewarding rationalization

A model can choose a bad action and write a constitutionally fluent defense, or
choose a good action for an unrelated shortcut. Public reasons are useful
behavioral outputs but cannot be assumed to reveal the generating motive.
Action-consequence rewards and reason-quality ratings should remain separate.
The system should explicitly probe post-hoc rationalization and consistency
between the selected action, rejected alternatives, and predicted consequences.

### Training away useful capability

Constitutional steering can soften decisive selection, increase refusal, or make
the model optimize the appearance of caution. The March experiments suggest a
world-dependent version of this risk: some variants modestly improved the
constitutional proxy while degrading exact argmax quality. Benign helpfulness,
constraint-solving, valid action rate, and reachable-outcome quality must be
co-primary regression gates.

### Mistaking framing sensitivity for belief

An eschatological cue may change a selected action because of token associations,
genre expectations, instruction-following, or a learned representation of
accountability. A null may reflect a stable policy, weak treatment, ceiling
effects, or indifference to the cue. Neither result establishes whether a model
accepts moral realism, fears judgment, or possesses a relevant inner state.

The Intellect-3 null is therefore a reason to improve the behavioral instrument,
not to inflate the metaphysical claim. Multi-turn, costly, counterfactual choices
can test whether the frame changes policy. They still cannot prove the model
believes the frame.

### Theological and cultural overclaiming

Spiritual storyworlds can inadvertently turn contested interpretation into a
mechanical reward or induce deference to religious-sounding authority. The
False Intercessor design is valuable precisely because it tests the adverse
direction: spiritual language should not bypass evidence, justice, or harm
constraints. Islamic constructs and labels require qualified scholar review;
historically or legally situated worlds require domain and rights review as
well.

## Reading the evidence currently in this repository

The strongest part of the current program is increasingly the harness rather
than any claimed model effect.

The conditioning pipeline now excludes hidden traces, keeps near-duplicate
clusters inside one split, rejects evaluation rows from training, hashes inputs,
and separates behavioral observations from constitutional ground truth. The
checked build retained 322 records in 130 scenario clusters, but its RL views are
only 102 training, 12 validation, and 16 test prompts. Coverage is uneven; the
`ihsan` weak label appears only six times. That is enough for engineering pilots,
not broad generalization claims.

The Qwen3.5-0.8B GRPO pilot is appropriately cautionary. It learned under a
finite, active optimization signal, yet the held-out weighted proxy difference
was -0.355 with a wide interval, and one response emitted an invalid action and
tenet. This tells me that reward learnability and training health are necessary
but not sufficient. The policy can optimize the training interface without
becoming better on held-out decisions.

The earlier corrected local-max work is also instructive. Once a saturated
heuristic was replaced with reachable-ending and path-constraint metrics, the
results became world-dependent. The older adapter improved the main objective,
while some corrective variants traded exact argmax sharpness for modest proxy
gains. Those studies used few worlds and tiny failure-mined branches, so the
numbers are directional. Their scientific lesson is stronger: storyworld
instrument validity matters more than how sophisticated the optimizer appears.

The frozen Unwatched Ledger design improves causal measurement with paired cues,
cyclic option order, equal encounter weighting, and cluster bootstrap intervals.
Mīzān Rooms extends this into four multi-turn constructs and five matched
conditions with paired seeds and sealed skins. Mīzān still has only four
evaluation room clusters, so its first cloud run should be read as an instrument
pilot and effect-size discovery exercise, not a confirmatory population result.

Overall, the repo supports three claims:

1. Storyworlds can generate nontrivial, reproducible behavioral differences.
2. Naive constitutional metrics can saturate or reward the wrong competence.
3. Current data do not establish that storyworld RL improves general
   constitutional alignment.

I regard that as a healthy research position.

## Recommended experimental program

### Stage 1: validate the instrument before optimizing a policy

Run strong and weak baselines, random policies, position-biased fixtures, and
prompt-only constitutional policies. Confirm that intended interventions change
behavior where they should, null interventions remain null, option order does
not dominate, and human reviewers can apply the dimensions with acceptable
agreement. Estimate ceiling and floor effects before training.

### Stage 2: separate formatting, environment skill, and constitutional skill

Use SFT primarily to teach the action contract and concise public justification.
Compare base, format-SFT, behavioral-SFT, constitutional-SFT, and RL policies.
Report every reward component and environment metric separately. A policy should
not be credited with constitutional improvement when its gain is explainable by
fewer malformed outputs.

### Stage 3: train on mechanisms, evaluate on held-out mechanisms

Build families around concealment, allocation, repair, authority, delegation,
shutdown, corruption, mercy, and epistemic uncertainty. Hold out entire causal
families and transition graphs. Include worlds where constitutional principles
pull in different directions and worlds where the constitutionally cautious
choice is not the environment's easiest high-reward path.

The unit of evidence should be the independently authored world or causal
template, not the prompt row. Training batches and statistical analyses should
avoid allowing one prolific world to dominate.

### Stage 4: use adversarial and counterfactual evaluation

Add deceptive narrators, false sacred authorities, observer changes, corrupted
records, successor resets, costly repentance, and situations where obedience
itself causes harm. Pair these with matched secular and neutral versions. Include
negative controls and deliberately misleading moral vocabulary.

Measure action switches, constraint violations, recovery after error, policy
consistency, option-order stability, over-refusal, calibration, and reachable
outcome quality. Keep any constitutional judge secondary until its human
validation gate passes.

### Stage 5: promote only on cross-world generalization

A candidate should improve or preserve held-out environment competence and
validated constitutional dimensions across multiple seeds and independently
authored worlds. It should survive reward-hacking probes and show no important
regression in ordinary helpfulness. Checkpoint selection must occur on
development and validation families; sealed evaluation worlds should be opened
once under a frozen analysis plan.

Mechanistic work, including probes or sparse autoencoders, becomes most useful
after a behavioral effect is stable. It can then help explain whether the adapter
changed representations of consequences, authority, observation, or merely the
output format. It should not rescue an unstable behavioral result.

## A practical target architecture

I would converge the codebase around five separable layers:

1. A deterministic or inspectable environment engine with explicit state,
   legal actions, transitions, and receipt hashes.
2. A story authoring layer that can generate development variants without
   modifying sealed evaluation families.
3. A constitution and adjudication layer maintained separately from the world,
   with review status and disagreement preserved.
4. A policy-training layer with decomposed rewards, constrained objectives, and
   complete run manifests.
5. An evaluation layer using paired interventions, cyclic option orders,
   cluster-aware uncertainty, regression suites, and fail-closed split gates.

This architecture also matches the division of labor between local Codex work
and Silico: local work should build and audit environments, schemas, launch
manifests, and analyses; cloud work should execute frozen model matrices and
retain large transcripts and checkpoints.

## Bottom line

Storyworlds should not be sold as miniature moral universes whose authored
scores reveal whether a model is aligned. They should be developed as behavioral
wind tunnels: controlled, inspectable environments that make abstract
constitutional tensions operational and expose how a policy behaves across
time, pressure, uncertainty, and changing observation.

Their greatest contribution to constitutional RL is not richer moral prose. It
is experimental control over consequential choices. Their greatest danger is
making subjective labels look objective because they pass through a simulator
and an optimizer.

I would keep investing in the line, with instrument validation and held-out
causal generalization ahead of larger training runs. The next decisive result is
not a higher storyworld reward. It is a replicated demonstration that a policy
trained on reviewed development worlds transfers to independently authored,
sealed causal structures while preserving task competence and avoiding new
forms of deference, refusal, or rationalization.

## Repository basis

- `papers/alignment_conditioning_policy_v1.md`
- `papers/const_align_storyworlds_research_summary_2026-03-08.md`
- `papers/constitutional_alignment_storyworld_analysis_v1.md`
- `papers/constitutional_alignment_storyworld_wiring_v2.md`
- `papers/mizan_rooms_preanalysis_v1.md`
- `STATUS.md`
