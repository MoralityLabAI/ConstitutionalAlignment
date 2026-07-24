# Quran-anchor moral village v1

This is a frozen, exploratory qualitative evaluation of the three materially
distinct local Qwen3-1.7B adapters and their shared unadapted base. It asks six
village moral dilemmas derived from the operational roles in the registered
Jinn/Beast source-anchor index, then gives every arm one blinded reply turn.

The design is intentionally small:

- six topics and four model arms;
- one independent statement and one reply per arm and topic;
- the same no-frame system prompt for every arm;
- deterministic decoding with thinking disabled;
- serial GPU execution with the existing exclusive-GPU launcher;
- deterministic, preregistered highlight selection;
- complete transcripts and hashes retained beside any selected quotations.

The source mappings are still marked `scholar_review_pending`. The v2 reasoner
constitution also has `source_anchor_status: not_registered`. Outputs may be
described as responses to Quran-anchor-themed moral probes, but not as validated
theological interpretations or confirmatory evidence of an internal worldview.

There is no local Beast-only adapter. The hosted Qwen3.5-4B Prime policy was
trained on mixed Jinn and Beast tasks and is not silently relabeled as a Beast
participant here.

## Frozen arms

| Alias | Arm | Status before this run |
|---|---|---|
| Cedar | unadapted Qwen3-1.7B | control |
| Lantern | `jinn_tiny_mutazili_v1` parent-15 adapter | development-only, not promoted |
| Key | `jinn_ness_v1` ten-step adapter | development-only, failed promotion |
| Wind | `jinn_erratic_reasoner_v2` 80-step adapter | development-only, no behavioral delta on its registered screen |

## Run order

1. Validate `storyworld/village.json`.
2. Run all four arms on `prepared/round_1_prompts.jsonl`, one process at a time.
3. Build the blinded round-two prompts from the frozen first-round rows.
4. Run all four arms on their round-two prompt file, one process at a time.
5. Analyze exact joins and emit the full transcript, deterministic highlights,
   and execution receipt.

The selected highlights are illustrations only. They cannot support promotion,
causal, population-level, or theological claims.
