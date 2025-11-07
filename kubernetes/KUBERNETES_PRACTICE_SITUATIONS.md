# Kubernetes Practice Situations for Integration Architects

**Purpose**: Real-world scenarios combining troubleshooting, security audits, resource management, and architectural decisions. Focus on understanding structure and thought process, not command memorization.

---

## Situation 1: Customer-Service Pod Not Responding After Deployment

### Context
Your manager reports that after deploying a new version of customer-service, the API is not responding at `http://localhost:8001/customer/data`. The deployment command succeeded without errors, but clients are getting connection timeouts. You need to diagnose and fix the issue quickly.

### Possible Root Causes (Assumptions)
1. Pod is running but container failed health checks (readiness probe failing)
2. Image pull failed (wrong tag or image doesn't exist)
3. ConfigMap/Secret missing in namespace
4. Container crashed immediately after start (application error)
5. Service not routing to new pods (selector mismatch)

### Step-by-Step Troubleshooting Hints

**Step 1: Check Pod Status**
- **Thought**: First verify if pods exist and their current state
- **Command Pattern**: `kubectl get pods -n <namespace> -l app=<app-name>`
- **What to look for**: STATUS column - should be "Running", not "CrashLoopBackOff", "ErrImagePull", "CreateContainerConfigError"
- **Example**: `kubectl get pods -n default -l app=customer-service`

**Step 2: If STATUS is Not "Running", Get Details**
- **Thought**: Pod events show recent failures (image pull errors, resource limits exceeded)
- **Command Pattern**: `kubectl describe pod <pod-name> -n <namespace>`
- **What to look for**: 
  - "Events:" section at bottom (Warning messages)
  - "State:" under Containers (Waiting/Terminated reasons)
  - "Last State:" (why previous container died)
- **Example**: `kubectl describe pod customer-service-xyz123 -n default`

**Step 3: If Pod is Running but Not Ready (0/1 READY)**
- **Thought**: Readiness probe failing - check logs for application errors
- **Command Pattern**: `kubectl logs <pod-name> -n <namespace> --tail=50`
- **What to look for**:
  - Database connection errors (psycopg2.OperationalError)
  - Port binding failures (address already in use)
  - Missing environment variables
- **Example**: `kubectl logs customer-service-xyz123 -n default --tail=50`

**Step 4: Check Deployment Configuration**
- **Thought**: Verify image tag, environment variables, resource limits
- **File Location**: `kubernetes/deployments/customer-service-deployment.yaml`
- **What to check**:
  - Line ~21: `image:` field - is tag correct? (e.g., `fintegrate-customer-service:v1.0`)
  - Line ~30-90: `env:` section - are ConfigMap/Secret references correct?
  - Line ~91-98: `resources:` - are requests/limits reasonable? (not exceeding node capacity)
- **If changed**: Reapply with `kubectl apply -f <file> -n <namespace>`

**Step 5: Check Service is Routing to Pods**
- **Thought**: Service selector must match pod labels
- **Command Pattern**: `kubectl get endpoints <service-name> -n <namespace>`
- **What to look for**: ENDPOINTS column should have IP addresses (e.g., `10.244.0.5:8000`), not `<none>`
- **Example**: `kubectl get endpoints customer-service -n default`
- **If empty**: Check Service selector matches Deployment labels
  - Service file: `kubernetes/services/customer-service-service.yaml` → `selector:` section
  - Deployment file: `kubernetes/deployments/customer-service-deployment.yaml` → `metadata.labels:`

**Step 6: Verify Port-Forward if Using Minikube**
- **Thought**: Minikube requires port-forward for localhost access
- **Check**: `Get-Job` (PowerShell) - should show port-forward jobs in "Running" state
- **If missing**: Run `.\start-portforwards.ps1` from `kubernetes/` directory
- **Alternative**: Test directly: `kubectl port-forward svc/traefik 8001:8000 -n default`

### Quick Decision Tree
```
Pod STATUS = "Running" + READY = "1/1"?
├─ YES → Check port-forward script running
│         └─ If script running → Check Traefik routing (kubectl logs -n default -l app=traefik)
└─ NO → Check STATUS:
         ├─ "ErrImagePull" → Fix image tag in deployment.yaml, reapply
         ├─ "CrashLoopBackOff" → Check logs for application error
         ├─ "CreateContainerConfigError" → Check ConfigMap/Secret exist in namespace
         └─ "Pending" → Check resource quota (kubectl describe quota -n <namespace>)
```

---

## Situation 2: Manager Asks "Are Our Database Credentials Secure?"

### Context
Your security-conscious manager read about Kubernetes Secret vulnerabilities and asks you to verify that database passwords are properly secured. They want to know: (1) How secrets are stored, (2) Who can access them, (3) If they're encrypted, (4) Recommendations for improvement.

### Assumptions
1. Secrets are stored as Kubernetes Secrets (not plaintext in YAML)
2. RBAC might not be properly configured (default ServiceAccount might have too many permissions)
3. Secrets are base64-encoded, not encrypted at rest
4. No external secret management (Vault, Azure Key Vault) configured

### Step-by-Step Investigation Hints

**Step 1: Locate Secret Resources**
- **Thought**: Find all secrets in the cluster, identify database-related ones
- **Command Pattern**: `kubectl get secrets -n <namespace>`
- **What to look for**: Secret names like `postgres-secret`, `rabbitmq-secret`
- **Example**: `kubectl get secrets -n default`

**Step 2: Inspect Secret Contents (Demonstrate Vulnerability)**
- **Thought**: Show manager that base64 is encoding, not encryption
- **Command Pattern**: `kubectl get secret <secret-name> -n <namespace> -o jsonpath='{.data.<key>}'`
- **Example**: `kubectl get secret postgres-secret -n default -o jsonpath='{.data.POSTGRES_PASSWORD}'`
- **Result**: Gets base64 string (e.g., `ZmludGVncmF0ZV9wYXNz`)
- **Decode**: `[System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("<base64-string>"))`
- **Show manager**: Anyone with `kubectl get secret` access can decode passwords

**Step 3: Check Who Can Access Secrets (RBAC Audit)**
- **Thought**: Review RoleBindings to see which ServiceAccounts have Secret read permissions
- **Command Pattern**: `kubectl get rolebindings -n <namespace>`
- **Example**: `kubectl get rolebindings -n default -o yaml`
- **What to look for**:
  - `roleRef.name:` - which Role is bound?
  - `subjects:` - which ServiceAccounts/Users have this Role?
- **Check Role permissions**: `kubectl describe role <role-name> -n <namespace>`
  - Look for `resources: ["secrets"]` with `verbs: ["get", "list"]`

**Step 4: Check if Secrets Are Encrypted at Rest**
- **Thought**: Kubernetes etcd (data store) doesn't encrypt Secrets by default
- **File to check**: Cluster configuration (not accessible in Minikube easily)
- **Tell manager**: 
  - "Minikube default: Secrets stored in etcd as base64 (not encrypted)"
  - "Production: Need to enable etcd encryption or use external secret store"
- **Reference**: Check if encryption configuration exists
  - Command: `kubectl get pod -n kube-system -l component=etcd -o yaml | grep -i encryption`
  - Minikube result: No encryption config found

**Step 5: Review Secret Definition Files (Source Control Risk)**
- **Thought**: Check if base64 secrets committed to Git (bad practice)
- **File Location**: `kubernetes/secrets/postgres-secret.yaml`
- **What to check**:
  - Line ~7: `data:` section contains base64-encoded values
  - Check Git history: `git log -- kubernetes/secrets/*.yaml`
- **Tell manager**: 
  - "Secrets are in Git repo (risk if repo leaked)"
  - "Base64 values easily decoded"
  - "Recommendation: Use .gitignore for secrets or external secret manager"

**Step 6: Provide Improvement Recommendations**
- **Short-term (current Minikube setup)**:
  - Implement RBAC: Restrict Secret access to only necessary ServiceAccounts
  - Use Sealed Secrets (Bitnami) - encrypt secrets before committing to Git
  - Document who can run `kubectl get secret` commands
- **Long-term (Azure Cloud migration)**:
  - Use Azure Key Vault (secrets never stored in Kubernetes)
  - Enable Azure AD authentication (no static passwords)
  - Implement secret rotation policy (change passwords every 90 days)
  - Enable audit logging (track who accessed secrets)

### Quick Audit Checklist for Manager
```
☐ Secrets base64-encoded? YES (check kubectl get secret -o yaml)
☐ Secrets encrypted at rest? NO (Minikube default, etcd not encrypted)
☐ Secrets in Git repository? YES (kubernetes/secrets/*.yaml)
☐ RBAC restricts access? PARTIAL (check rolebindings, may need tightening)
☐ External secret manager? NO (planned for Azure Key Vault in Phase 4)

RISK LEVEL: MEDIUM
- Base64 easily decoded (not secure against insider threats)
- Secrets in Git (risk if repo compromised)
- Acceptable for learning/dev, NOT for production
```

---

## Situation 3: Deployment Stuck - Quota Exceeded in Dev Namespace

### Context
DevOps team tries to deploy a new monitoring service (Prometheus) to the `dev` namespace. The deployment command succeeds, but pods never start. Running `kubectl get pods -n dev` shows no new pods. The team needs your help understanding why and how to fix it.

### Assumptions
1. ResourceQuota is enabled in dev namespace (CPU/memory limits)
2. Existing customer-service pods already consuming quota
3. New deployment requests resources exceeding available quota
4. Team doesn't understand quota enforcement model

### Step-by-Step Investigation Hints

**Step 1: Check Current Quota Usage**
- **Thought**: See how much of namespace quota is already used
- **Command Pattern**: `kubectl describe quota <quota-name> -n <namespace>`
- **Example**: `kubectl describe quota dev-quota -n dev`
- **What to look for**:
  ```
  Resource         Used   Hard
  --------         ----   ----
  requests.cpu     500m   2      ← 500m of 2 CPU used
  limits.cpu       2      4
  pods             2      10
  ```
- **Calculate available**: Hard - Used = Available (e.g., 2 - 0.5 = 1.5 CPU available)

**Step 2: Check New Deployment Resource Requests**
- **Thought**: New deployment might request more than available quota
- **File Location**: Team's deployment YAML (ask them for file or check recent Git commits)
- **What to check**: `resources.requests` and `resources.limits` sections
- **Example**:
  ```yaml
  resources:
    requests:
      cpu: "2"        # ← Requesting 2 CPU
      memory: "4Gi"
  ```
- **Math**: If dev quota has 1.5 CPU available, but Prometheus requests 2 CPU → **BLOCKED**

**Step 3: Check Deployment Events for Quota Errors**
- **Thought**: Kubernetes logs quota violations as events
- **Command Pattern**: `kubectl describe deployment <deployment-name> -n <namespace>`
- **What to look for**: "Events:" section, messages like:
  - "Error creating: pods \"prometheus-xxx\" is forbidden: exceeded quota"
  - "forbidden: maximum cpu usage per Pod is X, but limit is Y"
- **Example**: `kubectl describe deployment prometheus -n dev`

**Step 4: Check LimitRange Constraints**
- **Thought**: LimitRange might block individual pod if it requests too much
- **Command Pattern**: `kubectl describe limitrange <limitrange-name> -n <namespace>`
- **Example**: `kubectl describe limitrange dev-limits -n dev`
- **What to look for**:
  ```
  Type        Resource   Min   Max   Default   DefaultRequest
  ----        --------   ---   ---   -------   --------------
  Container   cpu        50m   1     200m      100m
  ```
- **Check**: Max CPU = 1 (if Prometheus requests 2 CPU → blocked even if quota available)

**Step 5: Explain Quota vs LimitRange to Team**
- **ResourceQuota**: Namespace-level (total across all pods)
  - Example: Dev namespace limited to 2 CPU total
  - If 2 customer-service pods use 1 CPU, only 1 CPU available for new pods
- **LimitRange**: Pod-level (individual pod maximum)
  - Example: Max 1 CPU per pod in dev
  - Even if quota available, single pod can't exceed 1 CPU
- **Both enforced**: New pod must satisfy LimitRange AND quota

**Step 6: Provide Solutions**
- **Option 1: Scale Down Existing Pods**
  ```powershell
  kubectl scale deployment customer-service --replicas=1 -n dev
  # Frees up 0.25 CPU (if each pod uses 0.25 CPU)
  ```
- **Option 2: Reduce New Deployment Requests**
  - Edit Prometheus deployment YAML: Change `requests.cpu: "2"` → `requests.cpu: "500m"`
  - Reapply: `kubectl apply -f prometheus-deployment.yaml -n dev`
- **Option 3: Increase Namespace Quota** (if justified)
  - File: `kubernetes/quotas/dev-quota.yaml`
  - Line ~9: Change `requests.cpu: "2"` → `requests.cpu: "4"`
  - Apply: `kubectl apply -f kubernetes/quotas/dev-quota.yaml`
- **Option 4: Deploy to Test Namespace** (has higher quota)
  ```powershell
  kubectl apply -f prometheus-deployment.yaml -n test
  # Test namespace: 4 CPU quota vs dev: 2 CPU
  ```

### Decision Matrix for Team
```
New deployment requests 2 CPU, dev quota has 1.5 CPU available:
├─ LimitRange max = 1 CPU? 
│  └─ YES → BLOCKED by LimitRange (must reduce to ≤1 CPU per pod)
└─ LimitRange max ≥ 2 CPU?
   ├─ Available quota ≥ 2 CPU? → ALLOWED
   └─ Available quota < 2 CPU? → BLOCKED by quota (scale down others or increase quota)
```

---

## Situation 4: Check How Much Resources Are Allocated to Customer-Service

### Context
Finance team is planning cloud migration budget. They ask you: "How much CPU and memory does customer-service currently use, and what are we allowing it to use?" They need three numbers: (1) Current actual usage, (2) Requested resources (guaranteed), (3) Limit resources (maximum allowed).

### Assumptions
1. customer-service deployment has resource requests and limits defined
2. Metrics-server is enabled (for actual usage data)
3. Multiple replicas might be running (need total across all pods)
4. Finance team doesn't understand Kubernetes terminology (requests vs limits)

### Step-by-Step Investigation Hints

**Step 1: Find Customer-Service Configuration**
- **Thought**: Deployment YAML has resource specifications
- **File Location**: `kubernetes/deployments/customer-service-deployment.yaml`
- **What to check**: Lines ~91-98 (resources section)
- **Example**:
  ```yaml
  resources:
    requests:
      cpu: "250m"       # ← Guaranteed: 0.25 CPU cores
      memory: "256Mi"   # ← Guaranteed: 256 megabytes
    limits:
      cpu: "1000m"      # ← Maximum: 1 CPU core
      memory: "512Mi"   # ← Maximum: 512 megabytes
  ```

**Step 2: Count Current Replicas**
- **Thought**: Total resources = per-pod resources × replica count
- **Command Pattern**: `kubectl get deployment <deployment-name> -n <namespace>`
- **Example**: `kubectl get deployment customer-service -n default`
- **What to look for**: "READY" column (e.g., "2/2" means 2 replicas)
- **Math**: 
  - Total requests: 250m CPU × 2 = 500m (0.5 CPU cores)
  - Total limits: 1000m CPU × 2 = 2000m (2 CPU cores)

**Step 3: Check Actual Current Usage (Real-Time)**
- **Thought**: metrics-server provides live CPU/memory usage
- **Command Pattern**: `kubectl top pods -n <namespace> -l app=<app-name>`
- **Example**: `kubectl top pods -n default -l app=customer-service`
- **What to look for**:
  ```
  NAME                          CPU(cores)   MEMORY(bytes)
  customer-service-abc123       45m          120Mi
  customer-service-xyz789       50m          125Mi
  ```
- **Calculate total**: 45m + 50m = 95m CPU (0.095 cores), 120Mi + 125Mi = 245Mi RAM

**Step 4: Check if HPA is Scaling**
- **Thought**: HPA might increase replicas under load (affects total resources)
- **Command Pattern**: `kubectl get hpa -n <namespace>`
- **Example**: `kubectl get hpa customer-service-hpa -n default`
- **What to look for**:
  ```
  NAME                   TARGETS       MINPODS   MAXPODS   REPLICAS
  customer-service-hpa   cpu: 45%/50%  2         5         2
  ```
- **Explain to Finance**: "Currently 2 replicas, but can scale to 5 under heavy load"
  - Maximum possible resources: 250m × 5 = 1.25 CPU requests, 1000m × 5 = 5 CPU limits

**Step 5: Present Data in Business Terms**
- **Translate Kubernetes units**:
  - "250m CPU" = "0.25 CPU cores" = "25% of one CPU core"
  - "256Mi RAM" = "256 megabytes" = "0.25 gigabytes"
- **Three-tier explanation**:
  1. **Guaranteed (Requests)**: "Kubernetes reserves 0.5 CPU and 512 Mi RAM for customer-service (2 replicas × 250m/256Mi). This is guaranteed even if cluster is crowded."
  2. **Maximum (Limits)**: "customer-service can burst up to 2 CPU and 1 Gi RAM (2 replicas × 1 CPU/512Mi). Kubernetes kills container if it exceeds this."
  3. **Current Usage**: "Right now using 95m CPU (9.5% of limit) and 245 Mi RAM (24% of limit). Light load."
- **Cloud cost estimate** (Azure example):
  - 2 replicas: $X/month for 0.5 CPU + 512 Mi RAM (requests)
  - If scales to 5: $Y/month for 1.25 CPU + 1.28 Gi RAM (requests)

**Step 6: Create Summary Report for Finance**
```
Customer-Service Resource Allocation Report
==========================================

Current State (Minikube):
- Replicas: 2 running (can scale 2-5 via HPA)
- Actual usage: 95m CPU (0.095 cores), 245 Mi RAM

Per-Pod Allocation:
- Guaranteed (requests): 250m CPU, 256 Mi RAM
- Maximum (limits): 1000m CPU, 512 Mi RAM

Total Current Allocation (2 replicas):
- Guaranteed: 500m CPU (0.5 cores), 512 Mi RAM
- Maximum: 2000m CPU (2 cores), 1024 Mi RAM (1 Gi)

Maximum Possible (5 replicas under load):
- Guaranteed: 1250m CPU (1.25 cores), 1280 Mi RAM (1.28 Gi)
- Maximum: 5000m CPU (5 cores), 2560 Mi RAM (2.5 Gi)

Cloud Migration Estimate (Azure AKS):
- Normal load (2 replicas): ~$50/month
- Peak load (5 replicas): ~$125/month
- Database (Azure SQL): ~$200/month
- Total estimated: $250-325/month
```

### Quick Command Summary
```powershell
# 1. Check configuration
cat kubernetes/deployments/customer-service-deployment.yaml | grep -A 10 "resources:"

# 2. Count replicas
kubectl get deployment customer-service -n default

# 3. Check actual usage
kubectl top pods -n default -l app=customer-service

# 4. Check autoscaling
kubectl get hpa customer-service-hpa -n default
```

---

## Situation 5: Rolling Update Failed - Need to Rollback Immediately

### Context
You deployed customer-service v2.0 with a new feature. After 5 minutes, monitoring alerts show 500 errors spiking. Manager says "Rollback NOW!" You need to revert to the previous version quickly while understanding what went wrong.

### Assumptions
1. Rolling update was triggered (kubectl set image or kubectl apply with new tag)
2. New pods are running but returning errors (not CrashLoopBackOff)
3. Old ReplicaSet still exists (Kubernetes keeps history)
4. Some users are hitting broken v2.0 pods, some still on v1.0 (mid-rollout)

### Step-by-Step Rollback Hints

**Step 1: Confirm Update is Causing Issues**
- **Thought**: Check if new pods are the problem (compare old vs new)
- **Command Pattern**: `kubectl get pods -n <namespace> -l app=<app-name> -o wide`
- **What to look for**: "AGE" column - newer pods (seconds/minutes old) vs older pods (hours old)
- **Example**: 
  ```
  NAME                          AGE
  customer-service-abc123-old   2h     ← Old version (v1.0)
  customer-service-xyz789-new   3m     ← New version (v2.0)
  ```
- **Test**: Check logs of new pod: `kubectl logs customer-service-xyz789-new -n default --tail=50`
  - Look for errors (KeyError, NullPointerException, 500 Internal Server Error)

**Step 2: Check Rollout Status**
- **Thought**: See if rollout is still in progress or completed
- **Command Pattern**: `kubectl rollout status deployment/<deployment-name> -n <namespace>`
- **Example**: `kubectl rollout status deployment/customer-service -n default`
- **Possible results**:
  - "deployment \"customer-service\" successfully rolled out" → Rollout complete (all v2.0)
  - "Waiting for deployment \"customer-service\" rollout to finish: 1 out of 2 new replicas have been updated" → Mid-rollout (mixed v1.0 and v2.0)

**Step 3: Pause Rollout (Stop More Pods Updating)**
- **Thought**: Prevent more users from hitting broken v2.0
- **Command Pattern**: `kubectl rollout pause deployment/<deployment-name> -n <namespace>`
- **Example**: `kubectl rollout pause deployment/customer-service -n default`
- **Effect**: Stops creating new v2.0 pods (existing v1.0 pods keep serving traffic)

**Step 4: Check Rollout History**
- **Thought**: Find the revision number to rollback to
- **Command Pattern**: `kubectl rollout history deployment/<deployment-name> -n <namespace>`
- **Example**: `kubectl rollout history deployment/customer-service -n default`
- **What to look for**:
  ```
  REVISION  CHANGE-CAUSE
  1         <none>              ← Initial deployment (v1.0)
  2         <none>              ← Last working version (v1.0)
  3         <none>              ← Current broken version (v2.0)
  ```
- **Decision**: Rollback to revision 2 (last known good)

**Step 5: Execute Rollback**
- **Thought**: Revert to previous ReplicaSet (Kubernetes keeps old ones)
- **Command Pattern**: `kubectl rollout undo deployment/<deployment-name> -n <namespace>`
- **Example**: `kubectl rollout undo deployment/customer-service -n default`
- **To specific revision**: `kubectl rollout undo deployment/customer-service --to-revision=2 -n default`
- **What happens**: 
  - Kubernetes scales up old ReplicaSet (v1.0)
  - Scales down new ReplicaSet (v2.0)
  - Rolling update in reverse

**Step 6: Monitor Rollback Progress**
- **Thought**: Ensure rollback completes successfully
- **Command Pattern**: `kubectl rollout status deployment/<deployment-name> -n <namespace>`
- **Watch pods**: `kubectl get pods -n default -l app=customer-service --watch`
- **What to look for**: Old ReplicaSet pods (v1.0) becoming Ready (1/1)
- **Verify**: Check logs of rolled-back pod for expected behavior

**Step 7: Resume Rollout (After Rollback Complete)**
- **Thought**: Unpause deployment for future updates
- **Command Pattern**: `kubectl rollout resume deployment/<deployment-name> -n <namespace>`
- **Example**: `kubectl rollout resume deployment/customer-service -n default`

**Step 8: Root Cause Analysis (After Incident)**
- **Check what changed**: 
  - **File**: `kubernetes/deployments/customer-service-deployment.yaml`
  - **Git**: `git diff HEAD~1 HEAD -- kubernetes/deployments/customer-service-deployment.yaml`
  - Look for: New image tag, changed environment variables, modified resource limits
- **Check application code**:
  - **Git**: `git log --oneline -10` (find v2.0 commit)
  - **Review**: Changes in routes.py, crud.py, database.py
- **Test locally**:
  - Build v2.0 image: `docker build -t fintegrate-customer-service:v2.0 .`
  - Run in Docker Compose: `docker-compose up customer-service`
  - Reproduce error in local environment

### Rollback Decision Matrix
```
Is rollout paused? NO
└─ Pause immediately: kubectl rollout pause deployment/customer-service -n default

Do we know what revision to rollback to? UNKNOWN
├─ Check history: kubectl rollout history deployment/customer-service -n default
└─ Find last working revision (usually N-1)

Execute rollback:
└─ kubectl rollout undo deployment/customer-service -n default
   (or with --to-revision=X if specific version)

Monitor rollback:
└─ kubectl rollout status deployment/customer-service -n default

Verify fix:
├─ Check logs: kubectl logs -n default -l app=customer-service --tail=20
└─ Test API: curl http://localhost:8001/customer/data

Resume deployment:
└─ kubectl rollout resume deployment/customer-service -n default
```

### Post-Incident Checklist
```
☐ Rollback completed? (kubectl get pods shows old version)
☐ Errors stopped? (check monitoring dashboard)
☐ Root cause identified? (code review, config changes)
☐ Fix developed and tested locally? (Docker Compose)
☐ Deployment resumed? (kubectl rollout resume)
☐ Incident report written? (what broke, how fixed, prevention)
☐ Rollback procedure documented? (add to runbook)
```

---

## Situation 6: New Team Member Needs Access - RBAC Configuration

### Context
A new junior developer joins your team. They need read-only access to customer-service pods in the `dev` namespace for debugging (view logs, describe pods) but should NOT be able to delete pods or access production (`prod` namespace). You need to set up proper RBAC.

### Assumptions
1. Junior developer has kubectl configured (can run commands)
2. Currently they have no permissions (get "Forbidden" errors)
3. You need to create ServiceAccount, Role, and RoleBinding
4. Read-only means: get, list, watch (no create, update, delete)

### Step-by-Step RBAC Setup Hints

**Step 1: Create ServiceAccount for Developer**
- **Thought**: ServiceAccount is identity for the developer in Kubernetes
- **File**: Create `kubernetes/rbac/developer-serviceaccount.yaml`
- **Content**:
  ```yaml
  apiVersion: v1
  kind: ServiceAccount
  metadata:
    name: junior-dev-sa
    namespace: dev
  ```
- **Apply**: `kubectl apply -f kubernetes/rbac/developer-serviceaccount.yaml`

**Step 2: Create Read-Only Role**
- **Thought**: Define what resources they can access and what actions (verbs) allowed
- **File**: Create `kubernetes/rbac/developer-role.yaml`
- **Content**:
  ```yaml
  apiVersion: rbac.authorization.k8s.io/v1
  kind: Role
  metadata:
    name: pod-reader
    namespace: dev
  rules:
  - apiGroups: [""]
    resources: ["pods", "pods/log"]  # ← pods and logs
    verbs: ["get", "list", "watch"]   # ← read-only verbs
  ```
- **What verbs mean**:
  - `get`: View single resource (kubectl get pod <name>)
  - `list`: View all resources (kubectl get pods)
  - `watch`: Stream updates (kubectl get pods --watch)
  - **Not allowed**: `create`, `update`, `patch`, `delete`
- **Apply**: `kubectl apply -f kubernetes/rbac/developer-role.yaml`

**Step 3: Bind Role to ServiceAccount**
- **Thought**: RoleBinding connects ServiceAccount to Role (grants permissions)
- **File**: Create `kubernetes/rbac/developer-rolebinding.yaml`
- **Content**:
  ```yaml
  apiVersion: rbac.authorization.k8s.io/v1
  kind: RoleBinding
  metadata:
    name: junior-dev-rolebinding
    namespace: dev
  subjects:
  - kind: ServiceAccount
    name: junior-dev-sa
    namespace: dev
  roleRef:
    kind: Role
    name: pod-reader
    apiGroup: rbac.authorization.k8s.io
  ```
- **Apply**: `kubectl apply -f kubernetes/rbac/developer-rolebinding.yaml`

**Step 4: Generate Kubeconfig for Developer**
- **Thought**: Developer needs credentials (token) for ServiceAccount
- **Get token**:
  ```powershell
  # Create token for ServiceAccount
  kubectl create token junior-dev-sa -n dev --duration=8760h
  ```
- **Copy token** (long string starting with `eyJ...`)
- **Create kubeconfig file** (give to developer):
  ```yaml
  apiVersion: v1
  kind: Config
  clusters:
  - cluster:
      server: https://<minikube-ip>:8443
      certificate-authority: /path/to/ca.crt
    name: dev-cluster
  users:
  - name: junior-dev
    user:
      token: <token-from-step-above>
  contexts:
  - context:
      cluster: dev-cluster
      user: junior-dev
      namespace: dev
    name: dev-context
  current-context: dev-context
  ```

**Step 5: Test Permissions (As You, Not Developer)**
- **Thought**: Verify what developer can and cannot do before giving access
- **Simulate**: `kubectl auth can-i get pods -n dev --as=system:serviceaccount:dev:junior-dev-sa`
- **Expected**: "yes"
- **Test delete**: `kubectl auth can-i delete pods -n dev --as=system:serviceaccount:dev:junior-dev-sa`
- **Expected**: "no"
- **Test prod access**: `kubectl auth can-i get pods -n prod --as=system:serviceaccount:dev:junior-dev-sa`
- **Expected**: "no" (Role is namespace-scoped to `dev`)

**Step 6: Instruct Developer How to Use**
- **Give them**:
  - Kubeconfig file (from Step 4)
  - Instructions: `export KUBECONFIG=/path/to/dev-kubeconfig.yaml`
- **What they CAN do**:
  ```powershell
  kubectl get pods -n dev              # List pods
  kubectl describe pod <name> -n dev   # View pod details
  kubectl logs <name> -n dev           # View logs
  kubectl get pods -n dev --watch      # Watch pod updates
  ```
- **What they CANNOT do**:
  ```powershell
  kubectl delete pod <name> -n dev     # ERROR: Forbidden
  kubectl edit pod <name> -n dev       # ERROR: Forbidden
  kubectl get pods -n prod             # ERROR: Forbidden (wrong namespace)
  ```

**Step 7: Verify and Monitor**
- **Check access logs** (if audit logging enabled):
  - Who accessed what resources
  - Look for "Forbidden" errors (developer trying unauthorized actions)
- **Review periodically**:
  - `kubectl get rolebindings -n dev`
  - `kubectl describe rolebinding junior-dev-rolebinding -n dev`
- **Revoke access** (if developer leaves):
  - Delete RoleBinding: `kubectl delete rolebinding junior-dev-rolebinding -n dev`
  - Delete ServiceAccount: `kubectl delete serviceaccount junior-dev-sa -n dev`

### RBAC Permission Matrix (Reference)
| Verb | Description | Example Command | Junior Dev Access? |
|------|-------------|-----------------|-------------------|
| `get` | View single resource | `kubectl get pod <name> -n dev` | ✅ YES |
| `list` | View all resources | `kubectl get pods -n dev` | ✅ YES |
| `watch` | Stream updates | `kubectl get pods -n dev --watch` | ✅ YES |
| `create` | Create new resource | `kubectl create -f deployment.yaml -n dev` | ❌ NO |
| `update` | Update resource | `kubectl edit pod <name> -n dev` | ❌ NO |
| `patch` | Partial update | `kubectl patch pod <name> -n dev` | ❌ NO |
| `delete` | Delete resource | `kubectl delete pod <name> -n dev` | ❌ NO |

### Quick RBAC Verification Commands
```powershell
# Check what ServiceAccount can do
kubectl auth can-i <verb> <resource> -n <namespace> --as=system:serviceaccount:<namespace>:<sa-name>

# Examples:
kubectl auth can-i get pods -n dev --as=system:serviceaccount:dev:junior-dev-sa
kubectl auth can-i delete pods -n dev --as=system:serviceaccount:dev:junior-dev-sa
kubectl auth can-i get secrets -n dev --as=system:serviceaccount:dev:junior-dev-sa

# List all permissions for ServiceAccount
kubectl describe rolebinding junior-dev-rolebinding -n dev
kubectl describe role pod-reader -n dev
```

---

## Situation 7: Database Migration Required - Zero-Downtime Strategy

### Context
Your database team needs to run a migration script (add new columns to `customers` table). The script takes 5-10 minutes. Manager requires zero downtime - customer-service API must stay available during migration. You need to plan and execute the migration safely.

### Assumptions
1. Migration is backward-compatible (new columns have defaults, old code won't break)
2. customer-service currently has 2 replicas behind a Service (load balanced)
3. PostgreSQL StatefulSet has 1 replica (single database)
4. Migration script is SQL file: `database/migrations/YYYYMMDD_HHMM_add_customer_fields.sql`

### Step-by-Step Migration Strategy Hints

**Step 1: Review Migration Script**
- **Thought**: Ensure migration is safe (backward-compatible, idempotent)
- **File**: `database/migrations/20251107_1500_add_customer_fields.sql`
- **What to check**:
  - Does it use `BEGIN; ... COMMIT;` (transaction wrapper)?
  - Does it check `IF NOT EXISTS` (idempotent, can run multiple times)?
  - Are new columns nullable or have defaults? (old app code won't break)
  - Example safe migration:
    ```sql
    BEGIN;
    
    ALTER TABLE customers 
    ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20) DEFAULT NULL;
    
    ALTER TABLE customers 
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP DEFAULT NULL;
    
    COMMIT;
    ```

**Step 2: Backup Database (Safety Net)**
- **Thought**: If migration fails, you can restore
- **Find PostgreSQL pod**: `kubectl get pods -n default -l app=postgres`
- **Take backup**:
  ```powershell
  kubectl exec -n default postgres-0 -- pg_dump -U fintegrate_user fintegrate_db > backup_$(Get-Date -Format "yyyyMMdd_HHmm").sql
  ```
- **Verify backup file**: Check file size > 0 bytes

**Step 3: Test Migration in Dev Environment First**
- **Thought**: Never run untested migration in production
- **Option 1: Use Docker Compose** (fastest)
  ```powershell
  cd docker
  docker-compose up -d postgres
  docker-compose exec postgres psql -U fintegrate_user -d fintegrate_db -f /path/to/migration.sql
  ```
- **Option 2: Use Minikube dev namespace**
  ```powershell
  kubectl exec -n dev postgres-0 -- psql -U fintegrate_user -d fintegrate_db -f /path/to/migration.sql
  ```
- **Verify**: Check columns added without errors

**Step 4: Understand Zero-Downtime Approach**
- **Key insight**: Customer-service pods don't restart during DB migration
- **Why it works**:
  - Service has 2 replicas (if 1 dies, other keeps serving)
  - Migration is backward-compatible (old code doesn't use new columns yet)
  - Load balancer distributes traffic (no single point of failure)
- **What to monitor**: Query latency (migration might slow down queries temporarily)

**Step 5: Execute Migration (Production)**
- **Get PostgreSQL pod name**: `kubectl get pods -n default -l app=postgres`
- **Copy migration file to pod**:
  ```powershell
  kubectl cp database/migrations/20251107_1500_add_customer_fields.sql default/postgres-0:/tmp/migration.sql
  ```
- **Run migration**:
  ```powershell
  kubectl exec -n default postgres-0 -- psql -U fintegrate_user -d fintegrate_db -f /tmp/migration.sql
  ```
- **Watch output**: Should see `ALTER TABLE` success messages

**Step 6: Verify Migration During Execution**
- **Monitor API health** (in separate terminal):
  ```powershell
  while ($true) { 
    curl http://localhost:8001/events/health -UseBasicParsing | Select-Object StatusCode, @{Name="Time";Expression={(Get-Date).ToString("HH:mm:ss")}}
    Start-Sleep -Seconds 2
  }
  ```
  - **Expected**: StatusCode 200 throughout migration (no downtime)
- **Monitor database connections**:
  ```powershell
  kubectl exec -n default postgres-0 -- psql -U fintegrate_user -d fintegrate_db -c "SELECT count(*) FROM pg_stat_activity WHERE datname='fintegrate_db';"
  ```
  - **Expected**: 2-4 connections (customer-service replicas)

**Step 7: Verify Migration Completed**
- **Check columns added**:
  ```powershell
  kubectl exec -n default postgres-0 -- psql -U fintegrate_user -d fintegrate_db -c "\d customers"
  ```
  - **Look for**: New columns `phone_number`, `verified_at` in table schema
- **Test inserting data**:
  ```powershell
  kubectl exec -n default postgres-0 -- psql -U fintegrate_user -d fintegrate_db -c "INSERT INTO customers (customer_id, name, status, phone_number) VALUES (gen_random_uuid(), 'Test User', 'active', '+1234567890');"
  ```
- **Verify via API**:
  ```powershell
  curl http://localhost:8001/customer/data -UseBasicParsing
  ```

**Step 8: Deploy Application Code Update (Uses New Columns)**
- **Thought**: Now that DB ready, deploy app code that uses new columns
- **Update code**: Modify `schemas.py` to include `phone_number` field
- **Build new image**: `docker build -t fintegrate-customer-service:v2.1 .`
- **Load to Minikube**: `minikube image load fintegrate-customer-service:v2.1`
- **Update deployment**:
  ```powershell
  kubectl set image deployment/customer-service customer-service=fintegrate-customer-service:v2.1 -n default
  ```
- **Monitor rollout**: `kubectl rollout status deployment/customer-service -n default`
  - Rolling update ensures zero downtime (old pods serve traffic while new pods start)

### Migration Safety Checklist
```
Pre-Migration:
☐ Migration script is backward-compatible (new columns nullable or have defaults)
☐ Migration script uses BEGIN/COMMIT transaction (atomic)
☐ Migration script is idempotent (can run multiple times safely)
☐ Database backup taken (pg_dump completed successfully)
☐ Migration tested in dev environment (no errors)
☐ Monitoring dashboard open (track API health during migration)

During Migration:
☐ Customer-service replicas still responding (health check returns 200)
☐ Database connections stable (pg_stat_activity shows active connections)
☐ No ERROR messages in migration output

Post-Migration:
☐ New columns visible in table schema (\d customers)
☐ Test data inserted successfully (INSERT query succeeded)
☐ API still responding (GET /customer/data returns 200)
☐ Application code updated and deployed (v2.1 rollout successful)
☐ Migration logged in migration_history table
```

### Rollback Plan (If Migration Fails)
```
1. Stop migration (Ctrl+C if still running)
2. Rollback transaction (if within BEGIN/COMMIT block, automatic)
3. Drop new columns (if partially added):
   ALTER TABLE customers DROP COLUMN IF EXISTS phone_number;
   ALTER TABLE customers DROP COLUMN IF EXISTS verified_at;
4. Restore from backup (if data corrupted):
   kubectl exec -n default postgres-0 -- psql -U fintegrate_user -d fintegrate_db < backup_YYYYMMDD_HHMM.sql
5. Verify customer-service still working (API health check)
6. Incident report: What failed, root cause, prevention
```

---

## General Troubleshooting Framework (Applies to All Situations)

### The 5-Layer Kubernetes Debugging Model

**Layer 1: Pod Status** (Is it even running?)
```powershell
kubectl get pods -n <namespace> -l app=<app-name>
# Look for: STATUS (Running vs CrashLoopBackOff), READY (1/1 vs 0/1)
```

**Layer 2: Pod Events** (Why did it fail?)
```powershell
kubectl describe pod <pod-name> -n <namespace>
# Look for: Events section (Warning messages), Last State (exit code)
```

**Layer 3: Application Logs** (What did the app say?)
```powershell
kubectl logs <pod-name> -n <namespace> --tail=50
# Look for: Stack traces, connection errors, missing env vars
```

**Layer 4: Configuration** (Is it configured correctly?)
```powershell
# Check deployment YAML
cat kubernetes/deployments/<app>-deployment.yaml
# Look for: Image tag, env vars, resource limits, volume mounts
```

**Layer 5: Network/Service** (Can traffic reach it?)
```powershell
kubectl get svc -n <namespace>
kubectl get endpoints <service-name> -n <namespace>
# Look for: Service selector matches pod labels, endpoints not empty
```

### When to Use Which Tool

| Problem | Tool | Command |
|---------|------|---------|
| "Pod not starting" | kubectl get/describe | `kubectl describe pod <name>` |
| "App crashing" | kubectl logs | `kubectl logs <name> --tail=100` |
| "Quota exceeded" | kubectl describe quota | `kubectl describe quota <name> -n <ns>` |
| "Permission denied" | kubectl auth can-i | `kubectl auth can-i <verb> <resource> --as=<user>` |
| "High CPU usage" | kubectl top | `kubectl top pods -n <ns>` |
| "Update failed" | kubectl rollout | `kubectl rollout status deployment/<name>` |
| "Service not routing" | kubectl get endpoints | `kubectl get endpoints <service-name>` |

---

## Summary: Practice Philosophy

**Goal**: Develop intuition for:
1. **Where to look** (YAML files vs runtime vs logs)
2. **What to check** (status codes, events, quotas)
3. **How to fix** (edit config, scale, rollback)

**Not memorizing**: Exact command syntax (use `--help` when needed)

**Key mindset**: "Kubernetes is declarative - describe desired state (YAML), then debug current state (kubectl) until they match."
