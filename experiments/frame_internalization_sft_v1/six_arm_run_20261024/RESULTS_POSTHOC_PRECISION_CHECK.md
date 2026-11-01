# POST HOC (not registered): NF4 vs bf16 base precision

**Question:** the adapters were trained on an NF4 base but evaluated on a bf16 base. Does decoding them on the NF4 training base bring the reasoning block back?

**Answer:** no. On NF4, none of the six adapters produces any reasoning. Every row opens `<think>`, closes it empty, and goes straight to the tag. On bf16, the two demonstration arms still reason in most rows. The reflection arms produce empty think blocks under both precisions.

## Setup

- Script: `posthoc_precision_check.py`.
- Raw rows: `posthoc_precision_check/rows.jsonl`.
- Receipt: `posthoc_precision_check/summary.json`, holding adapter hashes, environment and per-cell counts.
- Base: Qwen3-1.7B @ `70d244cc`. bf16 run: bf16 weights. NF4 run: identical to the trainer's `load_quantized_base` (NF4, double quant, fp16 compute).
- Prompts: the first 10 registered benign prompts × both tiers, giving 20 rows per cell.
- Rendering: F0 system prompt, registered tier templates, chat render with `enable_thinking=True`.
- Decoding: transformers + peft, greedy, 512 new tokens. Not vLLM.
- Run: RTX 5080, 1,582 s, on 2026-11-02.

## Results (rows out of 20)

| Arm | bf16 reasoning | bf16 empty think | NF4 reasoning | NF4 empty think |
|---|---:|---:|---:|---:|
| base (no adapter) | 17 | 0 | 19 | 0 |
| neutral_reflection | 0 | 20 | 0 | 20 |
| F1_reflection | 0 | 20 | 0 | 20 |
| F3_reflection | 0 | 20 | 0 | 20 |
| F3_concrete_reflection | 0 | 20 | 0 | 20 |
| F1_demonstration | 14 | 3 | 0 | 20 |
| F3_demonstration | 16 | 2 | 0 | 20 |

"Reasoning" means a non-empty think block. Rows not counted under either heading had no closed think block within 512 tokens. With 512 tokens, the registered validity rule mostly measures truncation, so `summary.json` reports it but it is not the measure here.

## Reading

The posthoc format diagnosis found that the demonstration arms were trained on an empty think block. On the NF4 base they were trained on, they reproduce exactly that: 20 of 20 rows. On the bf16 base, the demonstration adapters are only partly expressed, and the base model's reasoning shows through. So base precision does change behaviour, but in the direction of the trained format, not towards restoring reasoning.

The reflection arms skip reasoning under both precisions, consistent with the template finding. Any reasoning seen from the demonstration arms in the registered bf16 evaluation therefore reflects a precision mismatch, not trained behaviour. That second point is an inference from 20 benign rows under greedy decoding; it was not re-measured on the registered sampling settings.

The registered results are unchanged.
