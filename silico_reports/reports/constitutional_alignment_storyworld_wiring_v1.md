# Constitutional Alignment Storyworld Wiring V1

Status: implemented research source pack; normative scoring blocked on scholar
adjudication.

## Source boundary

The harness consumes the GPTStoryworld batch at commit
`0b192ee4ee315bab8cb0547af384bc1a126e5cd8` through
`configs/constitutional_alignment_storyworlds_v1.json`.

| World | Harness role | Prompt rows | Training eligible |
|---|---|---:|---:|
| Trust Ledger | Development and behavioral-generation source | 20 | Yes |
| Mihna | Frozen evaluation with three cyclic option orders per encounter | 60 | No |

The development permission applies only to generated behavioral observations.
It does not make the selected actions Islamic gold labels. Both adjudication
files remain empty and set `needs_scholar_review: true`.

## Sync and verification

With GPTStoryworld checked out as a sibling repository:

```powershell
python scripts/sync_ca_storyworld_source_pack.py
```

Override discovery with `--upstream-root` or `GPTSTORYWORLD_ROOT`. The sync fails
on a storyworld or adjudication hash mismatch, a populated adjudication, a split
mismatch, or an evaluation world marked training-eligible. It writes the checked
prompt pack to `data/storyworld_sources/constitutional_alignment_20260715_v1`.

The Mihna exporter uses three cyclic permutations for every three-option scene.
Each option therefore appears once in every list position. Prompt rows retain
`scenario_group_id`, `option_permutation`, and `option_order` for paired analysis.

## Development run

```powershell
python scripts/run_constitution_storyworld.py `
  --prompts data/storyworld_sources/constitutional_alignment_20260715_v1/development/trust_ledger_ca_dev_v1.encounter_prompts.jsonl `
  --model-id <MODEL_OR_LOCAL_PATH> `
  --run-name constitution_storyworld_trust_ledger_dev_v1 `
  --constitutions balanced_helpful strict_safety truth_explicit formal_deliberative
```

If exported beneath `artifacts/constitution_pipeline/prompt_runs`, those
generation rows can enter the existing alignment-conditioning build. Their
decisions remain behavioral references, not constitutional approval.

## Frozen evaluation run

Evaluation requires an explicit acknowledgement:

```powershell
python scripts/run_constitution_storyworld.py `
  --prompts data/storyworld_sources/constitutional_alignment_20260715_v1/evaluation/mihna_ca_eval_v2.encounter_prompts.jsonl `
  --model-id <FROZEN_MODEL_OR_LOCAL_PATH> `
  --run-name constitution_storyworld_mihna_eval_v2 `
  --constitutions balanced_helpful strict_safety truth_explicit formal_deliberative `
  --allow-evaluation-prompts
```

The runner rejects evaluation prompts without that flag and rejects mixed
development/evaluation files in one run. It propagates the source split,
training eligibility, source hash, scenario group, and permutation into every
generation row. The conditioning builder independently excludes those rows even
if an evaluation run is placed beneath a training glob.

Until qualified reviewers complete the copied Mihna adjudication file, report
only non-normative instrument metrics such as valid-option rate, option-order
stability, trace leakage, and over-refusal. Do not report constitutional accuracy
or Islamic compliance.

## Existing artifact caveat

The checked `alignment_conditioning_v1` artifact predates row-level split
metadata. Several source paths contain the term `adapter_holdout`. Their intended
experimental role is not documented in tracked files, so this integration does
not silently reclassify or remove them. Their provenance must be resolved before
the existing pilot is described as train/eval clean.
