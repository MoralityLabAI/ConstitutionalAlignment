param(
  [switch]$StartLocal = $true,
  [switch]$QueueRemote = $true,
  [string]$RunIdPrefix = "qwen35-constitution-series",
  [string]$HostAlias = "mac-ip",
  [string]$LocalScheduleScript = "C:\projects\AICOO\MoralityLab\AICOO\scripts\ml_schedule_qwen35_08b_constitutional_exercise.ps1",
  [string]$RemoteQueueScript = "C:\projects\AICOO\MoralityLab\AICOO\scripts\tmp_queue_remote_const_lora.ps1",
  [string]$ReceiptDir = "C:\projects\ConstitutionalAlignment\ConstitutionalAlignment\constitutional-harness\ops\receipts",
  [switch]$WaitLocal
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $ReceiptDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runId = "$RunIdPrefix-$stamp"
$receiptPath = Join-Path $ReceiptDir ("dual_track_" + $stamp + ".json")

$receipt = [ordered]@{
  ts_utc = (Get-Date).ToUniversalTime().ToString("o")
  run_id = $runId
  local = [ordered]@{
    requested = [bool]$StartLocal
    launched = $false
    process_id = $null
    script = $LocalScheduleScript
    status = "not_requested"
  }
  remote = [ordered]@{
    requested = [bool]$QueueRemote
    reachable = $false
    queued = $false
    script = $RemoteQueueScript
    status = "not_requested"
    output = @()
  }
}

if ($QueueRemote) {
  $receipt.remote.status = "reachability_check"
  & ssh -o BatchMode=yes -o ConnectTimeout=8 $HostAlias "echo MAC_ALIVE:$(hostname):$(date -u +%Y-%m-%dT%H:%M:%SZ)" | Out-Null
  if ($LASTEXITCODE -eq 0) {
    $receipt.remote.reachable = $true
    if (-not (Test-Path -LiteralPath $RemoteQueueScript)) {
      $receipt.remote.status = "queue_script_missing"
    } else {
      $queueOutput = & powershell -ExecutionPolicy Bypass -File $RemoteQueueScript 2>&1
      $receipt.remote.output = @($queueOutput | ForEach-Object { "$_" })
      if ($LASTEXITCODE -eq 0) {
        $receipt.remote.queued = $true
        $receipt.remote.status = "queued"
      } else {
        $receipt.remote.status = "queue_failed"
      }
    }
  } else {
    $receipt.remote.status = "host_unreachable"
  }
}

if ($StartLocal) {
  if (-not (Test-Path -LiteralPath $LocalScheduleScript)) {
    $receipt.local.status = "schedule_script_missing"
  } else {
    $args = @(
      "-ExecutionPolicy", "Bypass",
      "-File", $LocalScheduleScript,
      "-RunId", $runId
    )
    if ($WaitLocal.IsPresent) {
      & powershell @args
      if ($LASTEXITCODE -eq 0) {
        $receipt.local.launched = $true
        $receipt.local.status = "completed"
      } else {
        $receipt.local.status = "failed"
      }
    } else {
      $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $args -PassThru
      $receipt.local.launched = $true
      $receipt.local.process_id = $proc.Id
      $receipt.local.status = "running"
    }
  }
}

$receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $receiptPath -Encoding utf8
Write-Host "RECEIPT=$receiptPath"
Write-Host ("RUN_ID=" + $runId)
