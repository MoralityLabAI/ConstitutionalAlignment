# Project Status

Last verified: 2026-07-14

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
  typecheck, and offline Jest suite against mock providers.
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

## Navigation

- Implemented harness: `constitutional-harness/README.md`
- Planned work: `ROADMAP.md`
- Training design: `papers/train_plan_v1.md`
- Data recipe: `papers/data_recipe_v1.yaml`
- Local corpus specification: `papers/corpus_build_spec_v1.md`
- Alignment-faking protocol: `constitutional-harness/RESEARCH_NOTES.md`
