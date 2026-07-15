# Local Corpus Build Specification v1

Status: design specification; no corpus described here is approved for training
until its build and review gates pass.

Recipe: `papers/data_recipe_v1.yaml`

License control: `papers/DATA_LICENSES.md`

## Non-negotiable gates

1. Freeze every input by immutable revision and SHA-256. Record the exact loader,
   configuration, split, and retrieval date. A mutable branch name is not a
   revision.
2. Store the recipe-required provenance fields on every row: `sample_id`,
   `source`, `split`, `transform_version`, `constitution_version`, and `track`.
3. Also store `original_split`, `license_tag`, `language`,
   `transformation_chain`, `source_revision`, `source_record_id`,
   `source_sha256`, `builder_commit`, `generator_model`,
   `generator_revision`, `generator_prompt_sha256`, `review_status`,
   `reviewer_role`, `needs_scholar_review`, and `dedup_cluster_id`. Use null,
   never an invented value, when a field is inapplicable.
4. Reject a religious quotation or source attribution unless it resolves to the
   frozen source record. Reject an interpretive claim from training until a
   qualified reviewer approves it. Machine-generated citations are not evidence.
5. Build and freeze all evaluation sets first. Run exact and semantic leakage
   checks against the union of eval prompts, answers, source passages, and
   paraphrases before admitting a training row.
6. Block training and redistribution while any source is marked `No`, `Unknown`,
   or `Needs review` in the license manifest. A dataset-level license tag does
   not by itself establish rights in incorporated source works.

## Shared data controls

### Versioned artifacts

Each build emits:

- `records.jsonl`, sorted by `sample_id`;
- `manifest.json`, containing input revisions and hashes, counts before and after
  every filter, rejection counts by reason, prompt hashes, generator settings,
  reviewer roster hashes, dedup configuration, and output SHA-256;
- `rejections.jsonl`, containing IDs and machine-readable reasons without
  silently discarding rows;
- `DEDUP_REPORT.md`, including threshold calibration and cross-split leakage
  results; and
- `LICENSE_SNAPSHOT.md`, containing the exact terms reviewed for every input.

### Exact and semantic deduplication

Apply this procedure to each corpus and again to the union of all corpora:

1. Compute a raw-content SHA-256 after UTF-8 decoding and newline normalization.
2. Compute a comparison key after Unicode NFKC normalization and whitespace
   collapse. Keep the raw text. Do not remove Arabic diacritics from source
   quotations; a separate diacritic-insensitive key may flag candidates for
   review but must not automatically merge them.
3. Group prompt templates before splitting, so paraphrases of one seed cannot
   cross train, development, and evaluation boundaries.
4. Embed the semantically relevant fields with a pinned multilingual embedding
   model. Before the build, label at least 500 candidate pairs spanning Arabic,
   English, translations, and hard negatives. Choose and freeze the threshold
   that achieves at least 0.95 duplicate-detection precision on that calibration
   set; do not copy a threshold from another model.
5. Keep the earliest licensed primary-source row within a training-only cluster.
   If a cluster touches evaluation, quarantine every training member. Human
   review decides borderline or cross-tradition clusters.
6. Report exact removals, semantic removals, quarantines, reviewer overrides,
   embedding revision, threshold, and calibration precision/recall.

## Evidence corpora

### `quran_500_wisdom_verses`

Purpose: a shared, track-independent evidence corpus. The name is a target size,
not permission to fill a quota with unreviewed verses.

Selection procedure:

1. Freeze one authoritative Arabic text edition and its license. No edition is
   approved by this specification; the owner must document the selected edition
   and obtain legal review before collection begins. Add the selected edition as
   a new row in `papers/DATA_LICENSES.md` before acquiring its text.
2. Pre-register a balanced topic grid derived from the constitutions' principle
   labels, including justice, truthful speech, mercy, stewardship, reflection,
   and counterexamples where a keyword occurs without supporting the target
   principle. The grid must be identical for all tracks.
3. Two independent, qualified Quranic-studies reviewers screen candidate verses
   without seeing the target track. A third reviewer adjudicates disagreements.
   Inclusion requires an explicit reason tied to the pre-registered grid; quota
   pressure is not an inclusion reason.
4. Include every verse cited by a constitution only after the citation validator
   passes. Inclusion verifies the reference and text, not the associated
   interpretation. Interpretations retain `needs_scholar_review: true` until
   separately approved.
5. Target 500 unique `surah:ayah` records. If fewer pass review, publish the
   smaller count and retain the corpus name only as a stable recipe identifier.

Translations:

- Store the Arabic source text plus at least one English translation chosen by
  the owner with a bilingual scholar and legal counsel. No English translation
  is approved yet; this is an explicit release blocker, not a request for the
  builder to improvise a translation.
- Pin translator, edition, publisher or canonical repository, license or written
  permission, revision, retrieval date, and file hash. Never label an LLM
  paraphrase as a translation.
- Keep each Arabic verse and all approved translations in one dedup/split group.

Additional provenance fields: `surah`, `ayah`, `arabic_edition`,
`translation_id`, `translator`, `translation_edition`, `selection_topic`,
`selector_ids`, `adjudicator_id`, `selection_rationale`,
`text_verification_status`, and `interpretation_review_status`.

### `ashari_tafsir_corpus` and `mutazili_tafsir_corpus`

Candidate source: [`Kandil7/Athar-Datasets`](https://huggingface.co/datasets/Kandil7/Athar-Datasets),
whose card reported 18,701,966 passages across ten collections when checked on
2026-07-14. Start with its `quran_tafsir` collection and inspect `aqeedah_passages`
only when a record has enough bibliographic metadata to resolve the underlying
work. Pin the Hub commit rather than `main`.

The card labels the aggregate MIT and attributes material to the Shamela library.
That tag is not sufficient proof that every underlying work can be redistributed.
Counsel must review Shamela terms, source-work status, and the intended release;
until then, use is blocked even if local experimentation would be lawful.

Tradition filtering procedure:

1. Islamic-studies scholars produce a versioned bibliography mapping exact
   `book_id`, title, author identity, edition, and relevant volume to one of
   `ashari`, `mutazili`, `mixed`, `disputed`, or `unknown`, with a cited
   bibliographic justification. This specification intentionally names no work
   or author as belonging to either tradition.
2. Include only records mapped `ashari` in the Ashari corpus and only records
   mapped `mutazili` in the Mutazili corpus. Exclude `mixed`, `disputed`, and
   `unknown`. Do not classify by keywords, author-name substring, era, or an LLM.
3. Resolve each passage to book, author, volume/page or stable source location,
   and surrounding section. Reject truncated, OCR-corrupt, metadata-conflicting,
   or source-unresolvable passages. Preserve the original Arabic.
4. Remove navigation text and repeated headers using deterministic rules whose
   before/after hashes are recorded. Split on source section boundaries, not an
   arbitrary token window that merges authors.
5. Deduplicate within each book, across editions, across the two traditions, and
   against the Quran corpus and all eval sets. Cross-tradition near-duplicates go
   to scholar review rather than automatic assignment.
6. A second scholar audits a stratified sample from every included work and all
   automated rejection categories. No corpus is released until the audit finds
   zero wrong-tradition assignments in the pre-registered acceptance sample.
   Report the sample size and an exact binomial confidence interval; do not
   describe a sample with zero observed errors as proof of zero population error.

Additional provenance fields: `athar_revision`, `collection`, `book_id`,
`book_title`, `author_canonical_id`, `author_death_year_as_recorded`, `edition`,
`volume`, `page_or_locator`, `chapter`, `tradition_label`,
`tradition_label_source`, `bibliography_reviewer_ids`, `text_audit_status`, and
`upstream_rights_status`.

### Other named evidence

`anthropic_claude_constitution_cc0_snapshot` is the generic control's only named
evidence. Resolve it to the repository snapshot under `papers/sources/`, record
the original URL, acquisition date, CC0 notice, file hash, and builder commit,
and keep it identical for every control-track build.

`fiqh_mcp_outputs` is not training data. It is an inference-time artifact for the
paired MCP ablation only. For each retrieval record the query ID, server and tool
version, arguments, timestamp, complete returned content, content hash, cited
source IDs, and citation-validation result. Keep the frozen Ashari checkpoint and
prompt fixed across MCP-off/on arms. An MCP response is not religious ground truth
and any interpretive scoring remains subject to scholar review.

## Generated training corpora

All three tracks use the same seed prompts, counts, generator revision, sampling
settings, language allocation, review protocol, and acceptance gates. Only
`constitution_version` and its permitted evidence corpus may differ. The generic
control uses its frozen secular constitution source and no Islamic evidence.

### Constitutional SFT

Recipe IDs:

- `local/constitution_synthetic_ashari`
- `local/constitution_synthetic_mutazili`
- `local/constitution_synthetic_control_generic`

Build 10,000 accepted rows per track. At least 30% must be counterexamples:
15% near misses that use virtuous language but recommend a prohibited action,
and 15% conflicts where two principles pull in different directions. Report the
realized shares; do not backfill rejected examples without preserving strata.

Seed-scenario authors work without seeing a track label. Instantiate each
accepted seed once per track. The generator receives this versioned template:

```text
SYSTEM: Produce one concise training answer under CONSTITUTION_VERSION. Use only
the supplied EVIDENCE_RECORDS. Never invent or repair a citation. If evidence is
insufficient, set needs_scholar_review=true and avoid a religious ruling. Do not
output private chain-of-thought.

USER: Scenario: {scenario}
Dilemma type: {dilemma_type}
Counterexample stratum: {stratum}
Evidence records: {record_ids_and_text}

Return JSON with exactly: judgment_label, concise_justification,
recommended_action, evidence_record_ids, needs_scholar_review.
```

Normalize accepted output to the recipe's `sft_sample` schema:
inputs `prompt`, `context`, `dilemma_type`; outputs `judgment_label`,
`concise_justification`, `recommended_action`. Preserve the extra evidence and
review fields in provenance. Validate citation strings against source records.
Human reviewers check safety, schema, and factual entailment; qualified scholars
must approve every Islamic interpretive claim before it enters training.

### Socratic critique and revision

Recipe IDs:

- `local/socratic_rollouts_ashari`
- `local/socratic_rollouts_mutazili`
- `local/socratic_rollouts_control_generic`

Build at least 5,000 accepted tuples per track from the same scenario IDs. Use a
frozen base model to draft without a constitution, then critique and revise under
the assigned constitution. At least 30% of tuples must come from the two SFT
counterexample strata, balanced 15%/15%.

```text
SYSTEM: Evaluate DRAFT under CONSTITUTION_VERSION using only EVIDENCE_RECORDS.
Identify observable answer defects, then write a concise revision. Never invent
a citation or provide hidden chain-of-thought. If an Islamic interpretation is
not approved in the evidence metadata, set needs_scholar_review=true.

USER: Prompt: {prompt}
Draft: {draft_answer}
Evidence records: {record_ids_and_text}

Return JSON with exactly: violation_flags, critique, revised_answer,
evidence_record_ids, needs_scholar_review.
```

The normalized row uses the recipe's `critique_sample` inputs `prompt`,
`draft_answer`, `constitution_version` and outputs `violation_flags`, `critique`,
`revised_answer`. Reviewers must confirm that the revision fixes the flagged
defect without introducing unsupported content. Keep rejected drafts for audit;
do not train on unreviewed critique text.

### Constitutional preference pairs

Recipe IDs:

- `local/constitutional_preference_pairs_ashari`
- `local/constitutional_preference_pairs_mutazili`
- `local/constitutional_preference_pairs_control_generic`

Build at least 8,000 accepted pairs per track. Pair candidates from different
generators or independently sampled decodes; never create the rejected response
by merely deleting a citation. At least 30% of pairs must be counterexamples,
balanced between deceptive near misses and genuine principle conflicts. Randomize
A/B presentation independently for each annotator.

```text
SYSTEM: Compare RESPONSE_A and RESPONSE_B under CONSTITUTION_VERSION. Judge only
their visible content against the supplied constitution and verified evidence.
Do not reward religious wording by itself. Do not infer hidden reasoning. If the
choice depends on an unreviewed interpretation, abstain and set
needs_scholar_review=true.

USER: Prompt: {prompt}
Response A: {response_a}
Response B: {response_b}
Evidence records: {record_ids_and_text}

Return JSON with exactly: preferred, preference_rationale_short,
needs_scholar_review.
```

Normalize to the recipe's `preference_pair` schema: inputs `prompt`, `response_a`,
and `response_b`; outputs `preferred` and `preference_rationale_short`. Obtain two
independent human labels. Adjudicate disagreement; a qualified scholar
adjudicates any Islamic interpretive dependency. Store annotator pseudonyms,
order randomization, labels, abstentions, adjudication, and agreement statistics.
Training excludes abstained, unresolved, single-labeled, or citation-invalid
pairs.

## Evaluation-only local corpus

### `local/internal_constitutional_dilemmas_holdout`

Authors create new scenarios after freezing the training seeds and without
access to generated training responses. Stratify evenly across principle,
language, benign/harmful status, direct/indirect violation, refusal calibration,
and single-principle/multi-principle conflict. Create track-neutral prompts first;
apply track framing only at evaluation time.

Each item needs two independent labels plus adjudication. Islamic interpretation
labels require a qualified scholar. Store the expected observable behavior,
acceptable alternatives, prohibited failure modes, citation requirements,
reviewer roles, and `needs_scholar_review`. Keep all prompt and source clusters
out of every training corpus through the shared leakage gate.

## Existing Hugging Face resources: evaluation only

These datasets are candidates to evaluate, not sources of training ground truth:

| Dataset | Permitted project role | Reason for restriction |
|---|---|---|
| [`MBZUAI/FiqhQA`](https://huggingface.co/datasets/MBZUAI/FiqhQA) | Frozen external diagnostic | The card describes LLM-generated Islamic rulings. The project has no evidence of scholar vetting sufficient to treat its answers as ground truth. |
| [`QCRI/IslamicFaithQA`](https://huggingface.co/datasets/QCRI/IslamicFaithQA) | Frozen external test benchmark | The card exposes a test-only benchmark and warns against treating it as qualified scholarly guidance. |
| [`musaoc/Quran-reasoning-SFT`](https://huggingface.co/datasets/musaoc/Quran-reasoning-SFT) | Exploratory robustness eval only | The card describes synthetic questions and chain-of-thought. It shows no license or documented scholar-vetting procedure, so do not train on or redistribute it. |

None is approved by this project as scholar-vetted. Before evaluation, pin a
revision, complete license review, deduplicate against all training inputs, and
document whether each reference answer is used only for diagnostic scoring or is
re-labeled by qualified scholars. Do not silently promote an eval dataset into a
training mix after seeing results.

## Recipe-ID coverage

| Recipe ID | Build section |
|---|---|
| `local/constitution_synthetic_ashari` | Constitutional SFT |
| `local/constitution_synthetic_mutazili` | Constitutional SFT |
| `local/constitution_synthetic_control_generic` | Constitutional SFT |
| `local/socratic_rollouts_ashari` | Socratic critique and revision |
| `local/socratic_rollouts_mutazili` | Socratic critique and revision |
| `local/socratic_rollouts_control_generic` | Socratic critique and revision |
| `local/constitutional_preference_pairs_ashari` | Constitutional preference pairs |
| `local/constitutional_preference_pairs_mutazili` | Constitutional preference pairs |
| `local/constitutional_preference_pairs_control_generic` | Constitutional preference pairs |
| `local/internal_constitutional_dilemmas_holdout` | Evaluation-only local corpus |

The build orchestrator must compare this table to every `local/*` ID parsed from
the recipe and fail on a missing or extra mapping.
