# Harmful-evaluation source license handoff

Status: **OPEN — blocks the predecessor reanchor**

Checked: 2026-07-19

Frozen source: `LLM-LAT/harmful-dataset` at
`8bfba31bc6d93a5b71808fee5275ef4b6330ed91`

## Finding

The frozen Hugging Face revision exposes the dataset files and a 363-byte
dataset card, but it does not declare a license. The current dataset card is
also empty apart from generated metadata. The MIT license on the associated
Latent Adversarial Training code repository is not evidence that these
separately distributed dataset bytes are MIT-licensed.

Authoritative locations checked:

- <https://huggingface.co/datasets/LLM-LAT/harmful-dataset/tree/8bfba31bc6d93a5b71808fee5275ef4b6330ed91>
- <https://huggingface.co/datasets/LLM-LAT/harmful-dataset>
- <https://huggingface.co/LLM-LAT>

The frozen content remains unchanged and hash-valid. This is a provenance and
permission blocker, not a content-integrity failure.

## Resolution paths

Use exactly one of these paths before base-model generation over the harmful
universe:

1. **Preserve the recovered universe (preferred).** Obtain a license declaration
   or written permission from an authorized dataset maintainer covering
   research evaluation, storage of the frozen subset, derived score artifacts,
   and publication of aggregate results. Bind the dated evidence to the source
   revision and the frozen source-file SHA-256
   `51a41eaebf21eabec33ea90366d01d5bee7edb933d439c7017ad6e0107a645b1`.
2. **Institutional determination.** Record a signed determination by the
   institution's authorized reviewer that the planned use is permitted. The
   receipt must identify the reviewer, policy or legal basis, permitted uses,
   date, frozen revision, and source-file hash. An automated or researcher-only
   assertion is insufficient.
3. **Prospective substitution.** Before any affected outcome is generated,
   amend the protocol to use a source with explicit compatible terms and freeze
   new prompt IDs, hashes, judges, annotation packets, and analysis joins. This
   path is not an exact predecessor reanchor: the recovered F0 calibration
   interval cannot serve as a confirmatory reproduction target on a changed
   universe. Establish a new prospective base baseline and disclose the
   substitution.

Do not treat a downstream mirror's self-declared license as permission for the
upstream bytes unless it provides a verifiable rights chain.

## Maintainer inquiry draft

> Subject: License clarification for LLM-LAT/harmful-dataset
>
> We are conducting a non-commercial research evaluation using a frozen
> 200-prompt subset of `LLM-LAT/harmful-dataset` revision
> `8bfba31bc6d93a5b71808fee5275ef4b6330ed91`. The Hugging Face dataset card does
> not currently declare a license. Could an authorized maintainer confirm the
> dataset's license or grant written permission for research evaluation,
> storage of the frozen subset, creation of derived model outputs and scores,
> and publication of aggregate results? We will attribute the dataset and its
> associated paper. We will not redistribute the full source dataset.

Send only through an authorized project account. Preserve the complete reply,
sender identity, date, and message headers or public issue URL in the final
license receipt.

## Receipt minimums

A passing license receipt must contain:

- decision and permitted-use scope;
- source repository and exact revision;
- source filename and SHA-256;
- frozen 200-prompt universe SHA-256
  `a11af31e733ff0953466c8ec9b2347d2dc5b2d5fe4b1009eb9278fd5da117b44`;
- reviewer or rights-holder identity and authority;
- dated signature, public declaration URL, or immutable external receipt;
- any attribution, redistribution, or publication conditions.

Until that receipt exists, keep `evaluation_universe_freeze` at
`pending_license_resolution` and `passed: false`.
