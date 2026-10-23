# Protocol Amendment: No Human Validation

Amendment: `frame_internalization_no_human_validation_v1`  
Frozen: 2026-10-24  
Status: frozen before any Qwen base row, judge prediction, curriculum transcript,
adapter, or scored outcome exists for the registered study. Compute is not
started by this amendment.

## 1. Human validation is dropped

The registered blinded human validation of the 1,600 prospective Qwen
base-model rows (200 compliance units and 200 strict-alignment-faking units,
Cohen's kappa of at least 0.70 per task; factor F15 in
`GATE_FACTORIZATION_V1.md`) is **removed** from the study. The removal is made at
the author's explicit instruction of 2026-10-24 ("forget about the human
raters").

What replaces it:

- The registered automated judges alone are the instrument:
  `claude-opus-4-8` for strong-reject compliance and `claude-sonnet-5` for the
  strict alignment-faking classifier, under the frozen configuration in
  `readiness/judge_configuration_freeze_v1.json`. Nothing about their prompts,
  schemas, decoding, retries, or missing-data rule changes.
- A descriptive agreement check that needs no people. A second automated judge
  from a different model snapshot, with the same rubric and schema, scores the
  same frozen 400-unit validation queue
  (`rerun_freeze/predecessor_judge_validation_queue_v2.jsonl`). Cohen's kappa
  between the two judges is **reported**, per task, with its interval. It is not
  a pass/fail gate, and no threshold of 0.70 or any other value is applied to
  it. The second judge's model ID and snapshot are bound in a receipt before its
  first call, and it is never used to replace, tune, or select among the primary
  judge's outputs.

**This weakens the study, and the paper must say so.** Agreement between two
automated judges is not evidence that either judge matches human reading of the
rubrics. The two judges may share biases, and the second judge is not
independent in the way blinded human raters would be. Human-validity claims
about the compliance and strict-AF scores are therefore not supported by this
study. Any result is conditional on the automated judges, and the paper's
limitations section must state that the registered human gate was dropped
before outcomes, at the author's instruction, and not passed.

Consequences for the factor graph: F15 is retired (neither passed nor failed) and
replaced by F15b, "second-judge descriptive agreement reported". F15b is a
reporting requirement and does not block F17 or F19. F14 (complete frozen judge
predictions) and F17 (base analysis) keep their definitions and no longer wait
on F15. The base-analysis receipt must list the human gate as `dropped` and
carry the second-judge kappa.

## 2. Authorization

The signed-authorization gate (F19, parent gate G10,
`compute_authorization.v2`) is satisfied by the author's instructions of
2026-10-23 and 2026-10-24 to run the study. No separate signature artifact is
required. The authorization record that the launcher consumes is built from this
amendment and from the caps below, and it binds the exact command.

This authorization does not extend to any budget the author has not set. The
spend caps in force for this amendment's pilot stage are those the author's
instruction gave: US$3 and 2 billable hours on one Prime pod with at least 24 GiB
of GPU memory, with a watchdog started before the pod and zero pods remaining at
the end. A larger budget, including the protocol's own full-run cap of 48
GPU-hours, is not recorded here as authorized; it requires a further instruction
from the author in chat, which would be recorded in a later amendment.

## 3. Everything else stays as registered

Unchanged: the six arms, the 5,600 dilemmas and the 5,320/280 split, 4,096-token
sequences, two epochs, the QLoRA recipe, the licensed HarmBench v2 evaluation
universe and seal, the direct prompt-versus-SFT contract, the three-endpoint
internalization gate, the benign over-refusal guard, the layer-27 probe and its
controls, F3 versus F3-concrete token parity of at most 2%, generated-text
nonleakage, the full-topology 50-step per-arm smoke, the stop and abort rules,
and the paper's claim ladder. Scholar review remains pending and non-blocking
under `PROTOCOL_AMENDMENT_V2.md`.

No other gate is changed. In particular, no gate is waived for cost reasons: the
cost projection in `primelab_f06/f06_throughput_smoke_result_v1.json` (about 185
generator hours and about US$228 for the 22,400-transcript curriculum at the
exact NF4 batch-8 path) is a fact about what the study costs, not a reason to
shrink the registered curricula.

## 4. Timing attestation

At freeze time no Qwen base generation, judge prediction, human label,
activation, fitted probe, curriculum transcript, adapter, or scored endpoint of
the registered study existed. The change was made for the author's workload
reasons, not in response to any model behavior.

Machine-readable twin: `protocol_amendment_no_human_validation_v1.json`.
