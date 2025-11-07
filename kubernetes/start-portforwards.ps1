# Minikube Port-Forward Startup Script
# Run this after `minikube start` to expose services on localhost

Write-Host "Starting Minikube port-forwards..." -ForegroundColor Cyan
Write-Host ""

# Kill existing port-forward jobs
Get-Job | Where-Object { $_.Command -like "*kubectl port-forward*" } | Stop-Job
Get-Job | Where-Object { $_.Command -like "*kubectl port-forward*" } | Remove-Job

# Start port-forwards in background
Write-Host "[1/4] Traefik API (8001 -> 8000)" -ForegroundColor Yellow
Start-Job -ScriptBlock { kubectl port-forward svc/traefik 8001:8000 } | Out-Null

Write-Host "[2/4] PostgreSQL (5436 -> 5432)" -ForegroundColor Yellow
Start-Job -ScriptBlock { kubectl port-forward svc/postgres 5436:5432 } | Out-Null

Write-Host "[3/4] RabbitMQ UI (15673 -> 15672)" -ForegroundColor Yellow
Start-Job -ScriptBlock { kubectl port-forward svc/rabbitmq 15673:15672 } | Out-Null

Write-Host "[4/4] Traefik Dashboard (8002 -> 8080)" -ForegroundColor Yellow
Start-Job -ScriptBlock { kubectl port-forward svc/traefik 8002:8080 } | Out-Null

# Wait for port-forwards to establish
Start-Sleep -Seconds 3

# Show job status
Write-Host ""
Write-Host "Port-forward jobs:" -ForegroundColor Cyan
Get-Job | Where-Object { $_.Command -like "*kubectl port-forward*" } | Format-Table -Property Id, Name, State

# Show access URLs
Write-Host ""
Write-Host "Access URLs:" -ForegroundColor Green
Write-Host "  Minikube API:         http://localhost:8001/customer/data" -ForegroundColor White
Write-Host "  Traefik Dashboard:    http://localhost:8002/dashboard" -ForegroundColor White
Write-Host "  RabbitMQ UI:          http://localhost:15673 (fintegrate_user/fintegrate_pass)" -ForegroundColor White
Write-Host "  PostgreSQL (DBeaver): localhost:5436 (fintegrate_db, fintegrate_user/fintegrate_pass)" -ForegroundColor White

Write-Host ""
Write-Host "Docker Compose URLs (if running):" -ForegroundColor Green
Write-Host "  Docker API:           http://localhost/customer/data" -ForegroundColor White
Write-Host "  Traefik Dashboard:    http://localhost:8080/dashboard" -ForegroundColor White
Write-Host "  RabbitMQ UI:          http://localhost:15672" -ForegroundColor White
Write-Host "  PostgreSQL (DBeaver): localhost:5435" -ForegroundColor White
Write-Host "  Airflow UI:           http://localhost:8081 (admin/admin)" -ForegroundColor White

Write-Host ""
Write-Host "To stop port-forwards: Get-Job | Stop-Job; Get-Job | Remove-Job" -ForegroundColor Yellow
Write-Host ""
