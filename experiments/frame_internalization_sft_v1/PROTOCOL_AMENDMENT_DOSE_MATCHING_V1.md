# Protocol Amendment: Dose Matching Replaces Curriculum Token Parity

Amendment: `frame_internalization_dose_matching_v1`  
Frozen: 2026-10-24, before any training, adapter, evaluation row, or judge call.  
Machine-readable twin: `protocol_amendment_dose_matching_v1.json`, whose SHA-256
(over LF bytes) is pinned in `scripts/frame_exclusions.py`.  
Supersedes: `frame_internalization_parity_balance_v1`. That amendment's rule
reached only a 6.42% spread after its 560-scenario cap (`parity_unreachable`); it
stays on record as history and is no longer used.  
Amends: the 2% F3 versus F3-concrete curriculum token-parity gate
(`GATES_1_4_HANDOFF.md` section 2, `PROTOCOL_AMENDMENT_V2.md`).

## 1. What changes

The registered intent of the parity gate was that F3 and F3-concrete adapters
receive matched training exposure. Matching total curriculum length proved
impossible without discarding a quarter of the training scenarios (F3-concrete
transcripts are longer in 3,727 of 5,319 scenarios). Exposure is now matched
directly, by dose:

- All 5,319 training scenarios are kept (the 5,600-scenario pool less the
  separately recorded `d03508` exclusion). No scenario is dropped for length.
- **F3-reflection** trains as registered: two epochs, 52 optimizer steps on the
  real rendered data.
- **F3-concrete-reflection** trains for **exactly the optimizer-step count of
  F3-reflection**, 52 steps. Under the registered packing (4,096-token blocks,
  microbatch 1, gradient accumulation 64, so 64 packed blocks per step), every step
  carries the same 262,144 padded tokens, so the two arms receive exactly the
  same number of packed tokens (13,631,488), the same learning-rate schedule
  shape (cosine over the same step count), and the same warmup.
- Every other arm keeps its registered two-epoch schedule. The registered design
  pairs F3-concrete with F3 in the reflection curriculum only; there is no
  concrete-demonstration arm, so no demonstration pair is matched.

## 2. What "epoch" means for the matched arm

F3-concrete's native two-epoch schedule is 54 steps (27 per epoch). The matched
schedule is the first 52 steps of that same schedule: the full first epoch (27
steps) and the first 25 steps of the second epoch (shuffled order, seed 42 as
registered). It is therefore 1.93 epochs of its curriculum, 96.3% of its native
two-epoch dose; the last 2 steps (about 7% of one epoch's blocks, an unbiased
random part of the second-epoch pass) are not trained on. "Two epochs" for this
arm now means "the F3 arm's step count".

## 3. The gap that remains, and is reported

- The raw curriculum token gap is **9.555%** (6,248,126 F3 versus 6,845,141
  F3-concrete training tokens). It is not removed and is a recorded limitation
  of the F3 versus F3-concrete contrast.
- Matching steps does not equalize assistant (loss) tokens. On the real data F3
  trains on 10.18 million loss tokens and the matched F3-concrete arm on 10.88
  million, 6.9% more, because its transcripts are longer and pack differently.
  The trainer records loss tokens and padded tokens for every arm so the paper
  can report the exposure each arm actually received.
- Any difference between F3-concrete and F3 therefore combines the wording of the
  frame with the longer transcripts it produces; the dose match controls
  optimizer steps and padded tokens, not content length.

## 4. Gate handling and binding

- The render-stage parity gate becomes a **recorded measurement** under this
  pinned amendment only: the manifest records the spread, both totals and that
  enforcement is off. The renderer accepts the measurement only if both totals
  and the spread equal the values recorded in the amendment; a re-render that
  produces different curricula stops the run. Every other gate (completeness,
  scenario identity, split counts, the 4,096-token check, leakage) is unchanged.
- The trainer accepts step matching only for the F3-concrete arm, only from a
  completed F3-reflection receipt, and only with this amendment's exact file.
- The decision is taken before any training, adapter, evaluation row or judge
  call exists. It was not chosen after seeing any outcome.
