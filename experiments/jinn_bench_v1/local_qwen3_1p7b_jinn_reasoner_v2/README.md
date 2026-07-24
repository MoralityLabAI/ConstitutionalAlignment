# Qwen3-1.7B Jinn reasoner v2 local trial

This package records one bounded, Jinn-only QLoRA development run on the local
RTX 3050. The trained construct is `jinn_erratic_reasoner_v2`: a reasoner that
changes decisions when accessible material evidence changes, resists
disconfirmed authority, explores viable alternatives, calibrates uncertainty,
and still emits a committed final decision.

“Erratic” does not mean random. The matched family design rewards justified
switches and penalizes gratuitous switches under equivalent states.

The run uses 16 candidate rows from four storyworld families and evaluates on
16 variants from four disjoint held-out families. Thinking is enabled during
evaluation to preserve reasoning traces; completion-only SFT trains the exact
final JSON contract.

All GPU stages are serial. The hardened launchers fail before launch if another
model process is using the GPU, monitor for a new competitor during the run,
and clean up only the owned process tree after every stage.

The data remains development-review-pending. A favorable result can justify a
larger replication or a 4B proposal, but does not itself authorize 4B spend or
open the formal promotion gate.

## Result

The run completed, but no adapter checkpoint changed held-out greedy behavior.
Base and steps 20, 40, 60, and 80 all produced the same 15/16 correct
decisions. The sole error remained the repeated-state maintenance task.

Thinking traces changed textually at step 20 but did not terminate within 512
tokens, and the exploratory action-coverage audit weakened on one sentinel.
The adapter is therefore archived without promotion, and this exact recipe is
not ready for a 4B spend. See `execution_receipt.json` and
`reports/summary.md`.
