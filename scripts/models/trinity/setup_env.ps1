param(
  [string]$EnvPath = "D:\Research_Engine\.venv-trinity",
  [string]$PythonExe = "python",
  [string]$CacheDir = "D:\Research_Engine\hf_cache",
  [string]$TorchIndexUrl = "https://download.pytorch.org/whl/cu121",
  [switch]$UpgradePip,
  [switch]$SkipSmokeTest,
  [string]$SmokeModelPath = "D:\Research_Engine\models\Trinity-Nano-Preview"
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
  Write-Host ""
  Write-Host "==> $Message"
}

if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
  throw "Python executable not found: $PythonExe"
}

$scriptRoot = $PSScriptRoot
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\..\.."))
$envPathResolved = [System.IO.Path]::GetFullPath($EnvPath)
$cacheDirResolved = [System.IO.Path]::GetFullPath($CacheDir)
$pythonInEnv = Join-Path $envPathResolved "Scripts\python.exe"
$smokeScript = Join-Path $repoRoot "scripts\model_env_smoke.py"

Write-Step "Creating Trinity venv at $envPathResolved"
if (-not (Test-Path $envPathResolved)) {
  & $PythonExe -m venv $envPathResolved
}

if (-not (Test-Path $pythonInEnv)) {
  throw "Expected venv python at $pythonInEnv"
}

if ($UpgradePip) {
  Write-Step "Upgrading pip tooling"
  & $pythonInEnv -m pip install --upgrade pip setuptools wheel
}

Write-Step "Installing PyTorch CUDA 12.1 wheels"
& $pythonInEnv -m pip install --upgrade torch torchvision torchaudio --index-url $TorchIndexUrl

Write-Step "Installing Trinity training dependencies"
& $pythonInEnv -m pip install --upgrade `
  accelerate `
  bitsandbytes `
  datasets `
  jsonschema `
  peft `
  pyyaml `
  sentencepiece `
  trl

Write-Step "Installing transformers main branch for AFMoE support"
& $pythonInEnv -m pip install --upgrade "git+https://github.com/huggingface/transformers.git"

Write-Step "Writing activation helper"
$activatePath = Join-Path $envPathResolved "Scripts\activate_trinity_env.ps1"
$activateBody = @(
  '$env:HF_HOME="' + $cacheDirResolved.Replace('\', '\\') + '"',
  '$env:HUGGINGFACE_HUB_CACHE=$env:HF_HOME',
  '$env:TRANSFORMERS_CACHE=$env:HF_HOME',
  '$env:TRITON_CACHE_DIR=Join-Path $env:HF_HOME "triton"',
  'Write-Host "HF_HOME=$env:HF_HOME"',
  '. "' + (Join-Path $envPathResolved "Scripts\Activate.ps1") + '"'
) -join "`r`n"
Set-Content -Path $activatePath -Value $activateBody -Encoding ASCII

if (-not $SkipSmokeTest) {
  Write-Step "Running Trinity smoke test"
  $env:HF_HOME = $cacheDirResolved
  $env:HUGGINGFACE_HUB_CACHE = $cacheDirResolved
  $env:TRANSFORMERS_CACHE = $cacheDirResolved
  $env:TRITON_CACHE_DIR = Join-Path $cacheDirResolved "triton"
  & $pythonInEnv $smokeScript --model-id $SmokeModelPath --cache-dir $cacheDirResolved
}

Write-Step "Trinity environment ready"
Write-Host "Env path: $envPathResolved"
Write-Host "Python: $pythonInEnv"
Write-Host "Activate with: powershell -ExecutionPolicy Bypass -File `"$activatePath`""
