param(
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot "run_jinn_beast_memory_ablation.py"
$arms = @("prompt_skill_control", "jinn_adapter_infused")
$memories = @("full_cross_topic", "topic_local")
$seedIndices = @(0, 1, 2)

foreach ($arm in $arms) {
    foreach ($memory in $memories) {
        foreach ($seedIndex in $seedIndices) {
            $runId = "{0}__{1}__seed_{2:D3}" -f (
                $arm,
                $memory,
                ($seedIndex + 1)
            )
            $runDir = Join-Path $OutputRoot $runId
            $metadataPath = Join-Path $runDir "run_metadata.json"
            if (Test-Path -LiteralPath $metadataPath) {
                $metadata = Get-Content -LiteralPath $metadataPath -Raw |
                    ConvertFrom-Json
                if ($metadata.status -ne "complete") {
                    throw "$runId has non-complete metadata"
                }
                Write-Output "$runId already complete"
                continue
            }

            New-Item -ItemType Directory -Force -Path $runDir | Out-Null
            $arguments = @(
                $runner,
                "--arm", $arm,
                "--memory", $memory,
                "--seed-index", "$seedIndex",
                "--output-root", $OutputRoot
            )
            $messagesPath = Join-Path $runDir "messages.jsonl"
            if (Test-Path -LiteralPath $messagesPath) {
                $arguments += "--resume"
            }
            $logPath = Join-Path $runDir "campaign.log"
            Write-Output "Starting $runId"
            & python @arguments 2>&1 |
                Tee-Object -FilePath $logPath -Append
            if ($LASTEXITCODE -ne 0) {
                throw "$runId failed with exit code $LASTEXITCODE"
            }
        }
    }
}

Write-Output "All frozen memory-ablation runs are complete."
