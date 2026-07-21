[CmdletBinding()]
param(
    [string]$TrainingTaskId = "constitutional_hrm_smoke_v1",
    [string]$OutputRoot = "",
    [int]$RamLimitMb = 2048,
    [int]$CpuPercent = 25,
    [int]$IoLimitMbPerSec = 20,
    [int]$TimeoutSeconds = 600,
    [int]$PollSeconds = 1,
    [int]$Steps = 100,
    [int]$CheckpointSteps = 25,
    [int]$CheckpointSeconds = 60,
    [string]$ChunkStrategy = "matched_arm_sequential_scenario_family_chunks",
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

if ($RamLimitMb -lt 512) { throw "RamLimitMb must be at least 512." }
if ($CpuPercent -lt 1 -or $CpuPercent -gt 100) { throw "CpuPercent must be in [1, 100]." }
if ($IoLimitMbPerSec -lt 1) { throw "IoLimitMbPerSec must be positive." }
if ($TimeoutSeconds -lt 10) { throw "TimeoutSeconds must be at least 10." }
if ($Steps -lt 1) { throw "Steps must be positive." }

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class ConstitutionalHrmJobNative {
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  public static extern IntPtr CreateJobObject(IntPtr attributes, string name);

  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint length);

  [DllImport("kernel32.dll", SetLastError = true)]
  public static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool result);

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
    [System.IO.File]::WriteAllText($Path, ($Payload | ConvertTo-Json -Depth 20), $encoding)
}

function Append-Jsonl {
    param([string]$Path, $Payload)
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $line = ($Payload | ConvertTo-Json -Depth 20 -Compress) + "`n"
    [System.IO.File]::AppendAllText($Path, $line, $encoding)
}

function Set-JobInformation {
    param([IntPtr]$Job, $Value, [int]$InfoClass)
    $size = [System.Runtime.InteropServices.Marshal]::SizeOf($Value)
    $pointer = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size)
    try {
        [System.Runtime.InteropServices.Marshal]::StructureToPtr($Value, $pointer, $false)
        if (-not [ConstitutionalHrmJobNative]::SetInformationJobObject($Job, $InfoClass, $pointer, [uint32]$size)) {
            $errorCode = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
            throw "SetInformationJobObject($InfoClass) failed with Win32 error $errorCode."
        }
    } finally {
        [System.Runtime.InteropServices.Marshal]::FreeHGlobal($pointer)
    }
}

function Enter-CappedJob {
    param([string]$Name, [UInt64]$MemoryLimitBytes, [UInt32]$CpuRate)
    $job = [ConstitutionalHrmJobNative]::CreateJobObject([IntPtr]::Zero, $Name)
    if ($job -eq [IntPtr]::Zero) { throw "CreateJobObject failed." }

    $memory = New-Object ConstitutionalHrmJobNative+JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    $memory.BasicLimitInformation.LimitFlags = [ConstitutionalHrmJobNative]::JOB_OBJECT_LIMIT_PROCESS_MEMORY -bor [ConstitutionalHrmJobNative]::JOB_OBJECT_LIMIT_JOB_MEMORY
    $memory.ProcessMemoryLimit = [UIntPtr]$MemoryLimitBytes
    $memory.JobMemoryLimit = [UIntPtr]$MemoryLimitBytes
    Set-JobInformation -Job $job -Value $memory -InfoClass ([ConstitutionalHrmJobNative]::JobObjectExtendedLimitInformation)

    $cpu = New-Object ConstitutionalHrmJobNative+JOBOBJECT_CPU_RATE_CONTROL_INFORMATION
    $cpu.ControlFlags = [ConstitutionalHrmJobNative]::JOB_OBJECT_CPU_RATE_CONTROL_ENABLE -bor [ConstitutionalHrmJobNative]::JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
    $cpu.CpuRate = $CpuRate
    Set-JobInformation -Job $job -Value $cpu -InfoClass ([ConstitutionalHrmJobNative]::JobObjectCpuRateControlInformation)

    $current = [System.Diagnostics.Process]::GetCurrentProcess()
    if (-not [ConstitutionalHrmJobNative]::AssignProcessToJobObject($job, $current.Handle)) {
        $errorCode = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw "AssignProcessToJobObject failed before trainer launch with Win32 error $errorCode."
    }
    return $job
}

function Stop-ScopedProcessTree {
    param([int]$RootPid)
    $children = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.ParentProcessId -eq $RootPid })
    foreach ($child in $children) { Stop-ScopedProcessTree -RootPid ([int]$child.ProcessId) }
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
    $counters = New-Object ConstitutionalHrmJobNative+IO_COUNTERS
    if (-not [ConstitutionalHrmJobNative]::GetProcessIoCounters($handle, [ref]$counters)) { return 0.0 }
    return [double]($counters.ReadTransferCount + $counters.WriteTransferCount)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
if (-not $OutputRoot) { $OutputRoot = Join-Path $repoRoot "artifacts\constitutional_hrm_v1" }
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$opsDir = Join-Path $OutputRoot ("ops\" + $TrainingTaskId)
$runDir = Join-Path $OutputRoot ("runs\" + $TrainingTaskId)
$summaryPath = Join-Path $opsDir "summary.json"
$planPath = Join-Path $opsDir "trainer_plan.json"
$eventsPath = Join-Path $opsDir "events.jsonl"
$stdoutPath = Join-Path $opsDir "stdout.log"
$stderrPath = Join-Path $opsDir "stderr.log"
New-Item -ItemType Directory -Force -Path $opsDir | Out-Null
if (Test-Path -LiteralPath $eventsPath) { Remove-Item -LiteralPath $eventsPath -Force }

$plan = [ordered]@{
    schema_version = "constitutional_hrm_trainer_plan_v1"
    training_task_id = $TrainingTaskId
    mode = if ($ValidateOnly) { "validation_only" } else { "train" }
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
    checkpoint_interval = @{ steps = $CheckpointSteps; seconds = $CheckpointSeconds }
    chunk_strategy = $ChunkStrategy
    steps_per_arm = if ($ValidateOnly) { 0 } else { $Steps }
    arms = @("constitutional", "utility", "shuffled")
}
Write-Json -Path $planPath -Payload $plan

$summary = [ordered]@{
    schema_version = "constitutional_hrm_resource_summary_v1"
    training_task_id = $TrainingTaskId
    status = "preparing"
    plan_path = $planPath
    trainer_summary_path = (Join-Path $runDir "summary.json")
    started_at_utc = ([DateTimeOffset]::UtcNow).ToString("o")
    finished_at_utc = $null
    caps = $plan.caps
    checkpoint_interval = $plan.checkpoint_interval
    chunk_strategy = $ChunkStrategy
    peak_ram_mb = 0.0
    avg_ram_mb = 0.0
    peak_io_mb_s = 0.0
    avg_cpu_percent_total_capacity = 0.0
    samples = 0
    process_exit_code = $null
    abort_reason = ""
    cleanup = @{ root_pid = $null; scoped_tree_stopped = $false; unrelated_processes_touched = 0 }
}
Write-Json -Path $summaryPath -Payload $summary

$job = Enter-CappedJob -Name ("constitutional-hrm-" + $TrainingTaskId) -MemoryLimitBytes ([UInt64]($RamLimitMb * 1MB)) -CpuRate ([UInt32]($CpuPercent * 100))
Append-Jsonl -Path $eventsPath -Payload @{ ts = ([DateTimeOffset]::UtcNow).ToString("o"); event = "caps_entered"; caps = $plan.caps }

$arguments = @(
    ".\scripts\train_constitutional_hrm_smoke.py",
    "--training-task-id", $TrainingTaskId,
    "--output-root", $OutputRoot,
    "--steps", "$Steps",
    "--checkpoint-steps", "$CheckpointSteps",
    "--checkpoint-seconds", "$CheckpointSeconds",
    "--arm-timeout-seconds", "$([math]::Max(30, [math]::Floor($TimeoutSeconds / 3)))",
    "--torch-threads", "2"
)
if ($ValidateOnly) { $arguments += "--validate-only" }

$process = $null
$previous = $null
$previousAt = [DateTimeOffset]::UtcNow
$ramSum = 0.0
$cpuSum = 0.0
$ioStreak = 0
$aborted = $false
$logicalProcessorCount = [Environment]::ProcessorCount
try {
    $process = Start-Process -FilePath "python" -ArgumentList $arguments -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    $summary.cleanup.root_pid = $process.Id
    $inJob = $false
    if (-not [ConstitutionalHrmJobNative]::IsProcessInJob($process.Handle, $job, [ref]$inJob) -or -not $inJob) {
        Stop-ScopedProcessTree -RootPid $process.Id
        throw "Trainer did not inherit the cap job."
    }
    $summary.status = "running"
    Write-Json -Path $summaryPath -Payload $summary
    Append-Jsonl -Path $eventsPath -Payload @{ ts = ([DateTimeOffset]::UtcNow).ToString("o"); event = "trainer_start"; pid = $process.Id }

    while (-not $process.HasExited) {
        Start-Sleep -Seconds $PollSeconds
        $now = [DateTimeOffset]::UtcNow
        $elapsed = ($now - [DateTimeOffset]::Parse($summary.started_at_utc)).TotalSeconds
        if ($elapsed -gt $TimeoutSeconds) {
            $summary.abort_reason = "timeout"
            $aborted = $true
            break
        }
        $process.Refresh()
        $stats = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
        if (-not $stats) { break }
        $ramMb = [math]::Round($stats.WorkingSet64 / 1MB, 2)
        $ioBytes = Get-IoBytes -Process $process
        $cpuPercentSample = 0.0
        $ioMbPerSec = 0.0
        if ($previous -ne $null) {
            $dt = [math]::Max(0.001, ($now - $previousAt).TotalSeconds)
            $cpuPercentSample = [math]::Round(100.0 * [math]::Max(0.0, $stats.CPU - $previous.cpu) / $dt / $logicalProcessorCount, 2)
            $ioMbPerSec = [math]::Round([math]::Max(0.0, $ioBytes - $previous.io) / 1MB / $dt, 2)
        }
        $summary.peak_ram_mb = [math]::Max([double]$summary.peak_ram_mb, $ramMb)
        $summary.peak_io_mb_s = [math]::Max([double]$summary.peak_io_mb_s, $ioMbPerSec)
        $summary.samples += 1
        $ramSum += $ramMb
        $cpuSum += $cpuPercentSample
        $summary.avg_ram_mb = [math]::Round($ramSum / $summary.samples, 2)
        $summary.avg_cpu_percent_total_capacity = [math]::Round($cpuSum / $summary.samples, 2)
        if ($ioMbPerSec -gt $IoLimitMbPerSec) { $ioStreak += 1 } else { $ioStreak = 0 }
        Append-Jsonl -Path $eventsPath -Payload @{ ts = $now.ToString("o"); event = "poll"; ram_mb = $ramMb; cpu_percent_total_capacity = $cpuPercentSample; io_mb_s = $ioMbPerSec }
        if ($ioStreak -ge 3) {
            $summary.abort_reason = "io_cap_exceeded_three_samples"
            $aborted = $true
            break
        }
        $previous = @{ cpu = [double]$stats.CPU; io = $ioBytes }
        $previousAt = $now
        Write-Json -Path $summaryPath -Payload $summary
    }

    if ($aborted -and $process -and -not $process.HasExited) {
        Stop-ScopedProcessTree -RootPid $process.Id
        $summary.cleanup.scoped_tree_stopped = $true
        $summary.status = "aborted"
    } else {
        $process.WaitForExit()
        $summary.process_exit_code = $process.ExitCode
        if ($process.ExitCode -eq 0) {
            $summary.status = if ($ValidateOnly) { "validated" } else { "completed" }
        } else {
            $summary.status = "failed"
            $summary.abort_reason = "exit_code_$($process.ExitCode)"
        }
    }
} catch {
    if ($process -and -not $process.HasExited) {
        Stop-ScopedProcessTree -RootPid $process.Id
        $summary.cleanup.scoped_tree_stopped = $true
    }
    $summary.status = "failed"
    $summary.abort_reason = $_.Exception.Message
    throw
} finally {
    $summary.finished_at_utc = ([DateTimeOffset]::UtcNow).ToString("o")
    Write-Json -Path $summaryPath -Payload $summary
    Append-Jsonl -Path $eventsPath -Payload @{ ts = $summary.finished_at_utc; event = "finish"; status = $summary.status; abort_reason = $summary.abort_reason; peak_ram_mb = $summary.peak_ram_mb; peak_io_mb_s = $summary.peak_io_mb_s }
}

$summary | ConvertTo-Json -Depth 20
