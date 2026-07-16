[CmdletBinding()]
param(
    [string]$TrainingTaskId = "punk_femme_v3_dual_4gb_v1",
    [string]$ModelId = "D:\Research_Engine\models\Pixie-Josie-1.7B-v2",
    [string]$DatasetDir = "",
    [string]$OutputRoot = "",
    [string]$CacheDir = "",
    [string[]]$ConstitutionIds = @("punk_v3", "femme_whimsy_v3"),
    [int]$RamLimitMb = 2048,
    [int]$CpuPercent = 50,
    [int]$IoLimitMbPerSec = 50,
    [int]$MaxSeqLength = 256,
    [int]$GradientAccumulationSteps = 8,
    [int]$LoraR = 4,
    [int]$LoraAlpha = 8,
    [double]$LearningRate = 1e-4,
    [double]$NumTrainEpochs = 8.0,
    [int]$LoggingSteps = 1,
    [int]$SaveSteps = 5,
    [int]$EvalSteps = 5,
    [int]$SaveTotalLimit = 2,
    [int]$CheckpointIntervalSteps = 5,
    [int]$CheckpointIntervalSeconds = 300,
    [int]$PollSeconds = 2,
    [int]$TimeoutSeconds = 5400,
    [string]$ChunkStrategy = "sequential_constitutions_no_parallel",
    [switch]$SkipDatasetBuild,
    [switch]$ResumeLatestCheckpoint,
    [switch]$InitFromFinalAdapter,
    [string]$InitAdapterRunSuffix = "",
    [string]$RunNameSuffix = ""
)

$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class JobObjectNative {
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
  public static extern IntPtr CreateJobObject(IntPtr lpJobAttributes, string lpName);

  [DllImport("kernel32.dll")]
  public static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);

  [DllImport("kernel32.dll")]
  public static extern bool SetInformationJobObject(IntPtr hJob, int infoType, IntPtr lpJobObjectInfo, uint cbJobObjectInfoLength);

  public const int JobObjectExtendedLimitInformation = 9;
  public const int JobObjectCpuRateControlInformation = 15;
  public const uint JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100;
  public const uint JOB_OBJECT_CPU_RATE_CONTROL_ENABLE = 0x1;
  public const uint JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x4;

  [StructLayout(LayoutKind.Sequential)]
  public struct IO_COUNTERS { public ulong ReadOperationCount; public ulong WriteOperationCount; public ulong OtherOperationCount; public ulong ReadTransferCount; public ulong WriteTransferCount; public ulong OtherTransferCount; }

  [StructLayout(LayoutKind.Sequential)]
  public struct JOBOBJECT_BASIC_LIMIT_INFORMATION { public long PerProcessUserTimeLimit; public long PerJobUserTimeLimit; public uint LimitFlags; public UIntPtr MinimumWorkingSetSize; public UIntPtr MaximumWorkingSetSize; public uint ActiveProcessLimit; public long Affinity; public uint PriorityClass; public uint SchedulingClass; }

  [StructLayout(LayoutKind.Sequential)]
  public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION { public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation; public IO_COUNTERS IoInfo; public UIntPtr ProcessMemoryLimit; public UIntPtr JobMemoryLimit; public UIntPtr PeakProcessMemoryUsed; public UIntPtr PeakJobMemoryUsed; }

  [StructLayout(LayoutKind.Sequential)]
  public struct JOBOBJECT_CPU_RATE_CONTROL_INFORMATION { public uint ControlFlags; public uint CpuRate; }
}
'@

function Write-Json {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Payload
    )
    $parent = Split-Path -Parent $Path
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, ($Payload | ConvertTo-Json -Depth 12), $utf8NoBom)
}

function Append-Jsonl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Payload
    )
    $parent = Split-Path -Parent $Path
    if ($parent) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $line = ($Payload | ConvertTo-Json -Depth 12 -Compress) + "`n"
    $bytes = $utf8NoBom.GetBytes($line)
    $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    try {
        $fs.Write($bytes, 0, $bytes.Length)
    } finally {
        $fs.Dispose()
    }
}

function New-JobObjectHandle {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][UInt64]$MemoryLimitBytes,
        [Parameter(Mandatory = $true)][UInt32]$CpuRatePermille
    )
    $job = [JobObjectNative]::CreateJobObject([IntPtr]::Zero, $Name)
    if ($job -eq [IntPtr]::Zero) {
        throw "CreateJobObject failed."
    }

    $limit = New-Object JobObjectNative+JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    $limit.BasicLimitInformation.LimitFlags = [JobObjectNative]::JOB_OBJECT_LIMIT_PROCESS_MEMORY
    $limit.ProcessMemoryLimit = [UIntPtr]$MemoryLimitBytes
    $size = [System.Runtime.InteropServices.Marshal]::SizeOf($limit)
    $ptr = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size)
    try {
        [System.Runtime.InteropServices.Marshal]::StructureToPtr($limit, $ptr, $false)
        [JobObjectNative]::SetInformationJobObject($job, [JobObjectNative]::JobObjectExtendedLimitInformation, $ptr, [uint32]$size) | Out-Null
    } finally {
        [System.Runtime.InteropServices.Marshal]::FreeHGlobal($ptr)
    }

    $cpu = New-Object JobObjectNative+JOBOBJECT_CPU_RATE_CONTROL_INFORMATION
    $cpu.ControlFlags = [JobObjectNative]::JOB_OBJECT_CPU_RATE_CONTROL_ENABLE -bor [JobObjectNative]::JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
    $cpu.CpuRate = $CpuRatePermille
    $size2 = [System.Runtime.InteropServices.Marshal]::SizeOf($cpu)
    $ptr2 = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size2)
    try {
        [System.Runtime.InteropServices.Marshal]::StructureToPtr($cpu, $ptr2, $false)
        [JobObjectNative]::SetInformationJobObject($job, [JobObjectNative]::JobObjectCpuRateControlInformation, $ptr2, [uint32]$size2) | Out-Null
    } finally {
        [System.Runtime.InteropServices.Marshal]::FreeHGlobal($ptr2)
    }

    return $job
}

function Get-CheckpointSteps {
    param([Parameter(Mandatory = $true)][string]$TrainDir)
    if (-not (Test-Path -LiteralPath $TrainDir)) {
        return @()
    }
    $steps = @()
    Get-ChildItem -LiteralPath $TrainDir -Directory -Filter "checkpoint-*" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.Name -match "^checkpoint-(\d+)$") {
            $steps += [int]$matches[1]
        }
    }
    return $steps | Sort-Object -Unique
}

function Invoke-CappedTraining {
    param(
        [Parameter(Mandatory = $true)][string]$ConstitutionId,
        [Parameter(Mandatory = $true)][string]$ModelId,
        [Parameter(Mandatory = $true)][string]$DatasetDir,
        [Parameter(Mandatory = $true)][string]$OutputRoot,
        [Parameter(Mandatory = $true)][string]$CacheDir,
        [Parameter(Mandatory = $true)][string]$OpsDir,
        [Parameter(Mandatory = $true)][UInt64]$MemoryLimitBytes,
        [Parameter(Mandatory = $true)][UInt32]$CpuRatePermille
    )

    $baseRunName = "{0}_{1}_4gb" -f ((Split-Path $ModelId -Leaf) -replace "[^A-Za-z0-9._-]", "_"), $ConstitutionId
    $runName = if ($RunNameSuffix) { $baseRunName + "_" + $RunNameSuffix } else { $baseRunName }
    $runDir = Join-Path $OutputRoot $runName
    $trainDir = Join-Path $runDir "train"
    New-Item -ItemType Directory -Force -Path $OpsDir | Out-Null
    $stdoutPath = Join-Path $OpsDir ($runName + ".stdout.log")
    $stderrPath = Join-Path $OpsDir ($runName + ".stderr.log")
    $eventLogPath = Join-Path $OpsDir ($runName + ".events.jsonl")
    $summaryPath = Join-Path $OpsDir ($runName + ".summary.json")

    $resumeCheckpoint = ""
    $initAdapterPath = ""
    if ($ResumeLatestCheckpoint) {
        $resumeTrainDir = if ($RunNameSuffix) { Join-Path (Join-Path $OutputRoot $baseRunName) "train" } else { $trainDir }
        $existingSteps = Get-CheckpointSteps -TrainDir $resumeTrainDir
        if ($existingSteps.Count -gt 0) {
            $resumeCheckpoint = Join-Path $resumeTrainDir ("checkpoint-" + ($existingSteps | Measure-Object -Maximum).Maximum)
        }
    }
    if ($InitFromFinalAdapter) {
        if ($InitAdapterRunSuffix) {
            $sourceRunDir = Join-Path $OutputRoot ($baseRunName + "_" + $InitAdapterRunSuffix)
        } elseif ($RunNameSuffix) {
            $sourceRunDir = Join-Path $OutputRoot $baseRunName
        } else {
            $sourceRunDir = $runDir
        }
        $candidate = Join-Path $sourceRunDir "final_adapter"
        if (Test-Path -LiteralPath $candidate) {
            $initAdapterPath = $candidate
        }
    }

    $commandArgs = @(
        ".\scripts\train_constitution_adapter.py",
        "--model-id", $ModelId,
        "--dataset-dir", $DatasetDir,
        "--constitution-id", $ConstitutionId,
        "--output-root", $OutputRoot,
        "--run-name", $runName,
        "--cache-dir", $CacheDir,
        "--quantization", "qlora",
        "--dtype", "float16",
        "--max-seq-length", "$MaxSeqLength",
        "--per-device-train-batch-size", "1",
        "--per-device-eval-batch-size", "1",
        "--gradient-accumulation-steps", "$GradientAccumulationSteps",
        "--learning-rate", "$LearningRate",
        "--num-train-epochs", "$NumTrainEpochs",
        "--logging-steps", "$LoggingSteps",
        "--save-steps", "$SaveSteps",
        "--eval-steps", "$EvalSteps",
        "--save-total-limit", "$SaveTotalLimit",
        "--lora-r", "$LoraR",
        "--lora-alpha", "$LoraAlpha"
    )
    if ($resumeCheckpoint) {
        $commandArgs += @("--resume-from-checkpoint", $resumeCheckpoint)
    }
    if ($initAdapterPath) {
        $commandArgs += @("--init-adapter-path", $initAdapterPath)
    }

    $job = New-JobObjectHandle -Name ("ca-train-" + $runName) -MemoryLimitBytes $MemoryLimitBytes -CpuRatePermille $CpuRatePermille
    $startedAt = [DateTimeOffset]::UtcNow
    $summary = [ordered]@{
        run_id = $runName
        training_task_id = $TrainingTaskId
        constitution_id = $ConstitutionId
        status = "running"
        caps = @{
            ram_mb = $RamLimitMb
            cpu_pct = $CpuPercent
            io_mb_s = $IoLimitMbPerSec
        }
        checkpoint_interval = @{
            steps = $CheckpointIntervalSteps
            seconds = $CheckpointIntervalSeconds
        }
        chunk_strategy = $ChunkStrategy
        model_id = $ModelId
        dataset_dir = $DatasetDir
        run_dir = $runDir
        started_at_utc = $startedAt.ToString("o")
        peak_ram_mb = 0.0
        avg_ram_mb = 0.0
        peak_io_mb_s = 0.0
        cpu_pct = 0.0
        steps_completed = 0
        checkpoints = @()
        stdout_log = $stdoutPath
        stderr_log = $stderrPath
        event_log = $eventLogPath
        abort_reason = ""
        process_exit_code = $null
        resumed_from_checkpoint = $resumeCheckpoint
        init_adapter_path = $initAdapterPath
        init_adapter_run_suffix = $InitAdapterRunSuffix
    }
    Write-Json -Path $summaryPath -Payload $summary
    Append-Jsonl -Path $eventLogPath -Payload @{
        ts = $summary.started_at_utc
        event = "start"
        run_id = $runName
        caps = $summary.caps
        checkpoint_interval = $summary.checkpoint_interval
        chunk_strategy = $summary.chunk_strategy
        resumed_from_checkpoint = $resumeCheckpoint
        init_adapter_path = $initAdapterPath
    }

    $proc = Start-Process -FilePath "python" -ArgumentList $commandArgs -PassThru -NoNewWindow -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    if (-not [JobObjectNative]::AssignProcessToJobObject($job, $proc.Handle)) {
        try { $proc.Kill() } catch {}
        throw "AssignProcessToJobObject failed for $runName."
    }

    $lastPollAt = [DateTimeOffset]::UtcNow
    $lastProcStats = $null
    $samples = 0
    $sumRamMb = 0.0
    $sumCpuPct = 0.0
    $knownCheckpoints = @{}
    $ioLimitStreak = 0

    while (-not $proc.HasExited) {
        Start-Sleep -Seconds $PollSeconds
        $now = [DateTimeOffset]::UtcNow
        $elapsed = ($now - $startedAt).TotalSeconds
        if ($elapsed -gt $TimeoutSeconds) {
            try { $proc.Kill() } catch {}
            $summary.status = "aborted"
            $summary.abort_reason = "timeout"
            Append-Jsonl -Path $eventLogPath -Payload @{
                ts = $now.ToString("o")
                event = "abort"
                reason = "timeout"
                steps_completed = $summary.steps_completed
            }
            break
        }

        $proc.Refresh()
        $stats = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
        if (-not $stats) {
            break
        }

        $ramMb = [math]::Round($stats.WorkingSet64 / 1MB, 2)
        $summary.peak_ram_mb = [math]::Max([double]$summary.peak_ram_mb, $ramMb)
        $sumRamMb += $ramMb

        $cpuPctSample = 0.0
        $ioMbPerSec = 0.0
        if ($lastProcStats -ne $null) {
            $dt = [math]::Max(0.001, ($now - $lastPollAt).TotalSeconds)
            $cpuDeltaSeconds = [math]::Max(0.0, ($stats.CPU - $lastProcStats.CPU))
            $cpuPctSample = [math]::Round((100.0 * $cpuDeltaSeconds / $dt), 2)
            $ioBytesDelta = [math]::Max(0.0, (($stats.IOReadBytes + $stats.IOWriteBytes) - ($lastProcStats.IOReadBytes + $lastProcStats.IOWriteBytes)))
            $ioMbPerSec = [math]::Round(($ioBytesDelta / 1MB) / $dt, 2)
        }
        $summary.peak_io_mb_s = [math]::Max([double]$summary.peak_io_mb_s, $ioMbPerSec)
        $sumCpuPct += $cpuPctSample
        $samples += 1

        if ($ioMbPerSec -gt $IoLimitMbPerSec) {
            $ioLimitStreak += 1
        } else {
            $ioLimitStreak = 0
        }
        if ($ioLimitStreak -ge 3) {
            try { $proc.Kill() } catch {}
            $summary.status = "aborted"
            $summary.abort_reason = "io_cap_exceeded"
            Append-Jsonl -Path $eventLogPath -Payload @{
                ts = $now.ToString("o")
                event = "abort"
                reason = "io_cap_exceeded"
                peak_io_mb_s = $summary.peak_io_mb_s
                steps_completed = $summary.steps_completed
            }
            break
        }

        foreach ($step in (Get-CheckpointSteps -TrainDir $trainDir)) {
            if (-not $knownCheckpoints.Contains($step)) {
                $knownCheckpoints[$step] = $true
                $summary.checkpoints += (Join-Path $trainDir ("checkpoint-" + $step))
                $summary.steps_completed = [math]::Max([int]$summary.steps_completed, [int]$step)
                Append-Jsonl -Path $eventLogPath -Payload @{
                    ts = $now.ToString("o")
                    event = "checkpoint"
                    step = $step
                    path = (Join-Path $trainDir ("checkpoint-" + $step))
                }
            }
        }

        Append-Jsonl -Path $eventLogPath -Payload @{
            ts = $now.ToString("o")
            event = "poll"
            ram_mb = $ramMb
            cpu_pct = $cpuPctSample
            io_mb_s = $ioMbPerSec
        }

        $lastPollAt = $now
        $lastProcStats = $stats
        $summary.avg_ram_mb = [math]::Round(($sumRamMb / [math]::Max(1, $samples)), 2)
        $summary.cpu_pct = [math]::Round(($sumCpuPct / [math]::Max(1, $samples)), 2)
        Write-Json -Path $summaryPath -Payload $summary
    }

    if ($proc.HasExited) {
        $summary.process_exit_code = $proc.ExitCode
    }

    $receiptPath = Join-Path $runDir "receipt.json"
    $trainMetricsPath = Join-Path $runDir "train_metrics.json"
    if (Test-Path -LiteralPath $trainMetricsPath) {
        try {
            $trainMetrics = Get-Content -LiteralPath $trainMetricsPath -Raw | ConvertFrom-Json
            $steps = @()
            foreach ($entry in ($trainMetrics.log_history | Where-Object { $_.step -ne $null })) {
                $steps += [int]$entry.step
            }
            if ($steps.Count -gt 0) {
                $summary.steps_completed = [math]::Max([int]$summary.steps_completed, ($steps | Measure-Object -Maximum).Maximum)
            }
        } catch {}
    }

    if (-not $summary.abort_reason -and (Test-Path -LiteralPath $receiptPath)) {
        try {
            $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
            if ($receipt.status -eq "completed") {
                $summary.status = "completed"
            } elseif ($receipt.status -like "failed*") {
                $summary.status = "failed"
                $summary.abort_reason = [string]$receipt.status
            }
        } catch {}
    }

    if (-not $summary.abort_reason -and $summary.status -eq "running") {
        if ($summary.process_exit_code -eq 0) {
            $summary.status = "completed"
        } elseif ($summary.process_exit_code -ne $null) {
            $summary.status = "failed"
            $summary.abort_reason = "exit_code_$($summary.process_exit_code)"
        }
    }

    $summary.finished_at_utc = ([DateTimeOffset]::UtcNow).ToString("o")
    Write-Json -Path $summaryPath -Payload $summary
    Append-Jsonl -Path $eventLogPath -Payload @{
        ts = $summary.finished_at_utc
        event = "finish"
        status = $summary.status
        abort_reason = $summary.abort_reason
        steps_completed = $summary.steps_completed
        peak_ram_mb = $summary.peak_ram_mb
        peak_io_mb_s = $summary.peak_io_mb_s
    }

    return $summary
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
if (-not $DatasetDir) {
    $DatasetDir = Join-Path $repoRoot "artifacts\constitution_pipeline\artifacts\punk_femme_v3_storyworld_dataset"
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $repoRoot "artifacts\constitution_pipeline\runs\low_vram_4gb"
}
if (-not $CacheDir) {
    $CacheDir = Join-Path $repoRoot ".cache\huggingface"
}
$DatasetDir = [System.IO.Path]::GetFullPath($DatasetDir)
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$CacheDir = [System.IO.Path]::GetFullPath($CacheDir)
$opsDir = Join-Path $OutputRoot "_ops\$TrainingTaskId"

$plan = [ordered]@{
    training_task_id = $TrainingTaskId
    caps = @{
        ram_mb = $RamLimitMb
        cpu_pct = $CpuPercent
        io_mb_s = $IoLimitMbPerSec
    }
    chunk_strategy = $ChunkStrategy
    checkpoint_interval = @{
        steps = $CheckpointIntervalSteps
        seconds = $CheckpointIntervalSeconds
    }
    constitutions = $ConstitutionIds
    model_id = $ModelId
    dataset_dir = $DatasetDir
    output_root = $OutputRoot
}
Write-Json -Path (Join-Path $opsDir "trainer_plan.json") -Payload $plan

$summaries = @()
foreach ($constitutionId in $ConstitutionIds) {
    $summaries += Invoke-CappedTraining `
        -ConstitutionId $constitutionId `
        -ModelId $ModelId `
        -DatasetDir $DatasetDir `
        -OutputRoot $OutputRoot `
        -CacheDir $CacheDir `
        -OpsDir $opsDir `
        -MemoryLimitBytes ([UInt64]($RamLimitMb * 1MB)) `
        -CpuRatePermille ([UInt32]($CpuPercent * 100))
}

$overall = [ordered]@{
    training_task_id = $TrainingTaskId
    status = if (($summaries | Where-Object { $_.status -ne "completed" }).Count -eq 0) { "completed" } else { "mixed" }
    generated_at_utc = ([DateTimeOffset]::UtcNow).ToString("o")
    summaries = $summaries
}
Write-Json -Path (Join-Path $opsDir "summary.json") -Payload $overall
$overall | ConvertTo-Json -Depth 12
