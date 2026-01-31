# Customer Agent - High Level Architecture

This document provides detailed architectural documentation for the Customer Agent component of the AKS Store Demo.

## Table of Contents

1. [Overview](#overview)
2. [Architecture Diagrams](#architecture-diagrams)
3. [Component Details](#component-details)
4. [Data Flow](#data-flow)
5. [Security Architecture](#security-architecture)
6. [Observability Architecture](#observability-architecture)
7. [Deployment Architecture](#deployment-architecture)

---

## Overview

The Customer Agent is an AI-powered conversational assistant that enables customers to interact with the AKS Pet Store through natural language. It integrates with Microsoft Agent Framework (connected to Azure AI Foundry) for intelligent responses and uses Workload Identity for secure, secret-free authentication on AKS.

### Key Design Principles

- **Serverless AI** - Leverages Azure AI Foundry managed agent runtime
- **Zero Trust Security** - Workload Identity for passwordless authentication
- **Observable by Design** - OpenTelemetry with Gen AI semantic conventions
- **Cloud Native** - Kubernetes-native deployment with LoadBalancer service
- **Event-Driven Tools** - Function tools connect to existing microservices

---

## Architecture Diagrams

### System Context Diagram

```
                                    ┌────────────────────────────────────────┐
                                    │           Azure Cloud                   │
                                    │                                         │
┌──────────────┐                   │  ┌─────────────────────────────────┐   │
│              │                   │  │      Azure AI Foundry            │   │
│   Customer   │  HTTPS            │  │                                  │   │
│   (Browser)  │◄──────────────────┼─▶│  ┌────────────────────────────┐ │   │
│              │                   │  │  │    Agent Service            │ │   │
└──────────────┘                   │  │  │  • Model Inference (GPT-4o) │ │   │
                                   │  │  │  • Conversation State       │ │   │
                                   │  │  │  • Tool Orchestration       │ │   │
                                   │  │  └────────────────────────────┘ │   │
                                   │  └───────────────▲─────────────────┘   │
                                   │                  │                      │
                                   │                  │ Workload Identity    │
                                   │                  │                      │
                                   │  ┌───────────────┴─────────────────┐   │
                                   │  │       AKS Cluster                │   │
                                   │  │                                  │   │
                                   │  │  ┌─────────────────────────┐    │   │
                                   │  │  │    Customer Agent Pod    │    │   │
                                   │  │  │    (Chainlit + Agent)    │    │   │
                                   │  │  └───────────┬─────────────┘    │   │
                                   │  │              │                   │   │
                                   │  │   ┌─────────┼─────────┐         │   │
                                   │  │   │         │         │         │   │
                                   │  │   ▼         ▼         ▼         │   │
                                   │  │ ┌─────┐ ┌─────┐ ┌─────────┐    │   │
                                   │  │ │Order│ │Prod │ │Makeline │    │   │
                                   │  │ │Svc  │ │Svc  │ │Service  │    │   │
                                   │  │ └─────┘ └─────┘ └─────────┘    │   │
                                   │  └─────────────────────────────────┘   │
                                   │                                         │
                                   │  ┌─────────────────────────────────┐   │
                                   │  │      Azure Monitor               │   │
                                   │  │      Application Insights        │   │
                                   │  └─────────────────────────────────┘   │
                                   └────────────────────────────────────────┘
```

### Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Customer Agent Service                                 │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        Chainlit Web Application                           │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐   │  │
│  │  │   WebSocket     │  │   Session       │  │      Message            │   │  │
│  │  │   Handler       │──│   Manager       │──│      Streaming          │   │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────────┘   │  │
│  └────────────────────────────────┬─────────────────────────────────────────┘  │
│                                   │                                             │
│  ┌────────────────────────────────┴─────────────────────────────────────────┐  │
│  │                         Customer Agent Core                               │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐   │  │
│  │  │ CustomerAgent   │  │    ChatAgent    │  │     ChatThread          │   │  │
│  │  │ Class           │──│   (Framework)   │──│  (Conversations)        │   │  │
│  │  └────────┬────────┘  └────────┬────────┘  └─────────────────────────┘   │  │
│  │           │                    │                                          │  │
│  │  ┌────────┴────────────────────┴────────┐                                │  │
│  │  │           Function Tools              │                                │  │
│  │  │  ┌──────────┐ ┌──────────┐ ┌───────┐ │                                │  │
│  │  │  │get_      │ │place_    │ │search_│ │                                │  │
│  │  │  │products  │ │order     │ │prods  │ │                                │  │
│  │  │  └────┬─────┘ └────┬─────┘ └───┬───┘ │                                │  │
│  │  └───────┼────────────┼───────────┼─────┘                                │  │
│  └──────────┼────────────┼───────────┼──────────────────────────────────────┘  │
│             │            │           │                                          │
│  ┌──────────┴────────────┴───────────┴──────────────────────────────────────┐  │
│  │                      Service Clients Layer                                │  │
│  │  ┌──────────────────────────┐  ┌──────────────────────────────────────┐  │  │
│  │  │   ProductServiceClient   │  │        OrderServiceClient            │  │  │
│  │  │   • get_all_products()   │  │   • place_order()                    │  │  │
│  │  │   • get_product_by_id()  │  │   • get_order_status()               │  │  │
│  │  │   • search_products()    │  │   • get_pending_orders()             │  │  │
│  │  └──────────────────────────┘  └──────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                      Telemetry Layer                                      │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐   │  │
│  │  │ OpenTelemetry   │  │ Gen AI Span     │  │  Azure Monitor          │   │  │
│  │  │ Tracer          │──│ Processor       │──│  Exporter               │   │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Microsoft Agent Framework Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│               Microsoft Agent Framework + Azure AI Foundry                       │
│                                                                                  │
│   User Message                                                                   │
│       │                                                                          │
│       ▼                                                                          │
│   ┌───────────────────┐                                                         │
│   │  Create Thread    │  ◄─── New conversation session                          │
│   │  (if new session) │                                                         │
│   └─────────┬─────────┘                                                         │
│             │                                                                    │
│             ▼                                                                    │
│   ┌───────────────────┐                                                         │
│   │  Create Message   │  ◄─── Add user message to thread                        │
│   │  (role: user)     │                                                         │
│   └─────────┬─────────┘                                                         │
│             │                                                                    │
│             ▼                                                                    │
│   ┌───────────────────┐                                                         │
│   │   Run Agent       │  ◄─── Process with model + tools                        │
│   │                   │                                                         │
│   │  ┌─────────────┐  │                                                         │
│   │  │   Model     │  │  GPT-4o-mini inference                                  │
│   │  │ (gpt-4o)    │  │                                                         │
│   │  └──────┬──────┘  │                                                         │
│   │         │         │                                                         │
│   │         ▼         │                                                         │
│   │  ┌─────────────┐  │                                                         │
│   │  │ Tool Calls? │──┼──▶ Yes ──▶ Execute function tools                       │
│   │  └──────┬──────┘  │           (get_products, place_order, etc.)             │
│   │         │ No      │                   │                                      │
│   │         ▼         │                   │                                      │
│   │  ┌─────────────┐  │◄──────────────────┘                                     │
│   │  │  Generate   │  │                                                         │
│   │  │  Response   │  │                                                         │
│   │  └─────────────┘  │                                                         │
│   └─────────┬─────────┘                                                         │
│             │                                                                    │
│             ▼                                                                    │
│   ┌───────────────────┐                                                         │
│   │  Stream Response  │  ◄─── Real-time token streaming                         │
│   │  to Chainlit      │                                                         │
│   └───────────────────┘                                                         │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Chainlit Web Application (`app.py`)

The conversational UI layer built with Chainlit:

| Component          | Purpose                               |
| ------------------ | ------------------------------------- |
| `on_chat_start`    | Initializes new conversation threads  |
| `on_message`       | Processes incoming user messages      |
| `stream_message`   | Streams AI responses in real-time     |
| Session Management | Maintains thread IDs per user session |

### 2. Customer Agent (`agent/customer_agent.py`)

Core agent implementation using Microsoft Agent Framework:

| Method              | Purpose                                     |
| ------------------- | ------------------------------------------- |
| `initialize()`      | Connects to Azure AI Foundry, creates agent |
| `create_thread()`   | Creates new conversation thread             |
| `process_message()` | Sends message, gets response                |
| `stream_message()`  | Streaming response generation               |
| `cleanup()`         | Deletes agent and cleans up resources       |

### 3. Function Tools (`agent/tools.py`)

Agent capabilities exposed as function tools:

| Tool                  | Backend Service  | Operation                |
| --------------------- | ---------------- | ------------------------ |
| `get_products`        | product-service  | GET /products            |
| `get_product_details` | product-service  | GET /products/{id}       |
| `search_products`     | product-service  | GET /products (filtered) |
| `place_order`         | order-service    | POST /order              |
| `get_order_status`    | makeline-service | GET /order/{id}          |

### 4. Service Clients (`services/`)

HTTP clients for backend service communication:

- **ProductServiceClient**: Communicates with Rust product-service
- **OrderServiceClient**: Communicates with Node.js order-service and Go makeline-service

### 5. Telemetry (`telemetry/otel_setup.py`)

OpenTelemetry configuration with Gen AI semantics:

- Custom span processor for Gen AI attributes
- Azure Monitor exporter integration
- Trace decorator for function tracing
- Content recording based on environment config

---

## Data Flow

### Order Placement Flow

```
┌──────────┐    ┌──────────────┐    ┌───────────────┐    ┌───────────────┐
│ Customer │───▶│ Customer     │───▶│ Azure AI      │───▶│ place_order   │
│ Browser  │    │ Agent        │    │ Foundry       │    │ tool          │
└──────────┘    └──────────────┘    └───────────────┘    └───────┬───────┘
                                                                  │
    ┌─────────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ order-service │───▶│   RabbitMQ    │───▶│  makeline-    │
│ (POST /order) │    │   Queue       │    │  service      │
└───────────────┘    └───────────────┘    └───────┬───────┘
                                                   │
                                                   ▼
                                          ┌───────────────┐
                                          │   MongoDB     │
                                          │  (Storage)    │
                                          └───────────────┘
```

### Message Processing Sequence

```
┌────────┐     ┌─────────┐     ┌─────────────┐     ┌────────────┐     ┌─────────┐
│Customer│     │Chainlit │     │CustomerAgent│     │Azure AI    │     │Backend  │
│        │     │         │     │             │     │Foundry     │     │Services │
└───┬────┘     └────┬────┘     └──────┬──────┘     └─────┬──────┘     └────┬────┘
    │               │                 │                  │                 │
    │  Send Message │                 │                  │                 │
    │──────────────▶│                 │                  │                 │
    │               │  on_message()   │                  │                 │
    │               │────────────────▶│                  │                 │
    │               │                 │  stream_message()│                 │
    │               │                 │─────────────────▶│                 │
    │               │                 │                  │                 │
    │               │                 │                  │  Tool Call      │
    │               │                 │                  │  (if needed)    │
    │               │                 │◀─────────────────│                 │
    │               │                 │                  │                 │
    │               │                 │  HTTP Request    │                 │
    │               │                 │─────────────────────────────────────▶
    │               │                 │                  │                 │
    │               │                 │  HTTP Response   │                 │
    │               │                 │◀─────────────────────────────────────
    │               │                 │                  │                 │
    │               │                 │  Tool Result     │                 │
    │               │                 │─────────────────▶│                 │
    │               │                 │                  │                 │
    │               │                 │  Stream Tokens   │                 │
    │               │                 │◀─────────────────│                 │
    │               │  Stream Tokens  │                  │                 │
    │               │◀────────────────│                  │                 │
    │  Display      │                 │                  │                 │
    │◀──────────────│                 │                  │                 │
    │               │                 │                  │                 │
```

---

## Security Architecture

### Workload Identity Authentication

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AKS Cluster                                           │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     Customer Agent Pod                               │   │
│   │                                                                      │   │
│   │   ┌───────────────┐                                                 │   │
│   │   │ ServiceAccount│◄──── azure.workload.identity/client-id          │   │
│   │   │ customer-     │      annotation                                  │   │
│   │   │ agent-sa      │                                                  │   │
│   │   └───────┬───────┘                                                 │   │
│   │           │                                                          │   │
│   │           │ Mounted Token                                            │   │
│   │           │ (AZURE_FEDERATED_TOKEN_FILE)                             │   │
│   │           ▼                                                          │   │
│   │   ┌───────────────┐      ┌─────────────────────────────────────┐    │   │
│   │   │DefaultAzure   │─────▶│ Exchange federated token for        │    │   │
│   │   │Credential     │      │ Azure AD access token                │    │   │
│   │   └───────────────┘      └──────────────────┬──────────────────┘    │   │
│   │                                              │                       │   │
│   └──────────────────────────────────────────────┼───────────────────────┘   │
│                                                  │                           │
└──────────────────────────────────────────────────┼───────────────────────────┘
                                                   │
                                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Azure AD                                         │
│                                                                               │
│   ┌───────────────────────────────────────────────────────────────────────┐  │
│   │                    Federated Identity Credential                       │  │
│   │                                                                        │  │
│   │   Issuer: https://<aks-oidc-issuer>                                   │  │
│   │   Subject: system:serviceaccount:pets:customer-agent-sa               │  │
│   │   Audience: api://AzureADTokenExchange                                │  │
│   │                                                                        │  │
│   │   Linked to: Managed Identity (customer-agent-identity)               │  │
│   │              with "Cognitive Services User" role                       │  │
│   └───────────────────────────────────────────────────────────────────────┘  │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Security Controls

| Layer    | Control                 | Purpose                    |
| -------- | ----------------------- | -------------------------- |
| Network  | LoadBalancer Service    | External access point      |
| Identity | Workload Identity       | Passwordless auth to Azure |
| Runtime  | Non-root container      | Reduced attack surface     |
| RBAC     | Cognitive Services User | Least privilege access     |
| Secrets  | No stored credentials   | Zero secret management     |

---

## Observability Architecture

### OpenTelemetry Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Customer Agent Application                            │
│                                                                              │
│   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────────────┐   │
│   │  Application    │   │  @trace_function│   │  Gen AI Span            │   │
│   │  Code           │──▶│  Decorator      │──▶│  Processor              │   │
│   │                 │   │                 │   │                         │   │
│   │  • Agent calls  │   │  Adds spans for:│   │  Enriches spans with:   │   │
│   │  • Tool calls   │   │  • Function name│   │  • gen_ai.system        │   │
│   │  • HTTP calls   │   │  • Parameters   │   │  • gen_ai.agent.name    │   │
│   │                 │   │  • Return values│   │  • gen_ai.operation.type│   │
│   └─────────────────┘   └─────────────────┘   └───────────┬─────────────┘   │
│                                                            │                 │
│   ┌────────────────────────────────────────────────────────┴─────────────┐   │
│   │                        OpenTelemetry SDK                              │   │
│   │                                                                       │   │
│   │   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐    │   │
│   │   │  TracerProvider │──▶│  BatchSpan      │──▶│  Azure Monitor  │    │   │
│   │   │                 │   │  Processor      │   │  Exporter       │    │   │
│   │   └─────────────────┘   └─────────────────┘   └────────┬────────┘    │   │
│   │                                                         │             │   │
│   └─────────────────────────────────────────────────────────┼─────────────┘   │
│                                                             │                 │
└─────────────────────────────────────────────────────────────┼─────────────────┘
                                                              │
                                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Azure Monitor / Application Insights                  │
│                                                                              │
│   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────────────┐   │
│   │  Transaction    │   │  Live Metrics   │   │  Log Analytics          │   │
│   │  Search         │   │                 │   │  Workspace              │   │
│   │                 │   │  • Real-time    │   │                         │   │
│   │  • End-to-end   │   │    telemetry    │   │  • KQL queries          │   │
│   │    traces       │   │  • Performance  │   │  • Dashboards           │   │
│   │  • Dependencies │   │    counters     │   │  • Alerts               │   │
│   └─────────────────┘   └─────────────────┘   └─────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Trace Example

```
Trace: chat_session (12.5s)
├── customer_agent_init (0.8s)
│   └── Attributes:
│       ├── agent.name: "Pet Store Customer Assistant"
│       └── model.deployment: "gpt-4o-mini"
│
├── agent_process_message (11.2s)
│   ├── Attributes:
│   │   ├── thread.id: "thread_abc123"
│   │   ├── message.length: 45
│   │   └── gen_ai.operation.type: "agent"
│   │
│   ├── get_products (0.3s)
│   │   └── HTTP GET http://product-service:3002/products
│   │
│   └── place_order (0.5s)
│       └── HTTP POST http://order-service:3000/order
│
└── response.length: 256
```

---

## Deployment Architecture

### Kubernetes Resources

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Kubernetes Namespace: pets                         │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        ServiceAccount                                │   │
│   │                        customer-agent-sa                             │   │
│   │                                                                      │   │
│   │   Labels:                                                            │   │
│   │     azure.workload.identity/use: "true"                             │   │
│   │   Annotations:                                                       │   │
│   │     azure.workload.identity/client-id: <managed-identity-client-id> │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                        │                                     │
│                                        │ uses                                │
│                                        ▼                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                          Deployment                                  │   │
│   │                          customer-agent                              │   │
│   │                                                                      │   │
│   │   ┌─────────────────────────────────────────────────────────────┐   │   │
│   │   │                      Pod                                     │   │   │
│   │   │                                                              │   │   │
│   │   │   ┌──────────────────────────────────────────────────────┐  │   │   │
│   │   │   │              Container: customer-agent                │  │   │   │
│   │   │   │                                                       │  │   │   │
│   │   │   │   Image: customer-agent:latest                       │  │   │   │
│   │   │   │   Port: 8000                                          │  │   │   │
│   │   │   │                                                       │  │   │   │
│   │   │   │   Resources:                                          │  │   │   │
│   │   │   │     requests: cpu=250m, memory=512Mi                  │  │   │   │
│   │   │   │     limits:   cpu=1000m, memory=1Gi                   │  │   │   │
│   │   │   │                                                       │  │   │   │
│   │   │   │   Probes:                                             │  │   │   │
│   │   │   │     liveness:  GET / :8000                            │  │   │   │
│   │   │   │     readiness: GET / :8000                            │  │   │   │
│   │   │   └──────────────────────────────────────────────────────┘  │   │   │
│   │   │                                                              │   │   │
│   │   └──────────────────────────────────────────────────────────────┘   │   │
│   │                                                                      │   │
│   │   envFrom:                                                           │   │
│   │     - configMapRef: customer-agent-config                            │   │
│   │     - secretRef:    customer-agent-secrets                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                        │                                     │
│                                        │ exposes                             │
│                                        ▼                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                           Service                                    │   │
│   │                           customer-agent                             │   │
│   │                           type: LoadBalancer                         │   │
│   │                                                                      │   │
│   │   Port: 80 → targetPort: 8000                                       │   │
│   │   External IP: <azure-lb-ip>                                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌──────────────────────────┐   ┌──────────────────────────────────────┐   │
│   │        ConfigMap          │   │             Secret                   │   │
│   │   customer-agent-config   │   │      customer-agent-secrets          │   │
│   │                           │   │                                      │   │
│   │ • AZURE_AI_PROJECT_       │   │ • APPLICATIONINSIGHTS_               │   │
│   │   ENDPOINT                │   │   CONNECTION_STRING                  │   │
│   │ • SERVICE URLs            │   │                                      │   │
│   │ • OTEL config             │   │                                      │   │
│   └──────────────────────────┘   └──────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Integration with Existing Services

The Customer Agent integrates with the existing AKS Store Demo services:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AKS Cluster - pets namespace                       │
│                                                                              │
│   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐          │
│   │  store-     │         │  store-     │         │  customer-  │          │
│   │  front      │         │  admin      │         │  agent      │  ◄── NEW │
│   │  (Vue.js)   │         │  (Vue.js)   │         │  (Python)   │          │
│   └──────┬──────┘         └──────┬──────┘         └──────┬──────┘          │
│          │                       │                       │                  │
│          │                       │                       │                  │
│          ▼                       ▼                       ▼                  │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                        Backend Services                              │  │
│   │                                                                      │  │
│   │   ┌─────────────┐   ┌─────────────┐   ┌─────────────────────────┐   │  │
│   │   │ product-    │   │ order-      │   │    makeline-service     │   │  │
│   │   │ service     │   │ service     │   │                         │   │  │
│   │   │ (Rust)      │   │ (Node.js)   │   │    (Golang)             │   │  │
│   │   │ :3002       │   │ :3000       │   │    :3001                │   │  │
│   │   └─────────────┘   └──────┬──────┘   └───────────┬─────────────┘   │  │
│   │                            │                       │                 │  │
│   │                            ▼                       │                 │  │
│   │                     ┌─────────────┐                │                 │  │
│   │                     │  RabbitMQ   │────────────────┘                 │  │
│   │                     │  (Queue)    │                                  │  │
│   │                     └─────────────┘                                  │  │
│   │                                                                      │  │
│   │                     ┌─────────────┐                                  │  │
│   │                     │  MongoDB    │                                  │  │
│   │                     │  (Storage)  │                                  │  │
│   │                     └─────────────┘                                  │  │
│   │                                                                      │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary

The Customer Agent extends the AKS Store Demo with:

1. **Conversational AI** - Natural language interface for customers
2. **Azure AI Integration** - Leverages Microsoft Agent Framework with Azure AI Foundry
3. **Secure by Design** - Workload Identity for zero-secret authentication
4. **Observable** - Full OpenTelemetry tracing with Gen AI semantics
5. **Cloud Native** - Kubernetes-native deployment with LoadBalancer access

This architecture enables customers to interact with the pet store through natural language while maintaining enterprise-grade security and observability.
