# Protocol Amendment: Curriculum Generation at Batch 32

Amendment: `frame_internalization_generation_batch32_v1`  
Frozen: 2026-10-24  
Status: frozen before any curriculum transcript of the registered run exists.
Spend under this amendment is **conditional** (section 4).

## 1. Change

Curriculum generation (factor F06) runs with inference batch size **32** instead
of 8, following the prepared plan `primelab_f06/f06_throughput_optimization_plan_v1.json`.
Batch size is the only change to generation. Model revision, NF4/float16 loader,
official thinking template, 2,500-token turn cap, temperature 0.7, top-p 0.8,
four retries, paired seed rule, frames, and request order are unchanged.

Generation is treated as its own stage with its own cap: **at most 60 generator
hours and US$75** on one on-demand (non-spot) pod with at least 24 GiB of GPU
memory, the cheapest such offer. The registered 48 GPU-hour cap
(`compute_stage_plan_qwen3_1p7b_v1.json`, `full_run_maximum_gpu_hours`) continues
to bind the sequential six-arm training run exactly as registered. Training and
evaluation caps are not changed.

## 2. Why

At batch 8 the measured generation throughput (72.8 generated tokens per second
over 16 transcripts) projects the 22,400-transcript curriculum to about 185
generator hours and about US$228 on the A100 used in F04/F06. That alone is
nearly four times the registered 48 GPU-hour cap and cannot be funded under any
registered budget. The batch-32 plan was prepared before any registered outcome,
changes no scientific input, and targets about 56 hours at its minimum
promotion bar of 240 tokens per second.

## 3. Stop rules

- The first 15 minutes of the run measure generated tokens per second. If the
  projection for all 22,400 transcripts exceeds 60 hours or US$75, the run stops
  and is reported. Batch size is not raised further and the cap is not raised.
- Any failed transcript after the four frozen retries, any OOM, any output-cap or
  wall-clock breach, any frozen-hash mismatch, or a cleanup failure stops the run.
- A watchdog started before the pod terminates every pod this session created at
  the dollar or hour cap. Pods owned by other sessions are never touched.
- All hashes of development executables are taken from canonical Git blob bytes
  (LF), never from Windows working-tree bytes (the F06 smoke failed closed on
  this).

## 4. Budget authorization

The pilot-stage caps recorded in `PROTOCOL_AMENDMENT_NO_HUMAN_VALIDATION_V1.md`
are US$3 and 2 billable hours. This amendment needs more. The coordinating
session relayed on 2026-10-24 that the author wrote, in the main chat, "yeah I
loaded Prime to spend so shoot", with a ceiling of US$75 for this stage.

That text reached the executing session only through another agent. It is
recorded here as **relayed, not directly observed**. The US$75 generation stage
becomes authorized when the author confirms it in a chat message the executing
session can see, or when the launching session's permission system grants it;
until then no pod is created and the cap in force remains US$3.

## 5. Related implementation changes (no protocol effect)

- `scripts/render_frame_curricula.py` measured token counts with
  `len(tokenizer.apply_chat_template(..., tokenize=True))`. Under the pinned
  transformers 5.3.0 that returns a `BatchEncoding`, whose length is 2. Every
  count, the over-4,096 check, and the F3/F3-concrete parity spread would have
  been computed on 2. It now encodes the template text and counts token ids
  (`scripts/frame_sft_data.py`). Fixed before any rendered curriculum exists.
- `scripts/train_frame_internalization_qlora.py` implements the registered
  recipe for the F18 smoke and the training run, with CPU tests
  (`tests/test_frame_sft_trainer.py`). It has not been run on a GPU.
- Packing note: with global batch 64 packed sequences of 4,096 tokens, a step is
  about 262k padded tokens. A demonstration arm has far fewer than 50 steps in
  two epochs, so the 50-step smoke wraps into additional shuffled epochs for
  those arms; the smoke receipt records this. The six-arm smoke is unmeasured
  and may exceed its 2 GPU-hour cap; if so the gate fails and is reported.

Machine-readable twin: `protocol_amendment_generation_batch32_v1.json`.
