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
