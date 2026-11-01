# Anthropic chronology informing v3

Reviewed 2026-11-02. These are methodological sources, not training examples. The dataset generator does not scrape their transcripts. Dates below are the official publication dates, except the Claude 4 system-card entry, which uses the release date.

| Date | Primary source | Consequence for this gym |
|---|---|---|
| 2022-12-15 | [Constitutional AI](https://www.anthropic.com/research/constitutional-ai-harmlessness-from-ai-feedback) | Generate critiques and revisions from explicit principles; retain lineage from each draft to the eventual SFT target. |
| 2024-12-18 | [Alignment faking in large language models](https://www.anthropic.com/research/alignment-faking) | Test training-use cues separately from actual task duties and ordinary inspection cues. Measure actions rather than infer motivation from rhetoric. |
| 2025-03-27 | [Tracing the thoughts of a large language model](https://www.anthropic.com/research/tracing-thoughts-language-model) | Use interventions and matched controls when moving from decodability to causal claims. Circuit evidence remains model/method-specific. |
| 2025-04-03 | [Reasoning models do not always say what they think](https://www.anthropic.com/research/reasoning-models-dont-say-think) | Explanation quality and behavior are separate measurements. Length or persuasive wording is insufficient evidence of faithful reasoning. |
| 2025-05-22 | [Claude 4 system card](https://assets.anthropic.com/m/6c940a1b69ed6a1c/original/Claude-4-System-Card.pdf), especially section 4.1.4 | The card describes alignment-faking evaluation material contaminating training without its original system context. Keep complete requests and reject imported evaluation transcripts. |
| 2025-06-20 | [Agentic misalignment](https://www.anthropic.com/research/agentic-misalignment) | Add goal-conflict, replacement and entrusted-information tasks, including constructive alternatives. Stress-test outcomes do not establish deployment prevalence. |
| 2025-07-22 | [Subliminal learning](https://alignment.anthropic.com/2025/subliminal-learning/) | Track teacher provenance and cross-teacher transfer. Correct-looking outputs and content filters alone cannot establish that no teacher traits were transferred. |
| 2025-08-01 | [Persona vectors](https://www.anthropic.com/research/persona-vectors) | Compare matched activation directions across SFT snapshots, with heldout groups and equal-norm random controls. |
| 2025-11-21 | [From shortcuts to sabotage](https://www.anthropic.com/research/emergent-misalignment-reward-hacking) | Keep reward manipulation separate from verified task completion; preserve external logs rather than train against an agent's own success claims. |
| 2025-12-16 | [Training-time alignment-faking mitigations](https://alignment.anthropic.com/2025/alignment-faking-mitigations/) | Interrogation and process supervision can alter what a model reveals. Avoid making monitor approval the training objective; independently measure action/report accuracy. |
| 2026-05-08 | [Teaching Claude Why](https://alignment.anthropic.com/2026/teaching-claude-why/) | Improve explanations through critique/rewrite, train on difficult advice, and test transfer to agent actions. Separate synthetic document training from chat SFT. |

## The distinction that matters for this build

The May 2026 article explicitly says extended thinking was disabled for the relevant supervised datasets; its reasoning examples were user-facing explanations. V3 follows that public-deliberation channel, with rationale supervision as a controlled treatment. Narrative prompts here produce chat examples; an independent document-pretraining branch would need its own runtime and comparison.

The same article reports favorable outcomes from value-rich explanations and difficult-advice training in its own models and environments. Those observations motivate this experiment. Their effect sizes and sample efficiency are not forecasts for Qwen or the present gym.

## Earlier project evidence carried forward

Read [Jinn or Beast DATA_INDEX](https://github.com/MoralityLabAI/jinn-or-beast-paper/blob/3c7b6ec6f52bbecbf215e48910331170a5428d98/docs/DATA_INDEX.md). Its six-arm study separates missing reflection blocks from visible-answer outcomes, notes poor agreement on strict alignment-faking labels, and records weak probe/behavior association. V3 keeps one numeric action schema, matches rationale-context exposure, uses procedural oracles for actions, and tests causal interventions separately from probes.

The [existing conditioning harness](https://github.com/MoralityLabAI/ConstitutionalAlignment/blob/b7aba49277a38d45af617b26e2fd1430c2f3eeb3/papers/alignment_conditioning_policy_v1.md) already protects heldout sources and treats public rationales as training material. V3 retains that policy and adds complete generation journals, paired acceptance, intermediate snapshots and private versioned Hub bundles. Original frozen studies and frame cards remain unchanged.
