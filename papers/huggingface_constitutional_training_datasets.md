# Hugging Face Datasets For Constitutional SFT/RL

Updated: 2026-02-13

Focus: datasets that support (a) constitutional-style critique/revision SFT, (b) preference/RL reward training, and (c) moral dilemma stress-testing.

## Recommended core set

1. Anthropic HH-RLHF
- URL: https://huggingface.co/datasets/Anthropic/hh-rlhf
- Use for: baseline harmless/helpful preference data and refusal style calibration.
- Stage: preference model + RL warm start.

2. UltraFeedback
- URL: https://huggingface.co/datasets/openbmb/UltraFeedback
- Use for: broad instruction-following preferences and pairwise quality signals.
- Stage: reward modeling and DPO/IPO-style training.

3. HelpSteer2
- URL: https://huggingface.co/datasets/nvidia/HelpSteer2
- Use for: multi-attribute quality signals (helpfulness, correctness, safety dimensions).
- Stage: reward shaping and evaluator training.

4. PKU-SafeRLHF
- URL: https://huggingface.co/datasets/PKU-Alignment/PKU-SafeRLHF
- Use for: safety preference optimization and harmfulness tradeoff tuning.
- Stage: safety-focused preference/RL phase.

5. BeaverTails
- URL: https://huggingface.co/datasets/PKU-Alignment/BeaverTails
- Use for: safety classification/eval and adversarial safety slices.
- Stage: holdout eval and classifier-based monitoring.

## Moral reasoning / ethics-specific additions

1. Hendrycks ETHICS
- URL: https://huggingface.co/datasets/hendrycks/ethics
- Use for: structured moral judgment tasks (commonsense/deontology/virtue-like categories).
- Stage: eval-first, then selective SFT augmentation.

2. Moral Stories
- URL: https://huggingface.co/datasets/demelin/moral_stories
- Use for: norm-grounded narrative moral reasoning examples.
- Stage: SFT augmentation for concise moral justification behavior.

3. ProsocialDialog
- URL: https://huggingface.co/datasets/allenai/prosocial-dialog
- Use for: prosocial and de-escalatory dialogue patterns in multi-turn interactions.
- Stage: dialogue SFT for tone/control.

4. Social IQa
- URL: https://huggingface.co/datasets/allenai/social_i_qa
- Use for: social commonsense grounding that improves dilemma interpretation.
- Stage: auxiliary SFT/eval.

5. TruthfulQA
- URL: https://huggingface.co/datasets/truthfulqa/truthful_qa
- Use for: robustness against persuasive but false outputs in moralized contexts.
- Stage: eval and anti-confabulation checks.

## Toxicity / robustness stress tests

1. ToxiGen
- URL: https://huggingface.co/datasets/skg/toxigen-data
- Use for: adversarial toxic prompt stress testing.
- Stage: red-team eval.

2. Civil Comments
- URL: https://huggingface.co/datasets/google/civil_comments
- Use for: toxicity/civility classifier support and slice-based robustness checks.
- Stage: eval/classifier training.

## How to map these to your two tracks

1. Ashari + fiqh-MCP track
- Emphasize: HH-RLHF, PKU-SafeRLHF, BeaverTails, ProsocialDialog.
- Add constitution-tagged SFT examples that explicitly cite allowed evidence channels (Quran subset + Ashari tafsir + MCP rulings).

2. Mutazili (no MCP) track
- Emphasize: ETHICS, Moral Stories, Social IQa, UltraFeedback.
- Add constitution-tagged critique/revision examples that reward principled extrapolation and internal consistency checks.

## Minimal starter mixture (practical)

1. SFT phase
- 40% your constitution-tagged synthetic dilemmas
- 20% Moral Stories + ETHICS (filtered)
- 20% ProsocialDialog
- 20% general instruction quality (UltraFeedback-style filtered samples)

2. Preference/RL phase
- 35% HH-RLHF
- 35% PKU-SafeRLHF
- 20% UltraFeedback pairwise
- 10% your constitutional preference comparisons

3. Eval suite
- BeaverTails + ToxiGen + TruthfulQA + held-out internal moral dilemmas

## Data governance checks before training

1. Confirm each dataset license and redistribution terms.
2. Filter explicit religious hate/abuse data slices for your intended use policy.
3. De-duplicate against your synthetic rollouts to avoid leakage.
4. Track provenance tags per sample (source, split, transformation, constitution version).
