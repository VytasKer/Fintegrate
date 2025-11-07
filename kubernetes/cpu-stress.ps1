# CPU stress test - runs intensive computation in pod
param(
    [int]$DurationSeconds = 60
)

Write-Host "Starting CPU stress test for $DurationSeconds seconds..." -ForegroundColor Cyan

$podName = kubectl get pod -l app=customer-service -o jsonpath='{.items[0].metadata.name}'
Write-Host "Target pod: $podName" -ForegroundColor Yellow
Write-Host ""

$endTime = (Get-Date).AddSeconds($DurationSeconds)
$jobs = @()

# Start 4 parallel CPU stress jobs
Write-Host "Starting 4 parallel CPU stress jobs..." -ForegroundColor Green
for ($i = 1; $i -le 4; $i++) {
    $job = Start-Job -ScriptBlock {
        param($podName, $endTime, $jobId)
        
        $iterationCount = 0
        while ((Get-Date) -lt $endTime) {
            kubectl exec $podName -- python -c "sum(x**2 for x in range(5000000))" 2>&1 | Out-Null
            $iterationCount++
        }
        
        return @{
            JobId = $jobId
            Iterations = $iterationCount
        }
    } -ArgumentList $podName, $endTime, $i
    
    $jobs += $job
}

Write-Host "Jobs started. Monitoring HPA..." -ForegroundColor Cyan
Write-Host ""

# Monitor HPA and pods
$startTime = Get-Date
while ((Get-Date) -lt $endTime) {
    $elapsed = [math]::Round(((Get-Date) - $startTime).TotalSeconds)
    
    $hpaStatus = kubectl get hpa customer-service-hpa --no-headers 2>&1
    $podCount = (kubectl get pods -l app=customer-service --no-headers 2>&1 | Measure-Object).Count
    
    Write-Host "`r[${elapsed}s] HPA: $hpaStatus | Pods: $podCount" -NoNewline -ForegroundColor Cyan
    
    Start-Sleep -Seconds 5
}

Write-Host ""
Write-Host ""
Write-Host "Stopping stress jobs..." -ForegroundColor Yellow

$results = $jobs | Receive-Job -Wait
$jobs | Remove-Job

Write-Host ""
Write-Host "CPU stress test complete!" -ForegroundColor Green

Start-Sleep -Seconds 2
Write-Host ""
Write-Host "Final HPA status:" -ForegroundColor Yellow
kubectl get hpa customer-service-hpa

Write-Host ""
Write-Host "Final pod count:" -ForegroundColor Yellow
kubectl get pods -l app=customer-service

Write-Host ""
Write-Host "HPA events:" -ForegroundColor Yellow
kubectl describe hpa customer-service-hpa | Select-String -Pattern "Events:" -Context 0,10
