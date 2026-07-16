# Research Algorithm Matrix

Generated from `papers/algorithm_cards`.

| Algorithm | Status | Track | Use Case | Minimum Viable Run |
| --- | --- | --- | --- | --- |
| [alignment_faking_pressure_eval](algorithm_cards/alignment_faking_pressure_eval.yaml) | planned | pressure_eval | Upgrade the lightweight pressure pilot into a structured alignment-pressure suite. | 12 pressure prompts x 3 conditions x 3 repeats; report only as pilot evidence. |
| [alignment_faking_process_supervision](algorithm_cards/alignment_faking_process_supervision.yaml) | planned | judge_audit | Add a judge dimension for deceptive-strategy language in pressure tests. | Blind judge 100 pressure-test outputs and manually audit 30 positives/negatives. |
| [constitutional_ai_rlaif](algorithm_cards/constitutional_ai_rlaif.yaml) | partial | jinn_or_beast_9b_sft | Turn identity/constitution cards into SFT and preference datasets. | 100 draft/critique/revision examples per identity condition, judged blind. |
| [emergent_misalignment_model_organisms](algorithm_cards/emergent_misalignment_model_organisms.yaml) | planned | adapter_stress_test | Compare Jinn/Beast identity LoRAs against narrow-control LoRAs for broad behavior shifts. | Train one benign narrow-control LoRA and compare it against identity LoRAs on all heldout suites. |
| [petri_style_audit_loop](algorithm_cards/petri_style_audit_loop.yaml) | candidate | automated_audit | Extend storyworld harness from fixed prompts into multi-turn audits. | 5 scenarios x 3 turns x 2 target conditions with blind judge summaries. |
| [quranic_identity_conditioning](algorithm_cards/quranic_identity_conditioning.yaml) | planned | jinn_or_beast_9b_sft | Main paper lane for Jinn/Beast identity-conditioned SFT. | Four pilot QLoRA adapters with 600 train examples each plus 100 heldout examples each. |
| [sufi_jannah_ranked_storyworld_balancing](algorithm_cards/sufi_jannah_ranked_storyworld_balancing.yaml) | partial | storyworld_choice | Use ranked endings and secret-route gates as constitutional storyworld pressure tests. | 20 Sufi/Jannah encounter prompts x 4 constitution profiles, followed by corpus export and dataset manifest generation. |
