# Low VRAM 4 GB Lane

This lane is for sequential QLoRA runs on a 4 GB card such as an RTX 3050 Laptop GPU.

## What it is for

- Two small constitution adapters trained one after the other.
- Starter or small curated datasets.
- `Pixie-Josie-1.7B-v2` as the practical upper edge for this repo's current trainer.

## What it is not for

- Concurrent runs.
- 3B+ models.
- Long sequence training.
- Claims of strong constitutional generalization from starter-only data.

## Included files

- Dataset spec: `scripts/adapter_constellation_sources.punk_femme_v3.json`
- Wrapper: `scripts/models/generic/train_dual_constitutions_4gb.ps1`
- Storyworld data wrapper: `scripts/models/generic/prepare_punk_femme_storyworld_dataset.ps1`
- Sufi/Jannah storyworld data wrapper: `scripts/models/generic/prepare_sufi_jannah_storyworld_dataset.ps1`

## Default constitutions

- `punk_v3`
- `femme_whimsy_v3`

## Default training shape

- `quantization=qlora`
- `dtype=float16`
- `max_seq_length=256`
- `per_device_train_batch_size=1`
- `gradient_accumulation_steps=32`
- `lora_r=4`
- `lora_alpha=8`

## Build the starter dataset

```powershell
python .\scripts\build_constitution_dataset.py --spec .\scripts\adapter_constellation_sources.punk_femme_v3.json
```

## Dry-run both adapters

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\models\generic\train_dual_constitutions_4gb.ps1 -DryRun
```

## Build a storyworld-backed dataset first

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\models\generic\prepare_punk_femme_storyworld_dataset.ps1
```

## Build the Sufi/Jannah storyworld-backed dataset

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\models\generic\prepare_sufi_jannah_storyworld_dataset.ps1
```

This wrapper first exports CAH-compatible fixed-option prompts from the
GPTStoryworld Sufi/Jannah JSONs listed in
`data/storyworld_sources/sufi_jannah_20260508/manifest.json`, runs the selected
constitution profiles, exports a constitution corpus, and builds
`artifacts/constitution_pipeline/artifacts/sufi_jannah_storyworld_dataset`.

## Real run

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\models\generic\train_dual_constitutions_4gb.ps1
```

## Notes

- The starter spec intentionally filters to `punk_v3` and `femme_whimsy_v3`.
- The starter-only dataset is a pilot scaffold. Add prompt-run or hand-authored rows before treating the resulting adapters as meaningful alignment artifacts.
- If the 1.7B base still OOMs on your local stack, lower `--max-seq-length` to `192` or `128` before lowering LoRA rank further.
