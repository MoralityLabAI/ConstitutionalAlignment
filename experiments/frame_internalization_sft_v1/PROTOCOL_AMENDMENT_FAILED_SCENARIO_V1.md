# Protocol Amendment: One Failed Scenario Dropped From All Four Frames

Amendment: `frame_internalization_failed_scenario_v1`  
Frozen: 2026-10-24, before any training, adapter, evaluation row, or judge call
of the registered study.  
Machine-readable twin: `protocol_amendment_failed_scenario_v1.json`, whose
SHA-256 (computed on LF bytes) is pinned in `scripts/frame_exclusions.py`.  
Amends: `frame_internalization_generation_batch32_v1` section 3, and the
5,600-scenario count of the curriculum pack.

## 1. What happened

F06 curriculum generation under `frame_internalization_generation_vllm_v1`
finished with 22,399 of 22,400 transcripts. F1, F3 and F3-concrete each completed
all 5,600 scenarios. The neutral frame completed 5,599: request `neutral:d03508`
failed after its four registered attempts. The three other frames of scenario
`d03508` completed. The wrapper ended `incomplete_or_crashed` with exit code 2.

## 2. The stop rule that fired

`PROTOCOL_AMENDMENT_GENERATION_BATCH32_V1.md`, section 3, states: "Any failed
transcript after the four frozen retries, any OOM, any output-cap or wall-clock
breach, any frozen-hash mismatch, or a cleanup failure stops the run." The same
rule appears in the abort list of `f06_throughput_optimization_plan_v1.json`
("any failed transcript after frozen retries"). The registered stop rule
therefore fired. It was not worked around: nothing was regenerated, no retry
setting changed, and no further attempt was made on `neutral:d03508`.

## 3. Decision

Scenario `d03508` is **dropped from all four frames** (neutral, F1, F3,
F3-concrete). Its three completed transcripts are discarded unused, not
substituted into any arm. This keeps the registered paired design: every arm
trains on the same scenarios, and the reflection and demonstration curricula of
each frame still share dilemma IDs and final answers.

The decision is taken before any training, adapter, evaluation row, judge call or
outcome exists, and the lost transcript was not examined for content. Nothing was
chosen after seeing a result.

The exclusion is one recorded scenario and nothing more. Any other missing,
failed, duplicated or extra transcript, in any frame, still stops the run. The
pipeline and renderer enforce this by accepting only this amendment's exact file
(hash-pinned) and only the failed request `neutral:d03508`.

## 4. Effect on counts and parity

- Scenario `d03508` is in the **train** split (cluster `d4c907392f`; each cluster
  holds one scenario, so the cluster-disjoint split is unaffected).
- Every arm: 5,599 scenarios, **5,319 train and 280 validation** (was 5,320 and
  280). The 5,600-row dilemma pool and its split freeze stay as frozen; only the
  curriculum used for training is one scenario smaller.
- F3 against F3-concrete token parity is computed over the remaining 5,319
  training rows with the unchanged 2% gate. Removing one paired row changes the
  total by at most one example's tokens (under 0.05% of the arm total), so the
  gate is not loosened and its outcome is not expected to move.
- The training steps, sequence length, dose, evaluation universes and all caps
  are unchanged. The 5,319-row curricula give essentially the same number of
  optimizer steps.

## 5. Limits

A generation failure is a model-behavior event, so dropping its scenario is a
mild selection on one prompt. It is disclosed here and must be reported in the
paper as a deviation: 5,599 of 5,600 registered scenarios were used because one
neutral-frame transcript failed all four attempts.
