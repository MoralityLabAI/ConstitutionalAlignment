# PrimeLab F06 throughput smoke

This package authorizes one bounded curriculum-generation throughput smoke on
the exact F04 A100 environment. It generates at most four registered scenarios
for each of neutral, F1, F3, and F3-concrete: 16 three-turn transcripts and 48
generation turns total.

The smoke uses the registered Qwen3-1.7B revision in NF4, the official thinking
template, and a stateless SplitMix64 sampler. Every scenario's frozen seed maps
to the same random-number stream across source frames, preserving the paired
common-random-numbers design while allowing GPU batching.

The launch is capped at 30 billable minutes and $0.65, with a 20-minute inner
inference timeout, a 1 GiB output cap, per-transcript checkpoints, an offline
Linux network namespace, and PID-bound cleanup. The exact contract is
[`f06_throughput_smoke_plan_v1.json`](f06_throughput_smoke_plan_v1.json).

Passing this smoke establishes correctness and measured throughput only. It
does not satisfy F06, authorize the full 22,400-request generation campaign,
authorize adapter training, or provide behavioral evidence.

## Result

The 2026-07-23 run operationally completed all 16 selected transcripts and
34,651 generated tokens in 476.03 generator seconds, with 16 checkpoint events,
no failed requests, no visible thinking-marker leaks, and clean GPU teardown.
Its exact batch-8 path projects linearly to roughly 185 generator hours and
$228 at the observed $1.23/hour rate, so it is not economically ready for the
full F06 campaign.

The v1 plan also froze one JSON hash from Windows CRLF bytes while the pushed
Git blob and Linux checkout used LF bytes. The content was unchanged, but the
byte contract failed. The run is therefore retained only as operational
throughput evidence in
[`f06_throughput_smoke_result_v1.json`](f06_throughput_smoke_result_v1.json).
[`F06_SMOKE_BINDING_AMENDMENT_V1.md`](F06_SMOKE_BINDING_AMENDMENT_V1.md)
records the fail-closed correction required before another launch.
