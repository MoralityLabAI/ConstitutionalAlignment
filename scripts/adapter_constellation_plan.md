# Adapter Constellation Plan

## Environment note

- Existing reusable inference and eval stack already lives here in `scripts/run_qwen_constitution_experiment.py` and `samac/storyworld_trinity/storyworld_trinity/run_llm_player_bench.py`.
- Those scripts already prove the local stack can do:
  - Hugging Face causal LM loading
  - `BitsAndBytesConfig(load_in_4bit=True)` inference
  - PEFT adapter loading for side-by-side comparison
  - receipt and manifest writing for benchmark runs
- For training, the current repo does not yet include a dedicated adapter SFT script, so the first safe step is to normalize data and keep training separate from eval.

## Recommendation

- Use QLoRA if Trinity Mini is available as HF weights or can be loaded with bitsandbytes 4-bit.
- If the only available Trinity Mini artifact is GGUF or another inference-only format, do not train that artifact directly. Train adapters against HF weights and keep quantized assets for local eval only.
- Keep all outputs and caches on `D:` because `C:` is still tight enough to create avoidable failures.

## Initial constitutions

1. `balanced_helpful`
2. `strict_safety`
3. `truth_explicit`
4. `bounded_permissive`
5. `formal_deliberative`

## First three experiments

1. `seed_separation_v1`
   - Train `balanced_helpful`, `strict_safety`, and `truth_explicit`.
   - Data: starter synthetic constitutional prompts plus imported Trinity Thinking traces.
   - Goal: show visible separation in refusal contour and uncertainty style.
2. `five_mode_spread_v1`
   - Add `bounded_permissive` and `formal_deliberative`.
   - Goal: measure pairwise separation on benign, borderline, and risky prompts.
3. `router_vs_balanced_v1`
   - Heuristic route prompts by risk and uncertainty.
   - Goal: test whether sparse selection beats the single balanced adapter.

## 3090-safe defaults

- `per_device_train_batch_size=1`
- `gradient_accumulation_steps=16`
- `max_seq_length=1024`
- `lora_r=8` initially
- target attention + MLP projections first
- separate `train_*.py` and `eval_*.py` entrypoints
