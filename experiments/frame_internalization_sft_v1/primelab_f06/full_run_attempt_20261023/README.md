# Full F06 generation attempt, 2026-10-23: stopped by the throughput gate

This attempt ran on one datacrunch A100-SXM4-80GB at US$2.128/h, pod
f0f92c97, launched at commit 8dc6020.

## What happened

1. **Launch 1 (commit 51af72e) stopped before generating anything.**
   - Cause: `requirements_f04.txt` does not pin transitive packages, so the
     installed set drifted from the 2026-07-23 lock. The wrapper's byte
     compare then failed.
   - Fix: commit 8dc6020 installs the exact lock first. This is an
     infrastructure-only change.
2. **Launch 2 generated for 15 minutes, then the registered gate aborted it.**
   - Measured throughput: 114.2 generated tokens/s at batch 32, over 32
     transcripts and 912 s.
   - Projection for 22,400 transcripts: 122 hours and US$260.
   - Caps under amendment `frame_internalization_generation_budget_v2`: 60
     hours and US$130.
   - As registered, neither the batch size nor the cap was raised.

The pod was terminated after the outputs were copied back. Total pod time was
about 1.1 hours, roughly US$2.40.

## What this means

On this stack (transformers 5.3.0, NF4 bitsandbytes, the registered sampler),
generating the curriculum cannot fit any registered budget. The 32 transcripts
produced here are a throughput record only; they are not used as curriculum.

A cheaper route would need a new amendment, written before any registered
transcript is used. One option is a different inference engine with an
equivalence check against the registered sampler. Changing the engine is a
change to scientific execution, so it is left to the author.
