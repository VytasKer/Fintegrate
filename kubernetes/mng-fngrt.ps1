# Fintegrate Kubernetes Management Menu
# Interactive script for managing Minikube cluster lifecycle

function Show-Menu {
    Clear-Host
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Fintegrate Kubernetes Management" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Check Minikube status
    $status = minikube status --format='{{.Host}}' 2>&1
    if ($status -match "Running") {
        Write-Host "Cluster Status: " -NoNewline -ForegroundColor Yellow
        Write-Host "RUNNING" -ForegroundColor Green
        
        # Check pod count
        $pods = kubectl get pods -n default --no-headers 2>&1
        if ($pods -and $LASTEXITCODE -eq 0) {
            $podCount = ($pods | Measure-Object).Count
            $runningPods = ($pods | Select-String "Running").Count
            Write-Host "Pods Running:   " -NoNewline -ForegroundColor Yellow
            Write-Host "$runningPods/$podCount" -ForegroundColor Green
        }
    } elseif ($status -match "Stopped") {
        Write-Host "Cluster Status: " -NoNewline -ForegroundColor Yellow
        Write-Host "STOPPED (data preserved)" -ForegroundColor Yellow
    } else {
        Write-Host "Cluster Status: " -NoNewline -ForegroundColor Yellow
        Write-Host "NOT CREATED" -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[1] Start Cluster" -ForegroundColor Green
    Write-Host "    Quick start with data preservation" -ForegroundColor Gray
    Write-Host "    (Keeps database, RabbitMQ queues, all configs)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[2] Full Deploy" -ForegroundColor Yellow
    Write-Host "    Start cluster + rebuild images + deploy services" -ForegroundColor Gray
    Write-Host "    (Use after first install or minikube delete)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[3] Restart Services Only" -ForegroundColor Cyan
    Write-Host "    Restart application pods (customer-service, consumers, aml-service)" -ForegroundColor Gray
    Write-Host "    (Keeps cluster running, preserves databases, no image rebuild)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[4] Stop Cluster (Safe)" -ForegroundColor Yellow
    Write-Host "    Stop Minikube but keep all data" -ForegroundColor Gray
    Write-Host "    (PersistentVolumes, images, configs preserved)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[5] Hard Reset" -ForegroundColor Red
    Write-Host "    Delete cluster completely and start fresh" -ForegroundColor Gray
    Write-Host "    (ALL DATA LOST: database, queues, images)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[6] View Logs" -ForegroundColor Cyan
    Write-Host "    Show logs from running pods" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[7] Open Dashboards" -ForegroundColor Cyan
    Write-Host "    Launch Kubernetes dashboard, Traefik, RabbitMQ" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[8] Run Database Migrations" -ForegroundColor Magenta
    Write-Host "    Execute SQL migrations on PostgreSQL" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[9] Cluster Status" -ForegroundColor Cyan
    Write-Host "    View detailed cluster health and resource usage" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[10] Update Service Images" -ForegroundColor Magenta
    Write-Host "    Smart rebuild images only if source code changed" -ForegroundColor Gray
    Write-Host "    (Checks file timestamps, updates and restarts services)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[Q] Quit" -ForegroundColor White
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Start-Cluster {
    Write-Host "`n[Starting Cluster...]" -ForegroundColor Green
    Write-Host "Starting Minikube (preserving existing data)..." -ForegroundColor Yellow
    minikube start
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to start Minikube" -ForegroundColor Red
        return
    }
    
    Write-Host "Enabling metrics-server..." -ForegroundColor Yellow
    minikube addons enable metrics-server | Out-Null
    
    Write-Host "Killing any stale port-forwards..." -ForegroundColor Yellow
    Stop-AllPortForwards
    
    Write-Host "Starting port-forwards..." -ForegroundColor Yellow
    Start-PortForwards
    
    Write-Host "`nCluster started successfully!" -ForegroundColor Green
    Write-Host "Access URLs:" -ForegroundColor Cyan
    Write-Host "  Customer API:    http://localhost:8001/customer/data" -ForegroundColor White
    Write-Host "  Health Check:    http://localhost:8001/events/health" -ForegroundColor White
    Write-Host "  RabbitMQ UI:     http://localhost:15673" -ForegroundColor White
    Write-Host "  RabbitMQ AMQP:   localhost:5673" -ForegroundColor White
    Write-Host "  PostgreSQL:      localhost:5436" -ForegroundColor White
    Write-Host "  Prometheus (K8s):http://localhost:9091" -ForegroundColor White
    Write-Host "  Grafana (K8s):   http://localhost:3001 (admin/fintegrate_admin)" -ForegroundColor White
}

function Start-FullDeploy {
    Write-Host "`n[Full Deployment...]" -ForegroundColor Green
    
    # Step 1: Start Minikube if not running
    Write-Host "[1/6] Checking Minikube status..." -ForegroundColor Yellow
    $status = minikube status --format='{{.Host}}' 2>&1
    if ($status -notmatch "Running") {
        Write-Host "  Starting Minikube..." -ForegroundColor Yellow
        minikube start
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Failed to start Minikube" -ForegroundColor Red
            return
        }
    }
    Write-Host "  Minikube running" -ForegroundColor Green
    
    # Step 2: Enable metrics-server
    Write-Host "[2/6] Enabling metrics-server..." -ForegroundColor Yellow
    minikube addons enable metrics-server 2>&1 | Out-Null
    Write-Host "  Metrics-server enabled" -ForegroundColor Green
    
    # Step 3: Build images in Minikube Docker
    Write-Host "[3/6] Building Docker images in Minikube..." -ForegroundColor Yellow
    Write-Host "  Switching Docker context to Minikube..." -ForegroundColor Gray
    & minikube docker-env --shell powershell | Invoke-Expression
    
    # Verify Docker context
    $dockerName = docker info --format "{{.Name}}" 2>&1
    if ($dockerName -notmatch "minikube") {
        Write-Host "  ERROR: Failed to switch to Minikube Docker" -ForegroundColor Red
        Write-Host "  Current Docker: $dockerName" -ForegroundColor Yellow
        return
    }
    Write-Host "  Docker context: $dockerName" -ForegroundColor Green
    
    # Check if images exist
    $customerImage = docker images --format "{{.Repository}}:{{.Tag}}" | Select-String "fintegrate-customer-service:v1.0"
    $consumerImage = docker images --format "{{.Repository}}:{{.Tag}}" | Select-String "fintegrate-event-consumer:v1.0"
    $amlImage = docker images --format "{{.Repository}}:{{.Tag}}" | Select-String "aml_service:latest"
    
    if (-not $customerImage -or -not $consumerImage -or -not $amlImage) {
        Write-Host "  Some images missing, building from project root..." -ForegroundColor Yellow
        $buildImages = $true
    } else {
        Write-Host "  Images exist, rebuilding to ensure latest code..." -ForegroundColor Yellow
        $buildImages = $true
    }
    
    if ($buildImages) {
        $projectRoot = Split-Path $PSScriptRoot
        $dockerPath = Join-Path $projectRoot "docker"
        
        if (-not (Test-Path $dockerPath)) {
            Write-Host "  ERROR: docker/ directory not found" -ForegroundColor Red
            return
        }
        
        # Build from project root (Dockerfiles expect services/ directory)
        Write-Host "    - Building customer-service image..." -ForegroundColor Gray
        Set-Location $projectRoot
        docker build -f docker/Dockerfile.customer_service -t fintegrate-customer-service:v1.0 . 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    ERROR: Failed to build customer-service image" -ForegroundColor Red
            return
        }
        
        Write-Host "    - Building event-consumer image..." -ForegroundColor Gray
        docker build -f docker/Dockerfile.event_consumer -t fintegrate-event-consumer:v1.0 . 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    ERROR: Failed to build event-consumer image" -ForegroundColor Red
            return
        }
        
        # Build AML service image
        Write-Host "    - Building aml_service image..." -ForegroundColor Gray
        docker build -f docker/Dockerfile.aml_service -t aml_service:latest . 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    ERROR: Failed to build aml_service image" -ForegroundColor Red
            return
        }
        Write-Host "    - AML service image built" -ForegroundColor Green

        Set-Location (Join-Path $projectRoot "kubernetes")
        Write-Host "  Images built successfully" -ForegroundColor Green
    }
    
    # Step 4: Deploy services
    Write-Host "[4/6] Deploying Kubernetes resources..." -ForegroundColor Yellow
    
    # Check if deployments exist
    $existingPods = kubectl get pods -n default --no-headers 2>&1
    $podCount = ($existingPods | Measure-Object).Count
    
    if ($podCount -gt 3) {
        # Pods exist (beyond just StatefulSets), check for errors
        $errorPods = $existingPods | Select-String "ErrImageNeverPull|ImagePullBackOff|CrashLoopBackOff"
        $duplicatePods = ($existingPods | Select-String "customer-service|event-consumer" | Measure-Object).Count
        
        if ($errorPods -or $duplicatePods -gt 5) {
            Write-Host "  Cleaning up failed deployments..." -ForegroundColor Gray
            kubectl delete deployment customer-service event-consumer-default event-consumer-swadia event-consumer-test001 traefik --ignore-not-found=true 2>&1 | Out-Null
            Start-Sleep -Seconds 5
        }
    }
    
    Write-Host "    - RBAC (ServiceAccounts, Roles)" -ForegroundColor Gray
    kubectl apply -f rbac/ 2>&1 | Out-Null
    
    Write-Host "    - ConfigMaps and Secrets" -ForegroundColor Gray
    kubectl apply -f configmaps/ 2>&1 | Out-Null
    kubectl apply -f secrets/ 2>&1 | Out-Null
    
    Write-Host "    - StatefulSets (databases)" -ForegroundColor Gray
    kubectl apply -f statefulsets/ 2>&1 | Out-Null
    Start-Sleep -Seconds 10
    
    Write-Host "    - Services" -ForegroundColor Gray
    kubectl apply -f services/ 2>&1 | Out-Null
    Write-Host "    - Deployments (applications)" -ForegroundColor Gray
    kubectl apply -f deployments/ 2>&1 | Out-Null
    Write-Host "    - HPA (autoscaling)" -ForegroundColor Gray
    kubectl apply -f hpa/ 2>&1 | Out-Null
    Write-Host "  Resources deployed" -ForegroundColor Green

    # Step 4b: Force rollout restart for all stateless deployments to use latest images
    Write-Host "[4b/6] Forcing rollout restart for stateless deployments..." -ForegroundColor Yellow
    $statelessDeployments = @(
        "customer-service",
        "event-consumer-default",
        "event-consumer-swadia",
        "event-consumer-test001",
        "aml-service",
        "traefik"
    )
    foreach ($dep in $statelessDeployments) {
        Write-Host "    - Restarting deployment: $dep" -ForegroundColor Gray
        kubectl rollout restart deployment/$dep 2>&1 | Out-Null
    }
    Write-Host "  Rollout restarts complete" -ForegroundColor Green

    # Step 5: Wait for pods
    Write-Host "[5/6] Waiting for pods to be ready..." -ForegroundColor Yellow
    $timeout = 90
    $elapsed = 0
    $allReady = $false
    
    while (-not $allReady -and $elapsed -lt $timeout) {
        $pods = kubectl get pods -n default --no-headers 2>&1
        $notReadyPods = ($pods | Select-String "0/1|0/2|Pending|ContainerCreating|ErrImage").Count
        
        if ($notReadyPods -eq 0) {
            $allReady = $true
            Write-Host "  All pods ready" -ForegroundColor Green
        } else {
            Start-Sleep -Seconds 5
            $elapsed += 5
            Write-Host "  Waiting... $notReadyPods pod(s) not ready ($elapsed/${timeout}s)" -ForegroundColor Gray
        }
    }
    
    if (-not $allReady) {
        Write-Host "  Warning: Some pods still not ready after ${timeout}s" -ForegroundColor Yellow
    }
    
    # Step 6: Start port-forwards
    Write-Host "[6/6] Starting port-forwards..." -ForegroundColor Yellow
    Start-PortForwards
    Write-Host "  Port-forwards established" -ForegroundColor Green
    
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  Deployment Complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Access URLs:" -ForegroundColor Cyan
    Write-Host "  Customer API:    http://localhost:8001/customer/data" -ForegroundColor White
    Write-Host "  Health Check:    http://localhost:8001/events/health" -ForegroundColor White
    Write-Host "  RabbitMQ UI:     http://localhost:15673" -ForegroundColor White
    Write-Host "  RabbitMQ AMQP:   localhost:5673" -ForegroundColor White
    Write-Host "  PostgreSQL:      localhost:5436" -ForegroundColor White
    Write-Host "  Prometheus (K8s):http://localhost:9091" -ForegroundColor White
    Write-Host "  Grafana (K8s):   http://localhost:3001 (admin/fintegrate_admin)" -ForegroundColor White
}

function Restart-Services {
    Write-Host "`n[Restarting Services...]" -ForegroundColor Cyan
    
    $status = minikube status --format='{{.Host}}' 2>&1
    if ($status -notmatch "Running") {
        Write-Host "ERROR: Cluster not running. Start cluster first (option 1)." -ForegroundColor Red
        return
    }
    
    Write-Host "Restarting customer-service..." -ForegroundColor Yellow
    kubectl rollout restart deployment/customer-service
    
    Write-Host "Restarting event-consumers..." -ForegroundColor Yellow
    kubectl rollout restart deployment/event-consumer-default
    kubectl rollout restart deployment/event-consumer-swadia
    kubectl rollout restart deployment/event-consumer-test001
    
    Write-Host "Restarting aml-service..." -ForegroundColor Yellow
    kubectl rollout restart deployment/aml-service
    
    Write-Host "`nWaiting for pods to be ready..." -ForegroundColor Gray
    kubectl wait --for=condition=ready pod -l app=customer-service --timeout=60s 2>&1 | Out-Null
    
    Write-Host "Restarting port-forwards..." -ForegroundColor Yellow
    Stop-AllPortForwards
    Start-PortForwards
    
    Write-Host "Services restarted successfully!" -ForegroundColor Green
}

function Stop-ClusterSafe {
    Write-Host "`n[Safe Stop...]" -ForegroundColor Yellow
    
    # Create backups directory if not exists
    $backupPath = Join-Path $PSScriptRoot "backups"
    if (-not (Test-Path $backupPath)) {
        New-Item -ItemType Directory -Path $backupPath | Out-Null
        Write-Host "Created backups directory: $backupPath" -ForegroundColor Gray
    }
    
    # Backup database before stopping
    Write-Host "Creating database backup..." -ForegroundColor Yellow
    $backupFile = Join-Path $backupPath "backup_$(Get-Date -Format 'yyyyMMdd_HHmm').sql"
    
    $status = minikube status --format='{{.Host}}' 2>&1
    if ($status -match "Running") {
        kubectl exec -n default postgres-0 -- pg_dump -U fintegrate_user fintegrate_db > $backupFile 2>&1
        
        if ($LASTEXITCODE -eq 0 -and (Test-Path $backupFile) -and (Get-Item $backupFile).Length -gt 0) {
            Write-Host "  Backup saved: $backupFile" -ForegroundColor Green
            
            # Clean up old backups (keep only 5 most recent)
            $backups = Get-ChildItem "$backupPath\backup_*.sql" | Sort-Object LastWriteTime -Descending
            if ($backups.Count -gt 5) {
                Write-Host "  Removing old backups (keeping 5 most recent)..." -ForegroundColor Gray
                $backups | Select-Object -Skip 5 | ForEach-Object {
                    Remove-Item $_.FullName -Force
                    Write-Host "    Deleted: $($_.Name)" -ForegroundColor Gray
                }
            }
        } else {
            Write-Host "  Warning: Backup failed or file empty" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Skipping backup (cluster not running)" -ForegroundColor Gray
    }
    
    Write-Host "Stopping port-forwards..." -ForegroundColor Gray
    Stop-AllPortForwards
    
    Write-Host "Stopping Minikube cluster..." -ForegroundColor Yellow
    minikube stop
    
    Write-Host "`nCluster stopped safely." -ForegroundColor Green
    Write-Host "All data preserved (PersistentVolumes, images, configs)" -ForegroundColor Gray
    Write-Host "Database backup saved in: kubernetes\backups\" -ForegroundColor Cyan
    Write-Host "To resume: Use option [1] Start Cluster" -ForegroundColor Cyan
}

function Reset-ClusterHard {
    Write-Host "`n[Hard Reset]" -ForegroundColor Red
    Write-Host "WARNING: This will DELETE ALL DATA" -ForegroundColor Red
    Write-Host "  - Database contents" -ForegroundColor Yellow
    Write-Host "  - RabbitMQ queues" -ForegroundColor Yellow
    Write-Host "  - Docker images" -ForegroundColor Yellow
    Write-Host "  - All configurations" -ForegroundColor Yellow
    Write-Host ""
    $confirm = Read-Host "Type 'DELETE' to confirm"
    
    if ($confirm -ne "DELETE") {
        Write-Host "Cancelled." -ForegroundColor Gray
        return
    }
    
    Write-Host "`nDeleting Minikube cluster..." -ForegroundColor Red
    minikube delete
    
    Write-Host "Cluster deleted." -ForegroundColor Yellow
    Write-Host "To rebuild: Use option [2] Full Deploy" -ForegroundColor Cyan
}

function Show-Logs {
    Write-Host "`n[View Logs]" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[1] Customer Service" -ForegroundColor White
    Write-Host "[2] Event Consumer (default)" -ForegroundColor White
    Write-Host "[3] Event Consumer (swadia)" -ForegroundColor White
    Write-Host "[4] Event Consumer (test001)" -ForegroundColor White
    Write-Host "[5] AML Service" -ForegroundColor White
    Write-Host "[6] PostgreSQL" -ForegroundColor White
    Write-Host "[7] RabbitMQ" -ForegroundColor White
    Write-Host "[8] All pods (last 50 lines)" -ForegroundColor White
    Write-Host ""
    $choice = Read-Host "Select service (Ctrl+C to exit logs)"
    
    Write-Host "Press Ctrl+C to stop following logs..." -ForegroundColor Gray
    Write-Host ""
    
    switch ($choice) {
        "1" { kubectl logs -l app=customer-service --tail=100 -f }
        "2" { kubectl logs -l app=event-consumer,consumer=default --tail=100 -f }
        "3" { kubectl logs -l app=event-consumer,consumer=swadia --tail=100 -f }
        "4" { kubectl logs -l app=event-consumer,consumer=test001 --tail=100 -f }
        "5" { kubectl logs -l app=aml-service --tail=100 -f }
        "6" { kubectl logs -l app=postgres --tail=100 -f }
        "7" { kubectl logs -l app=rabbitmq --tail=100 -f }
        "8" { kubectl logs -l app --tail=50 --all-containers=true }
        default { Write-Host "Invalid choice" -ForegroundColor Red; return }
    }
}

function Open-Dashboards {
    Write-Host "`n[Opening Dashboards...]" -ForegroundColor Cyan
    
    $status = minikube status --format='{{.Host}}' 2>&1
    if ($status -notmatch "Running") {
        Write-Host "ERROR: Cluster not running. Start cluster first (option 1)." -ForegroundColor Red
        return
    }
    
    Write-Host "Launching browsers..." -ForegroundColor Yellow
    
    Write-Host "  [1] Kubernetes Dashboard" -ForegroundColor Gray
    Start-Process "powershell" -ArgumentList "-NoExit", "-Command", "minikube dashboard" -WindowStyle Minimized
    
    Start-Sleep -Seconds 2
    
    Write-Host "  [2] Traefik Dashboard" -ForegroundColor Gray
    Start-Process "http://localhost:8002/dashboard"
    
    Write-Host "  [3] RabbitMQ Management" -ForegroundColor Gray
    Start-Process "http://localhost:15673"
    
    Write-Host "`nDashboards opened in browser" -ForegroundColor Green
}

function Stop-AllPortForwards {
    # Kill PowerShell job-based port-forwards
    Get-Job | Where-Object { $_.Command -like "*kubectl port-forward*" } | Stop-Job 2>&1 | Out-Null
    Get-Job | Where-Object { $_.Command -like "*kubectl port-forward*" } | Remove-Job 2>&1 | Out-Null
    
    # Kill any processes holding the ports (stale kubectl processes)
    $ports = @("8001", "5436", "15673", "5673", "9091", "3001")
    foreach ($port in $ports) {
        $connections = netstat -ano | Select-String ":$port\s" -ErrorAction SilentlyContinue
        if ($connections) {
            $connections | ForEach-Object {
                $pidMatch = $_.ToString() -match '\s+(\d+)\s*$'
                if ($pidMatch -and $matches[1] -ne "0") {
                    Stop-Process -Id $matches[1] -Force -ErrorAction SilentlyContinue
                }
            }
        }
    }
    
    Start-Sleep -Seconds 1
}

function Start-PortForwards {
    # Start port-forwards in background (direct to services, no Traefik)
    Write-Host "  Starting port-forwards..." -ForegroundColor Gray
    
    # Application services
    Start-Job -ScriptBlock { kubectl port-forward svc/customer-service 8001:8000 } | Out-Null
    Start-Job -ScriptBlock { kubectl port-forward svc/postgres 5436:5432 } | Out-Null
    Start-Job -ScriptBlock { kubectl port-forward svc/rabbitmq 15673:15672 } | Out-Null
    Start-Job -ScriptBlock { kubectl port-forward svc/rabbitmq 5673:5672 } | Out-Null
    
    # Monitoring services (different ports from Docker Compose to avoid conflicts)
    # Docker: Prometheus 9090, Grafana 3000
    # K8s:    Prometheus 9091, Grafana 3001
    Start-Job -ScriptBlock { kubectl port-forward -n fintegrate-monitoring svc/prometheus 9091:9090 } | Out-Null
    Start-Job -ScriptBlock { kubectl port-forward -n fintegrate-monitoring svc/grafana 3001:3000 } | Out-Null
    
    Start-Sleep -Seconds 3
    
    # Verify port-forwards are running
    $runningForwards = (Get-Job | Where-Object { $_.Command -like "*kubectl port-forward*" -and $_.State -eq "Running" } | Measure-Object).Count
    if ($runningForwards -eq 6) {
        Write-Host "  Port-forwards active: $runningForwards/6" -ForegroundColor Green
    } else {
        Write-Host "  Warning: Only $runningForwards/6 port-forwards active" -ForegroundColor Yellow
        Write-Host "  Check failed jobs: Get-Job | Where-Object { `$_.State -eq 'Failed' } | Receive-Job" -ForegroundColor Gray
    }
}

function Show-ClusterStatus {
    Write-Host "`n[Cluster Status]" -ForegroundColor Cyan
    Write-Host ""
    
    $status = minikube status --format='{{.Host}}' 2>&1
    if ($status -notmatch "Running") {
        Write-Host "ERROR: Cluster not running" -ForegroundColor Red
        return
    }
    
    # Nodes
    Write-Host "=== Nodes ===" -ForegroundColor Yellow
    kubectl get nodes
    Write-Host ""
    
    # Pods
    Write-Host "=== Pods ===" -ForegroundColor Yellow
    kubectl get pods -o wide
    Write-Host ""
    
    # Services
    Write-Host "=== Services ===" -ForegroundColor Yellow
    kubectl get svc
    Write-Host ""
    
    # HPA
    Write-Host "=== Horizontal Pod Autoscaler ===" -ForegroundColor Yellow
    kubectl get hpa
    Write-Host ""
    
    # Port-forwards
    Write-Host "=== Port-Forwards ===" -ForegroundColor Yellow
    $portForwards = Get-Job | Where-Object { $_.Command -like "*kubectl port-forward*" }
    if ($portForwards) {
        $portForwards | Format-Table -Property Id, State, Command
    } else {
        Write-Host "  No port-forwards running" -ForegroundColor Yellow
        Write-Host "  Run option 1 (Start Cluster) to establish port-forwards" -ForegroundColor Gray
    }
    Write-Host ""
    
    # Resource usage (if metrics available)
    Write-Host "=== Resource Usage ===" -ForegroundColor Yellow
    $metricsAvailable = kubectl top nodes 2>&1
    if ($LASTEXITCODE -eq 0) {
        kubectl top nodes
        Write-Host ""
        kubectl top pods --sort-by=cpu
    } else {
        Write-Host "  Metrics not available yet (wait 30s after startup)" -ForegroundColor Gray
    }
    Write-Host ""
    
    # Access URLs
    Write-Host "=== Access URLs ===" -ForegroundColor Yellow
    $runningForwards = (Get-Job | Where-Object { $_.Command -like "*kubectl port-forward*" -and $_.State -eq "Running" } | Measure-Object).Count
    if ($runningForwards -gt 0) {
        Write-Host "  Customer API:    http://localhost:8001/customer/data" -ForegroundColor Green
        Write-Host "  Health Check:    http://localhost:8001/events/health" -ForegroundColor Green
        Write-Host "  RabbitMQ UI:     http://localhost:15673" -ForegroundColor Green
        Write-Host "  RabbitMQ AMQP:   localhost:5673" -ForegroundColor Green
        Write-Host "  PostgreSQL:      localhost:5436" -ForegroundColor Green
        Write-Host "  Prometheus (K8s):http://localhost:9091" -ForegroundColor Green
        Write-Host "  Grafana (K8s):   http://localhost:3001 (admin/fintegrate_admin)" -ForegroundColor Green
    } else {
        Write-Host "  Port-forwards not running - URLs unavailable" -ForegroundColor Red
        Write-Host "  Run option 1 or 3 to start port-forwards" -ForegroundColor Yellow
    }
}

function Run-Migrations {
    Write-Host "`n[Database Migrations]" -ForegroundColor Magenta
    
    $status = minikube status --format='{{.Host}}' 2>&1
    if ($status -notmatch "Running") {
        Write-Host "ERROR: Cluster not running. Start cluster first (option 1)." -ForegroundColor Red
        return
    }
    
    Write-Host ""
    Write-Host "[1] Run Initial Migrations (fresh database)" -ForegroundColor White
    Write-Host "    Runs: 20251023_1630_init_schema.sql" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[2] Run All Migrations (including updates)" -ForegroundColor White
    Write-Host "    Runs all .sql files in database/migrations/" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[3] Run Specific Migration" -ForegroundColor White
    Write-Host "    Select migration file from list" -ForegroundColor Gray
    Write-Host ""
    Write-Host "[4] Manual Connection Info (DBeaver/psql)" -ForegroundColor White
    Write-Host ""
    $choice = Read-Host "Select option"
    
    $migrationsPath = "..\database\migrations"
    
    switch ($choice) {
        "1" {
            Write-Host "Running initial migration..." -ForegroundColor Yellow
            
            $initFile = "$migrationsPath\20251023_1630_init_schema.sql"
            if (-not (Test-Path $initFile)) {
                Write-Host "ERROR: init_schema.sql not found" -ForegroundColor Red
                return
            }
            
            # Read SQL file content
            $sqlContent = Get-Content $initFile -Raw
            
            # Execute via kubectl exec (no psql client needed)
            Write-Host "  Executing migration via kubectl..." -ForegroundColor Gray
            $env:PGPASSWORD = "fintegrate_pass"
            $result = $sqlContent | kubectl exec -i postgres-0 -- psql -U fintegrate_user -d fintegrate_db 2>&1
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Initial migration completed!" -ForegroundColor Green
            } else {
                Write-Host "ERROR: Migration failed" -ForegroundColor Red
                Write-Host $result -ForegroundColor Yellow
            }
        }
        "2" {
            Write-Host "Running all migrations in order..." -ForegroundColor Yellow
            
            $migrations = Get-ChildItem "$migrationsPath\*.sql" | Sort-Object Name
            $env:PGPASSWORD = "fintegrate_pass"
            
            foreach ($migration in $migrations) {
                Write-Host "  Applying: $($migration.Name)" -ForegroundColor Gray
                
                # Read SQL file content
                $sqlContent = Get-Content $migration.FullName -Raw
                
                # Execute via kubectl exec (no psql client needed)
                $result = $sqlContent | kubectl exec -i postgres-0 -- psql -U fintegrate_user -d fintegrate_db 2>&1
                
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "    WARNING: Failed to apply $($migration.Name)" -ForegroundColor Yellow
                }
            }
            Write-Host "All migrations completed!" -ForegroundColor Green
        }
        "3" {
            Write-Host "`nAvailable migrations:" -ForegroundColor Yellow
            $migrations = Get-ChildItem "$migrationsPath\*.sql" | Sort-Object Name
            $i = 1
            $migrations | ForEach-Object { Write-Host "  [$i] $($_.Name)" -ForegroundColor Gray; $i++ }
            Write-Host ""
            $fileChoice = Read-Host "Select file number"
            $selectedFile = $migrations[$fileChoice - 1]
            
            if ($selectedFile) {
                Write-Host "Running: $($selectedFile.Name)" -ForegroundColor Yellow
                
                # Read SQL file content
                $sqlContent = Get-Content $selectedFile.FullName -Raw
                
                # Execute via kubectl exec (no psql client needed)
                $env:PGPASSWORD = "fintegrate_pass"
                $result = $sqlContent | kubectl exec -i postgres-0 -- psql -U fintegrate_user -d fintegrate_db 2>&1
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "Migration completed!" -ForegroundColor Green
                } else {
                    Write-Host "ERROR: Migration failed" -ForegroundColor Red
                    Write-Host $result -ForegroundColor Yellow
                }
            } else {
                Write-Host "Invalid selection" -ForegroundColor Red
            }
        }
        "4" {
            Write-Host "`nDBeaver Connection Info:" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "First, start port-forward in separate terminal:" -ForegroundColor Yellow
            Write-Host "  kubectl port-forward svc/postgres 5436:5432" -ForegroundColor Gray
            Write-Host ""
            Write-Host "Then connect via DBeaver:" -ForegroundColor Cyan
            Write-Host "  Host:     localhost" -ForegroundColor White
            Write-Host "  Port:     5436" -ForegroundColor White
            Write-Host "  Database: fintegrate_db" -ForegroundColor White
            Write-Host "  User:     fintegrate_user" -ForegroundColor White
            Write-Host "  Password: fintegrate_pass" -ForegroundColor White
            Write-Host ""
            Write-Host "Or execute via kubectl directly:" -ForegroundColor Cyan
            Write-Host "  kubectl exec -it postgres-0 -- psql -U fintegrate_user -d fintegrate_db" -ForegroundColor Gray
        }
        default {
            Write-Host "Invalid option" -ForegroundColor Red
        }
    }
    
    Write-Host ""
    Write-Host "To create new migration:" -ForegroundColor Cyan
    Write-Host "  1. Create file: database/migrations/YYYYMMDD_HHMM_description.sql" -ForegroundColor Gray
    Write-Host "  2. Use idempotent SQL (IF NOT EXISTS, IF EXISTS)" -ForegroundColor Gray
    Write-Host "  3. Wrap in BEGIN/COMMIT transaction" -ForegroundColor Gray
    Write-Host "  4. Run via this menu (option 3)" -ForegroundColor Gray
}

function Update-ServiceImages {
    Write-Host "`n[Updating Service Images...]" -ForegroundColor Magenta
    
    $status = minikube status --format='{{.Host}}' 2>&1
    if ($status -notmatch "Running") {
        Write-Host "ERROR: Cluster not running. Start cluster first (option 1)." -ForegroundColor Red
        return
    }
    
    # Check if source code has changed since last build
    $projectRoot = Split-Path $PSScriptRoot
    $servicesPath = Join-Path $projectRoot "services"
    $timestampFile = Join-Path $PSScriptRoot ".last_build_timestamp"
    
    Write-Host "Checking for source code changes..." -ForegroundColor Yellow
    
    # Get latest modification time of Python files in services/
    $latestSourceTime = Get-ChildItem "$servicesPath\**\*.py" -Recurse | 
                        Sort-Object LastWriteTime -Descending | 
                        Select-Object -First 1 -ExpandProperty LastWriteTime
    
    if (-not $latestSourceTime) {
        Write-Host "ERROR: No Python files found in services/ directory" -ForegroundColor Red
        return
    }
    
    $lastBuildTime = $null
    if (Test-Path $timestampFile) {
        $lastBuildTime = Get-Content $timestampFile | Get-Date
    }
    
    Write-Host "  Latest source modification: $($latestSourceTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Gray
    if ($lastBuildTime) {
        Write-Host "  Last build timestamp: $($lastBuildTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Gray
    } else {
        Write-Host "  Last build timestamp: Never" -ForegroundColor Gray
    }
    
    $needsRebuild = $false
    if (-not $lastBuildTime -or $latestSourceTime -gt $lastBuildTime) {
        $needsRebuild = $true
        Write-Host "  Source code has changed - rebuilding images..." -ForegroundColor Yellow
    } else {
        Write-Host "  Source code unchanged - skipping rebuild" -ForegroundColor Green
    }
    
    if ($needsRebuild) {
        # Switch to Minikube Docker context
        Write-Host "Switching Docker context to Minikube..." -ForegroundColor Yellow
        & minikube docker-env --shell powershell | Invoke-Expression
        
        # Verify Docker context
        $dockerName = docker info --format "{{.Name}}" 2>&1
        if ($dockerName -notmatch "minikube") {
            Write-Host "  ERROR: Failed to switch to Minikube Docker" -ForegroundColor Red
            Write-Host "  Current Docker: $dockerName" -ForegroundColor Yellow
            return
        }
        Write-Host "  Docker context: $dockerName" -ForegroundColor Green
        
        # Build images
        Write-Host "Building updated images..." -ForegroundColor Yellow
        Set-Location $projectRoot
        
        Write-Host "  - Building customer-service image..." -ForegroundColor Gray
        docker build -f docker/Dockerfile.customer_service -t fintegrate-customer-service:v1.0 . 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    ERROR: Failed to build customer-service image" -ForegroundColor Red
            return
        }
        
        Write-Host "  - Building event-consumer image..." -ForegroundColor Gray
        docker build -f docker/Dockerfile.event_consumer -t fintegrate-event-consumer:v1.0 . 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    ERROR: Failed to build event-consumer image" -ForegroundColor Red
            return
        }
        
        Write-Host "  - Building aml_service image..." -ForegroundColor Gray
        docker build -f docker/Dockerfile.aml_service -t aml_service:latest . 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    ERROR: Failed to build aml_service image" -ForegroundColor Red
            return
        }
        
        # Update timestamp
        $latestSourceTime.ToString('o') | Out-File $timestampFile -Force
        Write-Host "  Build timestamp updated: $($latestSourceTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Green
        
        Set-Location (Join-Path $projectRoot "kubernetes")
        Write-Host "Images rebuilt successfully!" -ForegroundColor Green
    }
    
    # Always restart services to pick up new images (even if rebuilt)
    Write-Host "Restarting services with updated images..." -ForegroundColor Yellow
    
    $statelessDeployments = @(
        "customer-service",
        "event-consumer-default", 
        "event-consumer-swadia",
        "event-consumer-test001",
        "aml-service",
        "traefik"
    )
    
    foreach ($dep in $statelessDeployments) {
        Write-Host "  - Restarting deployment: $dep" -ForegroundColor Gray
        kubectl rollout restart deployment/$dep 2>&1 | Out-Null
    }
    
    Write-Host "Waiting for pods to be ready..." -ForegroundColor Gray
    kubectl wait --for=condition=ready pod -l app=customer-service --timeout=60s 2>&1 | Out-Null
    
    Write-Host "Service images updated and restarted successfully!" -ForegroundColor Green
}

# Main loop
while ($true) {
    Show-Menu
    $choice = Read-Host "Select option"
    
    switch ($choice) {
        "1" { Start-Cluster; Read-Host "`nPress Enter to continue" }
        "2" { Start-FullDeploy; Read-Host "`nPress Enter to continue" }
        "3" { Restart-Services; Read-Host "`nPress Enter to continue" }
        "4" { Stop-ClusterSafe; Read-Host "`nPress Enter to continue" }
        "5" { Reset-ClusterHard; Read-Host "`nPress Enter to continue" }
        "6" { Show-Logs }
        "7" { Open-Dashboards; Read-Host "`nPress Enter to continue" }
        "8" { Run-Migrations; Read-Host "`nPress Enter to continue" }
        "9" { Show-ClusterStatus; Read-Host "`nPress Enter to continue" }
        "10" { Update-ServiceImages; Read-Host "`nPress Enter to continue" }
        "q" { Write-Host "`nGoodbye!" -ForegroundColor Cyan; exit }
        "Q" { Write-Host "`nGoodbye!" -ForegroundColor Cyan; exit }
        default { Write-Host "`nInvalid option" -ForegroundColor Red; Start-Sleep -Seconds 1 }
    }
}
