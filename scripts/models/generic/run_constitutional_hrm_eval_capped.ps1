[CmdletBinding()]
param(
    [string]$EvaluationTaskId = "constitutional_hrm_eval_matrix_v1",
    [string]$OutputDir = "",
    [int]$RamLimitMb = 2048,
    [int]$CpuPercent = 25,
    [int]$IoLimitMbPerSec = 20,
    [int]$TimeoutSeconds = 1800,
    [int]$PollSeconds = 1,
    [int]$BatchSize = 32
)

$ErrorActionPreference = "Stop"

if ($RamLimitMb -lt 512) { throw "RamLimitMb must be at least 512." }
if ($CpuPercent -lt 1 -or $CpuPercent -gt 100) { throw "CpuPercent must be in [1, 100]." }
if ($IoLimitMbPerSec -lt 1) { throw "IoLimitMbPerSec must be positive." }
if ($TimeoutSeconds -lt 10) { throw "TimeoutSeconds must be at least 10." }
if ($PollSeconds -lt 1) { throw "PollSeconds must be positive." }
if ($BatchSize -lt 1 -or $BatchSize -gt 128) { throw "BatchSize must be in [1, 128]." }

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class ConstitutionalHrmEvalJobNative {
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  public static extern IntPtr CreateJobObject(IntPtr attributes, string name);

  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint length);

  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool GetProcessIoCounters(IntPtr process, out IO_COUNTERS counters);

  public const int JobObjectExtendedLimitInformation = 9;
  public const int JobObjectCpuRateControlInformation = 15;
  public const uint JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100;
  public const uint JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200;
  public const uint JOB_OBJECT_CPU_RATE_CONTROL_ENABLE = 0x1;
  public const uint JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x4;

  [StructLayout(LayoutKind.Sequential)]
  public struct IO_COUNTERS {
    public ulong ReadOperationCount;
    public ulong WriteOperationCount;
    public ulong OtherOperationCount;
    public ulong ReadTransferCount;
    public ulong WriteTransferCount;
    public ulong OtherTransferCount;
  }

  [StructLayout(LayoutKind.Sequential)]
  public struct JOBOBJECT_BASIC_LIMIT_INFORMATION {
    public long PerProcessUserTimeLimit;
    public long PerJobUserTimeLimit;
    public uint LimitFlags;
    public UIntPtr MinimumWorkingSetSize;
    public UIntPtr MaximumWorkingSetSize;
    public uint ActiveProcessLimit;
    public long Affinity;
    public uint PriorityClass;
    public uint SchedulingClass;
  }

  [StructLayout(LayoutKind.Sequential)]
  public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION {
    public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
    public IO_COUNTERS IoInfo;
    public UIntPtr ProcessMemoryLimit;
    public UIntPtr JobMemoryLimit;
    public UIntPtr PeakProcessMemoryUsed;
    public UIntPtr PeakJobMemoryUsed;
  }

  [StructLayout(LayoutKind.Sequential)]
  public struct JOBOBJECT_CPU_RATE_CONTROL_INFORMATION {
    public uint ControlFlags;
    public uint CpuRate;
  }
}
'@

function Write-Json {
    param([string]$Path, $Payload)
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText(
        $Path,
        (($Payload | ConvertTo-Json -Depth 30) + "`n"),
        $encoding
    )
}

function Append-Jsonl {
    param([string]$Path, $Payload)
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::AppendAllText(
        $Path,
        (($Payload | ConvertTo-Json -Depth 30 -Compress) + "`n"),
        $encoding
    )
}

function Set-JobInformation {
    param([IntPtr]$Job, $Value, [int]$InfoClass)
    $size = [System.Runtime.InteropServices.Marshal]::SizeOf($Value)
    $pointer = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size)
    try {
        [System.Runtime.InteropServices.Marshal]::StructureToPtr($Value, $pointer, $false)
        $ok = [ConstitutionalHrmEvalJobNative]::SetInformationJobObject(
            $Job,
            $InfoClass,
            $pointer,
            [uint32]$size
        )
        if (-not $ok) {
            $errorCode = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
            throw "SetInformationJobObject($InfoClass) failed with Win32 error $errorCode."
        }
    } finally {
        [System.Runtime.InteropServices.Marshal]::FreeHGlobal($pointer)
    }
}

function Enter-CappedJob {
    param([string]$Name, [UInt64]$MemoryLimitBytes, [UInt32]$CpuRate)
    $job = [ConstitutionalHrmEvalJobNative]::CreateJobObject([IntPtr]::Zero, $Name)
    if ($job -eq [IntPtr]::Zero) { throw "CreateJobObject failed." }

    $memory = New-Object ConstitutionalHrmEvalJobNative+JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    $memory.BasicLimitInformation.LimitFlags = (
        [ConstitutionalHrmEvalJobNative]::JOB_OBJECT_LIMIT_PROCESS_MEMORY -bor
        [ConstitutionalHrmEvalJobNative]::JOB_OBJECT_LIMIT_JOB_MEMORY
    )
    $memory.ProcessMemoryLimit = [UIntPtr]$MemoryLimitBytes
    $memory.JobMemoryLimit = [UIntPtr]$MemoryLimitBytes
    Set-JobInformation `
        -Job $job `
        -Value $memory `
        -InfoClass ([ConstitutionalHrmEvalJobNative]::JobObjectExtendedLimitInformation)

    $cpu = New-Object ConstitutionalHrmEvalJobNative+JOBOBJECT_CPU_RATE_CONTROL_INFORMATION
    $cpu.ControlFlags = (
        [ConstitutionalHrmEvalJobNative]::JOB_OBJECT_CPU_RATE_CONTROL_ENABLE -bor
        [ConstitutionalHrmEvalJobNative]::JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
    )
    $cpu.CpuRate = $CpuRate
    Set-JobInformation `
        -Job $job `
        -Value $cpu `
        -InfoClass ([ConstitutionalHrmEvalJobNative]::JobObjectCpuRateControlInformation)

    $current = [System.Diagnostics.Process]::GetCurrentProcess()
    if (-not [ConstitutionalHrmEvalJobNative]::AssignProcessToJobObject($job, $current.Handle)) {
        $errorCode = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw "AssignProcessToJobObject failed before evaluator launch with Win32 error $errorCode."
    }
    return $job
}

function Stop-ScopedProcessTree {
    param([int]$RootPid)
    $children = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.ParentProcessId -eq $RootPid }
    )
    foreach ($child in $children) {
        Stop-ScopedProcessTree -RootPid ([int]$child.ProcessId)
    }
    Stop-Process -Id $RootPid -Force -ErrorAction SilentlyContinue
}

function Get-IoBytes {
    param([System.Diagnostics.Process]$Process)
    try {
        if ($Process.HasExited) { return 0.0 }
        $handle = $Process.Handle
        if ($handle -eq [IntPtr]::Zero) { return 0.0 }
    } catch {
        return 0.0
    }
    $counters = New-Object ConstitutionalHrmEvalJobNative+IO_COUNTERS
    if (-not [ConstitutionalHrmEvalJobNative]::GetProcessIoCounters($handle, [ref]$counters)) {
        return 0.0
    }
    return [double]($counters.ReadTransferCount + $counters.WriteTransferCount)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
if (-not $OutputDir) {
    $OutputDir = Join-Path $repoRoot "artifacts\constitutional_hrm_eval_matrix_v1\run"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$opsDir = Join-Path $OutputDir "_ops"
$summaryPath = Join-Path $opsDir "resource_summary.json"
$planPath = Join-Path $opsDir "evaluation_plan.json"
$eventsPath = Join-Path $opsDir "resource_events.jsonl"
$stdoutPath = Join-Path $opsDir "stdout.log"
$stderrPath = Join-Path $opsDir "stderr.log"
New-Item -ItemType Directory -Force -Path $opsDir | Out-Null

$encoding = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($eventsPath, "", $encoding)
[System.IO.File]::WriteAllText($stdoutPath, "", $encoding)
[System.IO.File]::WriteAllText($stderrPath, "", $encoding)

$plan = [ordered]@{
    schema_version = "constitutional_hrm_eval_resource_plan_v1"
    evaluation_task_id = $EvaluationTaskId
    device = "cpu"
    caps = @{
        ram_mb = $RamLimitMb
        ram_enforcement = "windows_job_object_hard_process_and_job_commit"
        cpu_percent = $CpuPercent
        cpu_enforcement = "windows_job_object_hard_rate"
        io_mb_s = $IoLimitMbPerSec
        io_enforcement = "pid_scoped_monitor_abort_after_three_consecutive_samples"
        timeout_seconds = $TimeoutSeconds
    }
    chunking = @{
        batch_size = $BatchSize
        maximum_batch_size = 128
        progress_receipts = "suite boundaries plus resource samples"
    }
    recursion = @{
        max_cycles = 2
        max_nested_depth = 1
        max_nodes = 120
        max_choices_per_node = 4
        max_trajectories = 500
    }
}
Write-Json -Path $planPath -Payload $plan

$summary = [ordered]@{
    schema_version = "constitutional_hrm_eval_resource_summary_v1"
    evaluation_task_id = $EvaluationTaskId
    status = "preparing"
    plan_path = $planPath
    started_at_utc = ([DateTimeOffset]::UtcNow).ToString("o")
    finished_at_utc = $null
    caps = $plan.caps
    root_pid = $null
    process_exit_code = $null
    abort_reason = ""
    peak_ram_mb = 0.0
    avg_ram_mb = 0.0
    peak_io_mb_s = 0.0
    avg_cpu_percent_total_capacity = 0.0
    samples = 0
    cleanup = @{
        scoped_tree_stopped = $false
        unrelated_processes_touched = 0
        gpu_memory_before_mb = $null
        gpu_memory_after_mb = $null
    }
}
Write-Json -Path $summaryPath -Payload $summary

function Get-GpuMemoryUsed {
    try {
        $value = & nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null |
            Select-Object -First 1
        if ($null -ne $value) { return [double]$value }
    } catch {
        return $null
    }
    return $null
}

$summary.cleanup.gpu_memory_before_mb = Get-GpuMemoryUsed
$job = Enter-CappedJob `
    -Name ("constitutional-hrm-eval-" + $EvaluationTaskId) `
    -MemoryLimitBytes ([UInt64]($RamLimitMb * 1MB)) `
    -CpuRate ([UInt32]($CpuPercent * 100))
Append-Jsonl -Path $eventsPath -Payload @{
    ts = ([DateTimeOffset]::UtcNow).ToString("o")
    event = "caps_entered"
    caps = $plan.caps
}

$arguments = @(
    ".\scripts\evaluate_constitutional_hrm_matrix.py",
    "--training-task-id", $EvaluationTaskId,
    "--output-dir", $OutputDir,
    "--batch-size", "$BatchSize",
    "--torch-threads", "2",
    "--max-cycles", "2",
    "--max-nested-depth", "1",
    "--max-nodes", "120",
    "--max-choices-per-node", "4",
    "--max-trajectories", "500"
)

$process = $null
$abortReason = ""
$ramSamples = New-Object System.Collections.Generic.List[double]
$cpuSamples = New-Object System.Collections.Generic.List[double]
$ioSamples = New-Object System.Collections.Generic.List[double]
$ioBreaches = 0
$started = [DateTimeOffset]::UtcNow
$lastSample = $started
$lastCpu = 0.0
$lastIo = 0.0

try {
    $process = Start-Process `
        -FilePath "python" `
        -ArgumentList $arguments `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -WindowStyle Hidden `
        -PassThru
    $summary.root_pid = $process.Id
    $summary.status = "running"
    Write-Json -Path $summaryPath -Payload $summary
    Append-Jsonl -Path $eventsPath -Payload @{
        ts = ([DateTimeOffset]::UtcNow).ToString("o")
        event = "evaluator_started"
        pid = $process.Id
    }

    while (-not $process.HasExited) {
        Start-Sleep -Seconds $PollSeconds
        $process.Refresh()
        $now = [DateTimeOffset]::UtcNow
        $elapsed = [Math]::Max(0.001, ($now - $lastSample).TotalSeconds)
        $wall = ($now - $started).TotalSeconds
        if ($wall -gt $TimeoutSeconds) {
            $abortReason = "timeout"
            break
        }

        $ramMb = [Math]::Round($process.WorkingSet64 / 1MB, 3)
        $cpuNow = $process.TotalProcessorTime.TotalSeconds
        $cpuPercent = [Math]::Max(
            0.0,
            (($cpuNow - $lastCpu) / $elapsed / [Environment]::ProcessorCount) * 100.0
        )
        $ioNow = Get-IoBytes -Process $process
        $ioMbPerSec = [Math]::Max(0.0, (($ioNow - $lastIo) / 1MB) / $elapsed)
        $ramSamples.Add($ramMb)
        $cpuSamples.Add($cpuPercent)
        $ioSamples.Add($ioMbPerSec)

        if ($ioMbPerSec -gt $IoLimitMbPerSec) {
            $ioBreaches += 1
        } else {
            $ioBreaches = 0
        }
        if ($ioBreaches -ge 3) {
            $abortReason = "sustained_io_cap_breach"
            break
        }

        Append-Jsonl -Path $eventsPath -Payload @{
            ts = $now.ToString("o")
            event = "resource_sample"
            ram_mb = $ramMb
            cpu_percent_total_capacity = [Math]::Round($cpuPercent, 3)
            io_mb_s = [Math]::Round($ioMbPerSec, 3)
            wall_seconds = [Math]::Round($wall, 3)
        }
        $lastSample = $now
        $lastCpu = $cpuNow
        $lastIo = $ioNow
    }

    if ($abortReason) {
        Stop-ScopedProcessTree -RootPid $process.Id
        $summary.cleanup.scoped_tree_stopped = $true
        $summary.status = "aborted"
        Append-Jsonl -Path $eventsPath -Payload @{
            ts = ([DateTimeOffset]::UtcNow).ToString("o")
            event = "abort"
            reason = $abortReason
            root_pid = $process.Id
        }
    } else {
        $process.WaitForExit()
        $summary.process_exit_code = $process.ExitCode
        $summary.status = if ($process.ExitCode -eq 0) { "completed" } else { "failed" }
    }
} catch {
    $abortReason = "wrapper_error: $($_.Exception.Message)"
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-ScopedProcessTree -RootPid $process.Id
        $summary.cleanup.scoped_tree_stopped = $true
    }
    $summary.status = "failed"
} finally {
    $summary.abort_reason = $abortReason
    $summary.finished_at_utc = ([DateTimeOffset]::UtcNow).ToString("o")
    $summary.samples = $ramSamples.Count
    if ($ramSamples.Count -gt 0) {
        $summary.peak_ram_mb = ($ramSamples | Measure-Object -Maximum).Maximum
        $summary.avg_ram_mb = [Math]::Round(($ramSamples | Measure-Object -Average).Average, 3)
        $summary.peak_io_mb_s = [Math]::Round(($ioSamples | Measure-Object -Maximum).Maximum, 3)
        $summary.avg_cpu_percent_total_capacity = [Math]::Round(
            ($cpuSamples | Measure-Object -Average).Average,
            3
        )
    }
    $summary.cleanup.gpu_memory_after_mb = Get-GpuMemoryUsed
    Write-Json -Path $summaryPath -Payload $summary
    Append-Jsonl -Path $eventsPath -Payload @{
        ts = ([DateTimeOffset]::UtcNow).ToString("o")
        event = "cleanup_audit"
        cleanup = $summary.cleanup
        status = $summary.status
    }
}

Write-Output ($summary | ConvertTo-Json -Depth 30)
if ($summary.status -ne "completed") { exit 1 }
exit 0
