$ErrorActionPreference = 'SilentlyContinue'

Get-CimInstance Win32_Process |
    Where-Object { $_.Name -ieq 'llama-server.exe' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host 'Stopped llama-server processes when present.'
