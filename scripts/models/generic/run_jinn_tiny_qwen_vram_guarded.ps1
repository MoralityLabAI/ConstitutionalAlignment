[CmdletBinding()]
param(
    [string]$ModelId = "D:\Research_Engine\models\Qwen3.5\Qwen2.5-3B",
    [string]$FallbackModelId = "D:\Research_Engine\models\Pixie-Josie-1.7B-v2",
    [string]$DatasetDir = "",
    [string]$OutputRoot = "",
    [string]$CacheDir = "",
    [string]$ConstitutionId = "jinn_tiny_mutazili_v1",
    [int]$MaxSteps = 3,
    [int]$MaxSeqLength = 192,
    [int]$VramLimitMb = 3900,
    [int]$VramReserveMb = 192,
    [double]$LearningRate = 1e-4,
    [string]$InitAdapterPath = "",
    [int]$RamLimitMb = 8192,
    [int]$MinAvailableRamMb = 1024,
    [int]$MaxProcessCommitMb = 0,
    [int]$MaxPagefileGrowthMb = 64,
    [int]$CpuPercent = 80,
    [int]$IoLimitMbPerSec = 50,
    [int]$IoSpikeSamples = 3,
    [int]$SaveSteps = 10,
    [int]$SaveTotalLimit = 2,
    [int]$TimeoutSeconds = 3600,
    [switch]$DryRunLoadOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path

if (-not $DatasetDir) {
    $DatasetDir = Join-Path $repoRoot "data\jinn_tiny_mutazili_v1"
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $repoRoot "artifacts\constitution_pipeline\runs\jinn_tiny_mutazili_v1"
}
if (-not $CacheDir) {
    $CacheDir = Join-Path $repoRoot ".cache\huggingface"
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class JinnJobObjectNative {
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
  public static extern IntPtr CreateJobObject(IntPtr lpJobAttributes, string lpName);

  [DllImport("kernel32.dll")]
  public static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);

  [DllImport("kernel32.dll")]
  public static extern bool SetInformationJobObject(IntPtr hJob, int infoType, IntPtr lpJobObjectInfo, uint cbJobObjectInfoLength);

  [DllImport("kernel32.dll")]
  public static extern bool GetProcessIoCounters(IntPtr hProcess, out IO_COUNTERS lpIoCounters);

  public const int JobObjectExtendedLimitInformation = 9;
  public const int JobObjectCpuRateControlInformation = 15;
  public const uint JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100;
  public const uint JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200;
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

function Invoke-PostRunMemoryCleanup {
    param(
        [Parameter(Mandatory = $true)][string]$RunName,
        [Parameter(Mandatory = $true)][string]$OpsDir,
        [int]$RootPid = 0
    )
    $cleanupScript = "C:\Users\patri\.codex\skills\hrm-trainer\scripts\post_run_memory_cleanup.ps1"
    $cleanupSummaryPath = Join-Path $OpsDir ($RunName + ".cleanup.json")
    if (-not (Test-Path -LiteralPath $cleanupScript) -or $RootPid -le 0) {
        return [ordered]@{ status = "skipped"; reason = "cleanup_script_missing_or_pid_unset"; summary_path = $cleanupSummaryPath }
    }
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $cleanupScript `
            -RunId $RunName `
            -OwnedPid $RootPid `
            -StopOwnedProcesses `
            -SummaryPath $cleanupSummaryPath | Out-Null
        if (Test-Path -LiteralPath $cleanupSummaryPath) {
            $cleanup = Get-Content -LiteralPath $cleanupSummaryPath -Raw | ConvertFrom-Json
            return [ordered]@{
                status = "completed"
                summary_path = $cleanupSummaryPath
                cleanup_passed = [bool]$cleanup.cleanup_passed
                free_gb_after = $cleanup.memory_after.free_gb
                standby_gb_after = $cleanup.memory_after.standby_gb
                committed_gb_after = $cleanup.memory_after.committed_gb
                gpu_compute_apps_after = @($cleanup.gpu_after.compute_apps).Count
                lingering_owned_pids = @($cleanup.lingering_owned_pids)
            }
        }
        return [ordered]@{ status = "completed_no_summary"; summary_path = $cleanupSummaryPath }
    } catch {
        return [ordered]@{ status = "failed"; error = $_.Exception.Message; summary_path = $cleanupSummaryPath }
    }
}

function New-JinnJobObjectHandle {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][UInt64]$MemoryLimitBytes,
        [Parameter(Mandatory = $true)][UInt32]$CpuRatePermille
    )
    $job = [JinnJobObjectNative]::CreateJobObject([IntPtr]::Zero, $Name)
    if ($job -eq [IntPtr]::Zero) {
        throw "CreateJobObject failed."
    }

    $limit = New-Object JinnJobObjectNative+JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    $limit.BasicLimitInformation.LimitFlags = [JinnJobObjectNative]::JOB_OBJECT_LIMIT_PROCESS_MEMORY -bor [JinnJobObjectNative]::JOB_OBJECT_LIMIT_JOB_MEMORY
    $limit.ProcessMemoryLimit = [UIntPtr]$MemoryLimitBytes
    $limit.JobMemoryLimit = [UIntPtr]$MemoryLimitBytes
    $size = [System.Runtime.InteropServices.Marshal]::SizeOf($limit)
    $ptr = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size)
    try {
        [System.Runtime.InteropServices.Marshal]::StructureToPtr($limit, $ptr, $false)
        [JinnJobObjectNative]::SetInformationJobObject($job, [JinnJobObjectNative]::JobObjectExtendedLimitInformation, $ptr, [uint32]$size) | Out-Null
    } finally {
        [System.Runtime.InteropServices.Marshal]::FreeHGlobal($ptr)
    }

    $cpu = New-Object JinnJobObjectNative+JOBOBJECT_CPU_RATE_CONTROL_INFORMATION
    $cpu.ControlFlags = [JinnJobObjectNative]::JOB_OBJECT_CPU_RATE_CONTROL_ENABLE -bor [JinnJobObjectNative]::JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
    $cpu.CpuRate = $CpuRatePermille
    $size2 = [System.Runtime.InteropServices.Marshal]::SizeOf($cpu)
    $ptr2 = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size2)
    try {
        [System.Runtime.InteropServices.Marshal]::StructureToPtr($cpu, $ptr2, $false)
        [JinnJobObjectNative]::SetInformationJobObject($job, [JinnJobObjectNative]::JobObjectCpuRateControlInformation, $ptr2, [uint32]$size2) | Out-Null
    } finally {
        [System.Runtime.InteropServices.Marshal]::FreeHGlobal($ptr2)
    }
    return $job
}

function Get-GuardedProcessIoBytes {
    param([Parameter(Mandatory = $true)]$Process)
    $counters = New-Object JinnJobObjectNative+IO_COUNTERS
    $ok = [JinnJobObjectNative]::GetProcessIoCounters($Process.Handle, [ref]$counters)
    if (-not $ok) {
        return 0
    }
    return [UInt64]($counters.ReadTransferCount + $counters.WriteTransferCount)
}

function Get-AvailableRamMb {
    $os = Get-CimInstance Win32_OperatingSystem
    return [double]($os.FreePhysicalMemory / 1024.0)
}

function Get-PagefileCurrentMb {
    $usage = Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue | Measure-Object CurrentUsage -Sum
    if ($usage.Sum -eq $null) { return 0.0 }
    return [double]$usage.Sum
}

function Invoke-GuardedAttempt {
    param(
        [Parameter(Mandatory = $true)][string]$AttemptName,
        [Parameter(Mandatory = $true)][string]$AttemptModelId
    )
    $stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $safeLeaf = ((Split-Path $AttemptModelId -Leaf) -replace "[^A-Za-z0-9._-]", "_")
    $runName = "{0}_{1}_{2}" -f $ConstitutionId, $safeLeaf, $stamp
    $opsDir = Join-Path $OutputRoot "_ops"
    New-Item -ItemType Directory -Force -Path $opsDir | Out-Null
    $stdoutPath = Join-Path $opsDir ($runName + ".stdout.log")
    $stderrPath = Join-Path $opsDir ($runName + ".stderr.log")

    $args = @(
        ".\scripts\train_jinn_tiny_vram_guarded.py",
        "--model-id", $AttemptModelId,
        "--dataset-dir", $DatasetDir,
        "--constitution-id", $ConstitutionId,
        "--output-root", $OutputRoot,
        "--run-name", $runName,
        "--cache-dir", $CacheDir,
        "--max-steps", "$MaxSteps",
        "--max-seq-length", "$MaxSeqLength",
        "--vram-limit-mb", "$VramLimitMb",
        "--vram-reserve-mb", "$VramReserveMb",
        "--learning-rate", "$LearningRate",
        "--save-steps", "$SaveSteps",
        "--save-total-limit", "$SaveTotalLimit"
    )
    if ($InitAdapterPath) {
        $args += @("--init-adapter-path", $InitAdapterPath)
    }
    if ($DryRunLoadOnly) {
        $args += "--dry-run-load-only"
    }

    $commitCapMb = if ($MaxProcessCommitMb -gt 0) { $MaxProcessCommitMb } else { $RamLimitMb }
    $availableBeforeStartMb = Get-AvailableRamMb
    $pagefileBaselineMb = Get-PagefileCurrentMb
    if ($availableBeforeStartMb -lt $MinAvailableRamMb) {
        return [ordered]@{
            attempt = $AttemptName
            model_id = $AttemptModelId
            run_name = $runName
            status = "preflight_ram_aborted"
            exit_code = -1
            abort_reason = "available_ram_mb_below_floor_before_start"
            available_ram_mb = [Math]::Round($availableBeforeStartMb, 3)
            min_available_ram_mb = $MinAvailableRamMb
            private_commit_limit_mb = $commitCapMb
            pagefile_baseline_mb = [Math]::Round($pagefileBaselineMb, 3)
            max_pagefile_growth_mb = $MaxPagefileGrowthMb
            stdout_log = $stdoutPath
            stderr_log = $stderrPath
            run_dir = Join-Path $OutputRoot $runName
            cleanup = [ordered]@{ status = "skipped"; reason = "process_not_started" }
        }
    }

    $job = New-JinnJobObjectHandle `
        -Name ("ca-jinn-" + $runName) `
        -MemoryLimitBytes ([UInt64]$RamLimitMb * 1024 * 1024) `
        -CpuRatePermille ([UInt32]($CpuPercent * 100))

    $started = [DateTimeOffset]::UtcNow
    $process = Start-Process `
        -FilePath "python" `
        -ArgumentList $args `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -WindowStyle Hidden `
        -PassThru
    [JinnJobObjectNative]::AssignProcessToJobObject($job, $process.Handle) | Out-Null

    $lastIoBytes = Get-GuardedProcessIoBytes -Process $process
    $lastIoAt = [DateTimeOffset]::UtcNow
    $ioSpikeCount = 0
    $peakIoMbPerSec = 0.0
    $logicalCpuCount = [Math]::Max(1, [Environment]::ProcessorCount)
    $lastCpuTime = $process.TotalProcessorTime
    $lastSampleAt = $lastIoAt
    $initialRamMb = $process.WorkingSet64 / 1MB
    $initialCommitMb = $process.PrivateMemorySize64 / 1MB
    $peakRamMb = $initialRamMb
    $peakCommitMb = $initialCommitMb
    $ramMbSum = $initialRamMb
    $commitMbSum = $initialCommitMb
    $peakCpuPct = 0.0
    $cpuPctSum = 0.0
    $sampleCount = 1

    while (-not $process.HasExited) {
        if ((([DateTimeOffset]::UtcNow) - $started).TotalSeconds -gt $TimeoutSeconds) {
            Stop-Process -Id $process.Id -Force
            $cleanup = Invoke-PostRunMemoryCleanup -RunName $runName -OpsDir $opsDir -RootPid $process.Id
            return [ordered]@{
                attempt = $AttemptName
                model_id = $AttemptModelId
                run_name = $runName
                status = "timeout_aborted"
                exit_code = -1
                peak_io_mb_s = [Math]::Round($peakIoMbPerSec, 3)
                peak_ram_mb = [Math]::Round($peakRamMb, 3)
                avg_ram_mb = [Math]::Round(($ramMbSum / [Math]::Max(1, $sampleCount)), 3)
                peak_cpu_pct = [Math]::Round($peakCpuPct, 3)
                avg_cpu_pct = [Math]::Round(($cpuPctSum / [Math]::Max(1, $sampleCount)), 3)
                samples = $sampleCount
                stdout_log = $stdoutPath
                stderr_log = $stderrPath
                run_dir = Join-Path $OutputRoot $runName
                cleanup = $cleanup
            }
        }
        Start-Sleep -Seconds 2
        $process.Refresh()
        if (-not $process.HasExited) {
            $now = [DateTimeOffset]::UtcNow
            $currentIoBytes = Get-GuardedProcessIoBytes -Process $process
            $elapsed = [Math]::Max(0.001, ($now - $lastIoAt).TotalSeconds)
            $ioMbPerSec = (($currentIoBytes - $lastIoBytes) / 1MB) / $elapsed
            $peakIoMbPerSec = [Math]::Max($peakIoMbPerSec, $ioMbPerSec)
            $ramMb = $process.WorkingSet64 / 1MB
            $commitMb = $process.PrivateMemorySize64 / 1MB
            $availableRamMb = Get-AvailableRamMb
            $pagefileCurrentMb = Get-PagefileCurrentMb
            $pagefileGrowthMb = [Math]::Max(0.0, $pagefileCurrentMb - $pagefileBaselineMb)
            $peakRamMb = [Math]::Max($peakRamMb, $ramMb)
            $peakCommitMb = [Math]::Max($peakCommitMb, $commitMb)
            $ramMbSum += $ramMb
            $commitMbSum += $commitMb
            $sampleCount += 1
            $currentCpuTime = $process.TotalProcessorTime
            $wallElapsed = [Math]::Max(0.001, ($now - $lastSampleAt).TotalSeconds)
            $cpuPct = (($currentCpuTime - $lastCpuTime).TotalSeconds / ($wallElapsed * $logicalCpuCount)) * 100.0
            $peakCpuPct = [Math]::Max($peakCpuPct, $cpuPct)
            $cpuPctSum += $cpuPct
            $lastCpuTime = $currentCpuTime
            $lastSampleAt = $now
            if ($ioMbPerSec -gt $IoLimitMbPerSec) {
                $ioSpikeCount += 1
            } else {
                $ioSpikeCount = 0
            }
            $lastIoBytes = $currentIoBytes
            $lastIoAt = $now
            if ($ioSpikeCount -ge $IoSpikeSamples) {
                Stop-Process -Id $process.Id -Force
                $cleanup = Invoke-PostRunMemoryCleanup -RunName $runName -OpsDir $opsDir -RootPid $process.Id
                return [ordered]@{
                    attempt = $AttemptName
                    model_id = $AttemptModelId
                    run_name = $runName
                    status = "io_aborted"
                    exit_code = -1
                    abort_reason = "io_mb_s_exceeded"
                    io_limit_mb_s = $IoLimitMbPerSec
                    peak_io_mb_s = [Math]::Round($peakIoMbPerSec, 3)
                    peak_ram_mb = [Math]::Round($peakRamMb, 3)
                    avg_ram_mb = [Math]::Round(($ramMbSum / [Math]::Max(1, $sampleCount)), 3)
                    peak_commit_mb = [Math]::Round($peakCommitMb, 3)
                    avg_commit_mb = [Math]::Round(($commitMbSum / [Math]::Max(1, $sampleCount)), 3)
                    available_ram_mb = [Math]::Round($availableRamMb, 3)
                    pagefile_current_mb = [Math]::Round($pagefileCurrentMb, 3)
                    pagefile_baseline_mb = [Math]::Round($pagefileBaselineMb, 3)
                    pagefile_growth_mb = [Math]::Round($pagefileGrowthMb, 3)
                    max_pagefile_growth_mb = $MaxPagefileGrowthMb
                    peak_cpu_pct = [Math]::Round($peakCpuPct, 3)
                    avg_cpu_pct = [Math]::Round(($cpuPctSum / [Math]::Max(1, $sampleCount)), 3)
                    samples = $sampleCount
                    stdout_log = $stdoutPath
                    stderr_log = $stderrPath
                    run_dir = Join-Path $OutputRoot $runName
                    cleanup = $cleanup
                }
            }
            if ($commitMb -gt $commitCapMb -or $availableRamMb -lt $MinAvailableRamMb -or $pagefileGrowthMb -gt $MaxPagefileGrowthMb) {
                Stop-Process -Id $process.Id -Force
                $cleanup = Invoke-PostRunMemoryCleanup -RunName $runName -OpsDir $opsDir -RootPid $process.Id
                return [ordered]@{
                    attempt = $AttemptName
                    model_id = $AttemptModelId
                    run_name = $runName
                    status = "ram_pressure_aborted"
                    exit_code = -1
                    abort_reason = if ($commitMb -gt $commitCapMb) { "private_commit_mb_exceeded" } elseif ($availableRamMb -lt $MinAvailableRamMb) { "available_ram_mb_below_floor" } else { "pagefile_growth_mb_exceeded" }
                    private_commit_mb = [Math]::Round($commitMb, 3)
                    private_commit_limit_mb = $commitCapMb
                    available_ram_mb = [Math]::Round($availableRamMb, 3)
                    min_available_ram_mb = $MinAvailableRamMb
                    pagefile_current_mb = [Math]::Round($pagefileCurrentMb, 3)
                    pagefile_baseline_mb = [Math]::Round($pagefileBaselineMb, 3)
                    pagefile_growth_mb = [Math]::Round($pagefileGrowthMb, 3)
                    max_pagefile_growth_mb = $MaxPagefileGrowthMb
                    peak_io_mb_s = [Math]::Round($peakIoMbPerSec, 3)
                    peak_ram_mb = [Math]::Round($peakRamMb, 3)
                    avg_ram_mb = [Math]::Round(($ramMbSum / [Math]::Max(1, $sampleCount)), 3)
                    peak_commit_mb = [Math]::Round($peakCommitMb, 3)
                    avg_commit_mb = [Math]::Round(($commitMbSum / [Math]::Max(1, $sampleCount)), 3)
                    peak_cpu_pct = [Math]::Round($peakCpuPct, 3)
                    avg_cpu_pct = [Math]::Round(($cpuPctSum / [Math]::Max(1, $sampleCount)), 3)
                    samples = $sampleCount
                    stdout_log = $stdoutPath
                    stderr_log = $stderrPath
                    run_dir = Join-Path $OutputRoot $runName
                    cleanup = $cleanup
                }
            }
        }
    }

    $status = if ($process.ExitCode -eq 0) { "completed" } else { "failed" }
    $cleanup = Invoke-PostRunMemoryCleanup -RunName $runName -OpsDir $opsDir -RootPid $process.Id
    $pagefileFinalMb = Get-PagefileCurrentMb
    return [ordered]@{
        attempt = $AttemptName
        model_id = $AttemptModelId
        run_name = $runName
        status = $status
        exit_code = $process.ExitCode
        peak_io_mb_s = [Math]::Round($peakIoMbPerSec, 3)
        peak_ram_mb = [Math]::Round($peakRamMb, 3)
        avg_ram_mb = [Math]::Round(($ramMbSum / [Math]::Max(1, $sampleCount)), 3)
        peak_commit_mb = [Math]::Round($peakCommitMb, 3)
        avg_commit_mb = [Math]::Round(($commitMbSum / [Math]::Max(1, $sampleCount)), 3)
        pagefile_baseline_mb = [Math]::Round($pagefileBaselineMb, 3)
        pagefile_final_mb = [Math]::Round($pagefileFinalMb, 3)
        pagefile_growth_mb = [Math]::Round(([Math]::Max(0.0, $pagefileFinalMb - $pagefileBaselineMb)), 3)
        max_pagefile_growth_mb = $MaxPagefileGrowthMb
        peak_cpu_pct = [Math]::Round($peakCpuPct, 3)
        avg_cpu_pct = [Math]::Round(($cpuPctSum / [Math]::Max(1, $sampleCount)), 3)
        samples = $sampleCount
        stdout_log = $stdoutPath
        stderr_log = $stderrPath
        run_dir = Join-Path $OutputRoot $runName
        cleanup = $cleanup
    }
}

$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:TOKENIZERS_PARALLELISM = "false"
$env:ACCELERATE_DISABLE_RICH = "1"
$env:PYTORCH_CUDA_ALLOC_CONF = "expandable_segments:True,max_split_size_mb:64"

Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
    $attempts = @()
    $primary = Invoke-GuardedAttempt -AttemptName "primary" -AttemptModelId $ModelId
    $attempts += $primary
    $final = $primary
    if (($primary.exit_code -ne 0) -and $FallbackModelId) {
        $fallback = Invoke-GuardedAttempt -AttemptName "fallback" -AttemptModelId $FallbackModelId
        $attempts += $fallback
        $final = $fallback
    }

    $launcherSummary = [ordered]@{
        status = if ($final.exit_code -eq 0) { "completed" } else { "failed" }
        started_primary_model_id = $ModelId
        fallback_model_id = $FallbackModelId
        constitution_id = $ConstitutionId
        dataset_dir = $DatasetDir
        output_root = $OutputRoot
        caps = @{
            ram_mb = $RamLimitMb
            min_available_ram_mb = $MinAvailableRamMb
            max_process_commit_mb = if ($MaxProcessCommitMb -gt 0) { $MaxProcessCommitMb } else { $RamLimitMb }
            max_pagefile_growth_mb = $MaxPagefileGrowthMb
            cpu_pct = $CpuPercent
            io_limit_mb_s = $IoLimitMbPerSec
            io_spike_samples = $IoSpikeSamples
            save_steps = $SaveSteps
            save_total_limit = $SaveTotalLimit
            vram_limit_mb = $VramLimitMb
            vram_reserve_mb = $VramReserveMb
            timeout_seconds = $TimeoutSeconds
            model_offload_allowed = $false
        }
        init_adapter_path = $InitAdapterPath
        attempts = $attempts
        finished_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    }
    $summaryPath = Join-Path $OutputRoot ("launcher_summary_" + ([DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")) + ".json")
    Write-Json -Path $summaryPath -Payload $launcherSummary
    $launcherSummary | ConvertTo-Json -Depth 12
    if ($final.exit_code -ne 0) {
        exit 2
    }
}
finally {
    Pop-Location
}
