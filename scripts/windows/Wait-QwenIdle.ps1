param(
    [string]$TargetHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,
    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 900,
    [ValidateRange(1, 30)]
    [int]$PollSeconds = 5
)

$ErrorActionPreference = 'SilentlyContinue'
$healthUri = "http://$TargetHost`:$Port/health"
$slotsUri = "http://$TargetHost`:$Port/slots"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

while ((Get-Date) -lt $deadline) {
    try {
        $health = Invoke-WebRequest -Uri $healthUri -UseBasicParsing -TimeoutSec 5
        if ($health.StatusCode -ne 200) {
            Start-Sleep -Seconds $PollSeconds
            continue
        }

        $slots = @(Invoke-RestMethod -Uri $slotsUri -TimeoutSec 5)
        $busy = @($slots | Where-Object { $_.is_processing -eq $true })
        if ($busy.Count -eq 0) {
            Write-Host "llama-server is idle: $slotsUri"
            exit 0
        }

        Write-Host "llama-server has $($busy.Count) active slot(s); waiting before restart."
    } catch {
        if (-not (Test-NetConnection -ComputerName $TargetHost -Port $Port -InformationLevel Quiet)) {
            Write-Host 'llama-server is not listening; no active request needs draining.'
            exit 0
        }
        # A listening server with an unavailable health or slots endpoint is not safe to stop.
    }

    Start-Sleep -Seconds $PollSeconds
}

throw "llama-server did not become idle within $TimeoutSeconds seconds: $slotsUri"
