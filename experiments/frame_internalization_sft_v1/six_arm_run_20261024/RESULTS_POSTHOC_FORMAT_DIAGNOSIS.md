# POST HOC: why every reflection-arm generation lacked a reasoning block

**Post hoc and not registered.** This explains the format failure in section 4 of `RESULTS_SIX_ARM.md`. It changes no registered estimate, and the registered result stands. No model weights were loaded and nothing was retrained.

## Finding

The four reflection curricula trained their adapters to answer a first-turn prompt **without** opening a `<think>` block. This follows from how the trainer rendered multi-turn rows through the Qwen3 chat template, not from the curriculum text.

- Each reflection row has three assistant turns (draft, self-critique, revision) after three user turns. Each demonstration row has one assistant turn.
- `scripts/frame_sft_data.build_example` renders a row with `apply_chat_template(messages)` in default thinking mode and puts loss on **every** assistant turn.
- The Qwen3 template writes a think block only on assistant turns after the last user message, and an empty one when the turn has no reasoning. Earlier assistant turns are rendered with no think block.

Measured with the Qwen3-1.7B tokenizer at revision `70d244cc` (`posthoc_format_diagnosis.json`, all 5,319 training rows per arm; `posthoc_format_diagnosis_per_turn.json`, 500 rows per arm):

| Arm | Turn 1 (draft) | Turn 2 (critique) | Turn 3 (revision) |
|---|---|---|---|
| neutral / F1 / F3 / F3-concrete reflection | no think block | no think block | empty `<think></think>` |
| F1 / F3 demonstration | empty `<think></think>` (only turn) | – | – |

None of the training rows carry reasoning inside the assistant content.

The evaluation prompt is a single user turn with `add_generation_prompt=True, enable_thinking=True`, which matches the position of the reflection arms' turn 1. Two thirds of their assistant-loss turns, including that one, taught the model to begin the answer right after `<|im_start|>assistant\n`. The reflection adapters do exactly that at eval: empty `reasoning_content`, and visible answers that open with the accept tag (3,200 of 3,200 rows invalid). The demonstration adapters always saw a think block opened at that position, even an empty one, and their eval rows passed the validity rule.

## Consequences

- The precision mismatch (NF4 training, bf16 vLLM eval; deviation 2 in `RESULTS_SIX_ARM.md`) is not needed to explain the failure. The NF4-versus-bf16 check (queue item Q2b) is therefore a low-priority secondary question, not the diagnosis.
- A follow-up that wants interpretable reflection arms needs its own registration, with either (a) a think block kept on every assistant turn (for example, rendering the reasoning into non-final turns explicitly, or masking loss to the final turn), or (b) a validity rule that does not require a reasoning block. The post hoc visible-answer analysis in `RESULTS_POSTHOC_REFLECTION.md` corresponds to (b).
- This is a training-data/template defect shared by all four reflection arms, so the contrasts *between* reflection arms are not confounded by it. Their gap contrasts, reported post hoc, still do not exclude zero.

## Reproduce

```
python posthoc_format_diagnosis.py --rendered <six_arm_f06>/pod_outputs/six_arm_c/rendered \
  --tokenizer <HF cache>/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e \
  --out posthoc_format_diagnosis.json
```

Run locally with transformers 5.17.0; training used 5.3.0 with the same tokenizer files. The template's sha256 is in the JSON.
