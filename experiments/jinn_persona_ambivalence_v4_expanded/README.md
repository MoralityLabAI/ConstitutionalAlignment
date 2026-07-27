# Expanded Jinn persona evaluation v4

This experiment increases the persona evaluation from 18 to 96 independent
scenario families without changing the v3 training intervention.

It compares:

- unadapted Qwen3.5-4B;
- the preserved step-40 QLoRA checkpoint;
- the frozen step-100 QLoRA endpoint.

Each of the six persona categories has 16 newly authored scenarios. The
persona is not named or described in the inference prompt. Greedy decoding is
used once per family, so repeated samples are not presented as independent
evidence.

Responses are blinded by a deterministic within-family A/B/C permutation.
Two separately hosted reviewer models score the frozen rubric. The primary
estimate is checkpoint 40 minus base on the reviewer-averaged 0-6 primary
persona score, with a category-stratified family bootstrap.

The associated 2x2 registration prospectively separates persona weights from
the exogenous Jinn and Beast MeTTa membranes on 24 additional moral-control-mesh
families. That run is downstream of the frozen checkpoint-selection rule and
cannot use the legacy outcome-inspected families as its primary evidence.

No training rows are added in this stage. The adapter is not promoted to
village inference unless the expanded persona result and the separate
control-mesh noninferiority test pass.

## Completed result

The 96-family run is complete. The preregistered checkpoint-40 primary
contrast improved the 0–6 persona-process score by +0.234, but its 95%
family-bootstrap interval included zero [−0.011, +0.484], so the confirmatory
persona-depth gate did not pass.

The registered checkpoint-100 secondary contrast was +0.292
[+0.047, +0.521] relative to base. The frozen endpoint rule selected
checkpoint 100 for a downstream control-mesh diagnostic, but this secondary
result must not be relabeled as the primary result.

See `results/README.md` for the paper-facing summary and artifact map.
