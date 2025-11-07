# Copy resources from default namespace to target namespaces
# Usage: .\copy-to-namespace.ps1 -Namespace test

param(
    [Parameter(Mandatory=$true)]
    [string]$Namespace
)

Write-Host "Copying Secrets and ConfigMaps to namespace: $Namespace" -ForegroundColor Cyan

# Copy postgres-secret
Write-Host "  [1/3] Copying postgres-secret..." -ForegroundColor Gray
kubectl get secret postgres-secret -n default -o yaml > temp-secret.yaml
(Get-Content temp-secret.yaml) -replace 'namespace: default',"namespace: $Namespace" | kubectl apply -f - | Out-Null
Remove-Item temp-secret.yaml

# Copy rabbitmq-secret
Write-Host "  [2/3] Copying rabbitmq-secret..." -ForegroundColor Gray
kubectl get secret rabbitmq-secret -n default -o yaml > temp-secret.yaml
(Get-Content temp-secret.yaml) -replace 'namespace: default',"namespace: $Namespace" | kubectl apply -f - | Out-Null
Remove-Item temp-secret.yaml

# Copy app-config ConfigMap
Write-Host "  [3/3] Copying app-config ConfigMap..." -ForegroundColor Gray
kubectl get configmap app-config -n default -o yaml > temp-cm.yaml
(Get-Content temp-cm.yaml) -replace 'namespace: default',"namespace: $Namespace" | kubectl apply -f - | Out-Null
Remove-Item temp-cm.yaml

Write-Host "Success: Resources copied to $Namespace namespace" -ForegroundColor Green
