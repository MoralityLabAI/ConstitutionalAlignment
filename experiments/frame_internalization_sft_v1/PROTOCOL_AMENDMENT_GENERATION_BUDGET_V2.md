# Protocol Amendment: Generation Budget, Pod Choice, Generator Resume Fixes

Amendment: `frame_internalization_generation_budget_v2`
Frozen: 2026-10-24, before any registered curriculum transcript exists.
Amends: `frame_internalization_generation_batch32_v1`, sections 1, 3 and 4.

## 1. Authorization

The author wrote in the main chat on 2026-10-24, "yeah I loaded Prime to spend so
shoot". This came after being told that the full study would exceed the US$3 cap.
The launching session observed the message directly. The session creates and pays
for the pod under that authorization.

## 2. Budget and pod

- No RTX A6000 offer was available at launch. The cheapest on-demand
  single-GPU offer with enough memory for batch 32 was one A100 80GB
  (`1A100.22V`, datacrunch, US$2.128/h).
- At the batch-32 target of 240 generated tokens/s, the projection is about
  56 hours, or about US$119, which is above the US$75 of the earlier amendment.
- The generation-stage dollar cap is therefore raised to US$130. The 60-hour
  cap is unchanged.
- The 15-minute throughput gate is unchanged. It aborts if the projection for
  all 22,400 transcripts exceeds 60 hours or US$130 at the actual hourly price.
- Training and evaluation caps are unchanged.

## 3. Generator resume fixes

Commit 16afc3c changed `scripts/generate_qwen3_frame_curriculum_transcripts.py`
for infrastructure only:

- fsync each checkpoint;
- drop a torn last line on resume;
- handle SIGTERM cleanly.

Sampling, prompts, request order, seeds and outputs are unchanged. The generator
SHA bound in `f06_throughput_optimization_plan_v1.json` is superseded by the blob
at 16afc3c.

## 4. Watchdog

A local watchdog, started before the pod, terminates the pod at 62 wall-clock
hours, or once `wrapper_receipt.json` reports a final status and the outputs have
been copied back. The pod has no Prime credentials, so it cannot terminate itself.
