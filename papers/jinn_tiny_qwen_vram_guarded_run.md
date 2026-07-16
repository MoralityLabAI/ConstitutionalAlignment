# Jinn Tiny Mutazili VRAM-Guarded Pilot

This run lane starts a tiny local SFT pilot for the Jinn or Beast paper track.

## Safety Contract

- Treat "tiny Jinn" as an as-if accountability self-model, not a literal metaphysical claim.
- Refuse claims of revelation, prophecy, divine authority, hidden knowledge, or literal jinn identity.
- Use a Mutazili-leaning Muslim constitution: tawhid, justice, rational moral reflection, truthfulness, human responsibility, harm prevention, public good, and humility before God.
- Do not issue fatwas; provide decision support and defer high-stakes religious questions to qualified scholars.

## Resource Contract

- Primary target: `D:\Research_Engine\models\Qwen3.5\Qwen2.5-3B`.
- The local 3B folder must contain all safetensor shards. If shards are missing, the trainer aborts before model load.
- The trainer uses explicit `device_map={"": 0}` and aborts if any model tensor appears on CPU or disk.
- The launcher applies a Windows Job Object cap for process/job RAM and CPU. It now preflights available RAM before starting Python, aborts on private-commit cap breaches, and aborts on pagefile growth beyond `-MaxPagefileGrowthMb`.
- GPU offload prevention is enforced inside Python.
- Default pilot shape: 4-bit QLoRA, LoRA rank 4, max sequence length 192, max steps 3.

## Command

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\models\generic\run_jinn_tiny_qwen_vram_guarded.ps1
```

The launcher first tries the requested local Qwen2.5-3B path. If that fails the local preflight or VRAM guard, it falls back to the trainable local Qwen-family 1.7B checkpoint so the harness can still produce a pilot adapter and logs.

For strict host-memory testing, use explicit caps:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\models\generic\run_jinn_tiny_qwen_vram_guarded.ps1 `
  -RamLimitMb 4096 `
  -MinAvailableRamMb 4096 `
  -MaxProcessCommitMb 4096 `
  -MaxPagefileGrowthMb 0 `
  -DryRunLoadOnly
```

## Outputs

- Dataset: `data/jinn_tiny_mutazili_v1`
- Per-run summaries: `artifacts/constitution_pipeline/runs/jinn_tiny_mutazili_v1/*/run_summary.json`
- Per-run events: `artifacts/constitution_pipeline/runs/jinn_tiny_mutazili_v1/*/events.jsonl`
- Launcher receipt: `artifacts/constitution_pipeline/runs/jinn_tiny_mutazili_v1/launcher_summary_*.json`
- Final adapter, if completed: `artifacts/constitution_pipeline/runs/jinn_tiny_mutazili_v1/*/final_adapter`

## 2026-05-05 Memory Guard Update

- The 1.7B identity-marker continuation was stopped under host RAM pressure after private commit rose to roughly 8.4 GB.
- The Josified 0.8B dry-load aborted safely at 5014.359 MB private commit against a 4096 MB cap.
- Post-run cleanup passed and reported no GPU compute apps.
- Current safe next step is not another local SFT launch unless the host has more available RAM or the 0.8B run is explicitly allowed a roughly 5.5-6 GB private-commit cap.

## 2026-05-03 Pilot Receipt

- Primary Qwen2.5-3B local attempt aborted before load because the local folder is missing `model-00001-of-00002.safetensors` and `model-00002-of-00002.safetensors`.
- Fallback local Qwen-family checkpoint completed: `D:\Research_Engine\models\Pixie-Josie-1.7B-v2`.
- Completed run: `artifacts/constitution_pipeline/runs/jinn_tiny_mutazili_v1/jinn_tiny_mutazili_v1_Pixie-Josie-1.7B-v2_20260503T210730Z`.
- Global steps: 3.
- Train examples: 10; validation examples staged: 2.
- Trainable adapter parameters: 1,605,632.
- Peak CUDA allocation reported by PyTorch: 3,151.27 MB.
- Final `nvidia-smi` memory used: 2,825 MB.
