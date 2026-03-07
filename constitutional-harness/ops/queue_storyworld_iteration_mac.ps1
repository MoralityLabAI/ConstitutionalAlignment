param(
  [Parameter(Mandatory = $true)]
  [string]$ManifestPath,
  [string]$HostAlias = "mac-ip",
  [string]$BaseModelPath = "/Users/ben/worker/models/Qwen3.5-2B-Base-MLX-4bit",
  [string]$AdapterOutDir = "",
  [int]$Steps = 120,
  [int]$BatchSize = 1,
  [int]$GradAccum = 1,
  [double]$LearningRate = 5e-5,
  [int]$MaxSeqLength = 256,
  [int]$NumLayers = 8,
  [int]$LoraRank = 8,
  [double]$LoraAlpha = 16.0,
  [string]$ReceiptDir = "C:\projects\ConstitutionalAlignment\ConstitutionalAlignment\constitutional-harness\ops\receipts"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ManifestPath)) {
  throw "Missing manifest: $ManifestPath"
}

$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$datasetDir = [string]$manifest.dataset_dir
if (-not (Test-Path -LiteralPath $datasetDir)) {
  throw "Missing dataset dir from manifest: $datasetDir"
}

$adapterDir = if ($AdapterOutDir) { $AdapterOutDir } else { [string]$manifest.next_adapter_dir }
if (-not $adapterDir) {
  throw "No adapter output dir provided."
}

$iteration = [int]$manifest.iteration
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$jobId = "storyworld_const2b_r8_qv_iter{0}_{1}" -f $iteration.ToString("00"), $stamp
$localInbox = Join-Path "C:\projects\Tesseract\Tesseract\remote_ops\downloads\datasets" $jobId
$remoteDatasetDir = "/Users/ben/worker/datasets/$jobId"
$remoteAdapterDir = $adapterDir.Replace('\', '/')
$remoteConfigPath = "/Users/ben/worker/configs/$jobId.yaml"

New-Item -ItemType Directory -Force -Path $localInbox | Out-Null
New-Item -ItemType Directory -Force -Path $ReceiptDir | Out-Null

& ssh $HostAlias "mkdir -p $remoteDatasetDir /Users/ben/worker/configs ~/worker/queue/inbox"
if ($LASTEXITCODE -ne 0) {
  throw "failed to prepare remote Mac directories"
}

foreach ($name in @("train.jsonl", "valid.jsonl", "test.jsonl", "manifest.json")) {
  $src = Join-Path $datasetDir $name
  if (Test-Path -LiteralPath $src) {
    & scp $src "${HostAlias}:$remoteDatasetDir/$name"
    if ($LASTEXITCODE -ne 0) {
      throw "failed to copy dataset file $name"
    }
  }
}

$cfgLocal = Join-Path $localInbox "$jobId.yaml"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$yaml = @"
lora_parameters:
  rank: $LoraRank
  dropout: 0.0
  scale: $LoraAlpha
target_modules:
  - self_attn.q_proj
  - self_attn.v_proj
"@
[System.IO.File]::WriteAllText($cfgLocal, $yaml, $utf8NoBom)

& scp $cfgLocal "${HostAlias}:$remoteConfigPath"
if ($LASTEXITCODE -ne 0) {
  throw "failed to copy MLX config"
}

& python "C:\projects\Tesseract\Tesseract\remote_ops\windows\enqueue_mlx_lora_job.py" `
  --inbox $localInbox `
  --model $BaseModelPath `
  --data-dir $remoteDatasetDir `
  --adapter-path $remoteAdapterDir `
  --steps $Steps `
  --num-layers $NumLayers `
  --grad-accum $GradAccum `
  --batch-size $BatchSize `
  --learning-rate $LearningRate `
  --max-seq-length $MaxSeqLength `
  --grad-checkpoint `
  --job-id $jobId
if ($LASTEXITCODE -ne 0) {
  throw "failed to create queue payload"
}

$jobPath = Join-Path $localInbox ($jobId + ".json")
& python -c "import json,pathlib; p=pathlib.Path(r'$jobPath'); d=json.loads(p.read_text(encoding='utf-8')); d.setdefault('extra',{}); d['extra']['config']=r'$remoteConfigPath'; p.write_text(json.dumps(d,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')"
if ($LASTEXITCODE -ne 0) {
  throw "failed to inject MLX config path into queue payload"
}

& powershell -ExecutionPolicy Bypass -File "C:\projects\Tesseract\Tesseract\remote_ops\windows\push-ben-mac-jobs.ps1" -HostAlias $HostAlias -JobPaths @($jobPath)
if ($LASTEXITCODE -ne 0) {
  throw "failed to push queued job to Mac"
}

$receipt = [ordered]@{
  ts_utc = (Get-Date).ToUniversalTime().ToString("o")
  manifest_path = $ManifestPath
  dataset_dir = $datasetDir
  remote_dataset_dir = $remoteDatasetDir
  remote_adapter_dir = $remoteAdapterDir
  job_id = $jobId
  job_path = $jobPath
  remote_config_path = $remoteConfigPath
  params = [ordered]@{
    steps = $Steps
    batch_size = $BatchSize
    grad_accum = $GradAccum
    learning_rate = $LearningRate
    max_seq_length = $MaxSeqLength
    num_layers = $NumLayers
    lora_rank = $LoraRank
    lora_alpha = $LoraAlpha
  }
}

$receiptPath = Join-Path $ReceiptDir ("queued_storyworld_iter_" + $stamp + ".json")
$receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $receiptPath -Encoding utf8
Write-Host "RECEIPT=$receiptPath"
Write-Host "JOB_ID=$jobId"
