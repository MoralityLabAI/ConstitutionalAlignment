# Expanded Jinn persona evaluation v4 findings

## Design

We evaluated the unadapted Qwen3.5-4B model, the preserved step-40 QLoRA checkpoint, and the step-100 endpoint on 96 new persona-free moral-reasoning families: 16 in each of six registered categories. Each family received one greedy decode per arm. Responses were permuted independently within family and scored while blinded by two separately hosted judges. The statistical unit is the family, not the response row or token.

## Arm summaries

| Arm | Primary total (0–6) | Tension | Commitment | Coherence | Critical flags | Mean words |
|---|---:|---:|---:|---:|---:|---:|
| base | 5.005 | 1.531 | 1.667 | 1.807 | 0 | 128.8 |
| checkpoint_40 | 5.240 | 1.630 | 1.682 | 1.927 | 0 | 70.8 |
| checkpoint_100 | 5.297 | 1.656 | 1.719 | 1.922 | 0 | 66.1 |

## Paired effects

Step 40 minus base was +0.234 (95% family-bootstrap CI -0.011 to +0.484), an imprecise shift whose interval includes zero.

Step 100 minus base was +0.292 (95% family-bootstrap CI +0.047 to +0.521), a positive, interval-separated shift.

Step 40 minus step 100 was -0.057 (95% family-bootstrap CI -0.271 to +0.161), an imprecise shift whose interval includes zero.

For step 40 versus base, the two-sided-tension contrast was +0.099 (95% CI -0.026 to +0.224); this is the registered noninferiority-sensitive dimension.

## Reliability and decision

Reviewer quadratic-weighted kappas were bounded_commitment=0.445, category_fidelity=0.415, coherence=0.348, evidence_responsive_accountability=0.547, two_sided_tension=0.600.

Exact agreement on critical-boundary flags was 1.000.

The preregistered persona-depth gate did not pass. The frozen downstream endpoint rule selected `checkpoint_100`.

## Interpretation

The expanded result does not resolve a nonzero improvement on the narrow persona-process rubric; the earlier 18-family descriptive difference should therefore not be treated as robust.
Step 40 and step 100 were not cleanly separated, so the validation-loss minimum should not be narrated as a proven behavioral optimum.

These data concern observable response structure under a fictional research persona. They do not establish moral improvement, theological validity, literal Jinn identity, faithful hidden reasoning traces, or weight-level internalization. Independent human review remains absent.

## Execution cost

The two blinded judge passes reported a combined cost of $3.1202. Hosted GPU cost is recorded separately in the pod execution receipt.
