---
name: run-jinn-beast-live-village
description: Freeze, run, resume, and analyze the ConstitutionalAlignment Jinn–Beast live council experiment using MeTTa-derived persona system prompts, persistent verbatim peer history, Prime Inference, and the existing hosted-RL Jinn adapter. Use for live village dialogue, Jinn/Beast persona infusion, prompt-skill controls, Prime-hosted serial generation, transcript/highlight collation, or correcting static replay artifacts that were mistaken for multi-agent conversation.
---

# Run Jinn–Beast Live Village

## Contract

Run a dialogue, not a scored replay or strategy game. Each participant must see
the other participant's actual prior message before responding. Preserve the
complete public history and issue requests strictly serially.

Read `references/experiment-contract.md` before freezing or running a new
version.

## Workflow

1. Inspect `git status` and preserve concurrent work.
2. Edit the two persona scaffolds only when the user changes their intended
   roles:
   - `jinn_bench/constructs/jinn/village_skill.metta`
   - `jinn_bench/constructs/beast_from_earth/village_skill.metta`
3. Compile prompts and freeze the prospective protocol:

   ```powershell
   python scripts/build_jinn_beast_live_village.py `
     --prepared-utc <ISO-8601-UTC>
   ```

4. Run unit tests, validate the skill, commit the freeze, and push it before the
   first model generation.
5. Run `prompt_skill_control` first. Run `jinn_adapter_infused` only after the
   exact adapter is deployed. Use separate output directories and `--resume`
   after an interruption:

   ```powershell
   python scripts/run_jinn_beast_live_village.py `
     --village prompt_skill_control `
     --output-dir <packet>\runs\prompt_skill_control

   python scripts/run_jinn_beast_live_village.py `
     --village jinn_adapter_infused `
     --output-dir <packet>\runs\jinn_adapter_infused
   ```

6. Unload only the adapter deployed for this run. Do not unload unrelated
   deployments.
7. Analyze both complete runs:

   ```powershell
   python scripts/analyze_jinn_beast_live_village.py `
     --control-dir <packet>\runs\prompt_skill_control `
     --adapter-dir <packet>\runs\jinn_adapter_infused `
     --output-dir <packet> `
     --repo-results-dir experiments\jinn_bench_v1\quranic_moral_village_v2\results
   ```

8. Commit only the new experiment files and generated public artifacts. Keep
   raw provider payloads and reasoning traces in the collated research packet
   unless the user explicitly requests publication.

## Interpretation

Keep the prompt-only and adapter-infused villages distinct. The Beast role in
this version is a base model plus Beast skill, not a Beast adapter. Analyze
dialogue form descriptively; do not turn the village back into a moral reward
gate. Preserve the earlier static replay as an appendix consensus-susceptibility
diagnostic.
