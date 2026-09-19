param(
    [ValidateRange(1, 3600)]
    [int]$WaitSeconds = 900,
    [string]$TargetHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$Port = 8080
)

$ErrorActionPreference = 'Stop'

if (Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue) {
    & (Join-Path $PSScriptRoot 'Wait-QwenIdle.ps1') -TargetHost $TargetHost -Port $Port -TimeoutSeconds $WaitSeconds
}

Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue |
    Stop-Process -Force

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    $remaining = Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue
    if (-not $remaining) { break }
    Start-Sleep -Seconds 1
}

if (Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue) {
    throw "llama-server did not exit within $WaitSeconds seconds"
}

Write-Host 'Stopped llama-server processes when present.'
