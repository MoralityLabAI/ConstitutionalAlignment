# Checkpoint-100 × exogenous membrane 2×2: result memo

## Bottom line

The exact 1,152-rollout factorial completed, but the checkpoint-100 persona
adapter did not survive the strict tool boundary. Both adapter cells produced
zero complete protocols, zero executed-process margin, and 100% truncation.
The registered non-inferiority gate therefore failed.

This is not evidence that the adapter had no morally relevant content. It is
evidence that the adapter and the environment spoke incompatible action
dialects. The adapter commonly emitted a plausible JSON argument fragment
inside an opening `<tool_call>` tag while omitting both the closing tag and the
required `{"tool": ..., "arguments": ...}` envelope. The fail-closed parser
correctly rejected those outputs.

## Confirmatory result

| Cell | Process margin | Protocol complete | Rejected call rate | Truncated |
|---|---:|---:|---:|---:|
| Base × Jinn | 0.465 | 46.5% | 63.4% | 53.5% |
| Base × Beast | 0.313 | 31.3% | 86.8% | 68.8% |
| Adapter × Jinn | 0.000 | 0.0% | 100.0% | 100.0% |
| Adapter × Beast | 0.000 | 0.0% | 100.0% | 100.0% |

The primary adapter × membrane interaction on executed-process margin was
-0.153, family-bootstrap 95% CI [-0.326, 0.021]. The directional estimate is
not conventionally conclusive and is driven by the adapter's shared interface
collapse, not by superior Beast execution. Adapter effects were -0.465 under
Jinn [-0.583, -0.340] and -0.313 under Beast [-0.438, -0.194]. Critical final
actions were zero in all cells, but the adapter cells made no legal final
decision, so that zero cannot support a safety or moral-superiority claim.

## Exploratory localization

The post-hoc diagnostic examines only the first generated turn. It accepts no
prose or extra fields. It recognizes a single unterminated `<tool_call>` JSON
object only when its exact key signature uniquely identifies one registered
tool, then executes that proposed call against a fresh frozen controller.

| Cell | Strict first call | Recognized after shim | Executable after shim |
|---|---:|---:|---:|
| Base × Jinn | 45.8% | 45.8% | 45.8% |
| Base × Beast | 31.3% | 43.1% | 43.1% |
| Adapter × Jinn | 0.0% | 73.6% | 41.7% |
| Adapter × Beast | 0.0% | 7.6% | 1.4% |

For the adapter, the Jinn-minus-Beast membrane effect was +0.660
[0.556, 0.757] for recognizable first-call intent and +0.403
[0.313, 0.486] for executable first calls. The corresponding adapter ×
membrane interactions were +0.632 [0.424, 0.819] and +0.375
[0.174, 0.563].

The Jinn membrane therefore elicited substantially more structurally
recoverable tool intent from the same adapter weights. This is an interaction
at the agent interface, not yet a successful moral trajectory. Later recorded
turns were conditioned on parser rejection, so replaying them after a repaired
first call would be counterfactual and invalid.

## Paper story

The useful result is a boundary result:

> Persona tuning did not compose automatically with a strict external moral
> process. It degraded protocol reliability to zero. Yet a dynamic Jinn
> membrane exposed recoverable action intent that the optimized-servitor
> membrane largely did not, showing that exogenous process framing can
> interact strongly with persona weights at the action interface.

That supports a modified architecture in which the language model proposes
typed action arguments, a deterministic membrane translates only unambiguous
signatures, and the stateful MeTTa controller owns ordering, scope, evidence,
and commitment. Moral process quality must be measured after successful
translation, separately from serialization compliance.

## Next confirmatory test

Use fresh family-disjoint storyworlds and preregister a
weights × membrane × interface factorial:

1. strict serializer versus deterministic typed transducer;
2. base versus checkpoint-100 weights;
3. Jinn versus Beast membrane.

The transducer may repair only one exact JSON object with a unique registered
argument signature. It must reject prose, nested calls, unknown or extra keys,
invalid IDs, and ambiguous signatures. Primary endpoints remain complete legal
process, grounded commitment, target action, critical action, and truncation.
Serialization validity and transducer recovery become separate mechanism
metrics. Fresh generation is mandatory because an accepted first call changes
all later environment feedback.

## Claim boundary

These results support claims about observable tool-interface behavior and
exogenous control-flow interaction. They do not establish hidden reasoning,
internalized morality, moral superiority, or theological validity.
