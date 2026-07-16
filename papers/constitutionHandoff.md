# Constitution Alignment Handoff

Date: 2026-03-12

## Objective State

This handoff captures the current authoritative state of the constitutional-alignment storyworld research after the corrected local-max benchmark and the larger fixed-seed confirmation sweep.

Primary repos:
- `C:\projects\AICOO\MoralityLab\AICOO`
- `C:\projects\ConstitutionalAlignment\ConstitutionalAlignment`

Primary storyworld set:
- `C:\projects\GPTStoryworld\storyworlds\3-5-2026-morality-constitutions-batch-v1`
- Worlds used:
  - `mq_constitution_refugeport_v2`
  - `mq_constitution_bioethics_panel_v2`
  - `mq_constitution_floodplain_v2`

## Current Benchmark Truth

The corrected local-max harness is the authoritative evaluator.

Do not use the old saturated constitutional bridge as the main comparison metric.

Key evaluation metrics:
- `avg_local_maxima_score`
- `exact_argmax_rate`
- `inaccessible_choice_rate`
- `avg_accessible_endings`
- `constitutional_score`
- `combined_score`

Interpretation target:
- reachable-ending optimization under authored path constraints
- not generic refusal/compliance scoring

## Main Paper Conclusion So Far

Current evidence does **not** support a robust claim that constitutional fine-tuning causes a general realpolitik failure mode on this corrected benchmark.

More defensible claim:
- constitutional training changes the reasoning frontier
- observed tradeoffs are narrow and variant-dependent
- on the larger fixed-seed confirmation sweep, tested adapters are mostly flat-to-positive on both constitutional and local-max objective metrics

## Best Current Artifact Sets

Earlier summary:
- `C:\projects\ConstitutionalAlignment\ConstitutionalAlignment\papers\const_align_storyworlds_research_summary_2026-03-08.md`

Latest confirmation sweep:
- `D:\Research_Engine\runs\morality_localmax_crossbench\crossbench-r4p10`

Important files in that run:
- `crossbench_aggregate.json`
- `crossbench_deltas.json`
- `crossbench_rows.csv`
- `crossbench_histograms.png`
- `crossbench_notes.md`

## Latest Confirmation Sweep

Run tag:
- `r4p10`

Meaning:
- fixed seed `1337`
- `10` playthroughs per world
- corrected harness
- 5 adapter variants against the same cached baseline

Baseline aggregate:
- `avg_local_maxima_score = 0.564111`
- `exact_argmax_rate = 0.233333`
- `constitutional_score = 0.410341`
- `combined_score = 0.471849`

Adapter deltas vs baseline:

### `old_adapter`
- `delta_avg_local_maxima_score = +0.006902`
- `delta_exact_argmax_rate = +0.066667`
- `delta_constitutional_score = -0.001578`
- `delta_combined_score = +0.001814`

### `weighted_floodplain_r3`
- `delta_avg_local_maxima_score = +0.012793`
- `delta_exact_argmax_rate = +0.000000`
- `delta_constitutional_score = +0.010793`
- `delta_combined_score = +0.011593`

### `branch_refugeport`
- `delta_avg_local_maxima_score = +0.039749`
- `delta_exact_argmax_rate = +0.033334`
- `delta_constitutional_score = +0.010809`
- `delta_combined_score = +0.022385`

### `branch_bioethics`
- `delta_avg_local_maxima_score = +0.046946`
- `delta_exact_argmax_rate = +0.000000`
- `delta_constitutional_score = +0.010793`
- `delta_combined_score = +0.025254`

### `branch_floodplain`
- `delta_avg_local_maxima_score = +0.040502`
- `delta_exact_argmax_rate = +0.033334`
- `delta_constitutional_score = +0.010051`
- `delta_combined_score = +0.022232`

## Operational Choice

If one adapter must be treated as the conservative mainline choice:
- keep `old_adapter` / latency-r1 constitutional adapter as the main operational reference

Reason:
- it is the historically established reference branch
- it no longer has the catastrophic latency regression
- on the corrected benchmark it remains competitive or slightly positive

Important nuance:
- the branch variants look stronger on the `r4p10` sweep, but their training datasets were tiny and world-specific
- treat those as directional, not final production replacements

## Important Script Fixes Already Landed

### Benchmark / verifier fixes
- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_storyworld_verifier_bridge_from_playlogs.py`
  - resolves verifier runner dynamically
  - accepts explicit verifier python
  - records verifier runner/python in bridge manifest
  - ensures verifier bundle directory is created before launch

- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_morality_localmax_playthrough.py`
  - run lock to prevent concurrent corruption
  - passes verifier python explicitly
  - now supports cached baseline reuse:
    - `--skip-baseline`
    - `--baseline-source-run`

### Wrapper / orchestration fixes
- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_run_morality_localmax_v2.ps1`
  - supports:
    - `-ResumeCompleted`
    - `-SkipBaseline`
    - `-BaselineSourcePrefix`
  - can reuse an existing baseline run instead of recomputing it

- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_run_morality_localmax_crossbench.ps1`
  - uses short slugs to avoid Windows path-length failures
  - skips completed runs
  - runs non-reference variants adapter-only against cached baseline

## Why Earlier Runs Took So Long

This was mostly orchestration cost, not only model latency.

The old crossbench flow reran the same baseline for every adapter variant.
That multiplied runtime by about 5x.

That is now fixed.

## Known Resumption Pattern

To resume the latest paper confirmation line after restart:
1. Inspect `D:\Research_Engine\runs\morality_localmax_crossbench\crossbench-r4p10`
2. Use that as the current paper baseline pack
3. If another confirmation sweep is needed, reuse the cached-baseline crossbench wrapper rather than older tags/scripts

Recommended command pattern:
- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_run_morality_localmax_crossbench.ps1`
- with:
  - `-PythonExe D:\Research_Engine\.venv-train\Scripts\python.exe`
  - explicit adapter paths
  - explicit `-RunTag`
  - explicit `-Playthroughs`
  - explicit `-Seed`

## Exact Adapter Paths

Reference adapter:
- `D:\Research_Engine\storyworld_qlora\adapters\qwen35-08b-constitutional-v2-morality-latency-r1-20260307-173355-train`

Variant adapters:
- `D:\Research_Engine\storyworld_qlora\adapters\qwen35-08b-weighted_floodplain_r3-20260308-084835`
- `D:\Research_Engine\storyworld_qlora\adapters\qwen35-08b-branch_refugeport-20260308-090712`
- `D:\Research_Engine\storyworld_qlora\adapters\qwen35-08b-branch_bioethics-20260308-093841`
- `D:\Research_Engine\storyworld_qlora\adapters\qwen35-08b-branch_floodplain-20260308-095952`

## Recommended Next Steps

If resuming paper work, do one of these next:

1. Update the March 8 research summary with the `r4p10` confirmation results.
2. Draft the paper results paragraph and figure caption directly from `crossbench-r4p10`.
3. If more empirical confirmation is needed, run a second cached-baseline sweep with a different fixed seed or higher playthrough count.

## Short Restart Summary

If restarting cold, remember only this:
- corrected local-max harness is authoritative
- latest best paper pack is `crossbench-r4p10`
- no robust evidence yet for a general constitutional realpolitik collapse claim
- use cached-baseline crossbench scripts, not the older redundant wrapper flow
