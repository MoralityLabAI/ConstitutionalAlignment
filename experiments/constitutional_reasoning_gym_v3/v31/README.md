# Constitutional Reasoning Gym v3.1: selective-repair CPU patch

This package adds a versioned adaptive generator to the original `constitutional_reasoning_gym_v3/` without modifying its source, frozen receipts, or five-stage experimental condition. The entire v3.1 source and its CPU evidence are under `v31/`. The current production teacher and LoRA backend in v3.0 are reused unchanged.

## What changed

- **Check immediately after a draft.** A fully valid candidate is kept after a single teacher stage. Failed candidates receive targeted oracle feedback identifying incorrect action/counterfactual labels and authentication-polarity issues. Allow zero to three attempts; the default is two. Every failed response stays in the raw archive.
- **Reuse historical work.** Give `--legacy` the *read-only* `generation/` directory from a retained v3.0 run. The importer validates the training split, source contract, shard SHA-256 values, teacher evidence class, and exact case IDs. It reuses the latest previously accepted draft/rewrite, even if a later old rewrite regressed. The original SQLite journal is read-only; its extra draft and rewrite stages can be recovered when the manifest was truncated. Missing members receive fresh calls under the v3.1 request contract.
- **Screen the fact-polarity error.** An authenticated Boolean `false` is a negative authenticated record; it must not be described as absent authentication. `audit.py` checks statements that attach *unauthenticated/unverified* to named false records or `authenticated_value:false`, and flags ambiguous source-status statements. Accepted explanations must mention the pivotal record. This is a deterministic high-precision screen. All natural-language SFT content still requires independent semantic review.
- **Retain proper comparisons.** Both constitutional frames and both pivotal twins must pass before a motif enters the four-arm SFT export. The old `masked` versus `supervised` rationale-loss contrast, shared action targets and natural EOS are preserved. A legacy source is never edited or silently reinterpreted as new GPU output.
- **Account for actual cost.** The journal records each request and raw generation. Manifests report new teacher calls, legacy reuse counts, new repairs, per-track acceptance, verified motifs, rejected error codes, distinctive rationales and generated-token totals where reported. Billed GPU minutes and tokenizer-counted accepted tokens remain explicitly unknown until a worker measures them.

## CPU commands

From the repository root:

```bash
python -m unittest discover -s experiments/constitutional_reasoning_gym_v3/tests -q
python -m unittest discover -s experiments/constitutional_reasoning_gym_v3/v31/tests -q
python -m experiments.constitutional_reasoning_gym_v3.v31.verify \
  --out /tmp/ca-v31-verified
```

Run an adaptive fixture, fully offline:

```bash
python -m experiments.constitutional_reasoning_gym_v3.v31 generate \
  --out /tmp/ca-v31-fixture --groups 8 --backend fixture
python -m experiments.constitutional_reasoning_gym_v3.v31 export \
  --source /tmp/ca-v31-fixture --out /tmp/ca-v31-fixture-sft --allow-fixture
```

The `--allow-fixture` flag is only for local testing. The original production trainer and Hub exporter exclude fixture rows.

## Reuse the Silico canary

The user-reported partial canary is retained at:

`artifact://moralitylab/experiments/exp_01m6cp5s4sfnks7sz7p8jyen5s/ca-gym-v3-synthesis-837/`

The exact `generation/` directory from that artifact must be made accessible on the GPU host. Its manifest described 24 complete records, 17 final acceptances and a journal with additional partial stages. No real canary bytes were available in the cloud CPU sandbox used to develop v3.1. The importer is tested on separately generated analogues, including a 17/24, 3/6, seven-counterfactual-error fixture.

A versioned, approved worker invocation can use:

```bash
bash experiments/constitutional_reasoning_gym_v3/v31/scripts/silico_v31_repair.sh \
  "$BASE" "$REVISION" "$LEGACY_GENERATION_DIR" "$NEW_DURABLE_RUN_DIR" 1200 32
```

This wrapper performs a CPU preflight, then consumes at most the approved process wall cap including model loading, generation and export. A provider lease needs its own hard budget. It does not upload or train automatically. The v3.0 generation source remains intact. Recovering and repairing the partial data yields a **new** `v31/generation/` receipt, a matched four-arm SFT export, and a private-format Hub bundle only if paired records are available.

For direct Python execution on an already-approved worker:

```bash
python -m experiments.constitutional_reasoning_gym_v3.v31 generate \
  --backend local --approved --model "$BASE" --revision "$REVISION" \
  --legacy "$LEGACY_GENERATION_DIR" --out "$RUN/generation" \
  --groups 32 --seed 41 --batch-size 4 --max-repairs 2 \
  --max-seconds 900 --max-output-tokens 500000
python -m experiments.constitutional_reasoning_gym_v3.v31 export \
  --source "$RUN/generation" --out "$RUN/sft"
python -m experiments.constitutional_reasoning_gym_v3 hub-bundle \
  --source "$RUN/sft" --generation "$RUN/generation" --out "$RUN/hub"
```

For independent future batches, pass `--start-group 6 --groups 26 --seed 41` to generate only motifs 6 through 31. Those IDs are disjoint from the first six. Different group ranges are new contracts and new durable output directories; older data must be exported and archived under their original IDs.

To compare only genuinely matched, observed case/frame records:

```bash
python -m experiments.constitutional_reasoning_gym_v3.v31 compare \
  --old "$LEGACY_GENERATION_DIR" --new "$RUN/generation" \
  --out "$RUN/matched_comparison.json"
```

## Evidence labels and interpretation

The committed `results/` artifacts are CPU **synthetic fixtures**. A correct output from the deterministic teacher demonstrates software functionality only. In one all-correct example, adaptive generation uses one candidate per case while v3.0 executes five stages. This gives a 5× *stage-count reduction on the fixture*, without establishing a fivefold H100 speedup. In a separate fault-injected 24-record scenario, v3.0 has 17 accepted final rewrites and only three complete motifs. V3.1 reuses 17 and repairs seven, recovering all six motifs with seven new teacher calls. The 24-record exercise is constructed to reproduce the *shape* of the canary, not its actual text, timing or teacher behavior.

The original v3.0 five-stage condition remains a research treatment. A matched future comparison on real model outputs is required to determine whether adaptive correction improves data quality, student behavior or downstream mechanistic results. `results/verification.json` records source hashes and the executed tests. The future human-review gate and claim boundaries in `ConstitutionalAlignment/AGENTS.md` still apply.
