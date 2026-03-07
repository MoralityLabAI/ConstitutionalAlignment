param(
  [string]$AdictRoot = "C:\projects\Adict\Adict\addict_probe_lab\addict_probe_lab",
  [string]$PlanPath = "C:\projects\Adict\Adict\addict_probe_lab\addict_probe_lab\constitutional_storyworld_loop\iteration_plan.example.json",
  [string]$PythonExe = "python",
  [string]$ReceiptDir = "C:\projects\ConstitutionalAlignment\ConstitutionalAlignment\constitutional-harness\ops\receipts",
  [switch]$Wait
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $ReceiptDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$receiptPath = Join-Path $ReceiptDir ("storyworld_autoloop_" + $stamp + ".json")

$scriptPath = Join-Path $AdictRoot "scripts\run_constitutional_autoloop.py"
if (-not (Test-Path -LiteralPath $scriptPath)) {
  throw "Missing script: $scriptPath"
}

if (-not (Test-Path -LiteralPath $PlanPath)) {
  throw "Missing plan: $PlanPath"
}

$args = @($scriptPath, "--plan", $PlanPath)
$receipt = [ordered]@{
  ts_utc = (Get-Date).ToUniversalTime().ToString("o")
  adict_root = $AdictRoot
  plan_path = $PlanPath
  python = $PythonExe
  wait = [bool]$Wait
  status = "starting"
  process_id = $null
}

if ($Wait) {
  Push-Location $AdictRoot
  try {
    & $PythonExe @args
    if ($LASTEXITCODE -ne 0) {
      $receipt.status = "failed"
      $receipt.exit_code = $LASTEXITCODE
    } else {
      $receipt.status = "completed"
      $receipt.exit_code = 0
    }
  } finally {
    Pop-Location
  }
} else {
  $proc = Start-Process -FilePath $PythonExe -ArgumentList $args -WorkingDirectory $AdictRoot -PassThru
  $receipt.status = "running"
  $receipt.process_id = $proc.Id
}

$receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $receiptPath -Encoding utf8
Write-Host "RECEIPT=$receiptPath"
