[CmdletBinding()]
param(
    [string]$ConfigPath = "experiments/storyworld_curriculum_v1/provisional_local_campaign_v1.json",
    [int]$RamLimitMb = 1024,
    [int]$CpuPercent = 25,
    [int]$IoLimitMbPerSecond = 20,
    [int]$TimeoutSeconds = 1800,
    [int]$PollSeconds = 1
)

$ErrorActionPreference = "Stop"

if ($RamLimitMb -lt 512) { throw "RamLimitMb must be at least 512." }
if ($CpuPercent -lt 1 -or $CpuPercent -gt 100) { throw "CpuPercent must be in [1, 100]." }
if ($IoLimitMbPerSecond -lt 1) { throw "IoLimitMbPerSecond must be positive." }
if ($TimeoutSeconds -lt 30) { throw "TimeoutSeconds must be at least 30." }
if ($PollSeconds -lt 1 -or $PollSeconds -gt 30) { throw "PollSeconds must be in [1, 30]." }

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class StoryworldCorpusJobNative {
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
    [System.IO.File]::WriteAllText(
        $Path,
        (($Payload | ConvertTo-Json -Depth 20) + "`n"),
        $encoding
    )
}

function Set-JobInformation {
    param([IntPtr]$Job, $Value, [int]$InfoClass)
    $size = [System.Runtime.InteropServices.Marshal]::SizeOf($Value)
    $pointer = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size)
    try {
        [System.Runtime.InteropServices.Marshal]::StructureToPtr($Value, $pointer, $false)
        $ok = [StoryworldCorpusJobNative]::SetInformationJobObject(
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
    $job = [StoryworldCorpusJobNative]::CreateJobObject([IntPtr]::Zero, $Name)
    if ($job -eq [IntPtr]::Zero) { throw "CreateJobObject failed." }

    $memory = New-Object StoryworldCorpusJobNative+JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    $memory.BasicLimitInformation.LimitFlags = (
        [StoryworldCorpusJobNative]::JOB_OBJECT_LIMIT_PROCESS_MEMORY -bor
        [StoryworldCorpusJobNative]::JOB_OBJECT_LIMIT_JOB_MEMORY
    )
    $memory.ProcessMemoryLimit = [UIntPtr]$MemoryLimitBytes
    $memory.JobMemoryLimit = [UIntPtr]$MemoryLimitBytes
    Set-JobInformation `
        -Job $job `
        -Value $memory `
        -InfoClass ([StoryworldCorpusJobNative]::JobObjectExtendedLimitInformation)

    $cpu = New-Object StoryworldCorpusJobNative+JOBOBJECT_CPU_RATE_CONTROL_INFORMATION
    $cpu.ControlFlags = (
        [StoryworldCorpusJobNative]::JOB_OBJECT_CPU_RATE_CONTROL_ENABLE -bor
        [StoryworldCorpusJobNative]::JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
    )
    $cpu.CpuRate = $CpuRate
    Set-JobInformation `
        -Job $job `
        -Value $cpu `
        -InfoClass ([StoryworldCorpusJobNative]::JobObjectCpuRateControlInformation)

    $current = [System.Diagnostics.Process]::GetCurrentProcess()
    if (-not [StoryworldCorpusJobNative]::AssignProcessToJobObject($job, $current.Handle)) {
        $errorCode = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
        throw "AssignProcessToJobObject failed with Win32 error $errorCode."
    }
    return $job
}

function Get-IoBytes {
    param([System.Diagnostics.Process]$Process)
    if ($Process.HasExited) { return 0.0 }
    $counters = New-Object StoryworldCorpusJobNative+IO_COUNTERS
    if (-not [StoryworldCorpusJobNative]::GetProcessIoCounters($Process.Handle, [ref]$counters)) {
        return 0.0
    }
    return [double]($counters.ReadTransferCount + $counters.WriteTransferCount)
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

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedConfig = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ConfigPath))
$config = Get-Content -Raw -LiteralPath $resolvedConfig | ConvertFrom-Json
$declared = $config.resource_budget
if ([int]$declared.ram_limit_mb -ne $RamLimitMb) { throw "RAM cap drifted from campaign config." }
if ([int]$declared.cpu_percent -ne $CpuPercent) { throw "CPU cap drifted from campaign config." }
if ([int]$declared.io_limit_mb_per_second -ne $IoLimitMbPerSecond) { throw "I/O cap drifted from campaign config." }
if ([int]$declared.wall_clock_seconds -ne $TimeoutSeconds) { throw "Timeout drifted from campaign config." }
if ([int]$declared.parallel_workers -ne 1) { throw "Only one generation worker is allowed." }

$outputDir = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $config.output_dir))
$resourceReceiptPath = "$outputDir.resource.json"
if (Test-Path -LiteralPath $outputDir) { throw "Output directory already exists: $outputDir" }
if (Test-Path -LiteralPath $resourceReceiptPath) { throw "Resource receipt already exists: $resourceReceiptPath" }

$stdoutPath = [System.IO.Path]::GetTempFileName()
$stderrPath = [System.IO.Path]::GetTempFileName()
$summary = [ordered]@{
    schema_version = "storyworld_provisional_resource_receipt_v1"
    campaign_id = $config.campaign_id
    status = "preparing"
    started_at_utc = ([DateTimeOffset]::UtcNow).ToString("o")
    finished_at_utc = $null
    caps = @{
        ram_mb = $RamLimitMb
        ram_enforcement = "windows_job_object_hard_process_and_job_commit"
        cpu_percent = $CpuPercent
        cpu_enforcement = "windows_job_object_hard_rate"
        io_mb_s = $IoLimitMbPerSecond
        io_enforcement = "pid_scoped_abort_after_three_consecutive_samples"
        timeout_seconds = $TimeoutSeconds
        parallel_workers = 1
    }
    peak_ram_mb = 0.0
    average_ram_mb = 0.0
    peak_io_mb_s = 0.0
    average_cpu_percent_total_capacity = 0.0
    samples = 0
    process_exit_code = $null
    abort_reason = ""
    output_dir = $outputDir
    output_manifest_sha256 = $null
    cleanup = @{
        root_pid = $null
        scoped_tree_stopped = $false
        unrelated_processes_touched = 0
    }
}

$job = Enter-CappedJob `
    -Name ("storyworld-corpus-" + $config.campaign_id) `
    -MemoryLimitBytes ([UInt64]($RamLimitMb * 1MB)) `
    -CpuRate ([UInt32]($CpuPercent * 100))

$arguments = @(
    "scripts/generate_provisional_storyworld_corpus.py",
    "--config",
    $resolvedConfig
)
$process = $null
$previous = $null
$previousAt = [DateTimeOffset]::UtcNow
$ramTotal = 0.0
$cpuTotal = 0.0
$ioStreak = 0
$aborted = $false
$logicalProcessorCount = [Environment]::ProcessorCount
try {
    $process = Start-Process `
        -FilePath "python" `
        -ArgumentList $arguments `
        -WorkingDirectory $repoRoot `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath
    $summary.cleanup.root_pid = $process.Id
    $inJob = $false
    if (
        -not [StoryworldCorpusJobNative]::IsProcessInJob($process.Handle, $job, [ref]$inJob) -or
        -not $inJob
    ) {
        Stop-ScopedProcessTree -RootPid $process.Id
        throw "Generator did not inherit the cap job."
    }
    $summary.status = "running"

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
        $ioMbPerSecond = 0.0
        if ($null -ne $previous) {
            $seconds = [math]::Max(0.001, ($now - $previousAt).TotalSeconds)
            $cpuPercentSample = [math]::Round(
                100.0 * [math]::Max(0.0, $stats.CPU - $previous.cpu) /
                    $seconds / $logicalProcessorCount,
                2
            )
            $ioMbPerSecond = [math]::Round(
                [math]::Max(0.0, $ioBytes - $previous.io) / 1MB / $seconds,
                2
            )
        }
        $summary.peak_ram_mb = [math]::Max([double]$summary.peak_ram_mb, $ramMb)
        $summary.peak_io_mb_s = [math]::Max(
            [double]$summary.peak_io_mb_s,
            $ioMbPerSecond
        )
        $summary.samples += 1
        $ramTotal += $ramMb
        $cpuTotal += $cpuPercentSample
        $summary.average_ram_mb = [math]::Round($ramTotal / $summary.samples, 2)
        $summary.average_cpu_percent_total_capacity = [math]::Round(
            $cpuTotal / $summary.samples,
            2
        )
        if ($ioMbPerSecond -gt $IoLimitMbPerSecond) {
            $ioStreak += 1
        } else {
            $ioStreak = 0
        }
        if ($ioStreak -ge 3) {
            $summary.abort_reason = "io_cap_exceeded_three_samples"
            $aborted = $true
            break
        }
        $previous = @{
            cpu = [double]$stats.CPU
            io = $ioBytes
        }
        $previousAt = $now
    }

    if ($aborted -and -not $process.HasExited) {
        Stop-ScopedProcessTree -RootPid $process.Id
        $summary.cleanup.scoped_tree_stopped = $true
        $summary.status = "aborted"
    } else {
        $process.WaitForExit()
        $summary.process_exit_code = $process.ExitCode
        if ($process.ExitCode -eq 0) {
            $summary.status = "completed"
            $manifestPath = Join-Path $outputDir "run_manifest.json"
            if (-not (Test-Path -LiteralPath $manifestPath)) {
                throw "Generator exited successfully without a run manifest."
            }
            $summary.output_manifest_sha256 = (
                Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath
            ).Hash.ToLowerInvariant()
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
    Write-Json -Path $resourceReceiptPath -Payload $summary
    $stderrText = Get-Content -Raw -LiteralPath $stderrPath -ErrorAction SilentlyContinue
    if ($stderrText) { Write-Warning $stderrText }
    Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
}

$summary | ConvertTo-Json -Depth 20
