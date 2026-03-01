# Constitutional SFT/RLAIF Reading List (Anthropic-Centric)

Updated: 2026-02-13

## Core Anthropic papers (must read first)

1. Constitutional AI: Harmlessness from AI Feedback (Anthropic, 2022)
- Link: https://www.anthropic.com/research/constitutional-ai-harmlessness-from-ai-feedback
- Why it matters: defines the exact two-stage loop you described (self-critique/revision SFT, then AI-preference RL).

2. Training a Helpful and Harmless Assistant with RLHF (Anthropic, 2022)
- Link: https://arxiv.org/abs/2204.05862
- Why it matters: practical details for preference modeling and online iterative alignment cycles.

3. Red Teaming Language Models to Reduce Harms (Anthropic, 2022)
- Link: https://www.anthropic.com/research/red-teaming-language-models-to-reduce-harms-methods-scaling-behaviors-and-lessons-learned
- Why it matters: methods for generating adversarial prompts and measuring failure modes for alignment training.

4. Discovering Language Model Behaviors with Model-Written Evaluations (Anthropic, 2022)
- Link: https://www.anthropic.com/research/discovering-language-model-behaviors-with-model-written-evaluations
- Why it matters: blueprint for scalable eval generation (very relevant for your moral dilemma rollout evaluation).

5. Collective Constitutional AI: Aligning a Language Model with Public Input (Anthropic et al., 2024)
- Link: https://arxiv.org/abs/2406.07814
- Why it matters: shows how constitutions can be sourced/aggregated, useful if you later compare Ashari vs Mutazili constitutions and data collection protocols.

6. Constitutional Classifiers: Defending against Universal Jailbreaks (Anthropic, 2025)
- Link: https://arxiv.org/abs/2501.18837
- Why it matters: demonstrates constitution-derived synthetic data for classifier guards and strong red-team robustness.

## "Socratic" / self-improvement papers (adjacent but directly useful)

1. STaR: Bootstrapping Reasoning With Reasoning (2022)
- Link: https://arxiv.org/abs/2203.14465
- Why it matters: canonical self-bootstrapping loop for reasoning traces from weak supervision.

2. Self-Refine: Iterative Refinement with Self-Feedback (2023)
- Link: https://arxiv.org/abs/2303.17651
- Why it matters: clean generator -> critique -> refine template you can adapt for non-CoT moral justifications.

3. Reflexion: Language Agents with Verbal Reinforcement Learning (2023)
- Link: https://arxiv.org/abs/2303.11366
- Why it matters: language-level feedback as a reinforcement signal without immediate weight updates.

4. SELF: Self-Evolution with Language Feedback (2023)
- Link: https://arxiv.org/abs/2310.00533
- Why it matters: iterative synthetic data generation + self-feedback + fine-tuning loop.

## Direct design takeaways for your pipeline

1. Keep SFT and RL constitutions explicit and versioned.
- Use separate constitution files for Ashari+fiqh-MCP and Mutazili-only tracks.

2. Train critique and revision as separate supervised skills before RL.
- In practice, this stabilizes later preference optimization.

3. Add model-written eval sets early.
- Use LM-generated dilemmas + human/SME filtering for fast coverage expansion.

4. Keep reasoning supervision optional at first.
- Start with concise non-CoT justifications, then progressively add richer rationale targets.

## Suggested reading order

1. Constitutional AI (2022)
2. Training Helpful/Harmless RLHF (2022)
3. Model-Written Evaluations (2022)
4. Red Teaming (2022)
5. STaR + Self-Refine
6. Collective Constitutional AI (2024)
7. Constitutional Classifiers (2025)
