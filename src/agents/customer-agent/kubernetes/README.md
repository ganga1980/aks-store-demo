# Customer Agent Kubernetes Manifests

This directory contains Kubernetes manifests for deploying the Customer Agent to AKS.

## Files

- `customer-agent-deployment.yaml` - Deployment configuration
- `customer-agent-service.yaml` - LoadBalancer service for external access
- `customer-agent-configmap.yaml` - Configuration settings
- `customer-agent-serviceaccount.yaml` - ServiceAccount with Workload Identity

## Deployment

```bash
# Create namespace (if not exists)
kubectl create namespace pets

# Apply all manifests
cd ~/aks-store-demo/src/agents/customer-agent
kubectl kustomize kubernetes/
kubectl apply -k kubernetes/ -n pets
```

## Prerequisites

1. **Azure AI Foundry Project** - Create a project in Azure AI Foundry
2. **Workload Identity** - Configure AKS workload identity federation
3. **Application Insights** - Set up Application Insights for telemetry
