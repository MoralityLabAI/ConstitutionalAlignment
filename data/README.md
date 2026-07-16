# Research data tracked in this repository

This directory contains small, auditable research fixtures and synthetic pilot
datasets. It does not contain model checkpoints, raw cloud transcripts, or a
validated constitutional-alignment corpus.

## Jinn/Mutazili pilot data

The `jinn_tiny_mutazili_*`, `jinn_qwen*`, and
`jinn_identity_internalization_eval_v1` directories support local harness and
SFT-bracket experiments. "Jinn" is an as-if accountability frame. These records
must not be used to train literal claims of jinn identity, revelation, unseen
knowledge, prophecy, or religious authority.

The numbered correction, rehearsal, witness, and failure-mined tranches are
successive local engineering artifacts. They are highly dependent and must not
be counted as independent samples. The v1/v2 probe sets were repeatedly used for
failure discovery, evaluator repair, and tranche construction; they are open
development gates, not sealed evaluation sets. A future confirmatory run needs a
new independently authored held-out suite.

The MeTTa-derived datasets record symbolic provenance, but their targets remain
experimental labels rather than formal proofs of theological or constitutional
correctness. Qualified scholar review is still required.

## Sufi/Jannah storyworld prompts

`storyworld_sources/sufi_jannah_20260508` contains a small fixed-option prompt
export and source receipts derived from the separately maintained GPTStoryworld
project. Ranked Jannah endings are symbolic storyworld mechanics, not doctrinal
claims. Review provenance, distribution rights, historical representation, and
theological interpretation before training or publication.

## Artifact boundary

Large generated corpora, adapters, checkpoints, prompt runs, and model outputs
belong under ignored `artifacts/` paths or cloud artifact storage. Commit only
small source datasets, manifests, hash receipts, and cleared aggregate results.
