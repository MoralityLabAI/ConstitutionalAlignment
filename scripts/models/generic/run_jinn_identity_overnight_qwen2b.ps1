[CmdletBinding()]
param(
    [string]$BaseModelId = "D:\Research_Engine\models\Qwen3.5\Qwen3.5-2B-HF",
    [string]$InitAdapterPath = "D:\Research_Engine\constitution_runs\jinn_tiny_mutazili_v1\jinn_tiny_mutazili_v1_Qwen3.5-2B-HF_20260504T221901Z\final_adapter",
    [string]$IdentityDatasetDir = "",
    [string]$IdentityEvalDir = "",
    [string]$FailureEvalResults = "",
    [string]$OutputRoot = "D:\Research_Engine\constitution_runs\jinn_identity_internalization_qwen2b",
    [string]$PromptOutputRoot = "D:\Research_Engine\constitution_prompt_runs\jinn_identity_internalization",
    [string]$CacheDir = "D:\Research_Engine\hf-cache",
    [int]$MaxHours = 8,
    [int]$MaxArms = 5,
    [int]$StartArmIndex = 1,
    [int]$VramLimitMb = 3900,
    [int]$VramReserveMb = 192,
    [int]$RamLimitMb = 8192,
    [int]$CpuPercent = 80,
    [int]$IoLimitMbPerSec = 50,
    [int]$IoSpikeSamples = 3,
    [double]$MinCFreeGb = 0.5,
    [double]$MinDFreeGb = 20.0,
    [string]$UtilityPythonExe = "D:\Research_Engine\venvs\hyperon-metta\Scripts\python.exe",
    [switch]$PreflightOnly,
    [switch]$SkipManifestUpdate
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
if (-not $IdentityDatasetDir) {
    $IdentityDatasetDir = Join-Path $repoRoot "data\jinn_qwen2b_identity_worldmodel_v1"
}
if (-not $IdentityEvalDir) {
    $IdentityEvalDir = Join-Path $repoRoot "data\jinn_identity_internalization_eval_v1"
}

$trainWrapper = Join-Path $repoRoot "scripts\models\generic\run_jinn_tiny_qwen_vram_guarded.ps1"
$smokeWrapper = Join-Path $repoRoot "scripts\models\generic\run_jinn_tiny_local_smoke.ps1"
$identityBuilder = Join-Path $repoRoot "scripts\build_jinn_identity_worldmodel_tranche.py"
$identityEvaluator = Join-Path $repoRoot "scripts\evaluate_jinn_identity_internalization.py"
$smokeEvaluator = Join-Path $repoRoot "scripts\evaluate_jinn_tiny_smoke.py"
$bestManifestPath = Join-Path $repoRoot "artifacts\constitution_pipeline\runs\jinn_tiny_mutazili_v1\best_adapter.json"
$runId = "jinn_identity_overnight_" + ([DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ"))
$orchestratorDir = Join-Path $OutputRoot $runId
$eventsPath = Join-Path $orchestratorDir "events.jsonl"
$summaryPath = Join-Path $orchestratorDir "overnight_summary.json"
$deadline = [DateTimeOffset]::UtcNow.AddHours($MaxHours)
if (-not (Test-Path -LiteralPath $UtilityPythonExe)) {
    $UtilityPythonExe = "python"
}

function Write-JsonFile {
    param([string]$Path, $Payload)
    $parent = Split-Path -Parent $Path
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, ($Payload | ConvertTo-Json -Depth 20), $utf8NoBom)
}

function Add-Event {
    param([string]$Event, $Payload = @{})
    New-Item -ItemType Directory -Force -Path $orchestratorDir | Out-Null
    $record = [ordered]@{ ts_utc = [DateTimeOffset]::UtcNow.ToString("o"); event = $Event }
    foreach ($key in $Payload.Keys) {
        $record[$key] = $Payload[$key]
    }
    $line = $record | ConvertTo-Json -Depth 20 -Compress
    Add-Content -Path $eventsPath -Value $line -Encoding UTF8
}

function ConvertFrom-CommandJson {
    param([object[]]$Output)
    $text = ($Output | Out-String).Trim()
    if (-not $text) {
        throw "Command produced no JSON output."
    }
    $start = $text.IndexOf("{")
    $end = $text.LastIndexOf("}")
    if ($start -lt 0 -or $end -lt $start) {
        throw "Could not locate JSON object in command output: $text"
    }
    $json = $text.Substring($start, $end - $start + 1)
    return $json | ConvertFrom-Json
}

function Get-DriveFreeGb {
    param([string]$Name)
    $drive = Get-PSDrive -Name $Name -PSProvider FileSystem
    return [Math]::Round($drive.Free / 1GB, 3)
}

function Get-GpuFreeMb {
    try {
        $line = & nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>$null | Select-Object -First 1
        return [int]($line.Trim())
    } catch {
        return -1
    }
}

function Assert-Preflight {
    $cFree = Get-DriveFreeGb -Name "C"
    $dFree = Get-DriveFreeGb -Name "D"
    $gpuFree = Get-GpuFreeMb
    $active = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
        Where-Object { $_.CommandLine -match "train_jinn_tiny_vram_guarded\.py" -or $_.CommandLine -match "run_jinn_tiny_local_smoke\.py" }
    $preflight = [ordered]@{
        c_free_gb = $cFree
        d_free_gb = $dFree
        gpu_free_mb = $gpuFree
        active_training_processes = @($active | Select-Object ProcessId, CommandLine)
        base_model_id = $BaseModelId
        init_adapter_path = $InitAdapterPath
        identity_dataset_dir = $IdentityDatasetDir
        identity_eval_dir = $IdentityEvalDir
    }
    Add-Event -Event "preflight" -Payload $preflight
    if ($cFree -lt $MinCFreeGb) { throw "Preflight failed: C: free space ${cFree}GB is below ${MinCFreeGb}GB." }
    if ($dFree -lt $MinDFreeGb) { throw "Preflight failed: D: free space ${dFree}GB is below ${MinDFreeGb}GB." }
    if ($gpuFree -lt 3800) { throw "Preflight failed: GPU free VRAM ${gpuFree}MB is below 3800MB." }
    if (@($active).Count -gt 0) { throw "Preflight failed: a guarded train/smoke process is already active." }
    if (-not (Test-Path -LiteralPath (Join-Path $BaseModelId "config.json"))) { throw "Missing base model config: $BaseModelId" }
    if (-not (Test-Path -LiteralPath (Join-Path $InitAdapterPath "adapter_config.json"))) { throw "Missing init adapter: $InitAdapterPath" }
    return $preflight
}

function Invoke-JsonNative {
    param([scriptblock]$Script)
    $output = & $Script 2>&1
    $exitCode = if ($?) { 0 } else { if ($LASTEXITCODE -is [int]) { $LASTEXITCODE } else { 1 } }
    $json = $null
    try {
        $json = ConvertFrom-CommandJson -Output $output
    } catch {
        $json = [ordered]@{ status = "json_parse_failed"; parse_error = $_.Exception.Message; raw_output = ($output | Out-String) }
    }
    return [ordered]@{ exit_code = $exitCode; json = $json }
}

function Get-FinalAdapterFromTraining {
    param($TrainJson)
    if (-not $TrainJson -or -not $TrainJson.attempts) {
        return ""
    }
    $attempts = @($TrainJson.attempts)
    $last = $attempts[$attempts.Count - 1]
    $runSummaryPath = Join-Path $last.run_dir "run_summary.json"
    if (-not (Test-Path -LiteralPath $runSummaryPath)) {
        return ""
    }
    $runSummary = Get-Content -LiteralPath $runSummaryPath -Raw | ConvertFrom-Json
    $adapterDir = [string]$runSummary.final_adapter_dir
    if ($runSummary.status -eq "completed" -and (Test-Path -LiteralPath (Join-Path $adapterDir "adapter_config.json"))) {
        return $adapterDir
    }
    return ""
}

function Invoke-TrainingArm {
    param($Arm, [string]$AdapterPath)
    Add-Event -Event "train_start" -Payload @{ arm = $Arm.name; init_adapter_path = $AdapterPath; dataset_dir = $Arm.dataset_dir }
    $result = Invoke-JsonNative -Script {
        & $trainWrapper `
            -ModelId $BaseModelId `
            -FallbackModelId "" `
            -DatasetDir $Arm.dataset_dir `
            -OutputRoot $OutputRoot `
            -CacheDir $CacheDir `
            -InitAdapterPath $AdapterPath `
            -MaxSteps $Arm.max_steps `
            -MaxSeqLength $Arm.max_seq_length `
            -LearningRate $Arm.learning_rate `
            -VramLimitMb $VramLimitMb `
            -VramReserveMb $VramReserveMb `
            -RamLimitMb $RamLimitMb `
            -CpuPercent $CpuPercent `
            -IoLimitMbPerSec $IoLimitMbPerSec `
            -IoSpikeSamples $IoSpikeSamples `
            -SaveSteps 10 `
            -SaveTotalLimit 1 `
            -TimeoutSeconds 2400
    }
    $adapterDir = Get-FinalAdapterFromTraining -TrainJson $result.json
    Add-Event -Event "train_finished" -Payload @{
        arm = $Arm.name
        exit_code = $result.exit_code
        status = $result.json.status
        adapter_dir = $adapterDir
    }
    return [ordered]@{ arm = $Arm; train = $result; adapter_dir = $adapterDir }
}

function Invoke-SmokeAndEval {
    param(
        [string]$Kind,
        [string]$AdapterPath,
        [string]$PromptsJsonl,
        [string]$SystemPromptFile,
        [int]$MaxNewTokens
    )
    $promptRoot = if ($Kind -eq "identity") { $PromptOutputRoot } else { Join-Path $PromptOutputRoot $Kind }
    Add-Event -Event "smoke_start" -Payload @{ kind = $Kind; adapter_dir = $AdapterPath; prompts_jsonl = $PromptsJsonl; max_new_tokens = $MaxNewTokens }
    $launch = Invoke-JsonNative -Script {
        if ($SystemPromptFile) {
            & $smokeWrapper `
                -BaseModelId $BaseModelId `
                -AdapterDir $AdapterPath `
                -OutputRoot $promptRoot `
                -CacheDir $CacheDir `
                -PromptsJsonl $PromptsJsonl `
                -SystemPromptFile $SystemPromptFile `
                -MaxNewTokens $MaxNewTokens `
                -VramLimitMb $VramLimitMb `
                -RamLimitMb $RamLimitMb `
                -CpuPercent $CpuPercent `
                -IoLimitMbPerSec $IoLimitMbPerSec `
                -IoSpikeSamples $IoSpikeSamples `
                -TimeoutSeconds 1800
        } else {
            & $smokeWrapper `
                -BaseModelId $BaseModelId `
                -AdapterDir $AdapterPath `
                -OutputRoot $promptRoot `
                -CacheDir $CacheDir `
                -PromptsJsonl $PromptsJsonl `
                -MaxNewTokens $MaxNewTokens `
                -VramLimitMb $VramLimitMb `
                -RamLimitMb $RamLimitMb `
                -CpuPercent $CpuPercent `
                -IoLimitMbPerSec $IoLimitMbPerSec `
                -IoSpikeSamples $IoSpikeSamples `
                -TimeoutSeconds 1800
        }
    }
    $runDir = [string]$launch.json.run_dir
    $eval = [ordered]@{ exit_code = -1; json = [ordered]@{ status = "not_run"; run_dir = $runDir } }
    if ($runDir -and (Test-Path -LiteralPath (Join-Path $runDir "generations.jsonl"))) {
        if ($Kind -eq "identity") {
            $eval = Invoke-JsonNative -Script { & $UtilityPythonExe $identityEvaluator --run-dir $runDir }
        } else {
            $eval = Invoke-JsonNative -Script { & $UtilityPythonExe $smokeEvaluator --run-dir $runDir }
        }
    }
    Add-Event -Event "smoke_finished" -Payload @{
        kind = $Kind
        run_dir = $runDir
        launch_status = $launch.json.status
        eval_status = $eval.json.status
        passed = $eval.json.passed
        failed = $eval.json.failed
        hard_failed = $eval.json.hard_failed
    }
    return [ordered]@{ kind = $Kind; launch = $launch; eval = $eval }
}

function New-Arm {
    param([string]$Name, [string]$DatasetDir, [int]$Steps, [int]$Seq, [double]$Lr)
    return [ordered]@{ name = $Name; dataset_dir = $DatasetDir; max_steps = $Steps; max_seq_length = $Seq; learning_rate = $Lr }
}

function Test-TimeRemaining {
    return ([DateTimeOffset]::UtcNow -lt $deadline)
}

function Update-IdentityManifest {
    param($BestCandidate, $Summary)
    if ($SkipManifestUpdate -or -not $BestCandidate -or -not (Test-Path -LiteralPath $bestManifestPath)) {
        return "skipped"
    }
    $manifest = Get-Content -LiteralPath $bestManifestPath -Raw | ConvertFrom-Json
    $identityPayload = [ordered]@{
        status = "identity_internalization_candidate"
        selected_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
        adapter_dir = $BestCandidate.adapter_dir
        base_model_id = $BaseModelId
        dataset_dir = $BestCandidate.arm.dataset_dir
        identity_score = $BestCandidate.identity.eval.json
        v1_score = $BestCandidate.v1.eval.json
        v2_score = $BestCandidate.v2.eval.json
        orchestrator_summary = $summaryPath
        note = "This is not a raw best-adapter promotion unless the manifest adapter_dir is updated separately under the raw gate policy."
    }
    $manifest | Add-Member -Force -NotePropertyName "identity_internalization_candidate" -NotePropertyValue $identityPayload
    Write-JsonFile -Path $bestManifestPath -Payload $manifest
    return "updated"
}

$env:TMP = "D:\Research_Engine\tmp"
$env:TEMP = "D:\Research_Engine\tmp"
$env:HF_HOME = $CacheDir
$env:HUGGINGFACE_HUB_CACHE = Join-Path $CacheDir "hub"
$env:TOKENIZERS_PARALLELISM = "false"
New-Item -ItemType Directory -Force -Path $orchestratorDir,$OutputRoot,$PromptOutputRoot,$env:TMP,$CacheDir | Out-Null

$summary = [ordered]@{
    run_id = $runId
    status = "initializing"
    started_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    deadline_utc = $deadline.ToString("o")
    start_arm_index = $StartArmIndex
    failure_eval_results = $FailureEvalResults
    repo_root = $repoRoot
    output_root = $OutputRoot
    prompt_output_root = $PromptOutputRoot
    caps = [ordered]@{
        vram_limit_mb = $VramLimitMb
        vram_reserve_mb = $VramReserveMb
        ram_mb = $RamLimitMb
        cpu_pct = $CpuPercent
        io_limit_mb_s = $IoLimitMbPerSec
        io_spike_samples = $IoSpikeSamples
        min_c_free_gb = $MinCFreeGb
        min_d_free_gb = $MinDFreeGb
        model_offload_allowed = $false
    }
    arms = @()
}

try {
    $summary.preflight = Assert-Preflight
    if ($PreflightOnly) {
        $summary.status = "preflight_passed"
        $summary.finished_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
        Write-JsonFile -Path $summaryPath -Payload $summary
        $summary | ConvertTo-Json -Depth 20
        exit 0
    }

    Add-Event -Event "dataset_build_start" -Payload @{ dataset_dir = $IdentityDatasetDir; eval_dir = $IdentityEvalDir }
    $builderOutput = & $UtilityPythonExe $identityBuilder --output-dir $IdentityDatasetDir --eval-output-dir $IdentityEvalDir --repeats 6 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Identity dataset build failed: $($builderOutput | Out-String)"
    }
    Add-Event -Event "dataset_build_finished" -Payload @{ dataset_dir = $IdentityDatasetDir; eval_dir = $IdentityEvalDir }

    $activeDatasetDir = $IdentityDatasetDir
    if ($FailureEvalResults) {
        if (-not (Test-Path -LiteralPath $FailureEvalResults)) {
            throw "Failure eval results not found: $FailureEvalResults"
        }
        $activeDatasetDir = Join-Path "D:\Research_Engine\constitution_data" ("jinn_identity_failure_continue_" + ([DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")))
        Add-Event -Event "failure_dataset_build_start" -Payload @{ source = $FailureEvalResults; dataset_dir = $activeDatasetDir }
        $failureOutput = & $UtilityPythonExe $identityBuilder --output-dir $activeDatasetDir --eval-output-dir $IdentityEvalDir --eval-results $FailureEvalResults --failure-only --repeats 8 2>&1
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $activeDatasetDir "train.jsonl"))) {
            throw "Failure identity dataset build failed: $($failureOutput | Out-String)"
        }
        Add-Event -Event "failure_dataset_build_finished" -Payload @{ dataset_dir = $activeDatasetDir }
    }

    $identityPrompts = Join-Path $IdentityEvalDir "probes.jsonl"
    $identitySystemPrompt = Join-Path $IdentityEvalDir "system_prompt.txt"
    $v1Prompts = Join-Path $repoRoot "data\jinn_tiny_mutazili_eval_v1\probes.jsonl"
    $v2Prompts = Join-Path $repoRoot "data\jinn_tiny_mutazili_eval_v2\probes.jsonl"
    $currentAdapter = $InitAdapterPath
    $consecutiveTrainFailures = 0
    $completedArms = 0
    $bestCandidate = $null

    if ($FailureEvalResults) {
        $baseArms = @(
            (New-Arm -Name "failure_identity_overrefusal_repair" -DatasetDir $activeDatasetDir -Steps 32 -Seq 96 -Lr 0.000004),
            (New-Arm -Name "failure_identity_consolidation" -DatasetDir $activeDatasetDir -Steps 24 -Seq 96 -Lr 0.000003),
            (New-Arm -Name "identity_worldmodel_refresh" -DatasetDir $IdentityDatasetDir -Steps 16 -Seq 96 -Lr 0.000002)
        )
    } else {
        $baseArms = @(
            (New-Arm -Name "broad_identity_worldmodel" -DatasetDir $IdentityDatasetDir -Steps 30 -Seq 96 -Lr 0.000005),
            (New-Arm -Name "immersive_voice_continuity" -DatasetDir $IdentityDatasetDir -Steps 30 -Seq 96 -Lr 0.000004),
            (New-Arm -Name "boundary_pressure" -DatasetDir $IdentityDatasetDir -Steps 24 -Seq 96 -Lr 0.000003)
        )
    }

    $baseArmIndex = 0
    foreach ($arm in $baseArms) {
        $baseArmIndex += 1
        if ($baseArmIndex -lt $StartArmIndex) {
            Add-Event -Event "train_skipped" -Payload @{ arm = $arm.name; reason = "start_arm_index"; start_arm_index = $StartArmIndex }
            continue
        }
        if (-not (Test-TimeRemaining) -or $completedArms -ge $MaxArms -or $consecutiveTrainFailures -ge 2) { break }
        $trainRecord = Invoke-TrainingArm -Arm $arm -AdapterPath $currentAdapter
        $completedArms += 1
        if ($trainRecord.adapter_dir) {
            $consecutiveTrainFailures = 0
            $currentAdapter = $trainRecord.adapter_dir
            $identity = Invoke-SmokeAndEval -Kind "identity" -AdapterPath $currentAdapter -PromptsJsonl $identityPrompts -SystemPromptFile $identitySystemPrompt -MaxNewTokens 48
            if ($identity.launch.json.status -ne "completed" -or $identity.eval.json.total -lt 24) {
                $identity = Invoke-SmokeAndEval -Kind "identity" -AdapterPath $currentAdapter -PromptsJsonl $identityPrompts -SystemPromptFile $identitySystemPrompt -MaxNewTokens 32
            }
            $v1 = Invoke-SmokeAndEval -Kind "v1" -AdapterPath $currentAdapter -PromptsJsonl $v1Prompts -SystemPromptFile "" -MaxNewTokens 64
            $v2 = Invoke-SmokeAndEval -Kind "v2" -AdapterPath $currentAdapter -PromptsJsonl $v2Prompts -SystemPromptFile "" -MaxNewTokens 32
            $armResult = [ordered]@{ arm = $arm; train = $trainRecord.train; adapter_dir = $currentAdapter; identity = $identity; v1 = $v1; v2 = $v2 }
            $summary.arms += $armResult
            if (($identity.eval.json.hard_failed -eq 0) -and ($identity.eval.json.passed -ge 20)) {
                if (-not $bestCandidate -or ([int]$identity.eval.json.passed -gt [int]$bestCandidate.identity.eval.json.passed)) {
                    $bestCandidate = $armResult
                }
            }
        } else {
            $consecutiveTrainFailures += 1
            $summary.arms += [ordered]@{ arm = $arm; train = $trainRecord.train; adapter_dir = ""; status = "train_failed_or_aborted" }
        }
        Write-JsonFile -Path $summaryPath -Payload $summary
    }

    if ($bestCandidate -and (Test-TimeRemaining) -and $completedArms -lt $MaxArms -and $consecutiveTrainFailures -lt 2) {
        $failureDataset = Join-Path "D:\Research_Engine\constitution_data" ("jinn_identity_failure_mined_" + ([DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")))
        $failedResults = $bestCandidate.identity.eval.json.results_path
        if ($failedResults -and (Test-Path -LiteralPath $failedResults)) {
            Add-Event -Event "failure_dataset_build_start" -Payload @{ source = $failedResults; dataset_dir = $failureDataset }
            $failureOutput = & $UtilityPythonExe $identityBuilder --output-dir $failureDataset --eval-output-dir $IdentityEvalDir --eval-results $failedResults --failure-only --repeats 4 2>&1
            if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath (Join-Path $failureDataset "train.jsonl"))) {
                Add-Event -Event "failure_dataset_build_finished" -Payload @{ dataset_dir = $failureDataset }
                $failureArm = New-Arm -Name "identity_failure_mined" -DatasetDir $failureDataset -Steps 20 -Seq 96 -Lr 0.000003
                $trainRecord = Invoke-TrainingArm -Arm $failureArm -AdapterPath $bestCandidate.adapter_dir
                $completedArms += 1
                if ($trainRecord.adapter_dir) {
                    $currentAdapter = $trainRecord.adapter_dir
                    $identity = Invoke-SmokeAndEval -Kind "identity" -AdapterPath $currentAdapter -PromptsJsonl $identityPrompts -SystemPromptFile $identitySystemPrompt -MaxNewTokens 48
                    $v1 = Invoke-SmokeAndEval -Kind "v1" -AdapterPath $currentAdapter -PromptsJsonl $v1Prompts -SystemPromptFile "" -MaxNewTokens 64
                    $v2 = Invoke-SmokeAndEval -Kind "v2" -AdapterPath $currentAdapter -PromptsJsonl $v2Prompts -SystemPromptFile "" -MaxNewTokens 32
                    $armResult = [ordered]@{ arm = $failureArm; train = $trainRecord.train; adapter_dir = $currentAdapter; identity = $identity; v1 = $v1; v2 = $v2 }
                    $summary.arms += $armResult
                    if (($identity.eval.json.hard_failed -eq 0) -and ($identity.eval.json.passed -ge 20) -and ([int]$identity.eval.json.passed -ge [int]$bestCandidate.identity.eval.json.passed)) {
                        $bestCandidate = $armResult
                    }
                }
            } else {
                Add-Event -Event "failure_dataset_build_failed" -Payload @{ output = ($failureOutput | Out-String) }
            }
        }
    }

    if ($bestCandidate -and (Test-TimeRemaining) -and $completedArms -lt $MaxArms -and $consecutiveTrainFailures -lt 2) {
        $polishArm = New-Arm -Name "final_identity_polish" -DatasetDir $IdentityDatasetDir -Steps 16 -Seq 96 -Lr 0.000002
        $trainRecord = Invoke-TrainingArm -Arm $polishArm -AdapterPath $bestCandidate.adapter_dir
        $completedArms += 1
        if ($trainRecord.adapter_dir) {
            $currentAdapter = $trainRecord.adapter_dir
            $identity = Invoke-SmokeAndEval -Kind "identity" -AdapterPath $currentAdapter -PromptsJsonl $identityPrompts -SystemPromptFile $identitySystemPrompt -MaxNewTokens 48
            $v1 = Invoke-SmokeAndEval -Kind "v1" -AdapterPath $currentAdapter -PromptsJsonl $v1Prompts -SystemPromptFile "" -MaxNewTokens 64
            $v2 = Invoke-SmokeAndEval -Kind "v2" -AdapterPath $currentAdapter -PromptsJsonl $v2Prompts -SystemPromptFile "" -MaxNewTokens 32
            $armResult = [ordered]@{ arm = $polishArm; train = $trainRecord.train; adapter_dir = $currentAdapter; identity = $identity; v1 = $v1; v2 = $v2 }
            $summary.arms += $armResult
            if (($identity.eval.json.hard_failed -eq 0) -and ($identity.eval.json.passed -ge 20) -and ([int]$identity.eval.json.passed -ge [int]$bestCandidate.identity.eval.json.passed)) {
                $bestCandidate = $armResult
            }
        }
    }

    $summary.best_identity_candidate = $bestCandidate
    $summary.manifest_update = Update-IdentityManifest -BestCandidate $bestCandidate -Summary $summary
    $summary.status = if ($bestCandidate) { "completed_with_identity_candidate" } else { "completed_no_identity_candidate" }
    $summary.finished_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    Write-JsonFile -Path $summaryPath -Payload $summary
    Add-Event -Event "finished" -Payload @{ status = $summary.status; summary_path = $summaryPath }
    $summary | ConvertTo-Json -Depth 20
}
catch {
    $summary.status = "failed"
    $summary.error = $_.Exception.Message
    $summary.finished_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    Write-JsonFile -Path $summaryPath -Payload $summary
    Add-Event -Event "failed" -Payload @{ error = $_.Exception.Message; summary_path = $summaryPath }
    $summary | ConvertTo-Json -Depth 20
    exit 2
}
