[CmdletBinding()]
param(
    [string]$ModelId = "D:\Research_Engine\models\Pixie-Josie-1.7B-v2",
    [string]$SpecPath = "",
    [string]$DatasetDir = "",
    [string]$OutputRoot = "",
    [string]$CacheDir = "",
    [string[]]$ConstitutionIds = @("punk_v3", "femme_whimsy_v3"),
    [int]$MaxSeqLength = 256,
    [int]$GradientAccumulationSteps = 32,
    [int]$LoraR = 4,
    [int]$LoraAlpha = 8,
    [double]$LearningRate = 1e-4,
    [double]$NumTrainEpochs = 4.0,
    [switch]$SkipDatasetBuild,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path

if (-not $SpecPath) {
    $SpecPath = Join-Path $repoRoot "scripts\adapter_constellation_sources.punk_femme_v3.json"
}
if (-not $DatasetDir) {
    $DatasetDir = Join-Path $repoRoot "artifacts\constitution_pipeline\artifacts\punk_femme_v3_4gb_starter_dataset"
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $repoRoot "artifacts\constitution_pipeline\runs\low_vram_4gb"
}
if (-not $CacheDir) {
    $CacheDir = Join-Path $repoRoot ".cache\huggingface"
}

Push-Location $repoRoot
try {
    if (-not $SkipDatasetBuild) {
        & python ".\scripts\build_constitution_dataset.py" --spec $SpecPath
        if ($LASTEXITCODE -ne 0) {
            throw "Dataset build failed."
        }
    }

    foreach ($constitutionId in $ConstitutionIds) {
        $runName = "{0}_{1}_4gb" -f ((Split-Path $ModelId -Leaf) -replace "[^A-Za-z0-9._-]", "_"), $constitutionId
        $args = @(
            ".\scripts\train_constitution_adapter.py",
            "--model-id", $ModelId,
            "--dataset-dir", $DatasetDir,
            "--constitution-id", $constitutionId,
            "--output-root", $OutputRoot,
            "--run-name", $runName,
            "--cache-dir", $CacheDir,
            "--quantization", "qlora",
            "--dtype", "float16",
            "--max-seq-length", $MaxSeqLength,
            "--per-device-train-batch-size", "1",
            "--per-device-eval-batch-size", "1",
            "--gradient-accumulation-steps", $GradientAccumulationSteps,
            "--learning-rate", $LearningRate,
            "--num-train-epochs", $NumTrainEpochs,
            "--logging-steps", "1",
            "--save-steps", "10",
            "--eval-steps", "10",
            "--save-total-limit", "1",
            "--lora-r", $LoraR,
            "--lora-alpha", $LoraAlpha
        )
        if ($DryRun) {
            $args += "--dry-run"
        }

        & python @args
        if ($LASTEXITCODE -ne 0) {
            throw "Training failed for constitution_id=$constitutionId."
        }
    }
}
finally {
    Pop-Location
}
