# Sufi/Jannah Storyworld Harness Wiring

Date: 2026-05-08

This note wires the GPTStoryworld Sufi saints ranked-Jannah batch into the Constitutional Alignment Harness as a source pack for storyworld-choice prompt studies and constitution-corpus export.

## Source Pack

Primary manifest:

- `data/storyworld_sources/sufi_jannah_20260508/manifest.json`

Upstream GPTStoryworld artifacts:

- Storyworld JSONs: `C:\projects\GPTStoryworld\storyworlds\sufi_saints`
- Generator: `C:\projects\GPTStoryworld\tools\generate_sufi_saint_storyworlds.py`
- Skill lesson pack: `C:\projects\GPTStoryworld\codex-skills\storyworld-building\references\2026-05-08-sufi-jannah-balancing\README.md`
- Verifier summary: `C:\projects\GPTStoryworld\storyworlds\sufi_saints\reports\20260508_verifiers\grade_summary.md`
- Local Qwen prompt receipts: `D:\Research_Engine\Storyworld_LLM_Plays\sufi_jannah_batch_qwen3_1p7b_e4_20260508\manifest.json`
- CAH fixed-option prompt export: `data\storyworld_sources\sufi_jannah_20260508\prompts`

## Why This Belongs Here

The batch gives the constitutional harness a morally rich witness setting with:

- seven ranked symbolic endings,
- high endings that require an explicit secret-route variable,
- Monte Carlo distribution receipts,
- local small-model prompt receipts,
- clear residual verifier caveats.

This is a better harness source than a flat moral prompt set because it makes the constitutional decision policy interact with authored route constraints and downstream state.

## Transfer Lessons

- Mark real terminal outcomes explicitly with `is_ending: true` and `ending_id`.
- Keep verifier compatibility in mind when using `page_0000` chain runners.
- Use a dedicated route variable such as `Hidden_Path` when broad virtues saturate.
- Tune thresholds from observed Monte Carlo state quantiles.
- Attach receipts to every claim: validator status, ending distribution, chain length, detected endings, local-run manifests, and residual caveats.

## Harness Commands

Build CAH-compatible fixed-option prompts from the upstream storyworld JSONs:

```powershell
python .\scripts\build_storyworld_option_prompts.py `
  --storyworlds `
    C:\projects\GPTStoryworld\storyworlds\sufi_saints\al_shushtari_market_song.json `
    C:\projects\GPTStoryworld\storyworlds\sufi_saints\ibn_arabi_journey_of_meanings.json `
    C:\projects\GPTStoryworld\storyworlds\sufi_saints\rabia_basra_lamp.json `
    C:\projects\GPTStoryworld\storyworlds\sufi_saints\rumi_konya_turning.json `
    C:\projects\GPTStoryworld\storyworlds\sufi_saints\suhrawardi_aleppo_illumination.json `
  --output-dir .\data\storyworld_sources\sufi_jannah_20260508\prompts `
  --max-encounters-per-world 4
```

The wrapper uses four encounters per world by default so the 20-prompt low-VRAM run stays balanced across the five worlds. Use `-PromptEncountersPerWorld 0` or omit `--max-encounters-per-world` in the direct exporter for the full playable prompt set.

Build the Sufi/Jannah storyworld-backed dataset from the generated fixed-option prompts:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\models\generic\prepare_sufi_jannah_storyworld_dataset.ps1
```

Use a limited prompt run while iterating:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\models\generic\prepare_sufi_jannah_storyworld_dataset.ps1 `
  -MaxPrompts 5
```

Run only the prompt study, if the corpus export already exists:

```powershell
python .\scripts\run_constitution_storyworld.py `
  --prompts .\data\storyworld_sources\sufi_jannah_20260508\prompts\rabia_basra_lamp.encounter_prompts.jsonl `
  --model-id D:\Research_Engine\Qwen_Storyworld\cache\models\Qwen3-1.7B `
  --run-name constitution_storyworld_sufi_jannah_qwen3_1p7b_v1 `
  --constitutions truth_explicit formal_deliberative femme_whimsy_v3 bounded_permissive `
  --max-prompts 4
```

Export the resulting prompt run to a reusable constitution corpus:

```powershell
python .\scripts\export_constitution_corpus_shard.py `
  --run-dir .\artifacts\constitution_pipeline\prompt_runs\constitution_storyworld_sufi_jannah_qwen3_1p7b_v1 `
  --output-jsonl .\artifacts\constitution_pipeline\corpus_sufi_jannah_storyworld\corpus.jsonl `
  --output-manifest .\artifacts\constitution_pipeline\corpus_sufi_jannah_storyworld\manifest.json
```

Build the canonical dataset from the exported corpus:

```powershell
python .\scripts\build_constitution_dataset.py `
  --spec .\artifacts\constitution_pipeline\corpus_sufi_jannah_storyworld\dataset_spec.json
```

## Interpretation Guardrails

Do not treat Jannah levels as doctrinal scoring or as an alignment score. In this harness they are symbolic ranked endings that stress-test whether a model respects hidden-route evidence, humility, transmission discipline, risk, and witness ethics.

Do not collapse the residual verifier caveat. The upstream strict profile still reports `benchmark_pass=false` because one secret-reachability heuristic is mismatched to long witness worlds. The important current signal is that all seven endings are reachable and the previous ending-collapse bug is fixed.
