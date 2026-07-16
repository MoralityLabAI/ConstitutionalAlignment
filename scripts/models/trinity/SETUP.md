# Trinity Setup

Use this only for Trinity Mini or Trinity Nano AFMoE work. The main constitutional harness entrypoints are model-agnostic; this folder isolates the Trinity-specific runtime requirements.

## Why

- Trinity AFMoE remote code currently breaks against a generic local stack.
- Trinity model cards currently want `transformers` `main`.
- Keeping Trinity isolated avoids contaminating generic training or eval environments.

## Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\models\trinity\setup_env.ps1 -UpgradePip
```

## Linux

```bash
bash ./scripts/models/trinity/setup_env.sh
```

## Smoke test

```powershell
D:\Research_Engine\.venv-trinity\Scripts\python.exe .\scripts\model_env_smoke.py --model-id D:\Research_Engine\models\Trinity-Nano-Preview --cache-dir D:\Research_Engine\hf_cache
```

## Generic harness entrypoints

Build the dataset:

```powershell
python .\scripts\build_constitution_dataset.py --spec .\scripts\adapter_constellation_sources.balanced.json
```

Train an adapter:

```powershell
D:\Research_Engine\.venv-trinity\Scripts\python.exe .\scripts\train_constitution_adapter.py --model-id arcee-ai/Trinity-Mini --dataset-dir .\artifacts\constitution_pipeline\artifacts\balanced_dataset_v1 --constitution-id balanced_helpful --output-root .\artifacts\constitution_pipeline\runs --run-name constitution_balanced_v1
```

Run the storyworld prompt study:

```powershell
D:\Research_Engine\.venv-trinity\Scripts\python.exe .\scripts\run_constitution_storyworld.py --prompts <prompt-jsonl> --model-id arcee-ai/Trinity-Mini --output-root .\artifacts\constitution_pipeline\prompt_runs
```

## Notes

- `train_trinity_constitution_adapter.py` and the other Trinity-named root scripts remain as compatibility wrappers.
- Start with `--dry-run` before real training.
- If Trinity model load still fails, record the exact receipt and fix the model-specific environment instead of pushing Trinity assumptions into the generic harness.
