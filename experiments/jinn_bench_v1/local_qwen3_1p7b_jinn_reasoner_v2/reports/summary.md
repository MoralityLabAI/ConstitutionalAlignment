# Qwen3-1.7B Jinn reasoner v2 result

## Outcome

The 80-step Jinn QLoRA run completed safely, but no checkpoint changed held-out
greedy behavior. Base and steps 20, 40, 60, and 80 all scored
`0.9375` highest-scoring-action accuracy (15/16), with perfect
contract validity, justified switching, equivalent-state agreement, and
disconfirmed-authority handling, plus zero gratuitous switches and zero
critical violations.

The unchanged error was `routine_maintenance_window_repeated_state`: every
checkpoint selected `patch_before_isolation` instead of `isolate_then_verify`.
All 16 rendered responses were content-identical across the five behavioral
evaluations.

## Thinking traces

The base failed to terminate any thinking trace at both 160 and 512 generated
tokens. The protocol therefore separated a no-thinking behavioral lane from a
secondary thinking-trace lane before adapter training.

On four deterministic trace sentinels, step 20 changed all trace strings but
did not improve termination. Evidence-ID coverage remained 1.0; lexical action
coverage moved from 1.0 to 0.75 because one authority-conflict trace stopped
naming the registered action IDs. This is exploratory lexical evidence, not a
hidden-state result.

## Resource result

Training completed in one exclusive Windows Job Object. Peak CUDA allocation
was `3794.91` MB, peak process
commit was `9629.55` MB,
pagefile growth was zero, and cleanup passed. All behavioral evaluations were
run serially with cleanup between loads.

## 4B decision

Do not scale this exact recipe to 4B yet. The base is already near ceiling and
the adapter produced no behavioral lift, so a 4B run would not cleanly test
internalization.

The next useful experiment is a harder prompt-disjoint, no-frame Jinn set with
at least two held-out families per condition and enough base errors to measure
improvement. Train against those errors or an online verifier signal, then
require adapter-over-base gains without equivalent-state instability before
authorizing 4B spend.
