# Customer Agent for AKS Store Demo

A customer-facing AI agent for the AKS Pet Store Demo, built using **Microsoft Agent Framework**, **Chainlit** for conversational UI, and **OpenTelemetry** with Azure Monitor Application Insights for observability.

## 🎯 Features

- **Conversational AI Interface** - Chat-based UI powered by Chainlit
- **Microsoft Agent Framework** - Uses `agent-framework` package with `AzureAIProjectAgentProvider` for intelligent responses
- **Workload Identity Authentication** - Secure, secret-free authentication on AKS
- **OpenTelemetry Observability** - Full tracing with Gen AI semantic conventions
- **Function Tools** - Direct integration with store backend services using Annotated types

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Customer Agent                                   │
│                                                                          │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────────┐  │
│  │   Chainlit   │───▶│  Customer Agent  │───▶│  Microsoft Agent     │  │
│  │   Web UI     │    │   (Python)       │    │  Framework           │  │
│  └──────────────┘    └────────┬─────────┘    │  (Azure AI Foundry)  │  │
│                               │              └──────────────────────┘  │
│                    ┌──────────┴──────────┐                              │
│                    │    Function Tools    │                              │
│                    │  (Annotated types)  │                              │
│                    └──────────┬──────────┘                              │
│                               │                                          │
└───────────────────────────────│──────────────────────────────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                      │
         ▼                      ▼                      ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  order-service  │   │ product-service │   │makeline-service │
│   (Node.js)     │   │     (Rust)      │   │    (Golang)     │
└─────────────────┘   └─────────────────┘   └─────────────────┘
```

## 📋 Prerequisites

### Azure Resources

1. **Azure AI Foundry Project** with a deployed model (e.g., `gpt-4o-mini`)
2. **Azure Kubernetes Service (AKS)** cluster with:
   - OIDC issuer enabled
   - Workload Identity enabled
3. **Azure Application Insights** for telemetry
4. **Managed Identity** with federated credentials for Workload Identity

### Required Permissions

The managed identity needs:

- `Cognitive Services User` role on the Azure AI Foundry project
- Access to deployed model deployments

## 🚀 Quick Start

### Local Development

1. **Clone and navigate to the agent directory:**

   ```bash
   cd src/agents/customer-agent
   ```

2. **Create a virtual environment:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # or .venv\Scripts\activate on Windows
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**

   ```bash
   cp .env.example .env
   # Edit .env with your Azure AI Foundry endpoint
   ```

5. **Login to Azure (for local auth):**

   ```bash
   az login
   ```

6. **Start the backend services (from project root):**

   ```bash
   docker compose up -d mongodb rabbitmq order-service product-service makeline-service
   ```

7. **Run the agent:**

   ```bash
   chainlit run app.py --host 0.0.0.0 --port 8000
   ```

8. **Open the chat interface:**
   Navigate to http://localhost:8000

### Docker Development

```bash
# Build the image
cd ~/aks-store-demo

docker build -t customer-agent:latest -f  src/agents/customer-agent/Dockerfile src/

# Run with environment variables
docker run -p 8000:8000 \
  -e AZURE_AI_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com" \
  -e USE_WORKLOAD_IDENTITY_AUTH=false \
  customer-agent:dev
```

## ☸️ Kubernetes Deployment

### Step 1: Configure Workload Identity

```bash
export AKS_CLUSTER="<aks cluster>"
export AKS_CLUSTER_RG="<aks cluster rg>"

# Get your AKS OIDC issuer URL
OIDC_ISSUER=$(az aks show -n $AKS_CLUSTER$ -g $AKS_CLUSTER_RG$ --query "oidcIssuerProfile.issuerUrl" -o tsv)

# Create a managed identity (if not exists)
az identity create -n customer-agent-identity -g $AKS_CLUSTER_RG$

# Get the client ID
CLIENT_ID=$(az identity show -n customer-agent-identity -g $AKS_CLUSTER_RG --query clientId -o tsv)

# Create federated credential
az identity federated-credential create \
  --name customer-agent-federated-credential \
  --identity-name customer-agent-identity \
  --resource-group $AKS_CLUSTER_RG \
  --issuer $OIDC_ISSUER \
  --subject system:serviceaccount:pets:customer-agent-sa \
  --audience api://AzureADTokenExchange
```

### Step 2: Grant Permissions

```bash
# Get Azure AI Foundry project resource ID
export AI_PROJECT_NAME="ai-project-name"
export AI_PROJECT_RG="ai-project-rg"

AI_PROJECT_ID=$(az resource show -n $AI_PROJECT_NAME -g $AI_PROJECT_RG --resource-type "Microsoft.CognitiveServices/accounts" --query id -o tsv)

# Assign CAzure AI User role
az role assignment create \
  --assignee $CLIENT_ID \
  --role "Azure AI User" \
  --scope $AI_PROJECT_ID
```

### Step 3: Update Kubernetes Manifests

Edit `kubernetes/customer-agent-configmap.yaml`:

```yaml
AZURE_AI_PROJECT_ENDPOINT: "https://<your-project>.services.ai.azure.com"
```

Edit `kubernetes/customer-agent-serviceaccount.yaml`:

```yaml
azure.workload.identity/client-id: "<your-client-id>"
```

Edit `kubernetes/customer-agent-secrets.yaml`:

```yaml
APPLICATIONINSIGHTS_CONNECTION_STRING: "<your-connection-string>"
```

### Step 4: Deploy

```bash
# Create namespace (if not exists)
kubectl create namespace pets

# Apply manifests
kubectl apply -f kubernetes/ -n pets

# Check deployment status
kubectl get pods -n pets -l app=customer-agent

# Get the external IP
kubectl get svc customer-agent -n pets
```

## 🔧 Configuration

### Environment Variables

| Variable                                             | Description                       | Default                        |
| ---------------------------------------------------- | --------------------------------- | ------------------------------ |
| `AZURE_AI_PROJECT_ENDPOINT`                          | Azure AI Foundry project endpoint | Required                       |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME`                     | Model deployment name             | `gpt-4o-mini`                  |
| `USE_WORKLOAD_IDENTITY_AUTH`                         | Use Workload Identity auth        | `true`                         |
| `APPLICATIONINSIGHTS_CONNECTION_STRING`              | App Insights connection string    | Optional                       |
| `ORDER_SERVICE_URL`                                  | Order service endpoint            | `http://order-service:3000`    |
| `PRODUCT_SERVICE_URL`                                | Product service endpoint          | `http://product-service:3002`  |
| `MAKELINE_SERVICE_URL`                               | Makeline service endpoint         | `http://makeline-service:3001` |
| `OTEL_SERVICE_NAME`                                  | OpenTelemetry service name        | `customer-agent`               |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | Capture AI content in traces      | `true`                         |

## 🛠️ Agent Capabilities

The agent has the following function tools:

| Tool                  | Description                         |
| --------------------- | ----------------------------------- |
| `get_products`        | Get all products from the catalog   |
| `get_product_details` | Get details of a specific product   |
| `search_products`     | Search products by name/description |
| `place_order`         | Place a new order                   |
| `get_order_status`    | Check order status                  |

## 📊 Observability

### OpenTelemetry Gen AI Semantic Conventions

The agent implements the [OpenTelemetry Gen AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) for comprehensive observability of AI operations.

#### Spans

The following span types are emitted following Gen AI semantic conventions:

| Span Name Format            | Operation      | Span Kind | Description                      |
| --------------------------- | -------------- | --------- | -------------------------------- |
| `create_agent {agent_name}` | `create_agent` | CLIENT    | When the AI agent is created     |
| `invoke_agent {agent_name}` | `invoke_agent` | CLIENT    | For each user message processed  |
| `execute_tool {tool_name}`  | `execute_tool` | INTERNAL  | For each function tool execution |

#### Span Attributes

All spans include standard Gen AI attributes:

| Attribute                    | Description                                               |
| ---------------------------- | --------------------------------------------------------- |
| `gen_ai.operation.name`      | Operation type (create_agent, invoke_agent, execute_tool) |
| `gen_ai.system`              | Always `azure.ai.inference`                               |
| `gen_ai.request.model`       | Model deployment name                                     |
| `gen_ai.agent.id`            | Unique Agent ID from M365 Agents SDK (UUID format)        |
| `gen_ai.agent.name`          | Agent display name                                        |
| `gen_ai.agent.description`   | Agent instructions/description                            |
| `gen_ai.conversation.id`     | Thread ID for conversation tracking                       |
| `gen_ai.usage.input_tokens`  | Input token count (when available)                        |
| `gen_ai.usage.output_tokens` | Output token count (when available)                       |
| `gen_ai.tool.name`           | Function tool name                                        |
| `gen_ai.tool.description`    | Function tool description                                 |

#### Microsoft 365 Agents SDK Attributes

When integrated with Microsoft 365 Agents SDK, additional attributes are included:

| Attribute              | Description                                       |
| ---------------------- | ------------------------------------------------- |
| `m365.agent.id`        | Unique agent identifier (same as gen_ai.agent.id) |
| `m365.agent.name`      | Agent display name                                |
| `m365.agent.type`      | Agent type (e.g., 'customer', 'admin')            |
| `m365.channel.id`      | Communication channel (e.g., 'webchat', 'teams')  |
| `m365.conversation.id` | Conversation/thread ID                            |
| `m365.activity.id`     | Activity ID within the conversation               |
| `m365.tenant.id`       | Azure AD tenant ID (if configured)                |
| `m365.app.id`          | Azure AD application ID (if configured)           |

#### Metrics

The following metrics are recorded:

| Metric Name                        | Type      | Unit      | Description                   |
| ---------------------------------- | --------- | --------- | ----------------------------- |
| `gen_ai.client.token.usage`        | Histogram | `{token}` | Token usage per operation     |
| `gen_ai.client.operation.duration` | Histogram | `s`       | Operation duration in seconds |

Metrics include attributes: `gen_ai.operation.name`, `gen_ai.system`, `gen_ai.request.model`, `gen_ai.token.type`

#### Content Recording (Opt-In)

To record input/output message content in spans (useful for debugging), set:

```bash
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

When enabled, spans include:

- `gen_ai.content.prompt` - User input messages
- `gen_ai.content.completion` - Agent output messages

> ⚠️ **Privacy Note**: Disable content recording in production environments handling sensitive data.

### Azure Monitor Integration

When `APPLICATIONINSIGHTS_CONNECTION_STRING` is set:

- Traces appear in Application Insights Transaction Search
- Metrics appear in Application Insights Metrics Explorer
- Live Metrics provides real-time monitoring
- Application Map shows service dependencies

#### Viewing Gen AI Telemetry in Azure Portal

1. **Transaction Search**: Filter by `gen_ai.operation.name` to see agent operations
2. **Metrics Explorer**: Create charts for `gen_ai.client.token.usage` and `gen_ai.client.operation.duration`
3. **Kusto Queries**:
   ```kusto
   traces
   | where customDimensions["gen_ai.operation.name"] == "invoke_agent"
   | project timestamp, message, customDimensions["gen_ai.agent.name"],
             customDimensions["gen_ai.usage.output_tokens"]
   ```

### Local Development Tracing

Without App Insights, traces and metrics are printed to console:

```bash
# Enable verbose tracing
export OTEL_LOG_LEVEL=debug
chainlit run app.py
```

## 🧪 Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=html
```

## 📁 Project Structure

```
src/agents/customer-agent/
├── agent/                    # Agent implementation
│   ├── __init__.py
│   ├── customer_agent.py     # Main agent class
│   └── tools.py              # Function tools
├── config/                   # Configuration
│   ├── __init__.py
│   └── settings.py           # Pydantic settings
├── services/                 # Backend service clients
│   ├── __init__.py
│   ├── order_service_client.py
│   └── product_service_client.py
├── telemetry/                # OpenTelemetry setup
│   ├── __init__.py
│   ├── gen_ai_semantics.py   # Gen AI semantic conventions implementation
│   ├── m365_agent_integration.py  # Microsoft 365 Agents SDK integration
│   └── otel_setup.py         # Core telemetry configuration
├── kubernetes/               # K8s manifests
│   ├── customer-agent-deployment.yaml
│   ├── customer-agent-service.yaml
│   ├── customer-agent-configmap.yaml
│   └── customer-agent-serviceaccount.yaml
├── tests/                    # Unit tests
├── app.py                    # Chainlit application
├── chainlit.md               # Chat welcome message
├── Dockerfile
├── requirements.txt
└── pyproject.toml
```

## 🔗 Related Resources

- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- [Microsoft 365 Agents SDK](https://github.com/Microsoft/Agents-for-python)
- [Azure AI Foundry Documentation](https://learn.microsoft.com/azure/ai-services/agents/overview)
- [Chainlit Documentation](https://docs.chainlit.io)
- [AKS Workload Identity](https://learn.microsoft.com/azure/aks/workload-identity-overview)
- [OpenTelemetry Gen AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)

## 🆔 Microsoft 365 Agents SDK Integration

This agent integrates with the [Microsoft 365 Agents SDK](https://github.com/Microsoft/Agents-for-python) for enhanced agent identification. The integration provides:

### Unique Agent ID

Each agent instance receives a unique, stable identifier (UUID format) generated based on:

- Agent name and type
- Azure AD tenant ID (if configured)
- Azure AD application ID (if configured)
- Pod name (in Kubernetes) or hostname (local development)

This ensures:

- **Stability**: Same configuration produces the same agent ID
- **Uniqueness**: Different agent instances/pods have distinct IDs
- **Traceability**: Full correlation across distributed traces

### Configuration

To enable enhanced agent identification, set the following environment variables:

```bash
# Optional: Azure AD configuration for stable agent IDs
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
```

When running on AKS with Workload Identity, these values are automatically available from the pod's identity.

### Package Dependencies

The integration uses the following Microsoft 365 Agents SDK packages:

```
microsoft-agents-activity>=0.7.0
microsoft-agents-hosting-core>=0.7.0
```

> **Note**: The SDK is optional. If not installed, the agent will use a fallback ID generation mechanism and log a warning message.

### Verifying the Integration

Check the agent startup logs for the M365 Agent ID:

```
INFO - Customer Agent initialized with M365 Agent ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890, M365 SDK available: True
```

In your OTEL traces, look for the `m365.agent.id` and `gen_ai.agent.id` attributes.

## 📄 License

This project is part of the AKS Store Demo and is licensed under the MIT License.
