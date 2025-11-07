# Simple load test to trigger HPA autoscaling
param(
    [int]$DurationSeconds = 120,
    [int]$RequestsPerSecond = 50
)

Write-Host "Starting load test for $DurationSeconds seconds..." -ForegroundColor Cyan
Write-Host "Target: ~$RequestsPerSecond req/sec" -ForegroundColor Cyan
Write-Host ""

$endTime = (Get-Date).AddSeconds($DurationSeconds)
$requestCount = 0
$errorCount = 0

while ((Get-Date) -lt $endTime) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8001/events/health" -Method GET -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        $requestCount++
    } catch {
        $errorCount++
    }
    
    Start-Sleep -Milliseconds 20  # ~50 req/sec
}

Write-Host ""
Write-Host "Load test complete!" -ForegroundColor Green
Write-Host "  Requests: $requestCount" -ForegroundColor Cyan
Write-Host "  Errors: $errorCount" -ForegroundColor Cyan
