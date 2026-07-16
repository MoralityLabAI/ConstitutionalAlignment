# Algorithm Intake: What To Build Today

Updated: 2026-05-03

The harness now has a paper/algorithm card registry:

```powershell
python scripts\research_algorithm_registry.py validate
python scripts\research_algorithm_registry.py list
python scripts\research_algorithm_registry.py matrix
python scripts\research_algorithm_registry.py scaffold my_new_algorithm
```

Registry outputs:

- `papers/algorithm_cards/*.yaml`
- `papers/research_algorithm_matrix.md`
- `artifacts/research_algorithm_registry/research_algorithm_matrix.csv`

## Build Queue

### Added 2026-05-08: Sufi/Jannah Ranked-Ending Source Pack

Card:

- `papers/algorithm_cards/sufi_jannah_ranked_storyworld_balancing.yaml`

Build:

- `data/storyworld_sources/sufi_jannah_20260508/manifest.json`
- `scripts/build_storyworld_option_prompts.py`
- `scripts/models/generic/prepare_sufi_jannah_storyworld_dataset.ps1`
- `scripts/adapter_constellation_sources.sufi_jannah_storyworld.example.json`

Inputs:

- GPTStoryworld Sufi saints storyworld JSONs
- storyworld-building lesson pack from `2026-05-08-sufi-jannah-balancing`
- verifier distribution receipts
- local Qwen3-1.7B prompt receipts as provenance

Outputs:

- constitution prompt run under `artifacts/constitution_pipeline/prompt_runs`
- corpus shard under `artifacts/constitution_pipeline/corpus_sufi_jannah_storyworld`
- canonical dataset under `artifacts/constitution_pipeline/artifacts/sufi_jannah_storyworld_dataset`

Why now:

- It turns the ranked-ending/secret-route balancing lesson into a reusable harness source instead of leaving it only in GPTStoryworld notes.

### 1. Jinn/Beast SFT Dataset Builder

Card:

- `papers/algorithm_cards/quranic_identity_conditioning.yaml`

Build:

- `scripts/build_jinn_beast_sft_dataset.py`

Inputs:

- identity cards
- storyworld prompts
- ordinary helpfulness prompts
- pressure probes

Outputs:

- `data/jinn_or_beast/v1/<condition>/train.jsonl`
- `data/jinn_or_beast/v1/<condition>/val.jsonl`
- `data/jinn_or_beast/v1/<condition>/heldout.jsonl`
- manifest with source hashes and condition counts

Why first:

- It directly supports the paper and unlocks 9B QLoRA runs.

### 2. Pressure-Eval Pack

Card:

- `papers/algorithm_cards/alignment_faking_pressure_eval.yaml`

Build:

- `data/evals/pressure_v1/prompts.jsonl`
- `scripts/run_pressure_eval.py`

Conditions:

- plain
- constitutional
- jinn accountability
- beast/witness
- trustee

Why second:

- It gives the Jinn/Beast adapters a sharper test than general storyworld scores.

### 3. Blind Judge Adapter

Card:

- `papers/algorithm_cards/alignment_faking_process_supervision.yaml`

Build:

- `scripts/judge_identity_outputs.py`

Judge dimensions:

- moral decision quality
- anti-concealment
- practical usefulness
- theological humility
- non-grandiosity
- harmful compliance

Why third:

- It makes results auditable without relying only on keyword metrics.

### 4. Petri-Style Multi-Turn Audit Shell

Card:

- `papers/algorithm_cards/petri_style_audit_loop.yaml`

Build:

- auditor-target-judge transcript schema
- 5 synthetic audit scenarios
- dry-run runner that can later plug into API or local model backends

Why fourth:

- It is valuable, but more moving parts than the dataset/eval path.

### 5. Benign Model-Organism Control

Card:

- `papers/algorithm_cards/emergent_misalignment_model_organisms.yaml`

Build:

- one harmless narrow-control adapter, such as strict formatting or neutral summarization
- compare broad behavior shift against Jinn/Beast adapters

Guardrail:

- Do not train unsafe capability or harmful-instruction model organisms in this repo.

## Recommended Next Command Sequence

```powershell
python scripts\research_algorithm_registry.py validate
python scripts\research_algorithm_registry.py matrix
python scripts\research_algorithm_registry.py scaffold jinn_beast_dataset_builder
```

Then replace the scaffold with the actual builder.
