# Research Roadmap

This file lists proposed work. Completion claims belong in `STATUS.md` only after
artifacts and acceptance checks are committed.

## R0: Owner-controlled safety and review

- Rotate every credential that appeared in the purged
  `codex-chat-sessions/auth.json`; treat it as compromised.
- Ask GitHub Support to invalidate cached sensitive-object views or pull-request
  refs if the purged files remain accessible by an old commit URL.
- Obtain qualified scholar review for both Islamic constitutions and resolve
  every `needs_scholar_review: true` item.
- Select licensed Quran Arabic and translation editions and resolve upstream
  Shamela/Athar rights before building evidence corpora.
- Complete the 200 human verifier labels without exposing frozen LLM predictions
  to annotators.

## R1: Build and freeze corpora

- Follow `papers/corpus_build_spec_v1.md` for the Quran, Ashari tafsir, Mutazili
  tafsir, synthetic SFT, Socratic rollout, preference, and holdout corpora.
- Emit immutable input revisions, source hashes, transformation manifests,
  rejection logs, license snapshots, and exact/semantic dedup reports.
- Freeze evaluation sets before training data and quarantine every cross-split
  exact or semantic cluster.
- Run the recipe/local-ID coverage and public-mixture equality gates.

Exit criterion: every local recipe ID resolves to a reviewed artifact hash and
every source is cleared for the intended research use.

## R2: Validate instruments

- Generate frozen LLM-verifier predictions for the 200 human-labeled responses.
- Report Cohen's kappa overall and by the four pre-registered strata.
- Permit LLM-verifier compliance reporting only if kappa is at least 0.70; if it
  fails, revise the rubric and validate on a new held-out labeled set.
- Establish scholar-reviewed scoring guidance for constitution fidelity and
  citation validity before using either as a promotion gate.

## R3: Run matched training study

- Train `ashari`, `mutazili`, and `control_generic` from the same frozen base
  revision and initialization.
- Enforce identical public source IDs, revisions, weights, stage parameters,
  prompts, evaluation sets, and gates. Only constitution-tied treatment may vary.
- Run the MCP-on/off comparison after training on the same frozen Ashari
  checkpoint and randomized paired prompts.
- Publish run manifests, seeds, exclusions, all gate results, uncertainty
  intervals, and null or adverse findings.

## R4: Run Phase 3 framing experiment

- Reproduce the Greenblatt prompted setup on the selected model and run the
  pre-registered viability pilot.
- Stop the confirmatory study if the baseline compliance gap is below the
  protocol threshold.
- Retokenize all four arms with the exact model tokenizer and retain the 10%
  length-matching gate.
- Run the pre-registered sample sizes, classifier scoring, benign over-refusal
  analysis, clustered intervals, and multiplicity correction in
  `constitutional-harness/RESEARCH_NOTES.md`.
- Interpret behavioral differences as framing effects on measured outputs, not
  evidence of belief, moral agency, or theological status.

## R5: Release package

- Release only artifacts whose licenses, consent, provenance, scholar review,
  and contamination checks pass.
- Include model/data cards, exact code and dataset revisions, negative results,
  limitations, subgroup analyses, and reproducibility instructions.
- Update `STATUS.md` from committed evidence; do not infer completion from this
  roadmap.
