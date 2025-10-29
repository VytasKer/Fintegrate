# Traefik Gateway - Test Script
# Run this after starting docker-compose to verify gateway routing

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Traefik API Gateway - Testing Suite" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# Test 1: Check if Traefik is running
Write-Host "[Test 1] Checking if Traefik is running..." -ForegroundColor Yellow
try {
    $traefik = docker ps --filter "name=fintegrate-traefik" --format "{{.Status}}"
    if ($traefik -like "Up*") {
        Write-Host "✓ Traefik is running" -ForegroundColor Green
    } else {
        Write-Host "✗ Traefik is not running" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Error checking Traefik: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Test 2: Check if Customer Service is running
Write-Host "[Test 2] Checking if Customer Service is running..." -ForegroundColor Yellow
try {
    $customer = docker ps --filter "name=fintegrate-customer-service" --format "{{.Status}}"
    if ($customer -like "Up*") {
        Write-Host "✓ Customer Service is running" -ForegroundColor Green
    } else {
        Write-Host "✗ Customer Service is not running" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Error checking Customer Service: $_" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Test 3: Check Traefik Dashboard
Write-Host "[Test 3] Checking Traefik Dashboard..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8080/api/overview" -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "✓ Traefik Dashboard is accessible at http://localhost:8080" -ForegroundColor Green
    }
} catch {
    Write-Host "✗ Cannot access Traefik Dashboard: $_" -ForegroundColor Red
    Write-Host "  Try opening http://localhost:8080 in your browser" -ForegroundColor Gray
}
Write-Host ""

# Test 4: Check if routing is configured
Write-Host "[Test 4] Checking if routes are configured..." -ForegroundColor Yellow
try {
    $routers = Invoke-RestMethod -Uri "http://localhost:8080/api/http/routers"
    $customerRouter = $routers | Where-Object { $_.name -like "*customer-service*" }
    
    if ($customerRouter) {
        Write-Host "✓ Customer service router found" -ForegroundColor Green
        Write-Host "  Router Name: $($customerRouter.name)" -ForegroundColor Gray
        Write-Host "  Rule: $($customerRouter.rule)" -ForegroundColor Gray
    } else {
        Write-Host "✗ Customer service router not found" -ForegroundColor Red
        Write-Host "  Available routers:" -ForegroundColor Gray
        $routers | ForEach-Object { Write-Host "    - $($_.name)" -ForegroundColor Gray }
    }
} catch {
    Write-Host "✗ Error checking routes: $_" -ForegroundColor Red
}
Write-Host ""

# Test 5: Test health endpoint through gateway
Write-Host "[Test 5] Testing health endpoint through gateway..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost/" -Method GET
    if ($response.status -eq "running") {
        Write-Host "✓ Health endpoint accessible through gateway" -ForegroundColor Green
        Write-Host "  Service: $($response.service)" -ForegroundColor Gray
        Write-Host "  Version: $($response.version)" -ForegroundColor Gray
    }
} catch {
    Write-Host "✗ Cannot access health endpoint: $_" -ForegroundColor Red
}
Write-Host ""

# Test 6: Test customer creation through gateway
Write-Host "[Test 6] Testing customer creation through gateway..." -ForegroundColor Yellow
try {
    $body = @{
        name = "Gateway Test Customer - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "http://localhost/customer/data" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body

    if ($response.detail.status_code -eq "201") {
        Write-Host "✓ Customer created successfully through gateway" -ForegroundColor Green
        Write-Host "  Customer ID: $($response.data.customer_id)" -ForegroundColor Gray
        Write-Host "  Name: $($response.data.name)" -ForegroundColor Gray
        Write-Host "  Status: $($response.data.status)" -ForegroundColor Gray
        
        # Store customer ID for next test
        $script:testCustomerId = $response.data.customer_id
    }
} catch {
    Write-Host "✗ Error creating customer: $_" -ForegroundColor Red
    $script:testCustomerId = $null
}
Write-Host ""

# Test 7: Test customer retrieval through gateway
if ($script:testCustomerId) {
    Write-Host "[Test 7] Testing customer retrieval through gateway..." -ForegroundColor Yellow
    try {
        $response = Invoke-RestMethod -Uri "http://localhost/customer/data?customer_id=$($script:testCustomerId)" -Method GET

        if ($response.detail.status_code -eq "200") {
            Write-Host "✓ Customer retrieved successfully through gateway" -ForegroundColor Green
            Write-Host "  Name: $($response.data.name)" -ForegroundColor Gray
        }
    } catch {
        Write-Host "✗ Error retrieving customer: $_" -ForegroundColor Red
    }
    Write-Host ""
}

# Test 8: Test events health endpoint
Write-Host "[Test 8] Testing events health endpoint through gateway..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost/events/health" -Method GET

    if ($response.detail.status_code -eq "200") {
        Write-Host "✓ Events health endpoint accessible through gateway" -ForegroundColor Green
        Write-Host "  Pending Count: $($response.data.pending_count)" -ForegroundColor Gray
        Write-Host "  Failed Count: $($response.data.failed_count)" -ForegroundColor Gray
    }
} catch {
    Write-Host "✗ Error accessing events health: $_" -ForegroundColor Red
}
Write-Host ""

# Summary
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "Gateway URLs:" -ForegroundColor Yellow
Write-Host "  Traefik Dashboard: http://localhost:8080" -ForegroundColor White
Write-Host "  Customer API:      http://localhost/customer/data" -ForegroundColor White
Write-Host "  Events API:        http://localhost/events/health" -ForegroundColor White
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Open Traefik dashboard in browser: http://localhost:8080" -ForegroundColor White
Write-Host "  2. Navigate to 'HTTP Routers' to see routing rules" -ForegroundColor White
Write-Host "  3. Navigate to 'HTTP Services' to see backend services" -ForegroundColor White
Write-Host "  4. Try creating more customers through the gateway" -ForegroundColor White
Write-Host ""
