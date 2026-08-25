param(
    [ValidateRange(1, 120)]
    [int]$WaitSeconds = 30
)

$ErrorActionPreference = 'SilentlyContinue'

Get-CimInstance Win32_Process |
    Where-Object { $_.Name -ieq 'llama-server.exe' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

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
