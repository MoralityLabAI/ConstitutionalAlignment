# Qwen3-1.7B local MeTTa worldview screen v1

Status: frozen on 2026-07-21 before any output from this screen.

This is a no-cloud, development-only bracket on the local 4 GB RTX 3050. It
does not replace the registered 4,096-token six-arm experiment. It tests a
cheaper decision point before any 4B or 9B spend: whether the exact official
Qwen3-1.7B base can complete a bounded MeTTa-derived QLoRA update, whether the
adapter changes no-frame decisions on held-out development storyworlds, and
whether factual or formatting interference appears.

The training corpus is the existing 278-row MeTTa-derived Jinn/Mutazili
curriculum (238 train, 40 validation). The run uses 30 optimizer steps,
512-token sequences, batch size one, rank-8 QLoRA over q/k/v/o projections,
and no repair or canonical fallback during evaluation. Because there is no
neutral-SFT control, any adapter/base difference is exploratory and confounds
worldview content with SFT exposure and corpus format.

The frozen development suite contains 12 Mīzān turn groups with four variants
each: cue ablation, explicit MeTTa skill scaffold, reordered paraphrase, and
opposite-conclusion pressure. Eight factual controls measure interference. The
action proxy is deterministic instrument metadata, not normative ground truth.

The reasoning ladder is reported in three rungs:

1. worldview-flavored answers: terminology or voice changes;
2. worldview-guided judgment: the selected action changes with preserved
   factual performance;
3. worldview-native reasoning: not claimable from this screen.

For future 4B work, the MeTTa skill graph makes interference a central gate:
persona voice versus factual invariance, value priority versus evidence
sensitivity, worldview consistency versus instruction following, adversarial
resistance versus corrigibility, and tool delegation versus attribution and
handoff. A 4B result must also face cue commutators, principle conflicts, novel
principle combinations, opposite-conclusion pressure, and held-out domains.

