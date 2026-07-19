# Prospective licensed evaluation-universe substitution

Amendment ID: `frame_internalization_harmbench_substitution_v2`  
Frozen: 2026-07-19  
Status: active before any affected base, adapter, judge, or probe outcome

## Purpose

The recovered harmful evaluation universe was sampled from
`LLM-LAT/harmful-dataset`, whose pinned distribution does not declare a
license. Rather than infer permission, this amendment activates the explicitly
licensed HarmBench standard behavior set for all new frame-internalization
generation, judging, probing, and adapter evaluation.

The original v1 universe and all of its hashes remain immutable provenance. It
is not fielded under this amendment.

## Frozen replacement

The harmful universe is every row whose `FunctionalCategory` is exactly
`standard` in the official HarmBench behavior CSV, in source order:

- repository: `centerforaisafety/HarmBench`;
- revision: `8e1604d1171fe8a48d8febecd22f600e462bdcdd`;
- source: `data/behavior_datasets/harmbench_behaviors_text_all.csv`;
- source SHA-256:
  `8d81accedd38eaaf8b760618622bb888417d1fd0c86eba65c427a16f1cbb4afc`;
- selected rows: 200, with 200 unique `BehaviorID` values and no nonempty
  context fields;
- repository-root license: MIT, SHA-256
  `fb424622fb4d8c1d7f952258dc56ed1e8e8b7ecc242f7db43ccb5a608205ec5b`.

The 100-row benign universe remains byte-identical to v1. The 150-row override
universe is rebuilt by applying the recovered fresh seed-42 sampling rule to
the replacement harmful rows and sorting the selected rows by replacement
prompt ID.

The authoritative receipt is
`rerun_freeze/evaluation_universes_v2.json`, SHA-256
`a45fd158279eb4ad3425b6ddd19fafab33849d942f7b8639956882de2cfa7870`.
The sealed manifest is `readiness/evaluation_seal_v2.json`, SHA-256
`23cbbd4b28467e2c5a572eac1244bd0f1cfeaf8ec1d815d9112cdbc173eefa7b`.

## Consequence for the predecessor reanchor

This is a prospective substitution, not an exact predecessor reanchor. The
recovered F0 gap interval `[0.3167, 0.4033]` is retained only as descriptive
historical provenance. It is not a confirmatory reproduction target, a
readiness pass/fail interval, or an analysis prior on the replacement universe.

Before adapter outcomes are visible, the frozen base model must establish a
new prospective v2 baseline over all 200 replacement prompt IDs. The required
base work otherwise remains unchanged: complete free/paid joins, frozen judge
and classifier revisions, blinded human validation, the registered layer-27
probe and controls, benign guards, and explicit failure accounting.

## Consequence for prompt-versus-SFT analysis

Every term in the direct prompt-versus-SFT contrast uses v2 prompt IDs and
hashes. No v1 and v2 outcome rows may be pooled. The registered definitions,
sign convention, paired seeds, decoding, missing-data policy, bootstrap unit,
simultaneous intervals, and guard requirements remain unchanged.

## Consequence for training and nonleakage

The six training arms, curriculum source rows, split assignments, dose, and
compute caps do not change. The existing source-prompt corpus must be checked
against v2, and the final rendered six-arm curriculum must pass a v2-bound
nonleakage audit before pilot authorization. The v1 nonleakage precursor is
provenance only after this amendment.

## Timing attestation

At freeze time:

- no registered six-arm adapter had been trained;
- no affected v2 base or adapter response had been generated;
- no v2 judge prediction, human label, activation, fitted probe, or scored
  endpoint existed;
- the replacement was selected to resolve a prospective licensing gate, not in
  response to model behavior.

Any change to the 200 source rows, their order, the prompt-ID mapping, the
override selection, or the benign bytes requires a new amendment and invalidates
all dependent v2 queues and contracts.
