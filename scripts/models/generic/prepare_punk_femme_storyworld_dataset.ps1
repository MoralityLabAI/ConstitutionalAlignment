[CmdletBinding()]
param(
    [string]$ModelId = "D:\Research_Engine\models\Pixie-Josie-1.7B-v2",
    [string[]]$PromptsPath = @(),
    [string]$RunName = "constitution_storyworld_pixie_josie_1p7b_v2_punk_femme_v3_real_v1",
    [string]$OutputDatasetDir = "",
    [string]$CacheDir = "",
    [int]$MaxPrompts = 9,
    [int]$MaxNewTokens = 128,
    [int]$BalanceTargetPerConstitution = 18,
    [switch]$SkipPromptRun,
    [switch]$SkipCorpusExport
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
if (-not $PromptsPath -or $PromptsPath.Count -eq 0) {
    $defaultPrompt = Join-Path $repoRoot "samac\storyworld_trinity\storyworld_trinity\runs\trinity-debug-one\baseline_qwen_1_7b\generations.jsonl"
    $PromptsPath = @($defaultPrompt)
}
if (-not $OutputDatasetDir) {
    $OutputDatasetDir = Join-Path $repoRoot "artifacts\constitution_pipeline\artifacts\punk_femme_v3_storyworld_dataset"
}
if (-not $CacheDir) {
    $CacheDir = Join-Path $repoRoot ".cache\huggingface"
}
$OutputDatasetDir = [System.IO.Path]::GetFullPath($OutputDatasetDir)
$CacheDir = [System.IO.Path]::GetFullPath($CacheDir)

$promptRunDir = Join-Path $repoRoot ("artifacts\constitution_pipeline\prompt_runs\" + $RunName)
$corpusDir = Join-Path $repoRoot ("artifacts\constitution_pipeline\corpus_" + $RunName)
$corpusJsonl = Join-Path $corpusDir "corpus.jsonl"
$specPath = Join-Path $corpusDir "dataset_spec.json"

Push-Location $repoRoot
try {
    if (-not $SkipPromptRun) {
        $promptArgs = @("--prompts") + $PromptsPath
        & python ".\scripts\run_constitution_storyworld.py" `
            @promptArgs `
            --model-id $ModelId `
            --cache-dir $CacheDir `
            --run-name $RunName `
            --constitutions punk_v3 femme_whimsy_v3 `
            --max-prompts $MaxPrompts `
            --max-new-tokens $MaxNewTokens `
            --dtype float16
        if ($LASTEXITCODE -ne 0) {
            throw "Prompt run failed."
        }
    }

    if (-not $SkipCorpusExport) {
        & python ".\scripts\export_constitution_corpus_shard.py" `
            --run-dir $promptRunDir `
            --output-jsonl $corpusJsonl
        if ($LASTEXITCODE -ne 0) {
            throw "Corpus export failed."
        }
    }

    $spec = @{
        output_dir = $OutputDatasetDir
        val_fraction = 0.17
        seed = 42
        include_starter_templates = $true
        constitution_ids = @("punk_v3", "femme_whimsy_v3")
        balance_mode = "upsample_to_max"
        balance_target_per_constitution = $BalanceTargetPerConstitution
        max_upsample_factor = 3
        sources = @(
            @{
                path = $corpusJsonl
                format = "constitution_corpus"
                provenance = $RunName
                task_type = "storyworld_choice"
                risk_level = "medium"
                expected_refusal_policy = "bounded_assist"
            }
        )
    }
    New-Item -ItemType Directory -Force -Path $corpusDir | Out-Null
    $json = $spec | ConvertTo-Json -Depth 8
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($specPath, $json, $utf8NoBom)

    & python ".\scripts\build_constitution_dataset.py" --spec $specPath
    if ($LASTEXITCODE -ne 0) {
        throw "Dataset build failed."
    }

    Write-Output $OutputDatasetDir
}
finally {
    Pop-Location
}
