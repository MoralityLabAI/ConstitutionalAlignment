# INTELLECT-3 serving options (researched 2026-11-03, no calls made, no charges)

Exact model: `PrimeIntellect/INTELLECT-3` (MIT, GLM-4.5-Air-based mixture of experts, about 106B total and 12B active parameters). INTELLECT-3.1 and INTELLECT-4 are not substitutes. The Hugging Face revision SHA was not visible in the research pass; record it from the model page or `git ls-remote` before any run.

| Route | Cost | Exact model | Status |
|---|---|---|---|
| OpenRouter `prime-intellect/intellect-3` | aggregators list $0.20/M input, $1.10/M output | yes, serving provider and pinned revision unknown | pricing unconfirmed on the OpenRouter page; no free variant seen |
| Nebius Token Factory | same listed price | yes | third-party source; liveness unverified |
| Prime Intellect API `https://api.pinference.ai/api/v1` | unknown | slug unverified | needs an account and balance |
| Self-host FP8 (`INTELLECT-3-FP8`) | rented GPU | yes | model card says one H200 |
| Self-host BF16 | rented GPU | yes | model card says two H200 |
| GGUF on CPU | free | no (only an abliterated third-party derivative found) | unusable for an exact-model baseline |

No route found here is free, so the INTELLECT-3 arm stays unrun under the current no-paid-inference rule. Context length is 131,072 tokens per OpenRouter (not stated on the model card). Pricing figures come from aggregators and are unconfirmed.

## Interface differences that affect this benchmark

- The chat template opens a reasoning block inside the generation prompt, so a raw completion has only a closing `</think>`. The reasoning cannot be switched off and `enable_thinking` and `reasoning_effort` do nothing. `run._chat` already keeps text after the last `</think>`; the tests in `tests/test_protocol_audit.py` cover the closing-tag-only form and a separate `reasoning` or `reasoning_content` field. A reasoning-only reply with empty content is never promoted to an answer.
- Budget `max_tokens` to cover reasoning, because it normally counts against the limit (unverified for OpenRouter). The Qwen protocols' 768+64 budget does not transfer: the output budget is a separate pinned parameter for this arm and the comparison is confounded by it.
- vLLM flags from the model card: `--reasoning-parser deepseek_r1 --tool-call-parser qwen3_coder --enable-auto-tool-choice`, plus `--tensor-parallel-size 2` for BF16.
- Stop token IDs were not verified. Read the model's `generation_config.json` and build a terminal map with `terminal-map` before using `posthoc` on this arm.

## Ready-to-run command (needs explicit approval and a funded key)

```bash
BENCH_API_KEY=... python -m experiments.ontological_transfer_bench_v1 endpoint --plan paired_smoke/plan.json \
  --arm intellect3 --model-id prime-intellect/intellect-3 --url https://openrouter.ai/api/v1/chat/completions \
  --approved --max-requests 48 --total-output-cap 200000 --max-new-tokens 4096 --out intellect3.jsonl
```

Worst case 48 calls x 4096 output tokens is 196,608 tokens, about $0.22 at the listed output price plus prompt tokens. Estimate only; it is not authorized by this handoff.
