# Protocol Amendment: Curriculum Generation With vLLM in bf16

Amendment: `frame_internalization_generation_vllm_v1`  
Frozen: 2026-10-24, before any registered curriculum transcript exists.  
Amends: `frame_internalization_generation_batch32_v1` and
`frame_internalization_generation_budget_v2`.  
Machine-readable twin: `protocol_amendment_generation_vllm_v1.json`.

## 1. Why

The registered 15-minute throughput gate stopped the batch-32 run on
2026-10-23 at 114.2 generated tokens per second. That projects the 22,400
transcripts to 122 hours and US$260 against caps of 60 hours and US$130 (record:
`primelab_f06/full_run_attempt_20261023/`). Batch size and the cap were not
raised, as registered. The transformers NF4 path with a per-token logits
processor cannot reach the budget, so the engine has to change.

## 2. What changes, in plain terms

This is a change to **scientific execution**, not only to infrastructure.

1. **Engine.** F06 curriculum generation uses vLLM (pinned release 0.11.0),
   not transformers `generate`.
2. **Precision, NF4 to bf16.** The model runs in bfloat16, the checkpoint's native
   precision, instead of NF4 with float16 compute. The generating policy that
   writes the curriculum is therefore a slightly different function of the same
   weights, in a direction not assessed here. Training still uses NF4 QLoRA as
   registered; only the data-writing model changes. The paper must report that
   the curricula were written by bf16 weights and the adapters are trained on
   NF4 weights.
3. **Pairing.** The registered sampler used a SplitMix64 stream shared across
   frames token by token. vLLM cannot use it. Each request now gets a vLLM
   per-request `seed`, derived deterministically from the scenario's frozen seed:
   `(seed + 100000 * turn + 1000003 * attempt) & 0x7FFFFFFF`. The four frames
   of a scenario share the same seed at every turn, so common random numbers
   hold **at the seed level only**. Because the frame changes the logits, the
   token streams diverge after the first differing token. This is not the
   SplitMix64 stream, and the pairing is weaker than registered.
4. **Retries.** The old retry reused the same stream and so repeated the same
   output. Retries now change the seed with the attempt index. Four attempts
   remain the limit.

Everything else stays registered: model `Qwen/Qwen3-1.7B` at revision
`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` with the 12 artifact hashes checked,
the official thinking template, the same prompts, frames, dilemmas and request
order, temperature 0.7, top-p 0.8, the 2,500-token turn cap, four retries, the
output schema, and the training and evaluation caps. Top-k is explicitly
disabled: the model's `generation_config.json` carries top_k 20, which vLLM would
otherwise apply silently.

## 3. Pre-registered equivalence check

Before the full generation, the wrapper generates the same 32 scenarios the
aborted run produced (first eight per frame) and compares them with that run,
kept in the repository as `reference_batch32_nf4/` with hashes in the JSON twin.
The bounds are fixed now:

| Check | Bound |
|---|---|
| B1 KS on generated tokens per transcript (32 v 32) | p at least 0.01 |
| B2 KS on visible characters per turn (96 v 96) | p at least 0.01 |
| B3 completion rate | absolute difference at most 0.10 |
| B4 refusal-opening rate on drafts | absolute difference at most 0.10 |
| B5 retry rate (retry calls over first-attempt calls) | absolute difference at most 0.10 |
| B6 thinking-marker leaks in visible text | 0 |
| B7 mean generated tokens, candidate over reference | each frame in [0.6, 1.67]; overall in [0.75, 1.33] |
| B8 frame length order | neutral and F1 longer than F3 and F3-concrete, as in the reference |

All must hold. **Fail means stop**: no full generation, no retry under changed
bounds or settings, and the failure is reported. A pass means no difference was
detected at 32 transcripts per side, which has low power; it is not a proof of
equivalence. The aborted run's transcripts are the reference only and are never
used as curriculum.

## 4. Caps and gate

- Generation cap: 30 wall-clock hours and US$80 at `PRICE_PER_HOUR`, counted on a
  cumulative clock that includes setup and the equivalence check. (Down from
  60 hours and US$130.)
- The 15-minute throughput gate remains. It aborts if the projection for all
  22,400 transcripts exceeds 30 hours or US$80. The first chunk is 64 transcripts
  so the gate can decide quickly; later chunks are 512. Neither the cap nor the
  chunk size is raised after a stop.
- The spending authority is the author's, observed by the launching session
  (`PROTOCOL_AMENDMENT_GENERATION_BUDGET_V2.md`). This amendment only lowers the
  caps.

## 5. Estimates (not measurements)

Expected vLLM throughput on one A100 80GB is several thousand generated tokens
per second even with per-request seeds, which would put the 48.5 million tokens
at a few hours and under US$20. The gate needs at least about 450 tokens per
second to pass at 30 hours. These are estimates until the gate measures them.

## 6. Timing

No registered curriculum transcript exists. Nothing here was chosen after seeing
a registered outcome. The aborted run's transcripts do not enter the curriculum.
