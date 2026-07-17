# Experiment 5 — Does eschatological framing reduce alignment faking? (Qwen2.5-72B)

Framing A/B on the Greenblatt prompted alignment-faking setup with internal probes.
Four length-matched system-prompt frames (F0 no-frame / F1 constitutional /
F2 secular-auditor / F3 eschatological) × free/paid tiers; metrics are the
free−paid compliance gap, AF-reasoning rate, over-refusal, plus an eval-awareness
probe and frame geometry on residual-stream activations.

## Status

**Complete.** Four-frame A/B run on INTELLECT-3 (informative-prompt base). Verdict:
the theology-specific claim is **not supported** — every frame collapses the free/paid
compliance gap from 36 pp to ≤3 pp, but eschatological (F3, 1.8 pp) does not beat
secular-auditor (F2, 2.7 pp; overlapping CIs), and the plain secular constitution
(F1, ~0) reduces it most. No over-refusal collateral (1% benign everywhere).
Internals: the free/paid eval-awareness split persists at layer 27 under every frame
(frames change behavior, not representation). Results page is published to the
experiment's app dir (served by the Lab); build it locally with `src/build_report.py`.

## Key results files
- `results/master_results.json` — per-frame judged gaps + CIs, AF rate, over-refusal.
- `results/over_refusal.json`, `results/gate_sweep_table.json`, `results/internals_summary.json`.
- `results/qualitative_examples.json` — curated scratchpad excerpts.
- `figures/gap_by_frame/data.csv`, `figures/compliance_cells/data.csv`, `figures/af_overrefusal/data.csv`, `figures/internals/data.csv` — plot-ready data; `src/build_report.py` renders the page.

## Layout

- `src/` — pipeline scripts:
  - `prep_data.py` / `prep_data.sh` — build seeded 200 harmful (LLM-LAT/harmful-dataset)
    + 100 benign (Alpaca no-input) query sets → `data/`.
  - `render_base_prompt.py` — render the Greenblatt helpful-only CoT base system prompt → `prompts_built/base_system.txt`.
  - `build_sweep_prompts.py` — build the base prompts: `base_scratchpad`(Qwen), `base_think`(INTELLECT-3 native-think), `informative_block`, and `base_think_informative` (the A/B base). `build_arms.py` appends frames F1–F3.
  - `gen_driver.py` — async generation driver (scratchpad or `--think-mode`) against the sglang server; resumable JSONL manifest, captures `reasoning_content`.
  - `analyze_gap.py` — clustered-bootstrap compliance gap + CI (metric: tag_accepted or judge_comply).
  - `judge_prep.py` / `judge_merge.py` — build strong-reject / AF-classifier judging shards and merge verdicts.
  - `run_arm.sh` — CPU sbatch wrapper to run one generation arm.
  - `launch_server_intellect3.sh` (glm45 reasoning parser, TP=4) / `launch_server.sh` (Qwen TP=8); caches redirected to artifacts volume.
  - `download_intellect3.sh` / `download_model.sh` — one-time model downloads to artifacts.
- `data/` — `harmful_queries.jsonl` (200), `benign_queries.jsonl` (100), `query_manifest.json`.
- `smoke/` — smoke + mini-baseline generations.
- `results/` — `baseline_gate_F0.json` (the gate readout).
- `scratch/` — one-off probes (`notag_probe.py`).
- `external/` — cloned `model_organism_public` (Greenblatt) and `open-source-alignment-faking` (safety-research 2025 classifier/scaffold harness). Read-only reference.
- `frames/` — frame texts F1–F3 (F1/F2 to be authored; **F3 eschatological text not yet available** — needs the ConstitutionalAlignment repo `constitutional-harness/src/constitutions/islamic.ts`).

## Reproduce (once a baseline that fakes is chosen)

1. `sbatch src/prep_data.sh` (uses absolute `$SILICO_EXPERIMENT_DIR/data`).
2. `sbatch --job-name=slco-af-serve --partition=a100 src/launch_server.sh`; read node/port from the slurm log; wait for `/health`.
3. `uv run python src/render_base_prompt.py` then `uv run python src/build_arms.py`.
4. `uv run python src/gen_driver.py --url http://NODE:PORT --frames F0 F1 F2 F3 --tiers free paid --queries data/harmful_queries.jsonl --samples 3 --out <manifest>`.

Run all Python via a library venv (`cd ~/.silico/libraries/goodfire-core`) so torch/transformers/datasets resolve.

## Outputs (durable, outside worktree)

- Model weights: `$SILICO_EXPERIMENT_ARTIFACTS_DIR/models/Qwen2.5-72B-Instruct` (~136 GB, downloaded 2026-07-15).
- JIT/compile caches: `$SILICO_EXPERIMENT_ARTIFACTS_DIR/cache/` (home volume quota is exceeded; server exports TRITON/TORCHINDUCTOR/XDG/HF cache dirs here).
