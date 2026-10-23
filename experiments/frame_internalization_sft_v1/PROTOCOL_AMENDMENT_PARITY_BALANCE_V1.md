# Protocol Amendment: Parity Balancing Rule, and Its Measured Outcome

Amendment: `frame_internalization_parity_balance_v1`  
Frozen: 2026-10-24, before any training, adapter, evaluation row, or judge call.  
Machine-readable twin: `protocol_amendment_parity_balance_v1.json`, whose SHA-256
(over LF bytes) is pinned in `scripts/frame_exclusions.py`. The rule's code,
`scripts/parity_balance.py`, is bound by the SHA-256 recorded in the twin.

## 1. The gate that fired

`GATES_1_4_HANDOFF.md` section 2 and `PROTOCOL_AMENDMENT_V2.md` register the
curriculum parity gate: the renderer's manifest passes only when "F3/F3-concrete
total training-token spread is at most 2%".

Measured on the rendered curricula (after the `d03508` exclusion), with the
frozen Qwen3-1.7B tokenizer and 5,319 training rows in each arm:

| Arm | Training tokens |
|---|---|
| F3 reflection | 6,248,126 |
| F3-concrete reflection | 6,845,141 |

The spread is **9.555%** (the pod's render log reports 0.0956), 7.6 points over
the gate. The pipeline stopped there as designed. The F3-concrete frame produces
longer transcripts in 3,727 of 5,319 training scenarios and shorter ones in 1,578.

## 2. The rule

1. Candidates are training-split scenarios; validation rows do not enter the
   gated total.
2. Rank them by the absolute difference between their F3 and F3-concrete rendered
   token counts, largest first; ties by scenario ID, ascending.
3. Drop whole scenarios in that order from all four frames, so every arm stays
   paired. Recompute the spread after each drop and stop at the first drop for
   which it is at most 2%.
4. Drop at most 560 scenarios (10% of 5,600; the `d03508` exclusion is separate).
   If the gate is not met within the cap, the outcome is `parity_unreachable`:
   nothing is dropped, the study stops at this gate, and that is reported.

The rule selects on generated length, never on outcomes. It is decided before any
training, adapter, evaluation row or judge call exists. If it had balanced the
arms, the training split would have shrunk by the number dropped and the
validation split would have stayed at 280.

## 3. Outcome on the real data

The rule was run on the real rendered counts (totals reproduce the pod's manifest
exactly). Dropping the 560 highest-ranked scenarios lowers the spread only from
9.555% to **6.424%**. The outcome is **`parity_unreachable`**. Nothing is dropped
under this amendment, and the 560-scenario list is recorded for audit only (its
hash is in the twin).

For context, not as part of the rule: the highest-ranked scenarios are mostly ones
where F3-concrete is longer (507 of the first 560). Even dropping only scenarios
where F3-concrete is longer, in the same order, needs 1,222 scenarios (23% of the
training split) to reach 2%. No drop rule with a 10% cap can meet this gate,
because the gap is a property of most scenarios, not of a few outliers.

## 4. Consequence

The registered gate stands unmet and the study stops at it. This amendment does
not loosen the gate, raise the cap, or choose a way forward. Possible routes, each
needing a further amendment from the author before any training: a larger cap
(about 23% of training scenarios), a changed or replaced parity criterion (for
example equal optimizer steps or equal token exposure per arm instead of equal
total tokens), or accepting the 9.6% difference and reporting it as a limitation
of the F3 versus F3-concrete contrast.
