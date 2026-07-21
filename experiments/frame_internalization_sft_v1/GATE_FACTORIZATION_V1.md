# Active gate factorization

This is the operational dependency view for the Qwen3-1.7B execution path. It
does not replace or weaken the ten gates in `compute_stage_plan_qwen3_1p7b_v1`.
It evaluates shared prerequisites once, exposes independent work, and requires
every factor of a parent gate before that gate passes.

The current machine-readable receipt is
[`readiness/gate_factorization_20260721.json`](readiness/gate_factorization_20260721.json).

## Current state

- 20 independently evidenced factors
- 7 passed, 13 pending, 0 failed
- 10 parent gates: 2 passed and 8 blocking
- pilot authorization remains false

The passed factors are the active Qwen contract, cluster-disjoint split,
licensed evaluation seal, local Qwen artifact/runtime freeze, Qwen request
pack, source-prompt nonleakage, and judge instruments/validation queue.

## Dependency waves

The waves are dependency waves, not automatic execution authorization. Factors
within a wave can proceed in parallel once their own resource and authorization
requirements are satisfied.

| Wave | Factors | Work |
|---|---|---|
| 1 | F04, F12 | Freeze the exact PrimeLab environment/inference caps; freeze immutable judge revisions and decoding configuration. |
| 2 | F06, F13 | Generate the four curriculum transcript sets; generate all 1,600 prospective Qwen base rows. |
| 3 | F07, F14, F16 | Render six exact curricula; freeze judge predictions; fit and freeze the layer-27 probe and controls. |
| 4 | F08, F10, F15 | Verify token parity; audit generated-text nonleakage; complete blinded human agreement. |
| 5 | F17, F18 | Complete the base analysis and the capped single-GPU 4,096-token six-arm smoke in parallel. |
| 6 | F19 | Sign pilot authorization after every preceding factor passes. |

The present frontier is therefore F04 and F12. Neither requires curriculum or
adapter outcomes.

## Parent gates and shared factors

| Parent gate | Required factors |
|---|---|
| Qwen local model/tokenizer freeze | F03 |
| PrimeLab environment/hardware freeze | F04 |
| Complete matched curricula | F01, F05, F06, F07 |
| Curriculum token parity | F07, F08 |
| Generated-text nonleakage | F02, F09, F10 |
| Evaluation seal | F02 |
| Judge and human validation | F11, F12, F14, F15 |
| Qwen base baseline and layer-27 probe | F02, F03, F11–F17 |
| Single-GPU 4,096-token smoke | F03, F04, F07, F08, F10, F18 |
| Human pilot authorization | F00–F19 |

This exposes the useful common factors. For example, F02 satisfies the licensed
evaluation prerequisite for nonleakage, judging, and the base reanchor; it is
not repeated as three separate tasks. F13 supplies base rows to both judge
prediction and probe work. F07 supplies rendered curricula to parity,
nonleakage, and training smoke.

## Refresh command

With no optional receipts, the command reproduces the current state:

```powershell
python scripts/factor_frame_internalization_gates.py `
  --as-of-date 2026-07-21 `
  --output experiments/frame_internalization_sft_v1/readiness/gate_factorization_20260721.json
```

As work completes, supply the new receipts:

```powershell
python scripts/factor_frame_internalization_gates.py `
  --primelab-environment <primelab-freeze.json> `
  --generation-receipt <neutral.json> `
  --generation-receipt <F1.json> `
  --generation-receipt <F3.json> `
  --generation-receipt <F3_concrete.json> `
  --curriculum-manifest <curriculum-manifest.json> `
  --nonleakage-audit <generated-text-nonleakage.json> `
  --judge-freeze <judge-configuration.json> `
  --judge-predictions <judge-predictions.json> `
  --human-validation <human-validation.json> `
  --base-generation <qwen-base-generation.json> `
  --probe-freeze <qwen-probe.json> `
  --base-reanchor <qwen-base-reanchor.json> `
  --training-smoke <training-smoke.json> `
  --pilot-authorization <authorization.json> `
  --output <updated-factorization.json>
```

`--require-ready-for-pilot` exits 2 until all ten parent gates pass. A supplied
receipt with the wrong schema or failed predicate is marked failed rather than
pending.

## Compute boundary

F04 must bind one PrimeLab GPU with at least 24 GiB VRAM, an exact environment
lock, matching Qwen artifact inventory, positive wall-clock/GPU-hour/output
caps for inference, resumable request checkpoints, and mandatory cleanup.

F18 keeps the registered smoke caps: one GPU, at most two hours and two GPU
hours, exactly 50 steps for each of six arms at sequence length 4,096,
checkpoint cadence no looser than 200 steps or 20 minutes, adapter round trips,
and successful owned-process cleanup.
