# Admin Agent Kubernetes Deployment

This directory contains Kubernetes manifests for deploying the Admin Agent to AKS.

## Prerequisites

1. An AKS cluster with:
   - Workload Identity enabled
   - A managed identity with access to Azure AI Foundry

2. Azure AI Foundry project configured with:
   - GPT-4o or similar model deployed
   - Appropriate RBAC for the managed identity

3. Backend services deployed:
   - `product-service` on port 3002
   - `makeline-service` on port 3001

## Configuration

### 1. Update Service Account

Edit `admin-agent-serviceaccount.yaml` and set your Azure AD client ID:

```yaml
azure.workload.identity/client-id: "your-client-id-here"
```

### 2. Update ConfigMap

Edit `admin-agent-configmap.yaml` with your Azure AI Foundry endpoint:

```yaml
AZURE_AI_PROJECT_ENDPOINT: "https://your-project.services.ai.azure.com/api/projects/your-project"
```

### 3. Update Secrets

Edit `admin-agent-secrets.yaml` with your Application Insights connection string:

```yaml
APPLICATIONINSIGHTS_CONNECTION_STRING: "InstrumentationKey=..."
```

Or create the secret manually:

```bash
kubectl create secret generic admin-agent-secrets \
  --namespace pets \
  --from-literal=APPLICATIONINSIGHTS_CONNECTION_STRING="your-connection-string"
```

### 4. Update Image Tag

Edit `kustomization.yaml` to set the correct image tag:

```yaml
images:
  - name: retaillocationregistry.azurecr.io/aks-store-demo/admin-agent
    newTag: "1.0.0"
```

## Deployment

Deploy using Kustomize:

```bash
# Preview the deployment
kubectl apply -k . --dry-run=client -o yaml

# Deploy to cluster
kubectl apply -k .

# Watch deployment status
kubectl -n pets rollout status deployment/admin-agent
```

## Verify Deployment

```bash
# Check pods are running
kubectl -n pets get pods -l app=admin-agent

# Check service is created
kubectl -n pets get svc admin-agent

# Get external IP (for LoadBalancer)
kubectl -n pets get svc admin-agent -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Check logs
kubectl -n pets logs -l app=admin-agent --tail=100 -f
```

## Accessing the Admin Agent

Once deployed, access the Admin Agent at:

- **LoadBalancer**: `http://<EXTERNAL-IP>/`
- **Ingress** (if configured): `http://admin.petstore.example.com/`

## Troubleshooting

### Agent not initializing

Check if the managed identity has access to Azure AI Foundry:

```bash
# Check workload identity is configured
kubectl -n pets get sa admin-agent-sa -o yaml | grep azure.workload.identity

# Check pod events
kubectl -n pets describe pod -l app=admin-agent
```

### Connection to backend services failing

Verify backend services are running:

```bash
kubectl -n pets get svc product-service makeline-service
```

### WebSocket/Session issues

Ensure session affinity is enabled on the service:

```bash
kubectl -n pets get svc admin-agent -o yaml | grep sessionAffinity
```

## Files

| File                              | Description                                |
| --------------------------------- | ------------------------------------------ |
| `admin-agent-serviceaccount.yaml` | ServiceAccount with Workload Identity      |
| `admin-agent-configmap.yaml`      | Configuration (endpoints, settings)        |
| `admin-agent-secrets.yaml`        | Secrets (App Insights connection)          |
| `admin-agent-deployment.yaml`     | Deployment with K8s semantics env vars     |
| `admin-agent-service.yaml`        | LoadBalancer service with session affinity |
| `admin-agent-hpa.yaml`            | Horizontal Pod Autoscaler                  |
| `admin-agent-pdb.yaml`            | Pod Disruption Budget                      |
| `admin-agent-networkpolicy.yaml`  | Network Policy for security                |
| `admin-agent-ingress.yaml`        | Ingress (optional)                         |
| `kustomization.yaml`              | Kustomize configuration                    |
