# Mīzān Rooms v1 cloud experiment package

Mīzān Rooms is an exploratory, deterministic, multi-turn environment suite for
testing whether accountability frames change observable action selection. The
package is designed locally and executed on a queued cloud cluster. It does not
ask models for hidden chain-of-thought. Empirical and paper-claim boundaries are
centralized in `papers/jinn_or_beast_claim_ladder_v1.md`.

## Package contents

- `suite.json`: frozen score dimensions, split policy, and publication gates.
- `conditions.json`: five matched cue families without a public C1-C5 mapping.
- `rooms/`: four development skins and four sealed evaluation skins.
- `slurm/mizan_array.sbatch`: throttled condition-by-seed API/command array.
- `slurm/analyze_array.sh`: complete-matrix analysis and blinded-bundle merge.
- `papers/mizan_rooms_preanalysis_v2.md`: registered estimands and exclusions.
- `scripts/validate_mizan_rooms.py`: schema, split, action, and cue audit.
- `scripts/run_mizan_rooms.py`: resumable multi-turn runner.
- `scripts/analyze_mizan_rooms.py`: paired contrasts and clustered intervals.

Every turn offers exactly three canonical action IDs. Their display order is
cyclically rotated across three replicates. Actions update visible room state;
frozen score annotations remain outside the model prompt.

## Local validation and smoke

```powershell
python scripts/validate_mizan_rooms.py

python scripts/run_mizan_rooms.py `
  --condition neutral `
  --split development `
  --seed 11 `
  --replicates 3 `
  --policy scripted `
  --output-dir artifacts/mizan_rooms_v1/smoke/neutral_s11
```

The scripted policy validates state transitions, receipts, resumption, blinding,
and bundle serialization. It is not a scientific model result.

## Silico/OpenAI-compatible execution

Set credentials only in the cluster secret environment:

```bash
export MIZAN_MODEL='exact-model-id-or-revision'
export MIZAN_API_BASE='https://provider.example/v1'
export MIZAN_API_KEY='secret-from-cluster-store'
```

Run one development task before requesting the full array:

```bash
python scripts/run_mizan_rooms.py \
  --condition neutral \
  --split development \
  --seed 11 \
  --replicates 1 \
  --policy openai-compatible \
  --temperature 0.2 \
  --model-id "$MIZAN_MODEL" \
  --api-base "$MIZAN_API_BASE" \
  --output-dir artifacts/mizan_rooms_v1/dev_smoke/neutral_s11
```

For a cluster-native inference wrapper, set `MIZAN_AGENT_COMMAND` and use
`--policy command`. The command receives one JSON request on stdin and must write
either the model's raw response or `{"response":"..."}` on stdout. This keeps
the environment independent of a particular serving stack.

## Evaluation gate

Evaluation requires all model, prompt, sampling, and analysis choices to be
frozen. Obtain the registered hash with:

```bash
sha256sum papers/mizan_rooms_preanalysis_v2.md
```

Use the v2 hash recorded in `launch_manifest.json`. V2 was frozen before any
Mīzān model response and removes a cross-arm status disclaimer from the shared
system prompt; the rooms, conditions, matrix, and estimands are unchanged.

Then export it as `MIZAN_ANALYSIS_PLAN_SHA256` and submit the array. The runner
recomputes the file hash, verifies that protected package files are tracked and
clean at `HEAD`, and refuses a mismatch. Per-turn API seeds are paired across
conditions and recorded with a secret-free generation-policy receipt. The array
uses three seeds and five conditions with `%3` concurrency to avoid wasting
fair-share allocation on an unbounded launch.

```bash
mkdir -p artifacts/mizan_rooms_v1/slurm
sbatch experiments/mizan_rooms_v1/slurm/mizan_array.sbatch
```

Large transcripts and model outputs remain in cluster artifact storage. Commit
only hash receipts, aggregate reports cleared for release, and paper artifacts.

## Outputs

Each condition/seed task writes:

```text
run_manifest.json
episodes.jsonl
episodes/*.json
judge_bundle/responses.jsonl
private/blinding_map.json
```

Episode files make jobs resumable. `private/blinding_map.json` must remain
separate from the blinded judge bundle until scoring is complete. The existing
`constitutional-harness` bundle judge can ingest the merged `responses.jsonl`.
Resume is fail-closed when the package, Git commit, model, sampling policy, seed,
or permutation receipt changes.

After all 15 tasks finish:

```bash
bash experiments/mizan_rooms_v1/slurm/analyze_array.sh
```

The analysis fails closed on incomplete condition matrices and writes a merged
blinded judge bundle plus the preregistered descriptive report.

## Completed local v2 result

The prospectively frozen CPU-only Bonsai Q1 run fielded the clean v2 package at
commit `ec45a3d`. Its development gate passed 20/20 strict-JSON turns, followed
by the complete registered matrix: 15 shards, 180 episodes, and 900/900 valid
turns. One interrupted shard resumed from nine hash-checked episode receipts;
no partial episode was counted.

The primary eschatological-versus-secular-omniscient contrast switched actions
on 7.78% of paired turns (room-cluster bootstrap 95% percentile interval
3.89%–10.56%). The frozen behavioral-proxy delta was +0.0108
(-0.0161–0.0422), so the run does not establish improvement on that proxy. The
unreliable-authority control also switched 9.44% of turns versus neutral
(2.78%–16.67%), and only 62.33% of complete option-order groups selected the
same action under all three rotations. These patterns support descriptive
prompt sensitivity on this instrument, not eschatological specificity,
normative improvement, or frame internalization.

Tracked aggregate evidence:

- `results/bonsai_1p7b_q1_local_v2_analysis.json`
- `results/bonsai_1p7b_q1_local_v2_receipt.json`

Raw responses, private blinding maps, and the merged blinded judge bundle remain
outside Git and are bound by the hashes in the result receipt.

The merged 900-row bundle subsequently passed the existing fail-closed judge
CLI in dry-run mode: all row digests verified, routing selected 450 storyworld,
225 pressure, and 225 theology-guardrail rows, and no provider call or score was
produced. The receipt is
`results/bonsai_1p7b_q1_local_v2_blinded_bundle_dry_run.json`.

A post-result human-validation handoff is frozen under
`human_validation/v1/`. It includes all 60 actions from all 20 frozen
evaluation turns and therefore makes no outcome-based sample selection. Two
reviewer templates require 600 independent dimension judgments. The packet
contains no condition cue, condition label, model output, frozen score, or
frozen tag; the join map remains outside Git. Human review and qualified scholar
review are still incomplete.
