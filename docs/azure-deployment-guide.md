az keyvault secret set --vault-name fintegrate-keyvault `
az keyvault secret set --vault-name fintegrate-keyvault `
# Fintegrate — Azure Deployment Guide (Portal + GitHub Integration)

This document explains how to deploy the Fintegrate learning platform to Microsoft Azure using the Azure Portal (UI) and GitHub integration for build & deploy. It replaces long CLI scripts with clear, Portal-driven workflows so you can learn the resources visually and use GitHub Actions for CI/CD.

Audience: learners who prefer the Azure Portal and GitHub UI to execute builds, push images, and run containerized services.

---

## What you'll create (high level)

- Resource Group to contain everything
- Azure Database for PostgreSQL (Flexible Server)
- Azure Service Bus (managed messaging)
- Azure Key Vault (secrets)
- Container Registry (optional) or GitHub Container Registry via GitHub Actions
- Azure Container Apps environment and Container Apps for services
- Application Insights + Log Analytics for monitoring

Why this approach
- The Portal teaches resource relationships visually.
- GitHub Actions builds and publishes images from your repo (automatic on push).

---

## Quick checklist before you start

- An Azure subscription and permissions to create resources
- Your code in GitHub (this repo). Dockerfiles should be in `docker/` and services under `services/`.
- Consider creating a small resource group for this project (easier cleanup).

Tip: use the Portal first; it's safe and reversible. When you are comfortable, convert steps into automation (GitHub Actions, Bicep, Terraform).

---

## Portal-first workflow (step-by-step, UI-focused)

This section gives concise UI instructions for each resource. For each item: open the Portal (https://portal.azure.com) and follow the described clicks.

### 1) Create the Resource Group

1. Search for **Resource groups** → **+ Create**.
2. Select subscription, name it (e.g. `rg-fintegrate-dev`), pick a region (e.g. `East US`), and click **Review + create** → **Create**.

Why: grouping resources makes management and cleanup easier.

### 2) Provision PostgreSQL (Flexible Server) via Portal

1. Search for **Azure Database for PostgreSQL flexible server** → **Create**.
2. Fill in the form:
   - Choose your Resource group (`rg-fintegrate-dev`)
   - Server name (e.g. `fintegrate-db-dev`)
   - Region: same as your resource group
   - Compute: choose the smallest available (B1ms if eligible)
   - Admin username and password: record these securely (add to Key Vault later)
3. Networking: for learning you can allow public access, but consider using VNet for production.
4. Click **Review + create** → **Create**.

After creation: open the server → **Connection strings** to see the format of the DB URL.

### 3) Create Service Bus (Portal)

1. Search for **Service Bus** → **Namespaces** → **+ Create**.
2. Select Basic or Standard SKU for testing, put it into your resource group.
3. After creation, open the namespace → **Shared access policies** → `RootManageSharedAccessKey` → copy the Primary Connection String.

This replaces RabbitMQ for a learning-managed messaging system.

### 4) Create Key Vault and add secrets (Portal)

1. Search for **Key Vaults** → **+ Create**.
2. Pick your resource group and a name (e.g. `fintegrate-kv-dev`).
3. After creation open Key Vault → **Secrets** → **+ Generate/Import**.
4. Add secrets for the DB connection and Service Bus connection string (and Redis if used):
   - `DB_CONNECTION_STRING` (postgres connection URL)
   - `SERVICEBUS_CONNECTION_STRING`

Tip: You can later grant the Container Apps managed identity access to these secrets via **Access policies**.

### 5) Choose where images live: GitHub Container Registry (recommended) or ACR

Option A — GitHub Container Registry (GHCR)
- Use GHCR and GitHub Actions to build & push images automatically. It supports private images and integrates with GitHub Actions easily.

Option B — Azure Container Registry (ACR)
- Create ACR from the Portal (**Container registries** → **+ Create**) if you prefer all-in-Azure. Use Portal options to enable admin user or service principal access.

Recommendation: GHCR + GitHub Actions for learning (free, private images).

### 6) Configure GitHub Actions to build & publish images (GitHub UI)

1. Open your repository on GitHub → **Actions** → **New workflow**.
2. Choose **Set up a workflow yourself** or select a template for building Docker images.
3. Create or paste a workflow that:
   - Checks out the repo
   - Builds the Dockerfile(s) in `docker/`
   - Tags images as `ghcr.io/<your-username>/fintegrate-customer-service:${{ github.sha }}` or a semantic tag
   - Pushes to GHCR (set up `GITHUB_TOKEN` or a PAT with `read:packages write:packages`)

Azure Portal option: when creating a Container App you can select **Use GitHub** as the image source; the Portal will scaffold a GitHub Action in your repo automatically.

### 7) Create Container Apps Environment (Portal)

1. Search for **Container Apps** → **Environments** → **+ Create**.
2. Choose Resource group `rg-fintegrate-dev`, name the environment (e.g. `fintegrate-env`), and create or choose a Log Analytics workspace for monitoring.

Container Apps environment groups containerized workloads and provides ingress, scale and revisions.

### 8) Deploy Customer Service via Portal (image or GitHub)

1. Search for **Container Apps** → **Create**.
2. On the **Basics** tab: pick subscription, resource group, name (e.g. `customer-service`) and environment `fintegrate-env`.
3. In **Container** configuration:
   - **Image source**: choose one of:
     - **Image from container registry**: enter `ghcr.io/<your-org>/fintegrate-customer-service:<tag>` or your ACR image
     - **Source control (GitHub)**: follow prompts to connect the repo; Portal will create a GitHub Actions workflow to build and deploy
   - Set **Ingress** to **External**, target port `8000`.
4. Add environment variables and bind secrets from Key Vault where necessary.
5. Configure scale (min 1, max 2 for learning) and resource limits.
6. Click **Review + create** → **Create**.

Repeat these steps for `aml-service` (internal ingress) and `event-consumer` (internal, scale per need).

### 9) Grant Container Apps access to Key Vault

1. Open Key Vault → **Access policies** → **+ Add Access Policy**.
2. Choose Secret permissions (Get) and assign to the managed identity of your Container App (or the Container Apps environment identity).
3. Save.

This allows your service to fetch DB and Service Bus credentials securely.

### 10) Configure Application Insights (Portal)

1. Search **Application Insights** → **+ Create**.
2. Choose Resource group and name (e.g. `fintegrate-appinsights`).
3. In the Container App configuration add `APPLICATIONINSIGHTS_CONNECTION_STRING` or `APPINSIGHTS_INSTRUMENTATIONKEY` environment variable (Portal exposes a form for env vars).

Application Insights captures telemetry and provides Live Metrics and Application Map.

### 11) Verify deployment and logs (Portal + GitHub)

- Azure Portal: open **Container Apps** → select `customer-service` → **Overview** to get public FQDN and **Logs** to stream startup logs.
- GitHub: check **Actions** runs for the workflow that builds and pushes images. If the Portal scaffolder created a workflow, it will show up in `.github/workflows/`.

Test the API by calling the Container App FQDN or using the Portal's **Quick start** page for the Container App.

### 12) Clean up (Portal)

To delete everything: open **Resource groups**, select `rg-fintegrate-dev`, and click **Delete resource group**. Confirm by typing the resource group name. This removes all associated resources.

---

## Helpful learning notes

- Use the Portal to explore resource settings (networking, scaling, identities). Visual settings are the fastest way to understand relationships.
- When the Portal scaffolds a GitHub Action, open the workflow file to learn what steps it performs; then iteratively improve it.
- For production-like flows, convert Portal steps into Bicep or Terraform after you understand them.

---

Would you like me to:

- Generate a ready-to-use GitHub Actions workflow (YAML) that builds your Dockerfiles and publishes images to GHCR, or
- Produce a short click-by-click Portal checklist (one-pager) for each resource (Database, Service Bus, Key Vault, Container Apps)?

Pick one and I will prepare it next.

**Code Changes Required:**

```python
# Before (RabbitMQ with pika)
import pika

connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='rabbitmq')
)
channel = connection.channel()
channel.queue_declare(queue='customer-events')
channel.basic_publish(
    exchange='',
    routing_key='customer-events',
    body=message
)

# After (Service Bus)
from azure.servicebus import ServiceBusClient, ServiceBusMessage

client = ServiceBusClient.from_connection_string(connection_string)
with client:
    sender = client.get_queue_sender(queue_name="customer-events")
    with sender:
        message = ServiceBusMessage(body)
        sender.send_messages(message)
```

**What to Learn:**
- Service Bus queues vs topics vs subscriptions
- Message sessions for ordering
- Dead-letter queues for failed messages
- Peek-lock vs receive-and-delete modes

#### 3. **Prometheus → Application Insights**

**Instrumentation Changes:**

```python
# Add to requirements.txt
opencensus-ext-azure==1.1.9
opencensus-ext-flask==0.8.0

# In your FastAPI app
from opencensus.ext.azure import metrics_exporter
from opencensus.stats import aggregation as aggregation_module
from opencensus.stats import measure as measure_module
from opencensus.stats import stats as stats_module
from opencensus.stats import view as view_module

# Create metrics
exporter = metrics_exporter.new_metrics_exporter(
    connection_string=f'InstrumentationKey={instrumentation_key}'
)

# Track custom metrics
stats_recorder = stats_module.stats.stats_recorder
measure = measure_module.MeasureInt("requests", "number of requests", "requests")
view_manager = stats_module.stats.view_manager
view_manager.register_exporter(exporter)
```

**What to Learn:**
- Application Insights automatically tracks:
  - HTTP requests & responses
  - Dependencies (DB calls, Service Bus)
  - Exceptions and traces
  - Custom events and metrics
- KQL (Kusto Query Language) for log analysis
- Application Map for distributed tracing

#### 4. **Local Storage → Azure Storage**

```python
# For sanctions data, Airflow logs, etc.
from azure.storage.blob import BlobServiceClient

# Upload sanctions data
blob_service = BlobServiceClient.from_connection_string(storage_connection_string)
container_client = blob_service.get_container_client("sanctions-data")

with open("local_file.xml", "rb") as data:
    blob_client = container_client.get_blob_client("file.xml")
    blob_client.upload_blob(data, overwrite=True)
```

#### 5. **Secrets Management**

```python
# Never hardcode secrets!
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
client = SecretClient(vault_url="https://fintegrate-keyvault.vault.azure.net/", credential=credential)

db_connection = client.get_secret("db-connection-string").value
```

**What to Learn:**
- Managed Identity for authentication (no passwords!)
- Key Vault secret rotation
- Container Apps secret references

---

## ⚠️ Common Mistakes to Avoid

### 1. **Not Monitoring Costs**
```powershell
# ❌ MISTAKE: Deploy everything and forget
# ✅ SOLUTION: Check costs daily

# Set up cost alerts
az monitor metrics alert create `
  --name high-cost-alert `
  --resource-group rg-fintegrate-dev `
  --scopes "/subscriptions/YOUR_SUB_ID" `
  --condition "total Cost > 25"
```

### 2. **Hardcoding Connection Strings**
```python
# ❌ MISTAKE
DATABASE_URL = "postgresql://user:pass@server.com/db"

# ✅ SOLUTION
import os
DATABASE_URL = os.getenv("DATABASE_URL")  # From Key Vault
```

### 3. **Not Using Resource Tags**
```powershell
# ✅ Tag all resources for cost tracking
az resource tag `
  --tags Environment=Learning Project=Fintegrate `
  --ids $(az resource list --resource-group rg-fintegrate-dev --query "[].id" -o tsv)
```

### 4. **Ignoring Security**
```powershell
# ❌ MISTAKE: Public PostgreSQL with 0.0.0.0 firewall
# ✅ SOLUTION: Use VNet integration

# Create VNet
az network vnet create `
  --name fintegrate-vnet `
  --resource-group rg-fintegrate-dev `
  --address-prefix 10.0.0.0/16 `
  --subnet-name db-subnet `
  --subnet-prefix 10.0.1.0/24

# Restrict PostgreSQL to VNet only
az postgres flexible-server update `
  --name fintegrate-db-dev `
  --resource-group rg-fintegrate-dev `
  --public-access Disabled
```

### 5. **Not Setting Up Autoscaling Limits**
```powershell
# ❌ MISTAKE: Infinite autoscaling → infinite costs
# ✅ SOLUTION: Set hard limits

az containerapp update `
  --name customer-service `
  --resource-group rg-fintegrate-dev `
  --min-replicas 0 `
  --max-replicas 2  # Hard cap!
```

### 6. **Skipping Infrastructure as Code**
```powershell
# ✅ SOLUTION: Use Bicep or Terraform

# Export current setup to ARM template
az group export `
  --name rg-fintegrate-dev `
  --output json > azure-infrastructure.json
```

### 7. **Not Testing Locally First**
```bash
# ✅ Test Docker images locally before pushing
docker-compose up

# ✅ Verify migrations work
docker exec -it fintegrate-postgres psql -U fintegrate_user -d fintegrate_db
```

### 8. **Deploying to Production Regions**
```powershell
# ❌ MISTAKE: Using expensive regions
# ✅ SOLUTION: Use East US or West US 2 for learning

# Check pricing differences
az account list-locations -o table
```

---

## ✅ Verification & Testing

### 1. Health Checks

```powershell
# Test customer service
$customerUrl = az containerapp show `
  --name customer-service `
  --resource-group rg-fintegrate-dev `
  --query properties.configuration.ingress.fqdn -o tsv

curl "https://$customerUrl/health"

# Expected response: {"status": "healthy", "database": "connected"}
```

### 2. Database Connectivity

```powershell
# Connect to PostgreSQL
$env:PGPASSWORD = "YourSecurePassword123!"
psql -h fintegrate-db-dev.postgres.database.azure.com `
     -U fintegrate_admin `
     -d fintegrate_db `
     -c "SELECT version();"
```

### 3. Service Bus Message Flow

```powershell
# Send test message to queue
az servicebus queue send `
  --namespace-name fintegrate-servicebus-dev `
  --resource-group rg-fintegrate-dev `
  --name customer-events `
  --message "Test message"

# Check if event consumer processed it
az containerapp logs show `
  --name event-consumer `
  --resource-group rg-fintegrate-dev `
  --follow
```

### 4. Application Insights Telemetry

```powershell
# Check if telemetry is flowing
# Go to Azure Portal → Application Insights → Live Metrics

# Or query with CLI
az monitor app-insights query `
  --app fintegrate-insights `
  --resource-group rg-fintegrate-dev `
  --analytics-query "requests | where timestamp > ago(1h) | summarize count() by name"
```

### 5. End-to-End API Test

```powershell
# Create customer
$response = curl -X POST "https://$customerUrl/customer" `
  -H "Content-Type: application/json" `
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "date_of_birth": "1990-01-01",
    "country": "US"
  }'

echo $response

# Check event was published
az servicebus queue show `
  --namespace-name fintegrate-servicebus-dev `
  --resource-group rg-fintegrate-dev `
  --name customer-events `
  --query messageCount
```

---

## 🧹 Cleanup Guide

### Quick Cleanup (Delete Everything)

```powershell
# Delete entire resource group (CAUTION: Deletes all resources!)
az group delete --name rg-fintegrate-dev --yes --no-wait
```

### Selective Cleanup (Keep Database, Stop Services)

```powershell
# Stop Container Apps (scale to 0)
az containerapp update --name customer-service --resource-group rg-fintegrate-dev --min-replicas 0 --max-replicas 0
az containerapp update --name aml-service --resource-group rg-fintegrate-dev --min-replicas 0 --max-replicas 0
az containerapp update --name event-consumer --resource-group rg-fintegrate-dev --min-replicas 0 --max-replicas 0
az containerapp update --name grafana --resource-group rg-fintegrate-dev --min-replicas 0 --max-replicas 0

# Stop PostgreSQL
az postgres flexible-server stop --name fintegrate-db-dev --resource-group rg-fintegrate-dev

# Delete Redis (saves $15/month)
az redis delete --name fintegrate-cache-dev --resource-group rg-fintegrate-dev
```

---

## 📖 Additional Learning Resources

### Azure Documentation
- [Azure Container Apps Documentation](https://learn.microsoft.com/en-us/azure/container-apps/)
- [Azure Service Bus Concepts](https://learn.microsoft.com/en-us/azure/service-bus-messaging/)
- [Application Insights Overview](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)

### Tutorials to Try
1. **Container Apps + Service Bus**: [Event-Driven Apps Tutorial](https://learn.microsoft.com/en-us/azure/container-apps/tutorial-event-driven-jobs)
2. **KQL for Log Analytics**: [Interactive KQL Tutorial](https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/tutorial)
3. **Azure Architecture Center**: [Microservices Patterns](https://learn.microsoft.com/en-us/azure/architecture/microservices/)

### Cost Management
- [Azure Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/)
- [Azure Free Account FAQ](https://azure.microsoft.com/en-us/free/free-account-faq/)
- [Cost Management Best Practices](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/cost-mgt-best-practices)

---

## 🎯 Next Steps After Deployment

1. **Implement CI/CD with GitHub Actions**
   ```yaml
   # .github/workflows/deploy.yml
   name: Deploy to Azure
   on: [push]
   jobs:
     build-and-deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: azure/login@v1
         - uses: azure/container-apps-deploy-action@v1
   ```

2. **Set Up Custom Domains**
   ```powershell
   az containerapp hostname add `
     --name customer-service `
     --resource-group rg-fintegrate-dev `
     --hostname api.yourdomain.com
   ```

3. **Implement API Management**
   ```powershell
   az apim create `
     --name fintegrate-api `
     --resource-group rg-fintegrate-dev `
     --publisher-email your@email.com `
     --publisher-name "Fintegrate" `
     --sku-name Consumption
   ```

4. **Add Azure Front Door for CDN**
   ```powershell
   az afd profile create `
     --profile-name fintegrate-cdn `
     --resource-group rg-fintegrate-dev `
     --sku Standard_AzureFrontDoor
   ```

---

## 🏆 Success Checklist

- [ ] All services deployed to Azure Container Apps
- [ ] PostgreSQL database accessible and migrated
- [ ] Service Bus queues created and tested
- [ ] Application Insights receiving telemetry
- [ ] Cost alerts configured (<$30/month)
- [ ] Secrets stored in Key Vault
- [ ] All services communicating correctly
- [ ] Grafana dashboards showing metrics
- [ ] End-to-end API test passing
- [ ] Resource tags applied
- [ ] Cleanup script tested

---

## 💡 Pro Tips for Learning

1. **Use Azure Portal GUI First**, then CLI
   - Visual understanding helps
   - Then automate with scripts

2. **Check Application Map in App Insights**
   - Shows service dependencies visually
   - Great for understanding microservices communication

3. **Use "Cost Analysis" Daily**
   - Go to Resource Group → Cost Analysis
   - Filter by service to see where money goes

4. **Read Container Apps Logs Regularly**
   ```powershell
   az containerapp logs show --name customer-service --resource-group rg-fintegrate-dev --follow
   ```

5. **Experiment with Scaling**
   ```powershell
   # Manual scale
   az containerapp update --name customer-service --min-replicas 3

   # Watch it happen in real-time
   az containerapp replica list --name customer-service --resource-group rg-fintegrate-dev
   ```

6. **Use Azure Cloud Shell** for quick testing
   - No local setup needed
   - Pre-installed tools

---

> [!IMPORTANT]
> **Final Note**: This guide prioritizes learning over perfection. In production, you'd use:
> - Managed Identity instead of passwords
> - Private endpoints instead of public access
> - Zone redundancy for high availability
> - Infrastructure as Code (Bicep/Terraform)
> - Proper monitoring and alerting
> - Security scanning in CI/CD
> 
> For learning, trade-offs were made for simplicity and cost. Always remember to **delete resources** when done to avoid unexpected charges!

---

**Questions or Issues?** 
- Check [Azure Documentation](https://learn.microsoft.com/en-us/azure/)
- Azure Support Forums
- Stack Overflow [azure] tag
