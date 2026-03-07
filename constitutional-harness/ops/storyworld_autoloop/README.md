# Storyworld Constitutional Autoloop

This mirror keeps the constitutional-methodology side of the work visible inside `constitutional-harness` while the executable Python loop lives in `Adict`.

Use it when you want the constitutional harness repo to:

- launch a 3-5 iteration storyworld refinement loop,
- capture a receipt,
- document the run as a constitution-style self-improvement experiment,
- hand off the exact plan to a Mac queue or local operator.

The actual loop entrypoint is:

- `C:\projects\Adict\Adict\addict_probe_lab\addict_probe_lab\scripts\run_constitutional_autoloop.py`

The loop itself does:

1. primer storyworld plays
2. Addict lexica training
3. base vs adapter bench
4. transition-aware lens extrapolation
5. replay tensor export under `data/adapter_training/replay/repeat/`
6. optional short-context LoRA training command
7. repeat for 3-5 iterations

For unattended Windows-to-Mac training, use:

- `ops/queue_storyworld_iteration_mac.ps1`

That script reads the autoloop manifest, copies the replay JSONL dataset to `~/worker/datasets/...`, and enqueues a bounded MLX LoRA job with the current 2B-safe profile:

- 4-bit base
- batch size `1`
- grad accum `1`
- max seq length `256`
- gradient checkpointing on
- LoRA rank `8`
- LoRA alpha `16`
- target modules `q_proj,v_proj`
- last `8` layers adapted

This keeps the methodology aligned with constitutional-style data generation:

- critique and revision happen over scenario traces,
- the signal is multi-step moral reasoning under pressure,
- the next adapter is trained from those traces rather than from generic preference chatter.
