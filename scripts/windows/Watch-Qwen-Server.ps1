param(
    [ValidateSet('Q2', 'Q3')]
    [string]$Profile = 'Q3'
)

$ErrorActionPreference = 'Continue'
$configPath = Join-Path $PSScriptRoot 'config.local.ps1'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Missing local configuration. Copy config.local.ps1.example to config.local.ps1."
}
. $configPath

$profileSettings = @{
    Q2 = @{
        Model = 'Qwen3.8-27B-UD-Q2_K_XL.gguf'
        Alias = 'Qwen3.8-27B-Q2'
        Context = 182000
        HardLimit = 178000
    }
    Q3 = @{
        Model = 'Qwen3.8-27B-UD-Q3_K_XL.gguf'
        Alias = 'Qwen3.8-27B-Q3'
        Context = 92160
        HardLimit = 87063
    }
}
$selected = $profileSettings[$Profile]
$model = Join-Path $ModelDir $selected.Model
$mmproj = if ($MmprojPath) { $MmprojPath } else { Join-Path $ModelDir 'mmproj-Qwen3.8-27B-BF16.gguf' }
$serverArgs = @(
    '--model', $model,
    '--host', $BackendHost,
    '--port', $BackendPort,
    '--alias', $selected.Alias,
    '--ctx-size', $selected.Context,
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
$env:MTMD_BACKEND_DEVICE = 'none'

$env:LLAMA_BACKEND_CONTEXT_TOKENS = [string]$selected.Context
$env:CONTEXT_HARD_LIMIT = [string]$selected.HardLimit
$env:LLAMA_CONTEXT_SAFETY_TOKENS = '4096'

$mutex = New-Object System.Threading.Mutex($false, 'Global\Qwen38ServerWatchdog')
if (-not $mutex.WaitOne(0)) {
    Write-Host 'Another Qwen server watchdog is already running.'
    exit 0
}

function Test-BackendReady {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/health" -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -ne 200) { return $false }
        $props = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/props" -TimeoutSec 5
        return $props.modalities.vision -eq $true
    } catch {
        return $false
    }
}

function Get-QwenServerProcess {
    return Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue
}

function Start-QwenServerOnce {
    $existing = Get-QwenServerProcess
    if ($existing) {
        if (Test-BackendReady) {
            Write-Host "Vision-enabled llama-server already exists (PID $($existing.Id)); waiting for readiness."
            return
        }
        Write-Host "Existing llama-server is not vision-enabled; waiting for it to become idle before replacement."
        & (Join-Path $PSScriptRoot 'Wait-QwenIdle.ps1') -TargetHost '127.0.0.1' -Port ([int]$BackendPort)
        & (Join-Path $PSScriptRoot 'Stop-Qwen.ps1')
    }

    if (-not (Test-Path -LiteralPath $mmproj)) { throw "Qwen3.8 vision projector not found: $mmproj" }

    if ($existing) {
        Write-Host "Replaced the previous llama-server process with the vision-enabled profile."
    }

    if (-not (Test-Path -LiteralPath $ServerExe)) { throw "llama-server not found: $ServerExe" }
    if (-not (Test-Path -LiteralPath $model)) { throw "Model not found: $model" }

    Start-Process -FilePath $ServerExe -ArgumentList $serverArgs -WorkingDirectory (Split-Path $ServerExe) | Out-Null
    Write-Host "Started $Profile llama-server; waiting for /health."

    $waiter = Join-Path $PSScriptRoot 'Wait-QwenReady.ps1'
    & $waiter -TargetHost '127.0.0.1' -Port ([int]$BackendPort) -TimeoutSeconds 900 -RequireVision
}

try {
    while ($true) {
        if (-not (Test-BackendReady)) {
            Start-QwenServerOnce
        }
        Start-Sleep -Seconds 15
    }
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
