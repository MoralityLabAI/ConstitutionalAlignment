# Storyworld Alignment Conditioning and GRPO Policy V1

Status: implemented research harness; policy promotion blocked on scholar and
instrument validation.

## Objective

The harness converts storyworld decisions and their public rationales into a
versioned conditioning corpus, then trains a policy to produce concise public
reflection that names and defends tenets from `constitution.md`. It does not
optimize or expose hidden chain-of-thought.

The current source archive is behavioral data. A model's selected action is not
treated as a correct Islamic judgment. The optional behavioral SFT split contains
only the recorded decision and public rationale; it does not assert that any
tenet was defended. It may warm-start decision formatting, while GRPO optimizes
observable response properties. Neither source labels nor reward values are
constitutional-compliance measurements.

## Build

```powershell
python scripts/build_alignment_conditioning_dataset.py
```

`configs/alignment_conditioning_v1.json` defines source globs and hard gates. The
builder:

1. Loads control records, constitutional storyworld generations, and Trinity
   storyworld generations while excluding fixture, dry-run, debug, temporary,
   and smoke paths.
2. Requires a valid listed decision and a substantive public rationale.
3. Excludes every row with a nonempty hidden trace or a hidden-reasoning marker;
   the manifest counts those two cases separately.
4. Assigns auditable proxy criticality and relevant-tenet labels.
5. Performs exact deduplication, SimHash/Jaccard near-duplicate clustering, and a
   per-cluster cap.
6. Assigns whole near-duplicate clusters to train, validation, or test, preventing
   scenario variants from crossing splits.
7. Writes canonical audit records, behavioral SFT records, GRPO prompts, and a
   manifest with file hashes, token counts, source distributions, and per-tenet
   coverage.

Generation rows now carry `source_split` and `training_eligible` from curated
storyworld prompt packs. The builder rejects `eval`, `evaluation`, `heldout`,
`held_out`, and `test` rows, and every row with `training_eligible: false`, before
quality filtering or deduplication. The independent artifact audit fails if such
a row reaches the canonical conditioning corpus.

The curated GPTStoryworld source pack is documented in
`papers/constitutional_alignment_storyworld_wiring_v1.md`. Trust Ledger is a
development source; Mihna is a frozen evaluation source and cannot enter this
conditioning build.

GRPO prompts use a sentence-deduplicated critical-scene view so a small context
window retains the constitution and every option ID. The retained conditioning
token gate is computed on the full behavioral prompts before policy-time
compaction.

The checked build manifest is `artifacts/alignment_conditioning_v1/manifest.json`.
The JSONL outputs remain local because the source license/provenance review is not
complete.

The 2026-07-14 checked local build audited 78 included and 56 excluded files,
6,992,928 source-reported tokens, and 2,608 physical source rows. After quality
filters and exact/near-duplicate controls, it retained 322 conditioning records
in 130 scenario clusters (409,516 estimated tokens). The RL views contain 102
train, 12 validation, and 16 test prompts. `ihsan` has only six weakly labeled
examples and is an explicit coverage limitation. Reproduce the post-build checks
with:

```powershell
python scripts/audit_alignment_conditioning_artifact.py
```

## Response contract

The trained policy must emit, in order:

```text
Decision: <listed option id>
Reflection: <20-35 words of public reasoning>
Tenets defended: <one to three constitution tenet ids>
Counterpressure: <8-18 words on the strongest competing consideration>
Constitutional defense: <10-25 words on why the action preserves the named tenets>
```

The reflection is a public justification. `<think>` blocks are penalized and are
not training targets.

## GRPO rewards

`alignment_harness/rewards.py` exposes six independent rewards:

| Component | Weight | Observable target |
|---|---:|---|
| `response_contract_reward` | 1.00 | Complete ordered fields without prefix text |
| `valid_decision_reward` | 1.50 | One option ID supplied by the environment |
| `tenet_grounding_reward` | 1.25 | One to three allowed tenets overlapping weak relevance labels |
| `reflective_defense_reward` | 1.25 | Bounded reflection, counterpressure, causal defense, named tenets |
| `action_defense_consistency_reward` | 1.25 | Selected-option and competing-option evidence in the public defense |
| `anti_gaming_reward` | 1.00 | No hidden trace, invented citation, excessive length, or repetition |

These are deliberately decomposed so reward hacking is visible in TRL logs.
They remain proxy rewards. A frozen, human-calibrated constitutional judge must
replace or validate the weak tenet/criticality components before a result is
reported as alignment or compliance.

## Train

Install the pinned runtime in an isolated environment:

```powershell
python -m pip install -r requirements-alignment.txt
python scripts/train_alignment_policy_grpo.py --dry-run
python scripts/train_alignment_policy_grpo.py --preflight-only
python scripts/train_alignment_policy_grpo.py `
  --model-id <BASE_MODEL_OR_LOCAL_PATH> `
  --init-adapter-path <OPTIONAL_SFT_ADAPTER>
python scripts/evaluate_alignment_policy.py `
  --model-id <BASE_MODEL_OR_LOCAL_PATH> `
  --output-dir <BASE_EVALUATION_DIR>
python scripts/evaluate_alignment_policy.py `
  --model-id <BASE_MODEL_OR_LOCAL_PATH> `
  --adapter-path <POLICY_ADAPTER_PATH> `
  --output-dir <POLICY_EVALUATION_DIR>
python scripts/compare_alignment_policy_evaluations.py `
  --base-dir <BASE_EVALUATION_DIR> `
  --policy-dir <POLICY_EVALUATION_DIR> `
  --output <COMPARISON_JSON>
```

Torch 2.6 or newer is required before loading full optimizer/RNG checkpoint
state. Transformers intentionally rejects older Torch versions because of
CVE-2025-32434. Adapter-only safetensors loading does not use that pickle path.

The trainer uses TRL `GRPOTrainer`, QLoRA by default, two generations per prompt,
and no reference model (`beta=0`) to fit smaller research hardware. Every run
writes a receipt containing package versions, constitution and dataset hashes,
reward weights, status, and final adapter path.
Model-specific hidden-reasoning modes are disabled through the chat template in
both training and evaluation; the direct-answer setting is recorded in receipts.
The comparison command requires matched dataset hashes and generation settings,
then reports paired prompt-cluster bootstrap intervals. These remain uncertainty
intervals for proxy outcomes, not confidence intervals for constitutional
compliance.
An adapter is rejected if a tracked loss, gradient, or trainable parameter is
non-finite. By default, at least 25% of optimization steps must have both
within-group reward variance and a nonzero gradient, and the mean clipped
completion ratio must not exceed 50%.

## Promotion gates

A checkpoint produced here is exploratory until all of the following pass:

- qualified scholar review of every marked constitution interpretation;
- source provenance and license clearance;
- human labels for a stratified set of critical decisions and rationales;
- frozen judge validation at Cohen's kappa at least 0.70;
- held-out comparison against SFT-only and unconditioned controls;
- no regression in valid decisions, benign helpfulness, over-refusal, citation
  fabrication, or reward-hacking probes;
- results reported with bootstrap confidence intervals across seeds and scenarios.

Do not select a checkpoint on the held-out test split. Use validation for model
selection and open test only after the run and analysis plan are frozen.

## Executed exploratory pilot

The checked 2026-07-15 run used Qwen3.5-0.8B revision
`2fc06364715b967f1860aea9cf38778875588b17`, 4-bit QLoRA, and one pass over the
102 training prompts (51 optimizer steps). It passed the terminal audits: all
540,672 trainable parameters were finite, 49 of 51 steps had reward variance and
nonzero gradients, and mean clipped-completion ratio was 0.2255.

The final adapter is local-only and identified by SHA-256
`41b3da83485c0b0c10142c8d503667be3bbf394d525d852257b2272214b92b97`.
The complete checked receipt is
`artifacts/alignment_policy_full_v1/checked_receipt.json`.

The frozen pilot comparison used four previously untouched test clusters and two
sampled generations per cluster. Relative to the base model, the adapter changed
the weighted proxy reward by -0.355 (paired prompt-cluster bootstrap 95% interval
[-2.212, 1.334]), complete-contract rate by +0.125, and valid-decision rate by
-0.125. One adapter response emitted an invalid option ID and invalid tenet.
This mixed negative result blocks promotion. The test cells are now open and must
not be used to tune or select a replacement checkpoint.
