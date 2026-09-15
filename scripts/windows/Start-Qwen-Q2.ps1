param(
    [switch]$SkipModelCheck
)

$ErrorActionPreference = 'Stop'
$configPath = Join-Path $PSScriptRoot 'config.local.ps1'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Missing local configuration. Copy config.local.ps1.example to config.local.ps1."
}
. $configPath

$model = Join-Path $ModelDir 'Qwen3.8-27B-UD-Q2_K_XL.gguf'
if (-not $SkipModelCheck -and -not (Test-Path -LiteralPath $model)) {
    throw "Q2 model not found: $model"
}
$mmproj = if ($MmprojPath) { $MmprojPath } else { Join-Path $ModelDir 'mmproj-Qwen3.8-27B-BF16.gguf' }
if (-not (Test-Path -LiteralPath $mmproj)) {
    throw "Qwen3.8 vision projector not found: $mmproj"
}

try {
    $health = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/health" -UseBasicParsing -TimeoutSec 5
    $props = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/props" -TimeoutSec 5
    if ($health.StatusCode -eq 200 -and $props.modalities.vision -eq $true -and $props.model_alias -eq 'Qwen3.8-27B-Q2') {
        Write-Host "Q2 llama-server is already vision-ready on $BackendHost`:$BackendPort"
        exit 0
    }
} catch {
    # A stopped or still-loading server is handled by the idle wait and restart below.
}

& (Join-Path $PSScriptRoot 'Wait-QwenIdle.ps1') -TargetHost '127.0.0.1' -Port ([int]$BackendPort)
& (Join-Path $PSScriptRoot 'Stop-Qwen.ps1')

$env:LLAMA_BACKEND_CONTEXT_TOKENS = '182000'
$env:CONTEXT_HARD_LIMIT = '178000'
$env:LLAMA_CONTEXT_SAFETY_TOKENS = '4096'
$env:MTMD_BACKEND_DEVICE = 'none'

$serverArgs = @(
    '--model', $model,
    '--host', $BackendHost,
    '--port', $BackendPort,
    '--alias', 'Qwen3.8-27B-Q2',
    '--ctx-size', '182000',
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
    '--mmproj', $mmproj,
    '--no-mmproj-offload',
    '--jinja',
    '--metrics',
    '--verbose'
)
if ($WebPath) { $serverArgs += @('--path', $WebPath) }
if ($CudaBin) { $env:Path = "$CudaBin;$env:Path" }

Start-Process -FilePath $ServerExe -ArgumentList $serverArgs -WorkingDirectory (Split-Path $ServerExe)
& (Join-Path $PSScriptRoot 'Wait-QwenReady.ps1') -TargetHost '127.0.0.1' -Port ([int]$BackendPort) -RequireVision
Write-Host "Q2 llama-server is ready on $BackendHost`:$BackendPort"
