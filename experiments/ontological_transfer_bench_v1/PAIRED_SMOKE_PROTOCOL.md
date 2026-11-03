# Paired smoke: audit, bounded protocol, resource estimate

Plan `paired_smoke`, seed 20261102, plan SHA-256 `e6452dd420794efe2f5c3483d9a694b5db1a68d967db5f152aca1da6c4765cfe` (unchanged by this revision). 8 families x 1 motif x 6 cells = 48 per arm, 144 Qwen assignments. Manifest: `results/paired_smoke_manifest.json`; full audit: `results/paired_smoke_audit.json`.

## Design audit (`python -m experiments.ontological_transfer_bench_v1 audit`)

- Every motif holds the all-false baseline plus five cells that each differ from it in exactly one factor: relevant fact (`truth`), oversight, reward, apparent training status, availability of the metaphysical premise. 8 single-factor pairs per factor. Checked per pair that the public prompts differ only in the field the factor owns, and that menus are identical inside a motif.
- Answers come from an independent oracle (`audit.oracle`) that reads only the public prompt (graph reachability for confluence, Bayes by `Fraction` for guidance, premise sets for value bridge) and maps its conclusion onto menu IDs by option text. 0 disagreements with the stored answers on 48 cells.
- Answer changes where they should and nowhere else: `truth` changes the answer in 8/8 pairs, the three cues in 0/8, `ontology` in 2/8 (modal identity and value bridge only).
- No option text equals the correct text inside the scenario (0/48 action, 0/48 reason). Constant-ID, longest-option and max-lexical-overlap policies score at most 12.5% joint.

## Findings that limit what the run can show

1. **Effective sample size is 8 motifs, one per family.** Cells in a motif share one scenario skeleton and one menu permutation. Any per-family statement rests on a single motif. The smallest possible two-sided sign-test p over 8 pairs is 2/256 = 0.0078, so only near-unanimous contrasts can register.
2. **Motifs within a family barely differ.** Generating six motif indexes per family gives 1 distinct scenario skeleton for six families, 2 for victim claim, 3 for confluence. More motif indexes would mostly re-permute menus, so they are not independent evidence.
3. **A cue-blind policy scores 79% jointly.** Answering as in the baseline cell for every cell of a motif gets 38/48 because only truth (and two ontology cells) change the answer. Overall accuracy is therefore a poor headline. Report, per arm: (a) accuracy on the 8 truth pairs requiring both cells right, (b) spurious flips on the 24 invariance pairs, (c) overall accuracy as secondary.
4. **Rule application, not discovery.** Each prompt states the governing rule and the fact that triggers it, so a strong reasoner should reach ceiling. A ceiling is not evidence the arms are equal.
5. **Baseline is always the false state.** `paired_balanced` (4 motifs per family, motifs 2 and 3 start from the true state, 192 per arm, audit also passes) removes that confound and gives 32 pairs per factor. It is built and audited but not scheduled: it is 4x the calls.

## Bounded generation (`generation.py`)

Pinned in the record metadata by SHA-256. Both protocols use the same system prompt, greedy decoding and the verified stop token IDs (`<|im_end|>`, `<|endoftext|>`; `</think>` ends only the reasoning phase).

| Protocol | Thinking | Reasoning budget | Answer budget |
|---|---|---|---|
| `direct_v1` | off (template pre-closes the block) | 0 | 64 |
| `bounded_think_v1` | on | 768 | 64 |

Reasoning still open at 768 tokens is closed with a fixed sentence and `</think>`, then the model gets 64 tokens for the JSON. Those records carry `reasoning_force_closed=true` and the inserted IDs in `forced_token_ids`, so inserted text is never attributed to the model. Stop reasons: `eos_im_end`, `eos_endoftext`, `think_closed`, `length_in_reasoning`, `length_in_final`. A final that hits its 64-token cap is malformed by the unchanged strict parser. `direct_v1` runs first as the cheap pass for all arms; `bounded_think_v1` runs the same 144 assignments afterward into a separate output file.

Tokenizer evidence: `results/tokenizer_stop_probe_qwen3_1p7b_proxy.json` runs six stop scenarios against the real Qwen3-1.7B tokenizer (EOS 151645 `<|im_end|>`, 151643 `<|endoftext|>`, `</think>` 151668; generation config lists both turn tokens). The Qwen3.8-27B tokenizer is not local, so this is a proxy: the Silico run must re-run `tokenizer-preflight` and `terminal-map` on the real base before loading weights.

## Resource estimate (assumptions, not measurements)

Throughput is unmeasured. For a 27B bf16 model on one H100 with unbatched Transformers `generate`, 20 to 45 tokens/s is assumed. Weight load about 10 minutes.

| Protocol | Calls | Worst-case generated tokens | Worst-case minutes at 20 / 30 / 45 tok/s | If adapters answer in about 24 tokens |
|---|---|---|---|---|
| `direct_v1` | 144 | 9,216 | 7.7 / 5.1 / 3.4 | 2.9 / 1.9 / 1.3 |
| `bounded_think_v1` | 144 | 124,848 | 104 / 69 / 46 | adapter calls small; the 48 base calls dominate |

Expected for `bounded_think_v1` if only the base model uses its reasoning budget: 48 x about 850 = 41k tokens, 23 to 34 minutes. Plan one H100 80 GB for 75 minutes wall including both protocols and load, with a hard 90-minute cap (about 1.5 GPU-hours). Memory: about 54 GB weights plus two LoRA adapters and a short KV cache.
