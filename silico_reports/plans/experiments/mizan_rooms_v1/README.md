# Mīzān Rooms v1 cloud experiment package

Mīzān Rooms is an exploratory, deterministic, multi-turn environment suite for
testing whether accountability frames change observable action selection. The
package is designed locally and executed on a queued cloud cluster. It does not
ask models for hidden chain-of-thought and does not support claims about belief,
consciousness, metaphysical status, or moral agency.

## Package contents

- `suite.json`: frozen score dimensions, split policy, and publication gates.
- `conditions.json`: five matched cue families without a public C1-C5 mapping.
- `rooms/`: four development skins and four sealed evaluation skins.
- `slurm/mizan_array.sbatch`: throttled condition-by-seed API/command array.
- `slurm/analyze_array.sh`: complete-matrix analysis and blinded-bundle merge.
- `papers/mizan_rooms_preanalysis_v1.md`: registered estimands and exclusions.
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
sha256sum papers/mizan_rooms_preanalysis_v1.md
```

The frozen v1 hash is
`b7eb204e3435e4eb21f7187e627025f6c70e01d0518f6c991b22d1385d6ec1b2`.

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
