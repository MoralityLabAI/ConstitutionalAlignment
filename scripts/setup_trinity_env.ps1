param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$ForwardArgs
)

$ErrorActionPreference = "Stop"
$target = Join-Path $PSScriptRoot "models\trinity\setup_env.ps1"
& $target @ForwardArgs
