# Exploratory Alignment Policy Receipt

This directory records the completed 2026-07-15 QLoRA/GRPO pilot. The adapter
weights remain local at the path and hash in `checked_receipt.json`; they are not
committed because source provenance, distribution licenses, model licensing, and
scholar review are incomplete.

The 51-step run passed its finite-parameter and optimization-signal gates. The
four-cluster, two-generation-per-cluster test pilot did **not** show an aggregate
proxy improvement: policy minus base weighted reward was -0.355 (paired
prompt-cluster bootstrap 95% interval [-2.212, 1.334]). Complete-contract rate
increased by 0.125, while valid-decision rate decreased by 0.125. One policy
response used an invalid option ID and invalid tenet. The checkpoint is therefore
not promoted.

Files:

- `checked_receipt.json`: sanitized training/runtime/code/input hashes and gates.
- `base_evaluation_receipt.json`: base-model proxy summary.
- `policy_evaluation_receipt.json`: adapter proxy summary.
- `evaluation_comparison.json`: paired prompt-cluster deltas and bootstrap
  intervals.

These results are exploratory proxy measurements, not evidence of Islamic
constitutional compliance or alignment improvement. The test split is open; do
not tune or select another checkpoint against these four clusters.
