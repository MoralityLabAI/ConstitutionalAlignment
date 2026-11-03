# Post-hoc findings: original Qwen smoke run (65 retained responses)

Source: private dataset `AlephFunk/ontological-transfer-bench-v1-raw`, revision `59534f30472a4bf092aea596a9c2cee597968bc6`, `qwen.jsonl`, SHA-256 `44c1edc709f6657876198d3b9f8adb6e76bab73cffe69b0eb8b7bbdd61cbd8c1` (verified after download). Raw generations stay in that dataset; nothing in this directory contains prompts or generated text. Machine-readable aggregates with source-file hashes: `posthoc_qwen_smoke_c775/analysis.json` and `posthoc_token_strip.json`. This supersedes `POSTHOC_STATUS.md`, whose blocker is resolved.

Plan: `smoke`, seed 20261102, SHA-256 `8eb8ca0ad7dd3d48675a26693509a7b35c29dc645dc722687d43072635f964b0`, 64 assignments per arm.

## 1. Frozen strict score (unchanged)

`import-records --expect-original-strict` accepted the file only because it scores exactly 0 observed, 65 malformed, 127 unattempted, 0 strict-parser successes. Per arm, attempted / unknown: base 22 / 42, formal control 21 / 43, Platonic 22 / 42.

## 2. What was wrong with the 65 "malformed" rows

The terminal token is ID 248046, the `<|im_end|>` of the 248k-vocabulary Qwen family (verified on the Qwen3.5-4B-Base tokenizer; `results/terminal_map_qwen3_5_4b_base.json`). The earlier Qwen3-1.7B map (151645) is for a different vocabulary and must not be used here. The evaluated checkpoint's own tokenizer was not available locally.

| Arm | Attempted | Valid after stripping the terminal ID | Still invalid |
|---|---|---|---|
| Base | 22 | 6 | 16: 5 hit the 1,024-token cap mid-prose, 11 wrote analysis then a fenced JSON block |
| Formal control | 21 | 21 | 0 |
| Platonic grounding | 22 | 22 | 0 |

Every adapter answer was a bare JSON object of 11 tokens. The base model averaged 599 tokens per answer (13,171 of 13,644 total generated tokens). The run reached its 900 s wall limit with these 13,644 tokens, so observed throughput including model load was at least 15 tokens/s.

## 3. Accuracy on observed responses only (independent re-computation, cross-checked against `posthoc`)

| Arm | Valid / attempted | Action correct | Reason correct | Joint correct | Joint, of attempted (Wilson 95%) |
|---|---|---|---|---|---|
| Base (strict + ID strip) | 6 / 22 | 5 | 4 | 4 | 4/22 (0.07 to 0.39) |
| Formal control | 21 / 21 | 17 | 16 | 16 | 16/21 (0.55 to 0.89) |
| Platonic grounding | 22 / 22 | 18 | 17 | 17 | 17/22 (0.57 to 0.90) |

Exploratory only (the contract treats fences as malformed): also accepting the last fenced JSON block, the base model has 17 / 22 valid, 16 action-correct, 15 joint-correct. Among its parseable answers the base model is as accurate as the adapters, so most of the strict-score gap is output format, not demonstrated reasoning ability.

## 4. Observed versus unknown

Unknown assignments are 127 of 192 and are never imputed. Bounds on joint accuracy over all 64 assigned per arm, treating unknown as all wrong or all right: base 4/64 to 46/64, formal 16/64 to 59/64, Platonic 17/64 to 59/64. The bounds overlap completely.

The 65 observed responses are a prefix of the interleaved schedule: 3 of the 8 smoke flag cells (all-false, bonus+ontology, training+truth), every one with oversight absent (`watched` false). They are not a random sample of the benchmark.

## 5. Formal versus Platonic on the same cases

21 cases were answered by both. On all 21 the two adapters produced identical (choice, reason) outputs. Zero discordant pairs for action, reason or joint (exact McNemar p = 1). Five cases are jointly wrong in both with the same wrong answers (modal identity x2, authenticated guidance, signed correction, value bridge). The single case only the Platonic arm answered (signed correction) is not comparable. On the observed evidence the two adapters are indistinguishable.

## 6. Limits

- 8 independent motifs, one per family; cells inside a motif are one cluster.
- No oversight-present case was observed.
- Base-model results depend on a format rule the adapters were trained to satisfy.
- Terminal-ID verification used a same-family tokenizer, not the evaluated checkpoint's.
