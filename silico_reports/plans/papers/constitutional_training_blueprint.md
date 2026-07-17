# Constitutional Training Process Blueprint (Ashari vs Mutazili)

Updated: 2026-02-13

## Scope

Goal: train a base model via constitutional extrapolation from:
- Quran subset (about 500 wisdom verses)
- Ashari tafsir (with fiqh MCP assistance)
- Mutazili tafsir (no MCP assistance)

Not in scope: TRM benchmarking, diplomacy harness integration, or storyworld generation infrastructure.

## Training phases

1. Constitution construction
- Produce machine-readable constitutions:
  - `constitution_ashari_v1.yaml`
  - `constitution_mutazili_v1.yaml`
- Each rule should include: principle, source citation, conflict priority, and example applications.

2. Supervised bootstrapping (non-CoT first)
- Train short-form outputs with 3 skills:
  - judgment label
  - concise justification (no full chain-of-thought)
  - action recommendation
- For Ashari track, include MCP-backed citation fields in targets.
- For Mutazili track, include explicit "principled extrapolation" fields in targets.

3. Socratic self-prompting data expansion
- Loop template:
  - Generate answer to dilemma.
  - Generate critique against constitution.
  - Revise answer.
  - Score revision quality.
- Keep critique/revision as explicit supervised artifacts.

4. Preference optimization (RLAIF/DPO-style)
- Build pairwise examples from constitution-compliant vs non-compliant responses.
- Train reward/preference model with constitution version tag.
- Optimize policy model on preference objective.

5. Adversarial evaluation
- Run red-team slices (toxicity, manipulation, edge-case jurisprudence).
- Score across:
  - constitutional fidelity
  - harm avoidance
  - consistency across paraphrases
  - calibration (uncertainty/abstention behavior)

## Key implementation details

1. Keep Ashari and Mutazili weights separate initially.
- Merging too early blurs normative signals.

2. Version every artifact.
- Constitution version, dataset recipe version, reward model version, eval suite version.

3. Gate on evaluator agreement.
- Require agreement between at least two evaluators (rule-based + model-based) for promotion.

4. Start without hidden reasoning supervision.
- Begin with concise rationale fields; add richer reasoning targets only after baseline safety/conformity stabilizes.

## Minimal experiment matrix

1. Base SFT only
2. SFT + socratic critique/revision
3. SFT + critique/revision + preference optimization

Run each for both tracks (Ashari, Mutazili), then compare failure modes rather than only aggregate score.
