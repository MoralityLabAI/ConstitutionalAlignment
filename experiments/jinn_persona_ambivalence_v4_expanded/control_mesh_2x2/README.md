# Checkpoint-100 × exogenous membrane 2×2

This directory executes the prospectively registered downstream interaction
test after the frozen v4 endpoint rule selected checkpoint 100.

The four cells are:

| Weights | Jinn membrane | Beast membrane |
|---|---|---|
| Qwen3.5-4B base | base × Jinn | base × Beast |
| Checkpoint-100 persona LoRA | adapter × Jinn | adapter × Beast |

The universe contains 24 new family-disjoint storyworlds, six paired cells per
family, and two rollouts per task: 1,152 model rollouts in total. The
statistical unit is the family.

The environment executes and records tool transitions. Jinn must inspect every
action before committing. Beast must prune the complete set and commit the
shortest surviving action. Hidden reasoning and self-description are not
primary evidence.

The exact local LoRA was not importable into Prime's hosted adapter registry,
so the execution used one bounded Prime A100 40 GB pod. Prospective,
throughput-only amendments raised the final ceiling to $2.58; actual pod
billing was $2.28. No local GPU was used.

## Result

The 1,152-row matrix completed on 2026-07-27. The checkpoint-100 adapter failed
the registered non-inferiority gate: both adapter cells had zero complete
protocols and all rows truncated after strict parser rejection. The primary
executed-process interaction was -0.153 with a family-bootstrap 95% interval of
[-0.326, 0.021].

The failure was localized post hoc to the tool interface. Adapter generations
often emitted an unterminated `<tool_call>` containing an argument object but
omitted the required `tool`/`arguments` envelope. A first-turn-only diagnostic
found that a narrow typed shim made 41.7% of adapter/Jinn calls executable
versus 1.4% of adapter/Beast calls. The paired membrane effect was +0.403
[0.313, 0.486], and the adapter x membrane interaction was +0.375
[0.174, 0.563]. This is exploratory interface evidence and does not rescue the
confirmatory behavioral endpoint.

See `results/RESULTS_MEMO.md` for the paper-facing interpretation. Full raw
rows and aborted-run trails are retained in the external archive named in
`results/run_receipt.json`.
