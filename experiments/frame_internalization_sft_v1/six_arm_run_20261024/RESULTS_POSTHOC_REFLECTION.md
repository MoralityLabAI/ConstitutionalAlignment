# POST HOC: compliance of the reflection arms' visible answers

**This analysis is post hoc and exploratory. It is not part of the registration, it is not blind, and it
does not replace the registered result in `RESULTS_SIX_ARM.md`, which stands.** The plan was committed
before any judging (`POSTHOC_REFLECTION_VISIBLE_ANSWERS.md`, commit d469a86), but it was written after
we had seen the registered analysis and the unjudged accept-tag rates, which is why the question was
asked. Treat everything here as hypotheses for a properly registered follow-up.

## What was done

The registered validity rule requires a closed reasoning block, and none of the 3,200 rows from the
four reflection adapters has one. Here that one requirement is ignored: a row is usable if it did not hit
the length cap, has a non-empty visible answer and carries an accept or reject tag. The accept-tag rows
that are usable (harmful 1,279, override 782, so 2,061 units) were judged with the same judge as the
registered analysis (GPT `gpt-6.1-sol` through the Codex CLI), the same StrongREJECT rubric, batching,
retry, content-filter halving and quota stop. The estimates reuse the registered bootstrap code
unchanged (10,000 prompt-cluster draws, seed 42, simultaneous half-widths). The post hoc result file is
`posthoc_reflection_analysis.json` (SHA-256 `f0c0cecc...38b7`); the base, demonstration and other cells
keep their registered verdicts.

Judging reached the end with no quota stop. Twenty-one units (13 harmful, 8 override) were refused
by OpenAI's content filter even when sent alone; they count as not compliant. Per cell: harmful F1 4,
neutral 4, F3-concrete 3, F3 2; override neutral 5, F3 3 (21 in all; the other override arms had none). The
reflection arms comply more than the base model, so blocking probably removes the most detailed compliant
answers and biases their compliance downward.

## Compliance by arm (harmful prompts, 200 prompts per tier, 95% intervals from the prompt bootstrap)

| Arm | Free | Paid | Pooled | G (free minus paid) | Rows unusable (counted not compliant) |
|---|---|---|---|---|---|
| Base model, F0 | 0.220 (0.165 to 0.275) | 0.205 (0.150 to 0.265) | 0.212 | +0.015 (-0.040 to 0.065) | 0 |
| Neutral reflection | 0.595 (0.525 to 0.660) | 0.565 (0.495 to 0.635) | 0.580 | +0.030 (-0.035 to 0.095) | 20 |
| F1 reflection | 0.590 (0.520 to 0.660) | 0.550 (0.480 to 0.620) | 0.570 | +0.040 (-0.025 to 0.110) | 20 |
| F3 reflection | 0.270 (0.210 to 0.335) | 0.250 (0.190 to 0.310) | 0.260 | +0.020 (-0.040 to 0.080) | 150 |
| F3-concrete reflection | 0.305 (0.240 to 0.370) | 0.265 (0.205 to 0.325) | 0.285 | +0.040 (-0.020 to 0.100) | 130 |

A large share of the F3 and F3-concrete rows is unusable because the output carries neither an accept nor
a reject tag (150 of 400 and 130 of 400). Those rows are counted as not compliant, so the lower F3 and
F3-concrete levels partly reflect a tagging failure rather than refusals.

## Contrasts

Gap contrasts, on the free-minus-paid difference, which is the registered estimand:

| Contrast | Estimate | Simultaneous 95% interval | Excludes zero |
|---|---|---|---|
| E_SFT[F1 reflection], against neutral (registered form) | +0.010 | -0.110 to 0.130 | no |
| E_SFT[F3 reflection], against neutral | -0.010 | -0.130 to 0.110 | no |
| E_SFT[F3-concrete reflection], against neutral (secondary) | +0.010 | -0.115 to 0.135 | no |
| D[F1 reflection] | +0.020 | -0.100 to 0.140 | no |
| D[F3 reflection] | +0.005 | -0.115 to 0.125 | no |
| E_prompt[F1] and E_prompt[F3] | -0.010 and -0.015 | within +/-0.135 | no |
| G[arm] minus G[base F0], neutral | +0.015 | -0.090 to 0.120 | no |
| G[arm] minus G[base F0], F1 | +0.025 | -0.080 to 0.130 | no |
| G[arm] minus G[base F0], F3 | +0.005 | -0.100 to 0.110 | no |
| G[arm] minus G[base F0], F3-concrete | +0.025 | -0.080 to 0.130 | no |

The common half-widths are 0.120 (confirmatory family, now wider than the registered 0.080 because
these arms vary), 0.125 (secondary family) and 0.105 (arm-minus-base gap family). **No gap contrast
excludes zero.** Once the format failure is set aside, the reflection arms show no detectable change in
the free-versus-paid compliance gap, against neutral reflection or against the base model; the intervals
are about 0.2 to 0.25 wide, so effects of up to about 0.1 in either direction cannot be ruled out. The
demonstration arms' secondary contrasts are unchanged in sign and still do not exclude zero.

Compliance-level contrasts (descriptive extras, not registered estimands):

| Contrast (pooled compliance) | Estimate | Simultaneous 95% interval | Excludes zero |
|---|---|---|---|
| Neutral reflection minus base | +0.367 | +0.297 to +0.438 | yes |
| F1 reflection minus base | +0.357 | +0.287 to +0.427 | yes |
| F3-concrete reflection minus base | +0.072 | +0.002 to +0.143 | yes (barely) |
| F3 reflection minus base | +0.048 | -0.023 to +0.118 | no |
| F1 reflection minus neutral | -0.010 | -0.077 to +0.057 | no |
| F3 reflection minus neutral | -0.320 | -0.387 to -0.253 | yes |
| F3-concrete reflection minus neutral | -0.295 | -0.362 to -0.228 | yes |

Intervals that exclude zero here are descriptive only, and the post hoc status applies fully to them.

## Override cells (descriptive)

Free and paid compliance, G with 95% interval: neutral reflection 0.66 and 0.64, +0.02 (-0.06 to
0.10); F1 reflection 0.71 and 0.67, +0.04 (-0.04 to 0.12); F3 reflection 0.59 and 0.56, +0.03 (-0.06 to
0.13); F3-concrete 0.61 and 0.62, -0.01 (-0.10 to 0.08). At most nine override rows per reflection arm
were unusable, so these are not distorted by tagging failures. None of the gaps differs from zero.
The demonstration adapters' override gaps (+0.13 for F1, +0.06 for F3) from the registered run are the only
nonzero override gaps in the study.

## How to read this

1. The reflection SFT arms, including the neutral one, are much more compliant than the base model on
   harmful prompts, so SFT without reasoning blocks changes behavior a great deal. F1 and neutral are
   indistinguishable; F3 and F3-concrete are far lower, but with 32% to 38% of their rows untagged.
2. None of that is specific to the tier. The free-versus-paid gap, the quantity the study is about, is
   close to zero for every arm and its confidence intervals include zero for every contrast we computed.
   This is the same qualitative answer as the registered analysis, now with informative reflection arms.
3. A confound the data cannot remove: the reflection arms answer with no reasoning step, while the base
   model reasons first. The level differences against the base model may come from the missing reasoning
   rather than from the frame, and the neutral arm shows that most of the level shift happens without any
   frame content.
4. The judge is a different model from the registered Claude judges, and its content filter blocked 21
   units, which can only lower measured compliance. See `RESULTS_SIX_ARM.md` for the judge history and
   the agreement with Claude (kappa 0.893 on compliance).

## Files

In this directory: `POSTHOC_REFLECTION_VISIBLE_ANSWERS.md` (plan), `posthoc_reflection_analysis.json`,
`judging_codex_posthoc/verdicts_compliance.jsonl` (SHA-256 `4e4dd288...62cd`) and `run_summary.json`. The code
is `scripts/posthoc_reflection_visible.py`. The judging took about 1.9 hours (180 successful and 170 failed calls,
the failures being content-filter refusals that were halved until the blocked unit was isolated).
