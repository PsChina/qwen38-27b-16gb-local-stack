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
$uri = "http://$TargetHost`:$Port/health"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            Write-Host "llama-server is ready: $uri"
            exit 0
        }
    } catch {
        # 503 during model loading and connection refusal are expected here.
    }

    Start-Sleep -Seconds $PollSeconds
}

throw "llama-server did not become ready within $TimeoutSeconds seconds: $uri"
