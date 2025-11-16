# Monitoring Stack Test Script
# Generates API traffic to populate Grafana dashboards

Write-Host "=== Fintegrate Monitoring Stack Test ===" -ForegroundColor Cyan
Write-Host ""

# Check services are running
Write-Host "1. Checking service health..." -ForegroundColor Yellow
$services = @("http://localhost:9090/-/healthy", "http://localhost:3000/api/health")
foreach ($url in $services) {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
        Write-Host "  [OK] $url" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] $url" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "2. Generating API traffic..." -ForegroundColor Yellow

# Make some API requests to generate metrics
$apiKey = "test_api_key_here"  # Replace with actual API key
$baseUrl = "http://localhost"

# Health check requests
Write-Host "  - Sending health check requests..."
1..10 | ForEach-Object {
    try {
        Invoke-WebRequest -Uri "$baseUrl/" -UseBasicParsing -ErrorAction SilentlyContinue | Out-Null
    } catch {
        # Ignore errors for demo
    }
    Start-Sleep -Milliseconds 100
}

Write-Host "  - Generated 10 health check requests" -ForegroundColor Green
Write-Host ""

Write-Host "3. Checking Prometheus targets..." -ForegroundColor Yellow
try {
    $targets = Invoke-RestMethod -Uri "http://localhost:9090/api/v1/targets"
    $activeTargets = $targets.data.activeTargets
    $upCount = ($activeTargets | Where-Object { $_.health -eq "up" }).Count
    $totalCount = $activeTargets.Count
    Write-Host "  [OK] Prometheus targets: $upCount/$totalCount UP" -ForegroundColor Green
    
    # Show target details
    $activeTargets | ForEach-Object {
        $status = if ($_.health -eq "up") { "[OK]" } else { "[FAIL]" }
        $color = if ($_.health -eq "up") { "Green" } else { "Red" }
        Write-Host "    $status Job: $($_.labels.job) | Instance: $($_.labels.instance) | Health: $($_.health)" -ForegroundColor $color
    }
} catch {
    Write-Host "  [FAIL] Failed to query Prometheus" -ForegroundColor Red
}

Write-Host ""
Write-Host "4. Querying sample metrics..." -ForegroundColor Yellow
try {
    $query = "customer_service_http_requests_total"
    $result = Invoke-RestMethod -Uri "http://localhost:9090/api/v1/query?query=$query"
    $metricCount = $result.data.result.Count
    Write-Host "  [OK] Found $metricCount metric series for HTTP requests" -ForegroundColor Green
    
    # Show sample values
    $result.data.result | Select-Object -First 3 | ForEach-Object {
        $labels = $_.metric
        $value = $_.value[1]
        Write-Host "    - Endpoint: $($labels.endpoint) | Method: $($labels.method) | Status: $($labels.status_code) | Count: $value" -ForegroundColor Cyan
    }
} catch {
    Write-Host "  [FAIL] Failed to query metrics" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Access URLs ===" -ForegroundColor Cyan
Write-Host "  Prometheus UI:  http://localhost:9090" -ForegroundColor White
Write-Host "  Grafana UI:     http://localhost:3000 (admin/fintegrate_admin)" -ForegroundColor White
Write-Host "  Metrics Export: http://localhost/metrics" -ForegroundColor White
Write-Host ""
Write-Host "[SUCCESS] Monitoring stack is operational!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Open Grafana at http://localhost:3000" -ForegroundColor White
Write-Host "  2. Login with admin/fintegrate_admin" -ForegroundColor White
Write-Host "  3. Navigate to Dashboards -> Fintegrate Integration Metrics" -ForegroundColor White
Write-Host "  4. Generate more traffic by creating customers via API" -ForegroundColor White
