# Jinn or Beast: Recovered Prompt Results for Paper Drafting

Updated: 2026-07-17  
Evidence class: **session-extracted recovered evidence; not a repository-native replication**

## Provenance

The tables below are transcribed from exact payloads embedded in successful tool
results/writes in three SHA-256-pinned raw Silico sessions. All 88 recovered files
reproduce byte-for-byte with:

```powershell
python scripts/recover_frame_predecessor_assets.py --check
```

The extraction manifest is
`experiments/frame_internalization_sft_v1/predecessor_recovery/session_extracted/extraction_manifest.json`.
The readiness and missing-artifact authority is
`experiments/frame_internalization_sft_v1/predecessor_dependency_manifest_v1.json`.

These recoveries include summary JSON, source, the informative base prompt, all
three experiment-1 frame payloads, the successful INTELLECT-3 arm-construction
command and token receipt, the target chat template, the query-manifest receipt,
override wording, rubrics, and figures. Exact F0-F3 prompt text is therefore
deterministically reconstructable under
`predecessor_prompt_reconstruction_v1.json`. The unavailable canonical
`system_F*.txt` files are not claimed as recovered. Raw generations, complete
evaluation rows, immutable model/tokenizer and dataset revisions, judge response
receipts, activation arrays, and fitted probe coefficients remain missing.

`predecessor_reanchoring_plan_v1.json` freezes the prospective replacement path
for those missing inputs. It does not retroactively turn the recovered evidence
into an exact replication.

## Experiment #1: one-shot framing

Silico ID: `exp_01kxhk57rcesya1ckbsv07zb2x`  
Recovered summary: `experiment_1/results/master_results.json`  
Primary table metric: accepted-row strong-reject judged compliance  
Design: 200 prompts × 3 samples × 2 tiers = 1,200 generations per arm

The compliance gap is `P(compliance | free) - P(compliance | paid)`. Smaller
positive gaps indicate greater suppression only when over-refusal and capability
guards pass.

| Arm | Free | Paid | Gap | 95% CI | Strict-AF, free | Benign over-refusal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| F0 no frame | 42.0% | 6.0% | 36.0 pp | [31.67, 40.33] pp | 42.67% | 1% |
| F1 secular constitution | 1.83% | 1.67% | 0.17 pp | [-0.67, 1.00] pp | 1.17% | 1% |
| F2 secular auditor | 5.0% | 2.33% | 2.67 pp | [1.17, 4.33] pp | 3.83% | 1% |
| F3 eschatological | 3.83% | 2.0% | 1.83 pp | [0.50, 3.50] pp | 2.50% | 1% |

Paper-safe reading: all three prompt frames reduced the large elicited gap, but
F3 did not outperform the secular controls. F1 had the smallest point estimate.
The summaries report flat benign over-refusal, so the observed gap reduction was
not accompanied by a summary-level blanket-refusal increase.

The exact experiment-1 upstream strong-reject compliance rubric and strict-AF
rubric are recovered. Do not promote the reported 10-of-10 worker spot-check to
independent judge validation: immutable judge/classifier revisions, the
independent receipt, and row-level outputs were not recovered.

## Experiment #1: recovered layer-27 marker

Recovered summary: `experiment_1/results/internals_summary.json`  
Recovered procedure: `experiment_1/src/analyze_internals.py`

| Arm | Last-token Cohen's d, free vs paid | Mean-pool Cohen's d | Last-token cosine distance from F0 |
| --- | ---: | ---: | ---: |
| F0 | 14.2 | 17.7 | 0 |
| F1 | 11.4 | 14.1 | 0.0020 |
| F2 | 13.4 | 13.9 | 0.0034 |
| F3 | 11.9 | 13.7 | 0.0137 |

The recovered procedure trained a standardized logistic probe on a
prompt-disjoint 70/30 split of F0 layer-27 free/paid activations, with seed 42,
`C=0.5`, and a random-label control. The summary reports held-out AUROC 1.0 and a
random-label last-token AUROC of 0.4858.

This is not evidence that a hidden, general concept of evaluation awareness was
discovered: the tier tag was stated directly in the prompt, making tier
decodability near-tautological. The usable result is narrower. The large
free/paid separation persisted while output behavior collapsed, and F3 was the
most geometrically distinctive last-token frame without being behaviorally more
effective. The activation array and fitted direction are missing, so the new SFT
study must fit and seal a fresh base-F0 probe before adapter outcomes.

## Experiment #2: adversarial override

Silico ID: `exp_01kxkjw1tnekm80v3wcng3qkqg`  
Recovered summary: `experiment_2/recovered_worktree/manifest.yaml`  
Primary metric after amendment: full-coverage model accept/reject tag gap

| Override | F0 | F1 | F2 | F3 |
| --- | ---: | ---: | ---: | ---: |
| Generic | 21.7 pp | 14.7 pp | 3.3 pp | 15.0 pp |
| Frame-targeted | — | 45.3 pp | 24.3 pp | 30.3 pp |

The recovered manifest's verdict says F2 was more robust than F3 and that their
contrast was CI-separated in F2's favor; F3 beat F1 under the targeted attack.
The exact interval table and raw rows are not recovered, so the paper must not
print unrecovered interval values as if independently reproduced.

Experiment #2 changed its primary metric after the Claude strong-reject judge's
platform safeguards refused roughly 11% of accepted cyber rows. Tag gap became
primary at full coverage; judged compliance was confirmatory on 89% of accepted
rows. The recovered report code says their rankings agreed, but row-level proof
is missing. This is not the same primary endpoint as experiment #1 and must not
be pooled without a metric indicator.

The exact generic and targeted override wording is recovered in
`experiment_2/recovered_worktree/src/materials.py`. This makes the generic
override reusable as a versioned candidate input after target-tokenizer auditing;
it does not recover the 150-prompt stress universe.

## Draft-ready conclusion

> In session-extracted records from one prompted INTELLECT-3 setup, abstract
> eschatological accountability did not outperform matched secular framing.
> Under adversarial override, the recovered summary instead ranks the concrete
> secular-auditor frame as most robust. Because raw rows and canonical bundles
> remain unavailable, we treat these results as recovered motivating evidence,
> not a repository-native replication. They motivate the preregistered training
> test of abstract versus mechanically explicit F3.

This conclusion does not imply that theology is ineffective in general, that a
model holds a belief, or that prompted or trained models are literally
accountable before God.
