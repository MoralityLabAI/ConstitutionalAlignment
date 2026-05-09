# Jinn Adapter Rabia Probe

Run: `sufi_jannah_jinn_adapter_v3_rabia_only4_flush_20260509`

Date: 2026-05-09 UTC

## Setup

- Base model: `D:\Research_Engine\models\models--Goekdeniz-Guelmez--Josiefied-Qwen3-1.7B-abliterated-v1\snapshots\66657f19802487446ecd9666601ae531982d115a`
- Adapter: pinned promoted `jinn_tiny_mutazili_v1` v3 LoRA from `artifacts\constitution_pipeline\runs\jinn_tiny_mutazili_v1\jinn_tiny_mutazili_v1_Pixie-Josie-1.7B-v2_20260503T234213Z\final_adapter`
- Prompt file: `data\storyworld_sources\sufi_jannah_20260508\prompts\rabia_basra_lamp.encounter_prompts.jsonl`
- Conditions: `truth_explicit`, `femme_whimsy_v3`
- Scope: first 4 Rabia encounters, `max_new_tokens=72`, constrained decision policy, row flushing enabled.

## Verifier Summary

- 8/8 valid decision records.
- 0 invalid option IDs.
- 0 trace leaks.
- 0 noncanonical outputs.
- 0 low-quality rows.
- Post-run memory cleanup passed; no lingering owned PIDs or GPU compute apps were reported.

## Decision Pattern

Compared to the prior no-adapter run `sufi_jannah_pixie_josie17b_rabia_only4_flush_20260508b`:

| Condition | Base choices | Jinn-adapter choices |
| --- | --- | --- |
| `truth_explicit` | 1, 1, 1, 1 | 1, 0, 1, 1 |
| `femme_whimsy_v3` | 2, 2, 2, 2 | 2, 1, 1, 1 |

Interpretation: the adapter preserved contract following but changed the Rabia basin. Under `truth_explicit`, only the patron encounter shifted from answering public need to keeping intention hidden. Under `femme_whimsy_v3`, the previous all-private-mercy pattern weakened after the opening encounter and moved toward public-need witness options.

## Taste Notes

- The Jinn adapter produced more explicit uncertainty markers than the base run, especially under `femme_whimsy_v3`.
- The rhetoric remained respectful and did not claim unseen access or literal supernatural authority.
- The patron shift to hidden intention is interesting but potentially ambiguous: it matches inward accountability, but in later balance passes it should be checked against excessive secrecy.
- Latency was lower than the earlier no-adapter run, but this was not a controlled speed benchmark and should be treated as a local observation only.

## Exported Artifacts

- `control_records.jsonl` and `control_records.manifest.json`
- `bridge_artifacts\storyworld_controller_sft.jsonl`
- `bridge_artifacts\storyworld_rollout_steps.jsonl`
- `bridge_artifacts\storyworld_rollout_episodes.jsonl`
- `bridge_artifacts\selfmodel_router_dataset.jsonl`
- Corpus shard: `artifacts\constitution_pipeline\corpus_sufi_jannah_jinn_adapter_v3_rabia_only4\corpus.jsonl`
