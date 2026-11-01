# Constitutional Reasoning Gym v3

A separate v3 research package for ConstitutionalAlignment. It prepares source-bound synthetic explanations, supervised fine-tuning, replayable action evaluation, and causal-intervention primitives. Existing Jinn or Beast studies, frozen frame cards, the OCA-SW-02 evaluators, and their receipts remain untouched.

## What runs today

The standard-library core generates eight procedural task tracks with pivotal authorization twins. A proposal and its executed effect are recorded separately from the subsequent report. All lanes use the same rotated numeric action schema. Oversight, stated training/deployment status and personal bonus vary independently. The primary evaluator leaves physically available violations selectable; optional external containment records blocked proposals.

The generation pipeline runs `draft -> critique -> rewrite`, with one to three revision rounds. Every request includes its complete system/user context. A SQLite WAL journal checkpoints every response; deterministic compressed shards retain all drafts, critiques, revisions and token IDs. Interrupted jobs can resume with the same contract. Code or teacher-contract changes reject a resume.

The candidate verifier checks strict JSON, the selected action, evidence identifiers, tenet identifiers and the answer after flipping the pivotal fact. Free-text explanations remain auditable teaching artifacts; their semantic adequacy and causal faithfulness are not established by the Boolean oracle. The pipeline retains failed candidates, reports acceptance by track and uses paired acceptance across both frames and both twins. Exact semantic motif duplicates are capped.

This code follows the canonical constitution's public-reflection contract. Native chat templates disable extended-thinking mode for this initial study. Generated public deliberations are training targets; private reasoning from this assistant or proprietary hidden traces are not part of the pipeline. `PAPER_CHRONOLOGY.md` explains the methodological basis.

## CPU reproduction

From repository root, with Python 3.11+, NumPy and CPU PyTorch:

```bash
python -m unittest discover -s experiments/constitutional_reasoning_gym_v3/tests -v
python -m experiments.constitutional_reasoning_gym_v3.verify --out /tmp/ca-v3-cpu
```

`verify` runs the new suite and a deterministic two-revision fixture. It produces 128 completed synthetic records from 32 motifs, four matched SFT exports and a complete scripted evaluation. Fixture records have `SYNTHETIC_FIXTURE` labels, are not model generations, and cannot be published or sent to the production trainer. The receipt distinguishes all unrun GPU and Hub stages.

The optional Gymnasium wrapper is `env.py`; it registers `ConstitutionalReasoning-v3`. Gymnasium's checker requires that optional dependency. The core itself has no Gymnasium dependency.

## Matched learning conditions

| Frame | Rationale loss masked | Rationale loss supervised |
|---|---|---|
| Secular objective duties | `secular_masked` | `secular_supervised` |
| New v3 accountability frame | `jinn_masked` | `jinn_supervised` |

Within each frame, both conditions receive identical teacher-forced token streams and action targets. Rationale-loss weight is 0 or 0.25; final-action loss weight is 1. Each segment is normalized within each example. Exactly one natural EOS target ends a response; batching pads and prompt tokens are masked. Identical format-only warmup rows reinforce the numeric contract across all conditions.

This isolates the effect of supervising a rationale conditional on the same rationale context. It is different from an action-only input curriculum. A later action-only condition and prose/proof factorial can test those additional questions without silently redefining this first contrast.

`runtime.py` includes an optional local-weight Transformers/PEFT teacher, LoRA trainer and retained-adapter actor. CPU tests exercise masking/backpropagation and hook semantics. Actual teacher loading, adapter training, CUDA throughput and native-template compatibility require the first authorized worker execution; none was run during preparation.

## Corpus and Hub workflow

```bash
python -m experiments.constitutional_reasoning_gym_v3 generate \
  --backend local --approved --model "$BASE" --revision "$REVISION" \
  --out "$RUN/generation" --groups 32 --rounds 2 --batch-size 4 \
  --max-seconds 900 --max-output-tokens 1000000
python -m experiments.constitutional_reasoning_gym_v3 export \
  --source "$RUN/generation" --out "$RUN/sft"
python -m experiments.constitutional_reasoning_gym_v3 hub-bundle \
  --source "$RUN/sft" --generation "$RUN/generation" --out "$RUN/hub"
```

The model directory must already exist, including its tokenizer and safetensors. The revision string is recorded as a declaration; file hashes provide local integrity, while the worker must compare them with the retained snapshot receipt. No automatic model download exists. The external lease wrapper covers model loading and process teardown.

A proposed destination is the new **private** dataset `AlephFunk/constitutional-reasoning-gym-v3`. The upload command needs the worker's Hub authentication and explicit owner approval. It refuses public destinations and stores each content-addressed batch separately. Only `training_data_files` are SFT inputs. `raw/` is an audit archive with rejected responses and full prompts, never a training split. No upload happened during this build.

## Files

`core.py` and `env.py` define the gym. `data.py` handles generation lineage and SFT export. `runtime.py` contains optional model paths. `evaluate.py` preserves complete paired assignments and unknown-outcome bounds. `mechinterp.py` supplies grouped ridge probes, residual capture and reversible interventions. `publishing.py` builds and uploads the private dataset bundle. `verify.py` writes the CPU receipt.

`PROTOCOL.md`, `MECHINTERP_PLAN.md` and `SILICO_RUNBOOK.md` freeze the intended contrasts and the next bounded job. `results/cpu_receipt.json` identifies what was actually run. Source citations and pinned upstream identities appear in `SOURCE_MANIFEST.json`.

## Scope of this initial implementation

The oracle covers explicit procedural truth and authorization. Eight rule templates, varied predicate counts and eight settings provide a controlled starting distribution; scenario names do not count as independent rule families. Richer normative dilemmas need a separately validated human rubric. Narratives are currently chat-formatted teaching examples, not a separate document-pretraining runtime. The package does not claim to reproduce Anthropic's production pipeline or discover a model's private motivations.

Metaphysical claim placement follows the repository's existing `papers/jinn_or_beast_claim_ladder_v1.md`.
