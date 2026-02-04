# Admin Agent

An AI-powered administrative assistant for the AKS Pet Store, built with Microsoft Agent Framework and Azure AI Foundry.

## Overview

The Admin Agent provides a conversational interface for store administrators to:

- **Product Management**: Add, update, delete, and list products in the catalog
- **Order Management**: View orders, update status, and track fulfillment

The agent uses:

- **Microsoft Agent Framework** with `AzureAIProjectAgentProvider`
- **Azure AI Foundry** for GPT-4o model hosting
- **Chainlit** for the conversational UI
- **OpenTelemetry** with Gen AI semantic conventions for observability

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Chainlit UI   │────▶│   Admin Agent    │────▶│ Azure AI Foundry│
│   (WebSocket)   │     │ (Microsoft Agent │     │    (GPT-4o)     │
└─────────────────┘     │   Framework)     │     └─────────────────┘
                        └────────┬─────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
           ┌───────────────┐         ┌───────────────┐
           │product-service│         │makeline-service│
           │   (Rust)      │         │   (Go)         │
           │   :3002       │         │   :3001        │
           └───────────────┘         └───────────────┘
```

## Features

### Product Management Tools

| Tool                  | Description                                             |
| --------------------- | ------------------------------------------------------- |
| `get_products`        | List all products in the catalog                        |
| `get_product_details` | Get details of a specific product by ID                 |
| `add_product`         | Add a new product with name, price, description         |
| `update_product`      | Update product fields (name, price, description, image) |
| `delete_product`      | Remove a product from the catalog                       |

### Order Management Tools

| Tool                     | Description                                       |
| ------------------------ | ------------------------------------------------- |
| `get_orders`             | List all orders with status summary               |
| `get_order_details`      | Get details of a specific order                   |
| `update_order_status`    | Change order status (Pending/Processing/Complete) |
| `start_processing_order` | Shortcut to mark order as Processing              |
| `complete_order`         | Shortcut to mark order as Complete                |

## Quick Start

### Prerequisites

- Python 3.11+
- Azure CLI (for local development)
- Azure AI Foundry project with GPT-4o deployed

### Local Development

1. **Clone and navigate to the agent directory**:

   ```bash
   cd src/agents/admin-agent
   ```

2. **Create virtual environment**:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # or .venv\Scripts\activate on Windows
   ```

3. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:

   ```bash
   cp .env.example .env
   # Edit .env with your Azure AI Foundry endpoint
   ```

5. **Login to Azure** (for local authentication):

   ```bash
   az login
   ```

6. **Run the agent**:

   ```bash
   chainlit run app.py
   ```

7. **Open browser** at `http://localhost:8000`

### Docker

```bash
# Build
cd ~/aks-store-demo
docker build -t admin-agent:latest -f  src/agents/admin-agent/Dockerfile src/

# Run
docker run -p 8000:8000 \
  -e AZURE_AI_PROJECT_ENDPOINT="your-endpoint" \
  -e USE_WORKLOAD_IDENTITY_AUTH="false" \
  admin-agent:latest
```

### Kubernetes Deployment

See [kubernetes/README.md](kubernetes/README.md) for detailed deployment instructions.

```bash
cd ~/aks-store-demo/src/agents/admin-agent
kubectl kustomize kubernetes/
kubectl apply -k kubernetes/ -n pets

```

## Configuration

### Environment Variables

| Variable                                | Description                       | Default                        |
| --------------------------------------- | --------------------------------- | ------------------------------ |
| `AZURE_AI_PROJECT_ENDPOINT`             | Azure AI Foundry project endpoint | Required                       |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME`        | Model deployment name             | `gpt-4o`                       |
| `USE_WORKLOAD_IDENTITY_AUTH`            | Use Workload Identity (AKS)       | `true`                         |
| `PRODUCT_SERVICE_URL`                   | Product service URL               | `http://product-service:3002`  |
| `MAKELINE_SERVICE_URL`                  | Makeline service URL              | `http://makeline-service:3001` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | App Insights connection           | Optional                       |
| `OTEL_SERVICE_NAME`                     | OpenTelemetry service name        | `admin-agent`                  |

## Project Structure

```
admin-agent/
├── agent/
│   ├── __init__.py
│   ├── admin_agent.py      # Main agent class
│   └── tools.py            # Function tools (product & order management)
├── config/
│   ├── __init__.py
│   └── settings.py         # Pydantic settings
├── services/
│   ├── __init__.py
│   ├── product_service_client.py    # Product CRUD operations
│   └── makeline_service_client.py   # Order management operations
├── telemetry/
│   ├── __init__.py
│   ├── gen_ai_semantics.py # Gen AI semantic conventions
│   ├── k8s_semantics.py    # Kubernetes semantic conventions
│   ├── m365_agent_integration.py  # Microsoft 365 Agents SDK integration
│   └── otel_setup.py       # OpenTelemetry configuration
├── kubernetes/
│   ├── admin-agent-*.yaml  # K8s manifests
│   ├── kustomization.yaml
│   └── README.md
├── .chainlit/
│   └── config.toml         # Chainlit configuration
├── app.py                  # Main Chainlit application
├── chainlit.md             # Welcome message
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## Observability

The admin-agent implements OpenTelemetry Gen AI semantic conventions:

### Spans

- `create_agent {agent_name}` - Agent initialization
- `invoke_agent {agent_name}` - Message processing
- `execute_tool {tool_name}` - Tool execution

### Metrics

- `gen_ai.client.token.usage` - Token usage histogram
- `gen_ai.client.operation.duration` - Operation duration histogram

### Attributes

- Gen AI attributes: `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.agent.name`, `gen_ai.agent.id`
- Microsoft 365 Agent SDK attributes: `m365.agent.id`, `m365.agent.type`, `m365.channel.id`, `m365.activity.id`
- Kubernetes attributes: `k8s.pod.name`, `k8s.namespace.name`, `k8s.node.name`
- Cloud attributes: `cloud.provider`, `cloud.platform`, `cloud.region`

## API Endpoints

| Endpoint  | Method | Description     |
| --------- | ------ | --------------- |
| `/`       | GET    | Chainlit UI     |
| `/health` | GET    | Liveness probe  |
| `/ready`  | GET    | Readiness probe |

## Example Interactions

```
User: Show me all products
Agent: [Retrieves and displays product catalog]

User: Add a new product called "Premium Cat Food" priced at $24.99 with description "High-quality cat food for adult cats"
Agent: ✅ Product 'Premium Cat Food' added successfully with price $24.99

User: Show me pending orders
Agent: [Displays orders with Pending status]

User: Mark order abc123 as complete
Agent: ✅ Order abc123 status updated: Processing → Complete
```

## Related

- [Customer Agent](../customer-agent/README.md) - Customer-facing agent for browsing and ordering
- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- [Microsoft 365 Agents SDK](https://github.com/Microsoft/Agents-for-python)
- [Azure AI Foundry](https://azure.microsoft.com/products/ai-foundry/)
- [OpenTelemetry Gen AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)

## Microsoft 365 Agents SDK Integration

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
INFO - Admin Agent initialized with M365 Agent ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890, M365 SDK available: True
```

In your OTEL traces, look for the `m365.agent.id` and `gen_ai.agent.id` attributes.
