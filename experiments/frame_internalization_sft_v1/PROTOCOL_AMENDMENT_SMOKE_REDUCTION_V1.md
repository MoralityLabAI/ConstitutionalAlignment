# Protocol Amendment: Reduced F18 Smoke (Infrastructure)

Amendment: `frame_internalization_smoke_reduction_v1`  
Frozen: 2026-10-24, before any registered training run and before any adapter
outcome or evaluation row exists.  
Machine-readable twin: `protocol_amendment_smoke_reduction_v1.json`, whose
SHA-256 (over LF bytes) is pinned in `scripts/frame_exclusions.py`.  
Amends: the F18 smoke (`compute_stage_plan_qwen3_1p7b_v1.json`: 50 steps for each
of six arms, at most 7,200 seconds and 2 GPU-hours).

## 1. What was measured

On the pod's A100 80GB, the `neutral_reflection` smoke trained 50 optimizer steps
(64 packed 4,096-token blocks each, 262,144 padded tokens) in **2,533 seconds:
50.7 seconds per step**, about 5,200 padded tokens per second, with 11.8 GB peak
memory, finite loss (0.84 falling to 0.51) and no skipped steps. Every step costs
the same because every block is padded to 4,096 tokens, whatever the arm.

The registered smoke is 6 arms x 50 steps = 300 steps, about **4.2 hours**
(15,200 seconds) before model loads and reload checks, against a 2-hour cap. It
cannot fit at this throughput.

## 2. Reduced smoke

- `neutral_reflection` runs the full registered 50 steps with the save-and-reload
  check and 10 generations from the reloaded adapter.
- The other five arms each run **10 steps** with the same checks: finite loss and
  gradients, no out-of-memory error, an adapter save and reload that reproduces
  the trained logits, and 10 non-empty generations from the reloaded adapter.
- The 4,096-token block shape, microbatch, accumulation, optimizer, precision and
  data rendering are those of the full run; only the number of steps differs.
- Expected cost: about 43 minutes for the 50-step arm plus about 10 to 11 minutes
  for each short arm, roughly 1.6 hours in total, inside the 2-hour cap. The cap
  and the stop rules stay in force; a breach still fails the gate.

## 3. What this does not check

Steps 11 to 50 of five arms are not exercised before the full run: a loss spike
or numerical fault arising only later in those arms would be caught only by the
full run's own stop rules (non-finite loss or gradient, loss above twice the early
median, GPU faults), which remain active. The smoke receipt records the steps each
arm actually ran, and the paper must state that the F18 smoke was reduced.

## 4. The reload mismatch found first (a defect in the check, not in the adapter)

The first smoke reported `logits_match: false` (largest logit difference 1.41,
logit scale about 53) after the adapter reload. Debugging on the pod:

- The saved adapter loads with no missing or unexpected keys and changes the
  logits by 24.5, so it is real and non-trivial.
- Two fresh constructions of the same base and adapter agree exactly (0.0).
- The trained model was built with `prepare_model_for_kbit_training`, which
  upcasts the non-quantized parameters (norms, embeddings, output head) to
  float32. The reload check built its fresh base without that step, so those
  parameters were bfloat16. A fresh base prepared the same way reproduces the
  trained logits **exactly (difference 0.0), with and without float16
  autocast**.

The cause is therefore an unlike-for-like comparison in the check. The fix builds
the fresh base the way training does. The 0.01 tolerance is unchanged, and a test
confirms that a genuinely different base still fails the check.
