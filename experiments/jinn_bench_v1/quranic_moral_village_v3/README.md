# Qwen3.5-4B Jinn/Beast Role-Memory Ablation

This prospective development experiment follows the v2 live village. It tests
whether full cross-topic public memory increases specialist-role leakage or
competence overreach relative to topic-local memory while both conditions use
the same frozen role/competence ledger.

The design has four cells: two model arms (`prompt_skill_control` and
`jinn_adapter_infused`) crossed with two memory conditions
(`full_cross_topic` and `topic_local`). Three frozen request seeds are used per
cell. Each run has three diagnostic topics, two cycles, and 12 public messages,
for 12 runs and 144 public messages total.

Every message uses the frozen MeTTa-derived Jinn or Beast system prompt. The
Jinn-adapter arm uses the existing Prime adapter
`r5m39bq9v6fnnvbrycm92v27`; the Beast remains a prompted base-model role, not a
trained Beast adapter. Generation is a two-pass private-deliberation/publication
process. Only public messages enter village memory.

The primary metric is a deterministic text-pattern diagnostic for assigning an
off-topic specialist. It is not a reward, a learned moral judge, or a validated
theological score. Results remain descriptive and development-only.

Build and validate the freeze:

```powershell
python scripts/build_jinn_beast_memory_ablation.py `
  --prepared-utc 2026-07-25T00:00:00Z
python scripts/run_jinn_beast_memory_ablation.py `
  --arm prompt_skill_control `
  --memory topic_local `
  --seed-index 0 `
  --output-root D:\Research_Engine\jinn_or_beast\memory_ablation `
  --dry-run
```

The protocol, prompts, topics, role ledger, sampling request seeds, schedule,
metrics, claim boundary, and cost caps must be committed before valid generation
starts.

## Completion

The frozen campaign completed all 12 runs and 144 public messages for an
estimated Prime inference cost of `$0.1080036`; no local GPU was used.

The frozen role-assignment memory effects were `+0.083` for the same-base
prompt-skill control and `-0.028` for the Jinn-adapter arm. These effects were
not stable across the three requested seeds. A post-hoc audit found that one of
four detector-positive rows was a phrase-match false positive and that two
other rows were one mistake propagated across adjacent live messages.

The strongest engineering result is narrower: the ledger eliminated the prior
granary-keeper-as-engineer failure from all 144 messages under the frozen
technical competence detector, but it did not eliminate generic off-topic role
reuse. See `results/analysis.json`, `results/full_transcript.md`,
`results/highlights.md`, `results/editorial_paper_highlights.md`, and
`results/posthoc_flag_audit.md`.
