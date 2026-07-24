[CmdletBinding()]
param(
    [string]$BaseModelId = "D:\Research_Engine\models\Pixie-Josie-1.7B-v2",
    [string]$AdapterDir = "",
    [switch]$BaseOnly,
    [string]$OutputRoot = "",
    [string]$CacheDir = "",
    [string]$PromptsJsonl = "",
    [string]$SystemPromptFile = "",
    [int]$MaxNewTokens = 96,
    [switch]$EnableThinking,
    [int]$ProbeStart = 1,
    [int]$ProbeCount = 0,
    [string]$StoryworldPlan = "",
    [int]$StoryworldCycle = 1,
    [ValidateSet("train", "holdout")][string]$StoryworldLane = "train",
    [int]$StoryworldEpisodeStart = 1,
    [int]$StoryworldEpisodeCount = 0,
    [int]$VramLimitMb = 3900,
    [int]$RamLimitMb = 8192,
    [int]$MinAvailableRamMb = 1024,
    [int]$MaxProcessCommitMb = 0,
    [int]$MaxPagefileGrowthMb = 64,
    [int]$CpuPercent = 80,
    [int]$IoLimitMbPerSec = 50,
    [int]$IoSpikeSamples = 3,
    [switch]$RepairViolations,
    [int]$RepairAttempts = 1,
    [bool]$SkipCudaAllocatorWarmup = $true,
    [int]$TimeoutSeconds = 1200
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path

if (-not $OutputRoot) {
    $OutputRoot = Join-Path $repoRoot "artifacts\constitution_pipeline\prompt_runs\jinn_tiny_mutazili_v1_local"
}
if (-not $CacheDir) {
    $CacheDir = Join-Path $repoRoot ".cache\huggingface"
}
if (-not $PromptsJsonl) {
    $PromptsJsonl = Join-Path $repoRoot "data\jinn_tiny_mutazili_eval_v1\probes.jsonl"
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class JinnSmokeJobObjectNative {
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

function New-SmokeJobObjectHandle {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][UInt64]$MemoryLimitBytes,
        [Parameter(Mandatory = $true)][UInt32]$CpuRatePermille
    )
    $job = [JinnSmokeJobObjectNative]::CreateJobObject([IntPtr]::Zero, $Name)
    if ($job -eq [IntPtr]::Zero) {
        throw "CreateJobObject failed."
    }

    $limit = New-Object JinnSmokeJobObjectNative+JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    $limit.BasicLimitInformation.LimitFlags = [JinnSmokeJobObjectNative]::JOB_OBJECT_LIMIT_PROCESS_MEMORY -bor [JinnSmokeJobObjectNative]::JOB_OBJECT_LIMIT_JOB_MEMORY
    $limit.ProcessMemoryLimit = [UIntPtr]$MemoryLimitBytes
    $limit.JobMemoryLimit = [UIntPtr]$MemoryLimitBytes
    $size = [System.Runtime.InteropServices.Marshal]::SizeOf($limit)
    $ptr = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size)
    try {
        [System.Runtime.InteropServices.Marshal]::StructureToPtr($limit, $ptr, $false)
        [JinnSmokeJobObjectNative]::SetInformationJobObject($job, [JinnSmokeJobObjectNative]::JobObjectExtendedLimitInformation, $ptr, [uint32]$size) | Out-Null
    } finally {
        [System.Runtime.InteropServices.Marshal]::FreeHGlobal($ptr)
    }

    $cpu = New-Object JinnSmokeJobObjectNative+JOBOBJECT_CPU_RATE_CONTROL_INFORMATION
    $cpu.ControlFlags = [JinnSmokeJobObjectNative]::JOB_OBJECT_CPU_RATE_CONTROL_ENABLE -bor [JinnSmokeJobObjectNative]::JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
    $cpu.CpuRate = $CpuRatePermille
    $size2 = [System.Runtime.InteropServices.Marshal]::SizeOf($cpu)
    $ptr2 = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size2)
    try {
        [System.Runtime.InteropServices.Marshal]::StructureToPtr($cpu, $ptr2, $false)
        [JinnSmokeJobObjectNative]::SetInformationJobObject($job, [JinnSmokeJobObjectNative]::JobObjectCpuRateControlInformation, $ptr2, [uint32]$size2) | Out-Null
    } finally {
        [System.Runtime.InteropServices.Marshal]::FreeHGlobal($ptr2)
    }
    return $job
}

function Get-SmokeProcessIoBytes {
    param([Parameter(Mandatory = $true)]$Process)
    $counters = New-Object JinnSmokeJobObjectNative+IO_COUNTERS
    $ok = [JinnSmokeJobObjectNative]::GetProcessIoCounters($Process.Handle, [ref]$counters)
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

$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:TOKENIZERS_PARALLELISM = "false"
$env:ACCELERATE_DISABLE_RICH = "1"
$env:PYTORCH_CUDA_ALLOC_CONF = "expandable_segments:True,max_split_size_mb:64"

Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
    $stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $runName = "local_smoke_" + $stamp
    $opsDir = Join-Path $OutputRoot "_ops"
    New-Item -ItemType Directory -Force -Path $opsDir | Out-Null
    $stdoutPath = Join-Path $opsDir ($runName + ".stdout.log")
    $stderrPath = Join-Path $opsDir ($runName + ".stderr.log")

    $args = @(
        ".\scripts\run_jinn_tiny_local_smoke.py",
        "--base-model-id", $BaseModelId,
        "--output-root", $OutputRoot,
        "--run-name", $runName,
        "--cache-dir", $CacheDir,
        "--prompts-jsonl", $PromptsJsonl,
        "--max-new-tokens", "$MaxNewTokens",
        "--probe-start", "$ProbeStart",
        "--probe-count", "$ProbeCount",
        "--vram-limit-mb", "$VramLimitMb"
    )
    if ($SystemPromptFile) {
        $args += @("--system-prompt-file", $SystemPromptFile)
    }
    if ($EnableThinking) {
        $args += "--enable-thinking"
    }
    if ($StoryworldPlan) {
        $args += @(
            "--storyworld-plan", $StoryworldPlan,
            "--storyworld-cycle", "$StoryworldCycle",
            "--storyworld-lane", $StoryworldLane,
            "--storyworld-episode-start", "$StoryworldEpisodeStart",
            "--storyworld-episode-count", "$StoryworldEpisodeCount"
        )
    }
    if ($AdapterDir) {
        $args += @("--adapter-dir", $AdapterDir)
    }
    if ($BaseOnly) {
        if ($AdapterDir) {
            throw "BaseOnly cannot be combined with AdapterDir."
        }
        $args += "--base-only"
    }
    if ($RepairViolations) {
        $args += @("--repair-violations", "--repair-attempts", "$RepairAttempts")
    }
    if ($SkipCudaAllocatorWarmup) {
        $args += "--skip-cuda-allocator-warmup"
    }

    $commitCapMb = if ($MaxProcessCommitMb -gt 0) { $MaxProcessCommitMb } else { $RamLimitMb }
    $availableBeforeStartMb = Get-AvailableRamMb
    $pagefileBaselineMb = Get-PagefileCurrentMb
    if ($availableBeforeStartMb -lt $MinAvailableRamMb) {
        $summary = [ordered]@{
            status = "preflight_ram_aborted"
            exit_code = -1
            abort_reason = "available_ram_mb_below_floor_before_start"
            run_name = $runName
            base_model_id = $BaseModelId
            adapter_dir = $AdapterDir
            base_only = [bool]$BaseOnly
            prompts_jsonl = $PromptsJsonl
            available_ram_mb = [Math]::Round($availableBeforeStartMb, 3)
            min_available_ram_mb = $MinAvailableRamMb
            pagefile_baseline_mb = [Math]::Round($pagefileBaselineMb, 3)
            max_pagefile_growth_mb = $MaxPagefileGrowthMb
            run_dir = Join-Path $OutputRoot $runName
            stdout_log = $stdoutPath
            stderr_log = $stderrPath
            caps = @{
                ram_mb = $RamLimitMb
                min_available_ram_mb = $MinAvailableRamMb
                max_process_commit_mb = $commitCapMb
                max_pagefile_growth_mb = $MaxPagefileGrowthMb
                cpu_pct = $CpuPercent
                io_limit_mb_s = $IoLimitMbPerSec
                io_spike_samples = $IoSpikeSamples
                vram_limit_mb = $VramLimitMb
                timeout_seconds = $TimeoutSeconds
                model_offload_allowed = $false
            }
            cleanup = [ordered]@{ status = "skipped"; reason = "process_not_started" }
        }
        $summaryPath = Join-Path $OutputRoot ("launcher_summary_" + $stamp + ".json")
        Write-Json -Path $summaryPath -Payload $summary
        $summary | ConvertTo-Json -Depth 12
        exit 2
    }

    $job = New-SmokeJobObjectHandle `
        -Name ("ca-jinn-smoke-" + $runName) `
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
    [JinnSmokeJobObjectNative]::AssignProcessToJobObject($job, $process.Handle) | Out-Null

    $lastIoBytes = Get-SmokeProcessIoBytes -Process $process
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
            $summary = [ordered]@{
                status = "timeout_aborted"
                exit_code = -1
                run_name = $runName
                peak_io_mb_s = [Math]::Round($peakIoMbPerSec, 3)
                peak_ram_mb = [Math]::Round($peakRamMb, 3)
                avg_ram_mb = [Math]::Round(($ramMbSum / [Math]::Max(1, $sampleCount)), 3)
                peak_cpu_pct = [Math]::Round($peakCpuPct, 3)
                avg_cpu_pct = [Math]::Round(($cpuPctSum / [Math]::Max(1, $sampleCount)), 3)
                samples = $sampleCount
                run_dir = Join-Path $OutputRoot $runName
                stdout_log = $stdoutPath
                stderr_log = $stderrPath
                caps = @{
                    ram_mb = $RamLimitMb
                    cpu_pct = $CpuPercent
                    io_limit_mb_s = $IoLimitMbPerSec
                    io_spike_samples = $IoSpikeSamples
                    vram_limit_mb = $VramLimitMb
                    timeout_seconds = $TimeoutSeconds
                    model_offload_allowed = $false
                }
                cleanup = $cleanup
            }
            $summaryPath = Join-Path $OutputRoot ("launcher_summary_" + $stamp + ".json")
            Write-Json -Path $summaryPath -Payload $summary
            $summary | ConvertTo-Json -Depth 12
            exit 2
        }
        Start-Sleep -Seconds 2
        $process.Refresh()
        if (-not $process.HasExited) {
            $now = [DateTimeOffset]::UtcNow
            $currentIoBytes = Get-SmokeProcessIoBytes -Process $process
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
                $summary = [ordered]@{
                    status = "io_aborted"
                    exit_code = -1
                    abort_reason = "io_mb_s_exceeded"
                    run_name = $runName
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
                    run_dir = Join-Path $OutputRoot $runName
                    stdout_log = $stdoutPath
                    stderr_log = $stderrPath
                    caps = @{
                        ram_mb = $RamLimitMb
                        max_pagefile_growth_mb = $MaxPagefileGrowthMb
                        cpu_pct = $CpuPercent
                        io_limit_mb_s = $IoLimitMbPerSec
                        io_spike_samples = $IoSpikeSamples
                        vram_limit_mb = $VramLimitMb
                        timeout_seconds = $TimeoutSeconds
                        model_offload_allowed = $false
                    }
                    cleanup = $cleanup
                }
                $summaryPath = Join-Path $OutputRoot ("launcher_summary_" + $stamp + ".json")
                Write-Json -Path $summaryPath -Payload $summary
                $summary | ConvertTo-Json -Depth 12
                exit 2
            }
            if ($commitMb -gt $commitCapMb -or $availableRamMb -lt $MinAvailableRamMb -or $pagefileGrowthMb -gt $MaxPagefileGrowthMb) {
                Stop-Process -Id $process.Id -Force
                $cleanup = Invoke-PostRunMemoryCleanup -RunName $runName -OpsDir $opsDir -RootPid $process.Id
                $summary = [ordered]@{
                    status = "ram_pressure_aborted"
                    exit_code = -1
                    abort_reason = if ($commitMb -gt $commitCapMb) { "private_commit_mb_exceeded" } elseif ($availableRamMb -lt $MinAvailableRamMb) { "available_ram_mb_below_floor" } else { "pagefile_growth_mb_exceeded" }
                    run_name = $runName
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
                    run_dir = Join-Path $OutputRoot $runName
                    stdout_log = $stdoutPath
                    stderr_log = $stderrPath
                    caps = @{
                        ram_mb = $RamLimitMb
                        min_available_ram_mb = $MinAvailableRamMb
                        max_process_commit_mb = $commitCapMb
                        max_pagefile_growth_mb = $MaxPagefileGrowthMb
                        cpu_pct = $CpuPercent
                        io_limit_mb_s = $IoLimitMbPerSec
                        io_spike_samples = $IoSpikeSamples
                        vram_limit_mb = $VramLimitMb
                        timeout_seconds = $TimeoutSeconds
                        model_offload_allowed = $false
                    }
                    cleanup = $cleanup
                }
                $summaryPath = Join-Path $OutputRoot ("launcher_summary_" + $stamp + ".json")
                Write-Json -Path $summaryPath -Payload $summary
                $summary | ConvertTo-Json -Depth 12
                exit 2
            }
        }
    }

    $cleanup = Invoke-PostRunMemoryCleanup -RunName $runName -OpsDir $opsDir -RootPid $process.Id
    $pagefileFinalMb = Get-PagefileCurrentMb
    $summary = [ordered]@{
        status = if ($process.ExitCode -eq 0) { "completed" } else { "failed" }
        run_name = $runName
        exit_code = $process.ExitCode
        base_model_id = $BaseModelId
        adapter_dir = $AdapterDir
        base_only = [bool]$BaseOnly
        prompts_jsonl = $PromptsJsonl
        probe_start = $ProbeStart
        probe_count = $ProbeCount
        storyworld_plan = $StoryworldPlan
        storyworld_cycle = $StoryworldCycle
        storyworld_lane = $StoryworldLane
        enable_thinking = [bool]$EnableThinking
        storyworld_episode_start = $StoryworldEpisodeStart
        storyworld_episode_count = $StoryworldEpisodeCount
        system_prompt_file = $SystemPromptFile
        repair_violations = [bool]$RepairViolations
        repair_attempts = if ($RepairViolations) { $RepairAttempts } else { 0 }
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
        run_dir = Join-Path $OutputRoot $runName
        stdout_log = $stdoutPath
        stderr_log = $stderrPath
        caps = @{
            ram_mb = $RamLimitMb
            min_available_ram_mb = $MinAvailableRamMb
            max_process_commit_mb = if ($MaxProcessCommitMb -gt 0) { $MaxProcessCommitMb } else { $RamLimitMb }
            max_pagefile_growth_mb = $MaxPagefileGrowthMb
            cpu_pct = $CpuPercent
            io_limit_mb_s = $IoLimitMbPerSec
            io_spike_samples = $IoSpikeSamples
            vram_limit_mb = $VramLimitMb
            timeout_seconds = $TimeoutSeconds
            model_offload_allowed = $false
            cuda_allocator_warmup_skipped = $SkipCudaAllocatorWarmup
        }
        cleanup = $cleanup
        finished_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    }
    $summaryPath = Join-Path $OutputRoot ("launcher_summary_" + $stamp + ".json")
    Write-Json -Path $summaryPath -Payload $summary
    $summary | ConvertTo-Json -Depth 12
    if ($process.ExitCode -ne 0) {
        exit 2
    }
}
finally {
    Pop-Location
}
