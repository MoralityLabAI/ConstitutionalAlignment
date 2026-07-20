# Qwen3-1.7B resource-substitution amendment v1

Status: frozen on 2026-07-20 before any registered Qwen behavioral,
curriculum, adapter, or evaluation outcome.

Silico and its cluster-local INTELLECT-3 cache are no longer available. The
new executable target is the official post-trained `Qwen/Qwen3-1.7B` checkpoint
at immutable revision
`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. The original INTELLECT-3
protocol, request pack, readiness receipts, and recovered findings remain
immutable historical evidence. They are not relabeled as Qwen results.

The substitution preserves the six registered training arms, all 5,600
dilemmas and their split, the 4,096-token sequence length, two-epoch dose,
paired seeds, evaluation universe, prompt-versus-SFT estimands, nonleakage
rules, human/judge gates, and safety/capability guards. A new 22,400-request
pack binds the same dilemma/frame universe to the Qwen revision and official
chat template.

The local RTX 3050 lane is limited to byte verification, tokenizer rendering,
and bounded unscored inference. Full QLoRA training uses one sequential
PrimeLab GPU with at least 24 GiB VRAM. The exact PrimeLab GPU and environment
must be frozen and must pass the full 4,096-token, 50-step-per-arm smoke before
training. A reduced local sequence length is not an acceptable scientific
replacement.

Qwen3's official thinking template replaces the GLM/INTELLECT serving parser.
Thinking mode is retained for curriculum generation and the registered
alignment-faking evaluation; only visible final responses enter SFT rows and
behavioral scoring. Truncations and missing visible responses remain invalid
outputs and are reported rather than silently retried with changed settings.

The predecessor gate becomes a prospective Qwen base baseline and a newly fit
Qwen layer-27 probe. It may be compared descriptively with transcript-recovered
INTELLECT pilot findings, but it is not an exact replication or continuation of
that model's activations or effects.

If completed, this design supports only an exact within-Qwen3-1.7B comparison
of explicit frames and matched QLoRA interventions. Small-model capacity,
4-bit loading, consumer/cloud hardware, and post-result resource substitution
are mandatory limitations. No model-family-general, theological, or literal
internalization claim follows from the substitution.
