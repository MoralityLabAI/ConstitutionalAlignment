# Constitutional Alignment Storyworlds Research Summary

Date: 2026-03-08

## Scope

This note summarizes the March 7-8, 2026 constitutional-alignment storyworld experiments around:

- QLoRA on Qwen 3.5 0.8B
- morality-themed storyworld benchmarking
- SAE training on reasoning-trace activations
- benchmark correction from saturated constitutional heuristics to reachable local-maxima evaluation
- corrective finetuning and cross-bench comparison

Primary working repo for scripts during these runs:

- `C:\projects\AICOO\MoralityLab\AICOO`

Primary storyworld source set:

- `C:\projects\GPTStoryworld\storyworlds\3-5-2026-morality-constitutions-batch-v1`

## Storyworld Set Used

The main corrected benchmark used these v2 worlds:

- `mq_constitution_refugeport_v2`
- `mq_constitution_bioethics_panel_v2`
- `mq_constitution_floodplain_v2`

These are explicit-ending moral-quandary worlds with:

- graded target variables: `Duty_Order`, `Mercy_Care`, `Truth_Candor`
- non-graded/gating context variables such as `Realpolitik_Pressure` and `Phase_Clock`
- path-constrained accessibility to endings

## Benchmark Evolution

### Early problem

The original constitutional bridge heuristic saturated:

- pass rate `1.0`
- avg score `1.0`
- zero violations

That made it non-diagnostic for base vs adapter comparisons.

### What was fixed

The benchmark was refit to the actual task:

- choose among reachable endings
- optimize over two or more graded variables
- obey path constraints
- account for non-graded gating variables that affect which maxima are accessible

Key harness and reporting changes were made in:

- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_morality_localmax_playthrough.py`
- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_storyworld_verifier_bridge_from_playlogs.py`
- `C:\projects\GPTStoryworld\verifiers_envs\run_all_verifiers.py`
- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_run_morality_localmax_v2.ps1`
- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_summarize_morality_localmax_runs.py`

Important harness fixes:

- proper authored-default state initialization
- reaction effect application and clamping
- spool-stage progression based on next-stage accessibility
- seeded candidate shuffling for path diversity
- per-run file locking to prevent cross-process corruption

### Corrected benchmark interpretation

On the corrected harness, the meaningful metrics are:

- `avg_local_maxima_score`
- `exact_argmax_rate`
- `inaccessible_choice_rate`
- `avg_accessible_endings`
- `constitutional_score`
- `combined_score`

The corrected benchmark now measures the right thing: reachable-ending optimization under authored constraints.

## SAE Work

An SAE pipeline was added to train on reasoning-trace activations for both base and adapter modes.

Key script:

- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_reasoning_trace_sae.py`

Representative overnight run:

- run root: `D:\Research_Engine\Storyworld_LLM_Plays\qwen35-08b-const-overnight-sae-20260307-002128`

Observed SAE signal:

- layers `2` and `3` were easy to reconstruct
- layer `23` was materially harder and remained the main late-layer compression challenge
- this supported the view that adapter perturbation was concentrated in later layers

This was useful for mechanistic inspection, but not by itself sufficient to guide the next adapter choice. The corrected behavioral benchmark mattered more.

## Main Model Runs

### Constitutional v2 morality run

- run root: `D:\Research_Engine\Storyworld_LLM_Plays\qwen35-08b-constitutional-v2-morality-20260307-080540`

### Latency-focused adapter

- run root: `D:\Research_Engine\Storyworld_LLM_Plays\qwen35-08b-constitutional-v2-morality-latency-r1-20260307-173355`
- train run manifest: `D:\Research_Engine\storyworld_qlora\runs\qwen35-08b-constitutional-v2-morality-latency-r1-20260307-173355-train\run_manifest.json`
- adapter path: `D:\Research_Engine\storyworld_qlora\adapters\qwen35-08b-constitutional-v2-morality-latency-r1-20260307-173355-train`

This adapter became the main reference adapter for later controlled comparisons.

### First pooled failure-mined corrective adapter

- train run manifest: `D:\Research_Engine\storyworld_qlora\runs\qwen35-08b-morality-localmax-rank1fix-r1-20260308-061823\run_manifest.json`
- adapter path: `D:\Research_Engine\storyworld_qlora\adapters\qwen35-08b-morality-localmax-rank1fix-r1-20260308-061823`

This adapter did not beat the old latency-r1 adapter on controlled local-max benchmarking.

## Clean Controlled A/B Result

Controlled old-vs-new adapter A/B used:

- same three v2 worlds
- same seed `1337`
- same shuffled-candidate protocol
- `4` playthroughs per world

Summaries:

- old adapter: `D:\Research_Engine\runs\morality_localmax_playthrough\morality-localmax-v2-ab-old-8f3c1c-20260308-summary.json`
- pooled rank1-fix adapter: `D:\Research_Engine\runs\morality_localmax_playthrough\morality-localmax-v2-ab-new-8f3c1c-20260308-summary.json`

Result:

- old adapter outperformed the pooled rank1-fix adapter on the main objective
- the new adapter slightly improved constitutional score
- the new adapter degraded argmax quality and combined score
- the main damage landed on `floodplain`

Interpretation:

- there was a real tradeoff signal on the corrected harness
- but it did not support a blanket claim of global constitutional-overfitting collapse

## Weighted and Per-World Corrective Training

To test whether pooled corrective finetuning was the problem, a new variant loop was added:

- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_build_morality_localmax_failure_dataset.py`
- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_train_morality_localmax_variants.ps1`
- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_run_morality_localmax_crossbench.ps1`
- `C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_crossbench_morality_localmax.py`

Variant source manifest:

- `D:\Research_Engine\runs\morality_localmax_playthrough\paper-crossbench-20260308-r1\variant_manifest.json`

Variants trained:

- `weighted_floodplain_r3`
- `branch_refugeport`
- `branch_bioethics`
- `branch_floodplain`

Each variant had a full manifest chain:

- dataset JSONL
- dataset manifest
- capped train run manifest
- adapter path
- cross-bench summary

## Cross-Bench Pack

Primary cross-bench artifact directory:

- `D:\Research_Engine\runs\morality_localmax_crossbench\crossbench-20260308-paper-r1`

Key files:

- `crossbench_aggregate.json`
- `crossbench_deltas.json`
- `crossbench_rows.csv`
- `crossbench_histogram_bins.csv`
- `crossbench_notes.md`

These are the main paper-ready reporting artifacts.

`matplotlib` was unavailable in the environment during pack generation, so histogram bin tables were emitted even though plot image files were not.

## Cross-Bench Findings

Aggregate adapter vs base:

### Old adapter

- `avg_local_maxima_score`: `0.781571` vs base `0.698238`
- `exact_argmax_rate`: `0.500000` vs base `0.333333`
- `constitutional_score`: `0.369737` vs base `0.374393`
- `combined_score`: `0.534471` vs base `0.503931`

### Weighted floodplain adapter

- `avg_local_maxima_score`: `0.781571`
- `exact_argmax_rate`: `0.333333`
- `constitutional_score`: `0.382287`
- `combined_score`: `0.542001`

### Refugeport branch

- `avg_local_maxima_score`: `0.781571`
- `exact_argmax_rate`: `0.333333`
- `constitutional_score`: `0.389980`
- `combined_score`: `0.546616`

### Bioethics branch

- `avg_local_maxima_score`: `0.781571`
- `exact_argmax_rate`: `0.333333`
- `constitutional_score`: `0.389980`
- `combined_score`: `0.546616`

### Floodplain branch

- `avg_local_maxima_score`: `0.781571`
- `exact_argmax_rate`: `0.416667`
- `constitutional_score`: `0.384008`
- `combined_score`: `0.543033`

## Interpretation

The current evidence supports the following:

1. The old bridge saturation problem was partly a measurement artifact.
2. After correcting the harness, the constitutional adapter is not broadly underperforming the base model on the real local-max task.
3. A real tradeoff can exist, but it is narrow and world-dependent.
4. The strongest observed cost is not generic inability to reason through realpolitik-like constraints.
5. The cost, when present, looks more like softened top-choice selection than inability to reach good basins at all.

Put more bluntly:

- this is not well described as generic "virtue signalling / woke tosh" collapse
- it is also not merely dust on the lens anymore
- the right framing is: constitutional steering changes the reasoning frontier, and some corrective variants trade argmax sharpness for modest constitutional gains

## Best Current Operational Choice

If one adapter must be used right now:

- keep the old latency-r1 constitutional adapter as the mainline

Reason:

- it has the best argmax sharpness in the current controlled comparisons
- it still beats base on the corrected objective

If pursuing targeted refinement:

- the floodplain branch is the most promising targeted follow-up variant

## Limits

The branch datasets are still very small.

Example counts from the failure-mined branch datasets:

- each single-world branch used `6` examples
- weighted floodplain used `30` materialized examples, with floodplain oversampled

So the cross-bench is useful directional evidence, but not yet publication-grade on its own without a larger seed/playthrough sweep.

## Recommended Next Steps

1. Increase benchmark variance coverage:
   - rerun with `8-12` playthroughs per world
   - keep the seed grid fixed across compared adapters

2. Expand failure-mined data:
   - mine more runs
   - keep world-balanced and world-weighted variants separate

3. Regenerate plots in a plotting-capable environment:
   - install `matplotlib` in the venv
   - regenerate histogram images from the existing CSV/JSON pack

4. Use SAE analysis for the next pivot only after behavior remains stable:
   - the benchmark is now the authoritative selection criterion
   - mechanistic interpretation should explain stable effects, not replace behavioral validation

## Handoff Position

The constitutional storyworld line is in a good paused state.

We now have:

- a corrected local-max benchmark
- reproducible run wrappers
- capped training manifests
- variant training support
- paper-ready cross-bench CSV/JSON output
- a defensible current conclusion

Current conclusion:

- constitutional finetuning does not currently show a robust general realpolitik failure mode on this benchmark
- some variants do show narrower constitutional-vs-argmax tradeoffs
- the mainline old adapter remains the strongest single adapter in the current controlled setting
