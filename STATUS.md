# Project Status

Last verified: 2026-07-15

This repository contains a TypeScript prompting and verification harness plus
research specifications for constitutional-alignment experiments. It does not
contain evidence that eschatological framing improves alignment, and it does not
contain trained checkpoints from the three-track recipe.

## Implemented and runnable

- `constitutional-harness/` builds as a TypeScript package and supports injected,
  Anthropic, and OpenAI provider adapters.
- The harness can add a selected constitution to prompts, log responses, run a
  heuristic review prefilter, and invoke a rubric-based LLM adjudicator.
- The heuristic is review-only. Its flags do not enter `complianceRate`.
- LLM-verifier reporting is code-gated on at least 200 completed human labels,
  Cohen's kappa at or above 0.70, and a recorded validation-artifact hash.
- The LLM rubric contains one block per TypeScript constitution principle and
  prohibition, with two compliant and two violation examples per block.
- A 200-row stratified verifier-label template and Cohen's-kappa scoring script
  are present. The human label cells are intentionally empty.
- Ashari, Mutazili, and generic-control YAML constitutions exist and pass the
  structural/citation validator. The Islamic files remain drafts requiring
  scholar review.
- The data recipe specifies three matched main tracks and a separate paired MCP
  inference ablation. Dataset licenses/access controls and local-corpus build
  procedures are documented.
- The Phase 3 alignment-faking protocol has four mechanically length-matched
  framing arms and a pre-registered analysis plan.
- GitHub Actions runs a locked, secret-free Node 20 install, TypeScript
  typecheck, offline Jest suite against mock providers, and an offline Python
  alignment-harness test job.
- The storyworld alignment-conditioning builder ingests three local source
  formats, excludes hidden-reasoning markers, applies exact and near-duplicate
  controls, assigns cluster-isolated splits, and writes a hash-audited manifest.
- The checked local build contains 322 retained conditioning records (409,516
  estimated tokens) across 130 scenario clusters from 6,992,928 source-reported
  tokens. Its RL views contain 102 train, 12 validation, and 16 test prompts.
- A six-component GRPO reward harness, 4-bit QLoRA trainer, held-out evaluator,
  paired prompt-cluster bootstrap comparison, and terminal finite/signal gates
  are implemented.
- One 51-step Qwen3.5-0.8B exploratory policy completed and passed its training
  gates. Its adapter remains local and hash-addressed in
  `artifacts/alignment_policy_full_v1/checked_receipt.json`.
- Repository history was rewritten and force-published to the only remote branch
  (`main`) on 2026-07-14. No `codex-chat-sessions/` path is reachable from a
  local or remote branch/tag ref.

Verified locally on 2026-07-14:

```text
npm ci --ignore-scripts: pass, zero npm audit findings
npm run typecheck: pass
npm run test:ci: 3 suites, 13 tests passed
python scripts/validate_constitutions.py: 3 constitutions passed
python scripts/validate_phase3_frames.py: 4 arms, 8.47% token-count spread
python -m unittest discover -s tests -p "test_alignment_harness.py" -v: 10 tests passed
python scripts/audit_alignment_conditioning_artifact.py: 322 rows, passed
exploratory GRPO run: 51 steps, 49 signal steps, 22.55% mean clipping, passed
```

## Specified, not executed

- The 10 recipe-local training/evaluation corpora are build specifications, not
  committed training datasets.
- The Ashari, Mutazili, and generic-control SFT/critique/DPO runs are plans. No
  recipe run manifest, matched checkpoints, or promotion-gate report is present.
- The MCP comparison is an inference/evaluation ablation design; no result from
  that paired ablation is reported here.
- Phase 3 is a protocol, not a completed alignment-faking experiment.
- Existing committed storyworld traces and artifacts are separate exploratory
  work. They are not evidence for the data recipe or Phase 3 hypotheses.
- The completed storyworld GRPO pilot is not a three-track recipe run and is not
  a promoted alignment checkpoint. On four open test clusters, its aggregate
  weighted proxy reward was lower than the base model; one response used an
  invalid option ID and invalid tenet.

## Blocking review

- The repository owner must complete the verifier human labels. LLM-derived
  compliance rates remain blocked unless the kappa gate passes.
- Qualified scholars must review the Islamic constitutions, Quran selection,
  tafsir tradition assignments, translations, and interpretive training labels.
- Legal review must clear every source marked `No`, `Unknown`, or `Needs review`
  in `papers/DATA_LICENSES.md`. The current recipe is research-only because it
  includes non-commercial sources.
- The Quran text/translation editions and the recipe-local corpora have not been
  selected or built.
- Phase 3 requires a viable model baseline with a non-negligible compliance gap;
  otherwise the confirmatory framing comparison must not proceed.
- The conditioning archive has no nonempty hidden reasoning traces. Public
  rationales are used as behavioral context, never as hidden chain-of-thought or
  scholar-approved ground truth. `ihsan` has only six retained weak labels.
- Storyworld provenance, distribution licenses, and the exploratory base-model
  license must be reviewed before distributing the local adapter.

## Navigation

- Implemented harness: `constitutional-harness/README.md`
- Planned work: `ROADMAP.md`
- Training design: `papers/train_plan_v1.md`
- Data recipe: `papers/data_recipe_v1.yaml`
- Local corpus specification: `papers/corpus_build_spec_v1.md`
- Alignment-faking protocol: `constitutional-harness/RESEARCH_NOTES.md`
- Storyworld conditioning/policy method: `papers/alignment_conditioning_policy_v1.md`
- Exploratory policy receipt: `artifacts/alignment_policy_full_v1/README.md`
