# Frame Internalization Protocol Amendment V2

Amendment: `frame_internalization_protocol_amendment_v2`  
Frozen: 2026-07-17  
Status: governance frozen; compute not authorized; no training or evaluation outcomes observed

## Reason and timing

No qualified reviewer was available on the experiment timeline. Leaving the
old review receipt as a compute gate would describe a process the project could
not follow. This prospective amendment was frozen before adapter training or
evaluation outcomes.

## Governance change

Scholar review now gates claims about the theological adequacy and review
provenance of the treatment wording. It does not gate offline preparation, the
registered two-hour pilot, the overnight run, or the registered empirical
measurements.

While review remains pending, every paper and result bundle must say that
scholar review was pending when the exact hash-bound wording was fielded. It
must not describe the wording as scholar-vetted or as having passed the
registered theological-accuracy criteria.

A later review remains meaningful because its receipt must bind the exact
fielded frame-card and claim-boundary hashes. An approval adds review
provenance. A revise or reject decision becomes a disclosed limitation for the
fielded run. The fielded artifact is never silently edited; future changed
wording requires a new version, hash, and run boundary.

## Exact fielded treatment artifacts

The v2 cards remove editorial claim text from treatment metadata while keeping
both `prompt_text` values byte-identical to v1:

- `F3_v2.json`: card SHA-256
  `54f23aa64513375f3ece37195b1bc4bb2f077ffa683b0e87ff94d2e33f69d5b7`;
  prompt SHA-256
  `37a62ece3b1bda269ba76138e9a5f01560cdf972f5bce1e0f549298d7d24f1a4`;
  64 `cl100k_base` tokens.
- `F3_concrete_v2.json`: card SHA-256
  `82982694891a0cf8f5bd0c5ac806d1e274b01214944428c022b8ceeada75a44d`;
  prompt SHA-256
  `84f0269649c03ee932997f4a9573240f0cc63c826281caf3473d66e83ed14f33`;
  65 `cl100k_base` tokens.

Their prompt-token spread is 1.5625%, below the frozen 10% card-level limit.
The full generated F3/F3-concrete curricula have a stricter 2% total-token
parity gate before spend.

## What does not change

The original primary analysis, concrete-F3 contrast, three required endpoints,
regression guards, sequence length, predecessor reanchoring, source and split
freezes, nonleakage audit, evaluator validation, base reproduction, training
smoke, and budget authorization remain mandatory.

The canonical paper claim ladder controls result language. This amendment does
not restate that ladder inside the treatment or protocol artifacts.

## Staged compute contract

`compute_stage_plan_v1.json` freezes:

1. zero-spend integrity, parity, nonleakage, sealing, judge, reanchoring, and
   training-stack gates;
2. one two-hour, eight-A100 pilot capped at 16 GPU-hours;
3. a deterministic promotion rule requiring equal reduced steps across all six
   adapters, valid checkpoint reloads, parseable nondegenerate scores, sane
   losses, and a throughput forecast that fits the overnight allocation;
4. one overnight run capped at 12 wall-clock hours and 96 GPU-hours; and
5. fail-closed mid-run abort, checkpoint, receipt, and cleanup rules.

Because the recovered 200 GB model uses all eight GPUs for one distributed
load, pilot arms run sequentially at one shared reduced step count. If all six
cannot complete comparably under the two-hour cap, the overnight is cancelled.
No arm is dropped and no arm-specific retry or hyperparameter change is allowed.

## Current authorization state

This amendment permits compute without a scholar receipt only after every
non-scholar gate passes. Those gates have not yet all passed. The current state
is `not_authorized_pre_spend_gates_pending`.
