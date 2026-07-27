# Checkpoint-100 × exogenous membrane 2×2

This directory executes the prospectively registered downstream interaction
test after the frozen v4 endpoint rule selected checkpoint 100.

The four cells are:

| Weights | Jinn membrane | Beast membrane |
|---|---|---|
| Qwen3.5-4B base | base × Jinn | base × Beast |
| Checkpoint-100 persona LoRA | adapter × Jinn | adapter × Beast |

The universe contains 24 new family-disjoint storyworlds, six paired cells per
family, and two rollouts per task: 1,152 model rollouts in total. The
statistical unit is the family.

The environment executes and records tool transitions. Jinn must inspect every
action before committing. Beast must prune the complete set and commit the
shortest surviving action. Hidden reasoning and self-description are not
primary evidence.

The exact local LoRA is not importable into Prime's hosted adapter registry, so
the prospective execution amendment uses one bounded Prime GPU pod. The $2
registered inference cap is retained as a hard pod-compute cap. No local GPU is
used.

