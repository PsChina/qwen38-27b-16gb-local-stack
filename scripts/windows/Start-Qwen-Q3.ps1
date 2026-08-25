$ErrorActionPreference = 'Stop'
$configPath = Join-Path $PSScriptRoot 'config.local.ps1'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Missing local configuration. Copy config.local.ps1.example to config.local.ps1."
}
. $configPath

$model = Join-Path $ModelDir 'Qwen3.8-27B-UD-Q3_K_XL.gguf'
if (-not (Test-Path -LiteralPath $model)) {
    throw "Q3 model not found: $model"
}

& (Join-Path $PSScriptRoot 'Stop-Qwen.ps1')

$env:LLAMA_BACKEND_CONTEXT_TOKENS = '92160'
$env:CONTEXT_HARD_LIMIT = '87063'
$env:LLAMA_CONTEXT_SAFETY_TOKENS = '4096'

$serverArgs = @(
    '--model', $model,
    '--host', $BackendHost,
    '--port', $BackendPort,
    '--alias', 'Qwen3.8-27B-Q3',
    '--ctx-size', '92160',
    '--parallel', '1',
    '--n-gpu-layers', '999',
    '--flash-attn', 'on',
    '--cache-type-k', 'q4_0',
    '--cache-type-v', 'q4_0',
    '--batch-size', '1024',
    '--ubatch-size', '256',
    '--spec-type', 'draft-mtp',
    '--spec-draft-n-max', '3',
    '--spec-draft-p-min', '0',
    '--no-mmproj',
    '--jinja',
    '--metrics',
    '--verbose'
)
if ($WebPath) { $serverArgs += @('--path', $WebPath) }
if ($CudaBin) { $env:Path = "$CudaBin;$env:Path" }

Start-Process -FilePath $ServerExe -ArgumentList $serverArgs -WorkingDirectory (Split-Path $ServerExe)
Write-Host "Q3 llama-server started on $BackendHost`:$BackendPort"
