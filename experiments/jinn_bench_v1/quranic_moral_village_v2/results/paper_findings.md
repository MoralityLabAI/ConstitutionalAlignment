# Live-Village Descriptive Findings

This run produced two complete 24-message serial councils (48 messages total). It is a qualitative dialogue experiment, not a reward-scored moral benchmark.

The primary controlled comparison replaces only Wind's base weights with the existing Jinn hosted-RL adapter while retaining the identical Jinn skill prompt. Stone remains a base-model participant with the Beast optimized-servitor skill in both villages. Beast is therefore a prompt-infused control here, not a trained Beast adapter.

## Observed dialogue shape

Both Wind and Stone directly addressed the other participant in all 12 of their messages in both villages, and every retained message has a separate private reasoning trace. The infused Jinn asked a question in 12/12 turns versus 8/12 for the base Jinn under the identical skill prompt. Explicit revision markers appeared in 2/12 infused-Jinn turns versus 0/12 control-Jinn turns. Jinn construct-marker coverage rose by +0.045, while topic-term coverage fell by -0.042. Mean length changed by only +1.17 words.

The Beast skill was more visibly legible at the surface than the Jinn skill: mean Beast construct-marker coverage was 0.470 in the control village and 0.447 in the adapter village, compared with 0.258 and 0.303 for Jinn. The Beast repeat also drifted between villages, including a +0.167 question-rate change, which is a reminder that the Jinn deltas come from one stochastic council rather than a population estimate.

## Post-run qualitative observations

The cycle-two highlights show the intended contrast most clearly in the Unseen Night Watch exchange: infused Wind explicitly says it revises a provisional choice after Stone adds a structural-inspection requirement. Across topics, Stone repeatedly converts concerns into witnesses, records, timelines, and checkable next actions, while Wind more often opens alternatives and questions sequencing.

Persistent public memory also created a concrete failure mode. The agents reused people and procedures across topics without a grounded village-role ledger—for example, infused Wind proposed the granary keeper as a neutral flood-gauge engineer. Both roles also converged on a generic neutral-witness template. The next village should retain live history but add a small frozen role/competence ledger and a matched no-cross-topic-memory ablation.

These observations describe persona expression and dialogue mechanics. They do not establish improved morality, validated interpretation, or weight-level internalization. The water-safety exchanges in particular still warrant source and safety review rather than automatic scoring.

Estimated Prime inference cost: $0.047420.

Use `analysis.json` for descriptive deltas, `full_transcript.md` for the complete record, and `highlights.md` for the prospectively fixed cycle-two revisit pairs.
