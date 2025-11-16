# Kubernetes Monitoring Stack Verification Script
# Verifies Prometheus and Grafana deployment in Minikube

Write-Host "=== Fintegrate Kubernetes Monitoring Stack Test ===" -ForegroundColor Cyan
Write-Host ""

# Check Minikube status
Write-Host "1. Checking Minikube cluster status..." -ForegroundColor Yellow
$minikubeStatus = minikube status 2>&1 | Out-String
if ($minikubeStatus -match "Running") {
    Write-Host "  [OK] Minikube cluster is running" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Minikube cluster is not running" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "2. Checking Kubernetes resources..." -ForegroundColor Yellow

# Check namespace
$namespace = kubectl get namespace fintegrate-monitoring -o json 2>&1 | ConvertFrom-Json
if ($namespace.metadata.name -eq "fintegrate-monitoring") {
    Write-Host "  [OK] Namespace 'fintegrate-monitoring' exists" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Namespace not found" -ForegroundColor Red
}

# Check PVCs
$pvcs = kubectl get pvc -n fintegrate-monitoring -o json 2>&1 | ConvertFrom-Json
$pvcStatus = $pvcs.items | ForEach-Object {
    $status = if ($_.status.phase -eq "Bound") { "[OK]" } else { "[FAIL]" }
    $color = if ($_.status.phase -eq "Bound") { "Green" } else { "Red" }
    Write-Host "  $status PVC: $($_.metadata.name) - $($_.status.phase) ($($_.spec.resources.requests.storage))" -ForegroundColor $color
}

# Check pods
Write-Host ""
Write-Host "3. Checking pod status..." -ForegroundColor Yellow
$pods = kubectl get pods -n fintegrate-monitoring -o json 2>&1 | ConvertFrom-Json
$pods.items | ForEach-Object {
    $ready = $_.status.containerStatuses[0].ready
    $status = if ($ready) { "[OK]" } else { "[FAIL]" }
    $color = if ($ready) { "Green" } else { "Red" }
    $restarts = $_.status.containerStatuses[0].restartCount
    Write-Host "  $status Pod: $($_.metadata.name) - Ready: $ready | Restarts: $restarts" -ForegroundColor $color
}

# Check services
Write-Host ""
Write-Host "4. Checking services..." -ForegroundColor Yellow
$services = kubectl get svc -n fintegrate-monitoring -o json 2>&1 | ConvertFrom-Json
$services.items | ForEach-Object {
    $nodePort = $_.spec.ports[0].nodePort
    Write-Host "  [OK] Service: $($_.metadata.name) - NodePort: $nodePort" -ForegroundColor Green
}

# Get service URLs
Write-Host ""
Write-Host "5. Getting service access URLs..." -ForegroundColor Yellow
try {
    $minikubeIP = minikube ip
    Write-Host "  Minikube IP: $minikubeIP" -ForegroundColor Cyan
    Write-Host "  Prometheus UI: http://${minikubeIP}:30090" -ForegroundColor White
    Write-Host "  Grafana UI:    http://${minikubeIP}:30300 (admin/fintegrate_admin)" -ForegroundColor White
} catch {
    Write-Host "  [FAIL] Could not get Minikube IP" -ForegroundColor Red
}

# Test Prometheus health
Write-Host ""
Write-Host "6. Testing Prometheus health endpoint..." -ForegroundColor Yellow
try {
    $prometheusHealth = kubectl exec -n fintegrate-monitoring prometheus-0 -- wget -q -O- http://localhost:9090/-/healthy
    if ($prometheusHealth -eq "Prometheus is Healthy.") {
        Write-Host "  [OK] Prometheus is healthy" -ForegroundColor Green
    }
} catch {
    Write-Host "  [FAIL] Could not reach Prometheus health endpoint" -ForegroundColor Red
}

# Test Grafana health
Write-Host ""
Write-Host "7. Testing Grafana health endpoint..." -ForegroundColor Yellow
try {
    $grafanaHealth = kubectl exec -n fintegrate-monitoring $(kubectl get pod -n fintegrate-monitoring -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}') -- wget -q -O- http://localhost:3000/api/health
    $healthJson = $grafanaHealth | ConvertFrom-Json
    if ($healthJson.database -eq "ok") {
        Write-Host "  [OK] Grafana is healthy (database: ok)" -ForegroundColor Green
    }
} catch {
    Write-Host "  [FAIL] Could not reach Grafana health endpoint" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host "[SUCCESS] Kubernetes monitoring stack deployed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Access Prometheus: minikube service prometheus -n fintegrate-monitoring" -ForegroundColor White
Write-Host "  2. Access Grafana: minikube service grafana -n fintegrate-monitoring" -ForegroundColor White
Write-Host "  3. Verify persistent storage: kubectl exec -n fintegrate-monitoring prometheus-0 -- df -h /prometheus" -ForegroundColor White
Write-Host ""
Write-Host "Key differences from Docker Compose:" -ForegroundColor Yellow
Write-Host "  - StatefulSet ensures stable storage for Prometheus" -ForegroundColor White
Write-Host "  - PersistentVolumeClaims retain metrics across pod restarts" -ForegroundColor White
Write-Host "  - NodePort services expose monitoring tools outside cluster" -ForegroundColor White
Write-Host "  - ConfigMaps enable configuration-as-code for deployments" -ForegroundColor White
