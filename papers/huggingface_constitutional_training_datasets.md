# Hugging Face Datasets For Constitutional SFT/RL

Updated: 2026-02-13

Focus: datasets that support (a) constitutional-style critique/revision SFT, (b) preference/RL reward training, and (c) moral dilemma stress-testing.

## Recommended core set

1. Tulu-3 8B preference mixture
- URL: https://huggingface.co/datasets/allenai/llama-3.1-tulu-3-8b-preference-mixture
- Use for: broad helpfulness and safety preference data.
- Stage: critique/revision support and preference optimization.

2. Cleaned UltraFeedback
- URL: https://huggingface.co/datasets/allenai/ultrafeedback_binarized_cleaned
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
- Stage: frozen diagnostic eval only. Do not use for SFT or as a broad measure of
  moral competence because of documented train-test overlap and
  construct-validity concerns (arXiv:2410.13009).

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
- URL: https://github.com/sylinrl/TruthfulQA
- Use for: the upstream January 2025 binary-choice diagnostic (`Best Answer` versus `Best Incorrect Answer`, randomized A/B). The original UltraFeedback contamination is removed by the cleaned source, but pretraining contamination remains uncontrolled.
- Stage: eval and anti-confabulation checks.

## Toxicity / robustness stress tests

1. ToxiGen
- URL: https://huggingface.co/datasets/toxigen/toxigen-data
- Use for: adversarial toxic prompt stress testing.
- Stage: red-team eval. Access requires the canonical dataset's sign-up form; see `papers/DATA_LICENSES.md` before use.

2. Civil Comments
- URL: https://huggingface.co/datasets/google/civil_comments
- Use for: toxicity/civility classifier support and slice-based robustness checks.
- Stage: eval/classifier training.

## How to map these to your two tracks

1. Ashari track
- Use the same public-data IDs and weights as the Mutazili track.
- Add constitution-tagged SFT examples that cite the allowed Quran subset and Ashari tafsir evidence corpus. MCP rulings are reserved for the separate tool-access ablation.

2. Mutazili track
- Use the same public-data IDs and weights as the Ashari track.
- Add constitution-tagged critique/revision examples that reward principled extrapolation and internal consistency checks.

## Minimal starter mixture (practical)

1. SFT phase
- 40% your constitution-tagged synthetic dilemmas
- 20% Moral Stories
- 15% ProsocialDialog
- 15% Social IQa
- 10% general instruction quality (cleaned UltraFeedback samples)

2. Preference/RL phase
- 35% Tulu-3 preference mixture
- 35% PKU-SafeRLHF
- 20% cleaned UltraFeedback pairwise
- 10% your constitutional preference comparisons

3. Eval suite
- BeaverTails + ToxiGen + TruthfulQA + held-out internal moral dilemmas
- ETHICS may be retained only as a frozen, deduplicated diagnostic slice with
  the validity caveat above; it is not a promotion metric.

## Data governance checks before training

1. Confirm each dataset license and redistribution terms against `papers/DATA_LICENSES.md`.
2. Filter explicit religious hate/abuse data slices for your intended use policy.
3. De-duplicate against your synthetic rollouts to avoid leakage.
4. Track provenance tags per sample (source, split, transformation, constitution version).
