# Fintegrate Azure Deployment - Quick Reference Guide

## 💰 Three Deployment Tiers

### Tier 1: Zero Cost (100% Free)
**Monthly Cost: $0** ✅

**What's Included:**
- ✅ Azure Container Apps (free tier)
- ✅ PostgreSQL (B1ms - free for 12 months)
- ✅ Azure Service Bus (1M ops/month free)
- ✅ GitHub Container Registry (unlimited private images)
- ✅ Application Insights (5GB/month free)
- ✅ Azure Monitor & Log Analytics
- ✅ Key Vault (10K ops/month free)
- ✅ Storage (5GB free)
- ❌ **No Redis** (use in-memory rate limiting)
- ❌ **Limited to ~100 hours/month** of runtime

**Best For:** 
- Learning Azure basics
- Testing deployments
- Short experiments
- Budget-conscious learners

---

### Tier 2: Minimal Cost (Almost Free)
**Monthly Cost: $0-15** 💵

**What's Included:**
- ✅ Everything from Tier 1
- ✅ GitHub Container Registry or Docker Hub (FREE)
- ✅ Optional: Redis ($15/month) for production-like features
- ❌ No ACR ($5 saved)

**Best For:**
- Longer learning sessions
- Testing with production-like features
- Learning Redis caching patterns
- Multi-day experiments

---

### Tier 3: Full Featured
**Monthly Cost: $20-25** 💰

**What's Included:**
- ✅ Everything from Tier 2
- ✅ Azure Container Registry ($5/month)
- ✅ Redis Cache ($15/month)
- ✅ All production-like features

**Best For:**
- Complete Azure learning experience
- Learning ACR specifically
- Long-term projects
- Resume-building portfolio

---

## 🚀 Quick Start: Zero Cost Deployment

### Prerequisites (5 minutes)
```powershell
# 1. Install Azure CLI
winget install Microsoft.AzureCLI

# 2. Login
az login

# 3. Install extensions
az extension add --name containerapp

# 4. Create resource group
az group create --name rg-fintegrate-dev --location eastus
```

### Container Registry Setup (FREE - GitHub)
```powershell
# 1. Create GitHub Personal Access Token
#    GitHub.com → Settings → Developer settings → Personal access tokens (classic)
#    Scopes: write:packages, read:packages

# 2. Save token as environment variable
$env:GITHUB_TOKEN = "ghp_YourTokenHere"
$env:GITHUB_USERNAME = "your-github-username"

# 3. Login to GitHub Container Registry
echo $env:GITHUB_TOKEN | docker login ghcr.io -u $env:GITHUB_USERNAME --password-stdin

# 4. Build and push images
cd "c:\Users\Vytas K\Documents\Software Projects\Fintegrate"

# Customer Service
docker build -t ghcr.io/$env:GITHUB_USERNAME/customer-service:v1.0 `
  -f docker/Dockerfile.customer_service .
docker push ghcr.io/$env:GITHUB_USERNAME/customer-service:v1.0

# AML Service
docker build -t ghcr.io/$env:GITHUB_USERNAME/aml-service:v1.0 `
  -f docker/Dockerfile.aml_service .
docker push ghcr.io/$env:GITHUB_USERNAME/aml-service:v1.0

# Event Consumer
docker build -t ghcr.io/$env:GITHUB_USERNAME/event-consumer:v1.0 `
  -f docker/Dockerfile.event_consumer .
docker push ghcr.io/$env:GITHUB_USERNAME/event-consumer:v1.0
```

### Database Setup (FREE - 12 months)
```powershell
# Create PostgreSQL Flexible Server (FREE B1ms tier)
az postgres flexible-server create `
  --name fintegrate-db-dev `
  --resource-group rg-fintegrate-dev `
  --location eastus `
  --admin-user fintegrate_admin `
  --admin-password "YourSecurePass123!" `
  --sku-name Standard_B1ms `
  --tier Burstable `
  --version 15 `
  --storage-size 32 `
  --public-access 0.0.0.0

# Create database
az postgres flexible-server db create `
  --server-name fintegrate-db-dev `
  --resource-group rg-fintegrate-dev `
  --database-name fintegrate_db

# Allow Azure services
az postgres flexible-server firewall-rule create `
  --name fintegrate-db-dev `
  --resource-group rg-fintegrate-dev `
  --rule-name AllowAzureServices `
  --start-ip-address 0.0.0.0 `
  --end-ip-address 0.0.0.0
```

### Service Bus Setup (FREE)
```powershell
# Create namespace
az servicebus namespace create `
  --name fintegrate-servicebus-dev `
  --resource-group rg-fintegrate-dev `
  --location eastus `
  --sku Basic

# Create queues
az servicebus queue create `
  --namespace-name fintegrate-servicebus-dev `
  --resource-group rg-fintegrate-dev `
  --name customer-events

# Get connection string (save this!)
$serviceBusConn = az servicebus namespace authorization-rule keys list `
  --namespace-name fintegrate-servicebus-dev `
  --resource-group rg-fintegrate-dev `
  --name RootManageSharedAccessKey `
  --query primaryConnectionString -o tsv
```

### Container Apps Environment (FREE)
```powershell
# Register provider
az provider register --namespace Microsoft.App

# Create environment
az containerapp env create `
  --name fintegrate-env `
  --resource-group rg-fintegrate-dev `
  --location eastus

# Create Application Insights
az monitor app-insights component create `
  --app fintegrate-insights `
  --location eastus `
  --resource-group rg-fintegrate-dev `
  --application-type web

$instrumentationKey = az monitor app-insights component show `
  --app fintegrate-insights `
  --resource-group rg-fintegrate-dev `
  --query instrumentationKey -o tsv
```

### Deploy Services (FREE)
```powershell
# Build DB connection string
$dbConnection = "postgresql://fintegrate_admin:YourSecurePass123!@fintegrate-db-dev.postgres.database.azure.com:5432/fintegrate_db"

# Deploy Customer Service
az containerapp create `
  --name customer-service `
  --resource-group rg-fintegrate-dev `
  --environment fintegrate-env `
  --image ghcr.io/$env:GITHUB_USERNAME/customer-service:v1.0 `
  --registry-server ghcr.io `
  --registry-username $env:GITHUB_USERNAME `
  --registry-password $env:GITHUB_TOKEN `
  --target-port 8000 `
  --ingress external `
  --min-replicas 1 `
  --max-replicas 2 `
  --cpu 0.5 `
  --memory 1Gi `
  --env-vars `
    "DATABASE_URL=$dbConnection" `
    "SERVICEBUS_CONNECTION_STRING=$serviceBusConn" `
    "APPINSIGHTS_INSTRUMENTATIONKEY=$instrumentationKey"

# Get your service URL
$customerUrl = az containerapp show `
  --name customer-service `
  --resource-group rg-fintegrate-dev `
  --query properties.configuration.ingress.fqdn -o tsv

Write-Host "Customer Service URL: https://$customerUrl"
```

---

## 📊 Cost Comparison Matrix

| Feature | Zero Cost | Minimal Cost | Full Featured |
|---------|-----------|--------------|---------------|
| **Container Registry** | GitHub (free) | Docker Hub/GitHub (free) | ACR ($5) |
| **Redis Cache** | ❌ None | ✅ Optional ($15) | ✅ Included ($15) |
| **PostgreSQL** | ✅ B1ms (free 12mo) | ✅ B1ms (free 12mo) | ✅ B1ms (free 12mo) |
| **Service Bus** | ✅ Basic (free) | ✅ Basic (free) | ✅ Basic (free) |
| **Container Apps** | ✅ Free tier | ✅ Free tier | ✅ Free tier |
| **Monitoring** | ✅ App Insights (free) | ✅ App Insights (free) | ✅ App Insights (free) |
| **Runtime Limit** | ~100 hrs/month | ~100 hrs/month | ~100 hrs/month |
| **Monthly Cost** | **$0** | **$0-15** | **$20-25** |

---

## 🛑 Daily Stop Script (Save Free Tier Hours)

```powershell
# save-free-tier.ps1
# Run this when you're done learning for the day

# Stop all Container Apps (scale to 0)
az containerapp update --name customer-service --resource-group rg-fintegrate-dev --min-replicas 0 --max-replicas 0
az containerapp update --name aml-service --resource-group rg-fintegrate-dev --min-replicas 0 --max-replicas 0
az containerapp update --name event-consumer --resource-group rg-fintegrate-dev --min-replicas 0 --max-replicas 0

# Stop PostgreSQL
az postgres flexible-server stop --name fintegrate-db-dev --resource-group rg-fintegrate-dev

Write-Host "✅ All services stopped. Free tier hours preserved!"
```

## ▶️ Daily Start Script

```powershell
# start-learning.ps1
# Run this when you want to resume learning

# Start PostgreSQL
az postgres flexible-server start --name fintegrate-db-dev --resource-group rg-fintegrate-dev

# Start Container Apps
az containerapp update --name customer-service --resource-group rg-fintegrate-dev --min-replicas 1 --max-replicas 2

Write-Host "✅ Services started. Ready to learn!"
```

---

## 🧹 Complete Cleanup (Delete Everything)

```powershell
# ⚠️ WARNING: This deletes ALL resources in the resource group!
# Are you sure? Type 'yes' if you're absolutely certain.

$confirmation = Read-Host "Type 'DELETE' to confirm deletion of all resources"

if ($confirmation -eq "DELETE") {
    az group delete --name rg-fintegrate-dev --yes --no-wait
    Write-Host "🗑️ Resource group deletion started. This may take 5-10 minutes."
} else {
    Write-Host "❌ Deletion cancelled."
}
```

---

## 📈 Free Tier Usage Monitoring

```powershell
# Check Container Apps usage
az containerapp list --resource-group rg-fintegrate-dev --output table

# Check PostgreSQL free tier status
az postgres flexible-server show `
  --name fintegrate-db-dev `
  --resource-group rg-fintegrate-dev `
  --query "{Name:name, Tier:sku.tier, Size:sku.name, Status:state}" `
  --output table

# Check Application Insights ingestion
az monitor app-insights component show `
  --app fintegrate-insights `
  --resource-group rg-fintegrate-dev `
  --query "{Name:name, IngestionMode:ingestionMode}" `
  --output table

# View current month costs
az consumption usage list `
  --start-date (Get-Date).ToString("yyyy-MM-01") `
  --end-date (Get-Date).ToString("yyyy-MM-dd") `
  --query "[].{Service:instanceName, Cost:pretaxCost}" `
  --output table
```

---

## 🎯 Recommended Learning Path

### Week 1: Zero Cost Tier
- Learn Azure basics
- Deploy with GitHub Container Registry
- Experiment with Container Apps
- Practice start/stop scripts
- **Cost: $0**

### Week 2-3: Add Redis (Minimal Cost)
- Enable Redis for rate limiting
- Learn Azure Cache patterns
- Implement production-like features
- **Cost: $15/month**

### Week 4+: Full Featured (Optional)
- Add Azure Container Registry
- Learn ACR features
- Implement CI/CD with Actions
- **Cost: $20-25/month**

---

## 💡 Pro Tips

1. **Use Azure Free Credits**: New Azure accounts get $200 credit for 30 days
2. **Set Budget Alerts**: Create alerts at $5, $10, $15 thresholds
3. **Tag Everything**: Tag resources with `Environment=Learning` for easy tracking
4. **Screenshot Everything**: Document your work for your resume/portfolio
5. **Use Cloud Shell**: No local setup needed for quick commands
6. **Check Free Tier Expiry**: PostgreSQL free tier ends after 12 months
7. **GitHub Student Pack**: Get extra Azure credits if you're a student

---

## 📞 Quick Support Links

- **Azure Free Account**: https://azure.microsoft.com/free/
- **GitHub Container Registry**: https://docs.github.com/packages
- **Docker Hub**: https://hub.docker.com/
- **Container Apps Docs**: https://learn.microsoft.com/azure/container-apps/
- **Cost Calculator**: https://azure.microsoft.com/pricing/calculator/

---

## ✅ Final Checklist for Zero Cost Deployment

- [ ] Azure account created (free tier)
- [ ] GitHub account with personal access token
- [ ] Docker Desktop installed
- [ ] Azure CLI installed
- [ ] Resource group created
- [ ] Images pushed to GitHub Container Registry (FREE)
- [ ] PostgreSQL deployed (FREE for 12 months)
- [ ] Service Bus created (FREE)
- [ ] Container Apps deployed (FREE tier)
- [ ] Application Insights enabled (FREE 5GB)
- [ ] Budget alert set at $5
- [ ] Stop script created for daily use
- [ ] **Total Monthly Cost: $0** ✅

**Next Step**: Start with the full deployment guide at `azure-deployment-guide.md`
