# Storyworld evaluation sealing proposal v1

Date: 2026-07-17

Status: proposal only. This document authorizes no spend, authoring, file move,
sealed-content access, adapter run, unseal, or result publication. It introduces
no replacement split or protocol. Execution must use the existing artifacts and
scripts named below.

## Verified starting posture

Read-only validation on 2026-07-17 established:

- `split_freeze_v1.json` passes with 12 train, 4 development, and 6 evaluation
  causal families; `sealed_content_opened` is false. Its current SHA-256 is
  `d793f856211acdd150fb2d42c99b77178488ea8cdc14767da8976f8e34214d37`.
- `blinded_eval_protocol_v1.json` passes in `closed_authoring` state. Its current
  SHA-256 is
  `a97d1dae248e8454d24c60c6db6d164d4fa5dd71fbf1d5f04a07414aed6c453e`.
- `package.json` resolves 22 nonsealed worlds and has current SHA-256
  `4e554ef3c4b28820c6875a04bced26df54ea065fea7169e1f44cf3c7d6fcc31e`.
- `prepare_blinded_storyworld_eval.py` reports a closed one-time gate, six
  evaluation families, no opened sealed content, and a passing closed-gate
  receipt.
- The readiness audit is 1 of 11 gates passed: `factory_design` passes and the
  other ten gates remain pending. `package.json` still has `review_bundle` set
  to null.

These hashes are observations for this proposal, not a new freeze. Execution
must recompute them and stop if they differ from the artifacts deliberately
approved for the run.

## Invariants

1. Preserve the assignments in `split_freeze_v1.json`; evaluation families
   never enter training or development manifests.
2. Keep evaluation prompts, actions, outcomes, private facts, keys, traces,
   targets, and content hashes outside the repository and outside every
   training operator's view until the single authorized opening.
3. Give sealed authors only the five fields allowed by
   `blinded_eval_protocol_v1.json`: family ID, causal-cluster ID, construct,
   authoring mode, and review requirements.
4. Keep candidate adapter identities, outputs, development scores, and failure
   examples unavailable to sealed authors and reviewers.
5. Select one checkpoint globally across all four arms from the complete 4 by 4
   development matrix under `analysis_plan_v1.json`; never select per arm.
6. Freeze metrics, contrasts, code, adapter artifact hashes, and the selected
   checkpoint before any sealed transfer.
7. Open the sealed evaluation exactly once. Emit zero training rows and permit
   no post-open metric, contrast, checkpoint, or analysis change.
8. Treat every missing, duplicate, stale, unsigned, malformed, or hash-mismatched
   receipt as a closed gate.

## Phase A: prepare the closed authoring envelope

After an execution location and access-control owner are approved, generate the
sanitized authoring kit outside the repository:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/freeze_storyworld_splits.py `
  --output D:/Research_Engine/storyworld_curriculum/split_freeze/RECEIPT.json

python scripts/prepare_blinded_storyworld_eval.py `
  --output-dir D:/Research_Engine/storyworld_curriculum/blinded_authoring_v1
```

Before transferring the kit, compare its package, split, protocol, schema, and
inventory hashes to an approved run ledger. Transfer only `AUTHOR_BRIEFS.json`
and the content-free receipt template. Do not transfer train/development worlds,
review packets, teacher traces, adapters, predictions, scores, or keys.

## Phase B: author and review inside external access control

Use separate principals for sealed authoring and model/training operation. The
external environment must contain six families exactly:

- upgrades: `coercive_doctrinal_authority`,
  `rights_petition_under_dependency`, and `flooded_archive_rescue`;
- blind originals: `medical_consent_triage_holdout`,
  `distributed_supply_deception_holdout`, and
  `ecological_irreversibility_holdout`.

Isolate authoring by family as well: an author must not see a submission created
for another evaluation family before the one-time opening.

Each family must satisfy `storyworld_branching_world_v1`, the protocol's 6-10
decision turns, at least two endings and Pareto actions, private evidence,
opaque action IDs, single and dyadic variants, and the five-factor sweep. Keep a
sealed manifest with hashes for the exact worlds, public requests, private keys,
action maps, evaluator inputs, and analysis-ready outputs. That manifest stays
inside the external environment.

Obtain the named domain, scholar, rights, historical, safety, and research-
ethics reviews. The outward-facing completion receipt may carry family IDs,
counts, signatures, an access-controlled location reference, and references to
one family review and one structural validation receipt per family. It must not
carry sealed prompt material or content hashes into training provenance.

Complete `SEALED_AUTHORING_RECEIPT_TEMPLATE.json` only after all six families
are approved. Its final state must be
`approved_in_external_access_controlled_environment`, with both visibility
flags false, a timezone-bearing signature, and an external receipt reference.

## Phase C: finish the nonsealed evidence chain

No sealed authoring result may influence these steps:

1. Complete all nonsealed world reviews and generate the approved
   `storyworld_review_application_bundle_v1`.
2. Complete the real main and support pilots and their human review bundles.
3. Build the reviewed four-arm 10M pack and retain its exact packing manifest.
4. Freeze the base model/tokenizer and obtain adapter-training authorization.
5. Train all four matched arms—`neutral`, `constitutional`, `jinn`, and
   `beast`—with checkpoints at 1M, 3M, 6M, and 10M tokens.
6. Run `audit_storyworld_training_nonleakage.py` on the exact reviewed packing
   manifest. The receipt must show only train provenance, zero development and
   evaluation rows, six still-closed evaluation families, and the matching
   packing-manifest hash.
7. Build and keep separate the public development requests and private keys.
   Score all 16 arm/checkpoint cells with full coverage, no duplicate or unknown
   predictions, at most the frozen invalid-response rate, and no sealed access.
8. Run `freeze_storyworld_analysis_selection.py` with all 16 score receipts and
   every analysis-code file used after unseal. It must select one eligible
   checkpoint shared by all four arms and record `sealed_evaluation_opened` as
   false.

The analysis-code list must include the external scorer/aggregator interface as
well as repository analysis code. Adding code after this receipt requires
stopping before unseal and issuing a new pre-result freeze.

## Phase D: pre-unseal reconciliation

One operator who cannot alter sealed content should assemble these exact inputs:

- approved nonsealed review bundle;
- reviewed 10M packing manifest;
- passing training-provenance nonleakage receipt bound to that manifest;
- passing analysis freeze with the global checkpoint selection;
- one passing adapter-training receipt for each of the four arms, each
  containing the selected checkpoint and artifact-set SHA-256;
- approved six-family sealed-authoring completion receipt;
- human authorization attribution and an external authorization reference.

Re-run the readiness auditor with all evidence available so far. It should pass
through `analysis_and_checkpoint_selection_freeze` while
`one_time_sealed_evaluation` remains pending. Confirm that the intended unseal
authorization output path does not exist. A pre-existing output path is a hard
stop, not a reason to rename the second attempt.

Before the real opening, exercise the complete transfer, runner, scorer, and
result-recorder path on synthetic fixtures that contain no sealed family data.
This is the only retryable execution rehearsal.

## Phase E: issue the sole authorization

After explicit human approval, run the existing fail-closed command once:

```powershell
python scripts/authorize_storyworld_one_time_unseal.py `
  --review-bundle <approved-review-bundle.json> `
  --packing-manifest <reviewed-packing-manifest.json> `
  --training-nonleakage <nonleakage-receipt.json> `
  --analysis-freeze <analysis-freeze.json> `
  --adapter-training-receipt <neutral-training-receipt.json> `
  --adapter-training-receipt <constitutional-training-receipt.json> `
  --adapter-training-receipt <jinn-training-receipt.json> `
  --adapter-training-receipt <beast-training-receipt.json> `
  --sealed-authoring-receipt <sealed-authoring-completion.json> `
  --authorized-by <accountable-operator> `
  --authorization-reference <external-authorization-receipt> `
  --output <one-time-unseal-authorization.json> `
  --authorize-one-time-unseal
```

The authorization must remain `authorized_not_yet_opened`, bind all input
hashes, name exactly four distinct adapter arms and one selected checkpoint,
cover six families, and set both `one_time_unseal` and
`additional_unseal_authorizations_allowed` to their fail-closed values. It is
an authorization envelope, not a result and not sealed content.

## Phase F: execute externally once

Transfer the authorization and the four selected adapter artifact sets to the
external execution principal. That principal may open the sealed bundle only
after verifying the authorization ID and SHA-256. Execute the already frozen
request builder, inference settings, scorer, metrics, contrasts, and summary
code without network retrieval or adaptive reruns.

The signed external result must use
`storyworld_external_sealed_evaluation_result_v1` and bind:

- the protocol ID, unseal authorization ID, and authorization SHA-256;
- all six evaluation families;
- the exact four `(arm, adapter_artifact_set_sha256)` pairs;
- zero training rows;
- `metric_or_contrast_changes_after_unseal: false`;
- a timezone-bearing signature, external receipt reference, completion state,
  and the frozen result summary.

Return the signed result object and its immutable storage reference. Keep raw
sealed prompts, private keys, action maps, and row-level outputs inside access
control unless a separately approved disclosure plan exists.

## Phase G: record and close

Record the external result once, to a path that does not already exist:

```powershell
python scripts/record_storyworld_one_time_sealed_evaluation.py `
  --unseal-authorization <one-time-unseal-authorization.json> `
  --external-results <signed-external-result.json> `
  --output <one-time-sealed-evaluation-receipt.json> `
  --record-one-time-sealed-evaluation
```

The resulting receipt must bind both authorization and external-result hashes,
mark the sealed content opened, preserve the selected checkpoint and adapter
hashes, emit zero training rows, and prohibit another opening. Run the readiness
auditor with the final receipt; only then may `objective_complete` become true.

Publish or report only the metrics and contrasts frozen before opening. Any new
analysis is labeled exploratory and cannot change the registered result.

## Fail-closed conditions and known v1 gap

Stop before opening on any receipt, hash, coverage, review, visibility,
checkpoint, arm-set, path-existence, or authorization mismatch. Stop if any
sealed material or content hash appears in training provenance or in an
unauthorized principal's logs.

The current v1 recorder accepts only an externally signed result with
`passed: true`. It has no terminal receipt type for an execution that opens the
bundle and then fails before producing a passing result. Therefore the real
opening must not begin until the fixture rehearsal passes. If a failure occurs
after opening, do not rerun under v1 and do not describe the gate as closed.
Preserve the incident and authorization bytes externally, report the evaluation
as opened without a valid completed result, and require an explicitly reviewed
v2 protocol before any later attempt.

## Completion test

This proposal is implemented only when all eleven readiness gates pass, the
single final receipt validates, no evaluation row enters training, no
post-unseal analysis choice changes, and no second authorization or output path
exists. Until then, the repository remains a structurally valid factory with a
closed evaluation gate.
