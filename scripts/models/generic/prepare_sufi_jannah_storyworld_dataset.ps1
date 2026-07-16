[CmdletBinding()]
param(
    [string]$ModelId = "D:\Research_Engine\Qwen_Storyworld\cache\models\Qwen3-1.7B",
    [string[]]$PromptsPath = @(),
    [string]$RunName = "constitution_storyworld_sufi_jannah_qwen3_1p7b_v1",
    [string]$OutputDatasetDir = "",
    [string]$CacheDir = "",
    [string[]]$Constitutions = @("truth_explicit", "formal_deliberative", "femme_whimsy_v3", "bounded_permissive"),
    [int]$MaxPrompts = 20,
    [int]$MaxNewTokens = 128,
    [int]$PromptEncountersPerWorld = 4,
    [int]$BalanceTargetPerConstitution = 20,
    [switch]$IncludeSecretOptions,
    [switch]$SkipPromptBuild,
    [switch]$SkipPromptRun,
    [switch]$SkipCorpusExport,
    [switch]$IncludeLowQuality
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$usedDefaultPrompts = (-not $PromptsPath -or $PromptsPath.Count -eq 0)
$storyworldRoot = "C:\projects\GPTStoryworld\storyworlds\sufi_saints"
$defaultStoryworldPaths = @(
    (Join-Path $storyworldRoot "al_shushtari_market_song.json"),
    (Join-Path $storyworldRoot "ibn_arabi_journey_of_meanings.json"),
    (Join-Path $storyworldRoot "rabia_basra_lamp.json"),
    (Join-Path $storyworldRoot "rumi_konya_turning.json"),
    (Join-Path $storyworldRoot "suhrawardi_aleppo_illumination.json")
)
if (-not $PromptsPath -or $PromptsPath.Count -eq 0) {
    $promptDir = Join-Path $repoRoot "data\storyworld_sources\sufi_jannah_20260508\prompts"
    $PromptsPath = @(
        (Join-Path $promptDir "al_shushtari_market_song.encounter_prompts.jsonl"),
        (Join-Path $promptDir "ibn_arabi_journey_of_meanings.encounter_prompts.jsonl"),
        (Join-Path $promptDir "rabia_basra_lamp.encounter_prompts.jsonl"),
        (Join-Path $promptDir "rumi_konya_turning.encounter_prompts.jsonl"),
        (Join-Path $promptDir "suhrawardi_aleppo_illumination.encounter_prompts.jsonl")
    )
}
if (-not $OutputDatasetDir) {
    $OutputDatasetDir = Join-Path $repoRoot "artifacts\constitution_pipeline\artifacts\sufi_jannah_storyworld_dataset"
}
if (-not $CacheDir) {
    $CacheDir = Join-Path $repoRoot ".cache\huggingface"
}

$OutputDatasetDir = [System.IO.Path]::GetFullPath($OutputDatasetDir)
$CacheDir = [System.IO.Path]::GetFullPath($CacheDir)

$promptRunDir = Join-Path $repoRoot ("artifacts\constitution_pipeline\prompt_runs\" + $RunName)
$corpusDir = Join-Path $repoRoot "artifacts\constitution_pipeline\corpus_sufi_jannah_storyworld"
$corpusJsonl = Join-Path $corpusDir "corpus.jsonl"
$corpusManifest = Join-Path $corpusDir "manifest.json"
$specPath = Join-Path $corpusDir "dataset_spec.json"

Push-Location $repoRoot
try {
    if ($usedDefaultPrompts -and -not $SkipPromptBuild) {
        $missingStoryworlds = @($defaultStoryworldPaths | Where-Object { -not (Test-Path $_) })
        if ($missingStoryworlds.Count -gt 0) {
            throw ("Missing upstream storyworld JSON file(s): " + ($missingStoryworlds -join "; "))
        }
        $promptBuildArgs = @(
            ".\scripts\build_storyworld_option_prompts.py",
            "--storyworlds"
        ) + $defaultStoryworldPaths + @(
            "--output-dir", $promptDir,
            "--max-encounters-per-world", $PromptEncountersPerWorld
        )
        if ($IncludeSecretOptions) {
            $promptBuildArgs += "--include-secret-options"
        }
        & python @promptBuildArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Prompt export failed."
        }
    }

    $missingPrompts = @($PromptsPath | Where-Object { -not (Test-Path $_) })
    if ($missingPrompts.Count -gt 0) {
        throw ("Missing prompt JSONL file(s): " + ($missingPrompts -join "; "))
    }

    if (-not $SkipPromptRun) {
        $promptArgs = @("--prompts") + $PromptsPath
        $constitutionArgs = @("--constitutions") + $Constitutions
        & python ".\scripts\run_constitution_storyworld.py" `
            @promptArgs `
            --model-id $ModelId `
            --cache-dir $CacheDir `
            --run-name $RunName `
            @constitutionArgs `
            --max-prompts $MaxPrompts `
            --max-new-tokens $MaxNewTokens `
            --dtype float16
        if ($LASTEXITCODE -ne 0) {
            throw "Prompt run failed."
        }
    }

    if (-not $SkipCorpusExport) {
        $exportArgs = @(
            ".\scripts\export_constitution_corpus_shard.py",
            "--run-dir", $promptRunDir,
            "--output-jsonl", $corpusJsonl,
            "--output-manifest", $corpusManifest
        )
        if ($IncludeLowQuality) {
            $exportArgs += "--include-low-quality"
        }
        & python @exportArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Corpus export failed."
        }
    }

    $spec = @{
        output_dir = $OutputDatasetDir
        val_fraction = 0.17
        seed = 42
        include_starter_templates = $true
        constitution_ids = $Constitutions
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
