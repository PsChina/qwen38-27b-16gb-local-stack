param(
    [string]$TargetHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,
    [ValidateRange(1, 3600)]
    [int]$TimeoutSeconds = 900,
    [ValidateRange(1, 30)]
    [int]$PollSeconds = 5,
    [switch]$RequireVision
)

$ErrorActionPreference = 'SilentlyContinue'
$healthUri = "http://$TargetHost`:$Port/health"
$propsUri = "http://$TargetHost`:$Port/props"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri $healthUri -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            if (-not $RequireVision) {
                Write-Host "llama-server is ready: $healthUri"
                exit 0
            }

            $props = Invoke-RestMethod -Uri $propsUri -TimeoutSec 5
            if ($props.modalities.vision -eq $true) {
                Write-Host "vision-enabled llama-server is ready: $propsUri"
                exit 0
            }

            Write-Host 'llama-server is healthy but its vision projector is not enabled; waiting.'
        }
    } catch {
        # 503 during model loading, an unavailable /props endpoint, and connection refusal are expected here.
    }

    Start-Sleep -Seconds $PollSeconds
}

throw "llama-server did not become ready within $TimeoutSeconds seconds: $healthUri"
