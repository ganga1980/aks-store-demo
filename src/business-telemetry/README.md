# Microsoft Fabric Business Telemetry Service

A standalone service for collecting and ingesting business telemetry data from AKS Store Demo applications into Microsoft Fabric for analytics and ontology building.

## Overview

This service provides a comprehensive solution for capturing business events (not observability/operational metrics) and streaming them to Microsoft Fabric for:

- **Real-time Analytics** via Event Hubs → Fabric Real-Time Analytics (KQL Database)
- **Batch Analytics** via OneLake (Delta Lake format) → Fabric Lakehouse
- **Business Intelligence** via Power BI DirectLake mode
- **Data Science** via Fabric Spark Notebooks
- **Microsoft Ontology** building for semantic data models

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AKS Store Demo Services                            │
├─────────────────┬─────────────────┬────────────────┬────────────────────────┤
│ Customer Agent  │  Admin Agent    │  Store Front   │  Order Service         │
│    (Python)     │    (Python)     │   (Vue.js)     │    (Node.js)           │
└────────┬────────┴────────┬────────┴───────┬────────┴───────────┬────────────┘
         │                 │                 │                    │
         │  SDK (async)    │  SDK (async)    │  HTTP API          │  HTTP API
         │                 │                 │                    │
         ▼                 ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Business Telemetry Service                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Events    │  │  Telemetry  │  │   Fabric    │  │     FastAPI         │ │
│  │   Models    │──│   Client    │──│   Sinks     │──│    HTTP API         │ │
│  │ (CDM-based) │  │  (Async)    │  │ (Pluggable) │  │  /events /batch     │ │
│  └─────────────┘  └─────────────┘  └──────┬──────┘  └─────────────────────┘ │
└───────────────────────────────────────────┼─────────────────────────────────┘
                                            │
              ┌─────────────────────────────┼─────────────────────────────┐
              │                             │                             │
              ▼                             ▼                             ▼
┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│   Azure Event Hubs   │    │       OneLake        │    │     Local File       │
│   (Real-time)        │    │   (Batch/Delta)      │    │    (Development)     │
└──────────┬───────────┘    └──────────┬───────────┘    └──────────────────────┘
           │                           │
           ▼                           ▼
┌──────────────────────┐    ┌──────────────────────┐
│  Fabric Real-Time    │    │   Fabric Lakehouse   │
│  Analytics (KQL)     │    │   (SQL/Spark)        │
└──────────────────────┘    └──────────────────────┘
           │                           │
           └───────────┬───────────────┘
                       ▼
              ┌──────────────────────┐
              │   Microsoft Fabric   │
              │   ┌──────────────┐   │
              │   │  Ontology    │   │
              │   │  (Semantic   │   │
              │   │   Model)     │   │
              │   └──────────────┘   │
              │   ┌──────────────┐   │
              │   │  Power BI    │   │
              │   │  Reports     │   │
              │   └──────────────┘   │
              └──────────────────────┘
```

## Business Event Types

### Product Events

| Event Type         | Description                    | Key Fields                                |
| ------------------ | ------------------------------ | ----------------------------------------- |
| `product.viewed`   | Customer viewed a product      | product_id, product_name, category, price |
| `product.searched` | Customer searched for products | search_query, results_count, product_ids  |
| `product.listed`   | Products were listed/displayed | product_ids, page, page_size              |

### Order Events

| Event Type             | Description              | Key Fields                            |
| ---------------------- | ------------------------ | ------------------------------------- |
| `order.placed`         | Customer placed an order | order_id, items, total, customer_name |
| `order.status_checked` | Order status was queried | order_id, status                      |
| `order.completed`      | Order was fulfilled      | order_id, processing_duration_ms      |
| `order.failed`         | Order processing failed  | order_id, error_reason                |

### Customer Events

| Event Type                 | Description                | Key Fields                                 |
| -------------------------- | -------------------------- | ------------------------------------------ |
| `customer.session_started` | Customer started a session | session_id, user_id                        |
| `customer.session_ended`   | Customer ended a session   | session_id, duration_ms, interaction_count |
| `customer.query`           | Customer asked a question  | query_text, response_time_ms, ai_model     |
| `customer.feedback`        | Customer provided feedback | feedback_rating, feedback_text             |

### Admin Events

| Event Type                | Description             | Key Fields                            |
| ------------------------- | ----------------------- | ------------------------------------- |
| `admin.inventory_updated` | Inventory was changed   | product_id, previous_qty, new_qty     |
| `admin.product_created`   | New product was created | product_id, product_name, ai_assisted |
| `admin.product_updated`   | Product was modified    | product_id, changes                   |
| `admin.product_deleted`   | Product was removed     | product_id                            |

### AI Events

| Event Type                 | Description              | Key Fields                              |
| -------------------------- | ------------------------ | --------------------------------------- |
| `ai.recommendation`        | AI made a recommendation | model_name, input_tokens, output_tokens |
| `ai.description_generated` | AI generated content     | model_name, content_type, tokens_used   |

## Quick Start

### 1. Install Dependencies

```bash
cd src/business-telemetry
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Minimal configuration (console output for development)
export FABRIC_SINK_TYPE=console
export FABRIC_ENVIRONMENT=development

# Production configuration (Event Hub)
export FABRIC_SINK_TYPE=eventhub
export FABRIC_EVENT_HUB_CONNECTION_STRING="Endpoint=sb://..."
export FABRIC_EVENT_HUB_NAME=business-telemetry
export FABRIC_ENVIRONMENT=production
```

### 3. Run the Service

```bash
# Development
python main.py

# Production with uvicorn
uvicorn main:app --host 0.0.0.0 --port 8080 --workers 4
```

### 4. Send Events

```bash
# Single event
curl -X POST http://localhost:8080/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "product.viewed",
    "data": {
      "product_id": "123",
      "product_name": "Widget"
    }
  }'

# Batch events
curl -X POST http://localhost:8080/events/batch \
  -H "Content-Type: application/json" \
  -d '{
    "events": [
      {"event_type": "product.viewed", "data": {"product_id": "123"}},
      {"event_type": "product.viewed", "data": {"product_id": "456"}}
    ]
  }'
```

## SDK Usage

For Python services, use the SDK directly instead of HTTP:

```python
from telemetry_client import BusinessTelemetryClient

# Initialize client
client = BusinessTelemetryClient.from_env()
await client.start()

# Use session context for automatic session events
async with client.session_context(session_id="sess-123") as ctx:
    # Emit product viewed event
    await client.emit_product_viewed(
        product_id="prod-456",
        product_name="Premium Widget",
        category="electronics",
        price=99.99
    )

    # Emit order placed event
    await client.emit_order_placed(
        order_id="ord-789",
        items=[{"product_id": "prod-456", "quantity": 2}],
        total=199.98,
        customer_name="John Doe"
    )

# Cleanup
await client.stop()
```

## Microsoft 365 Agents SDK Integration

The Business Telemetry service supports integration with Microsoft 365 Agents SDK for unique agent identification. This enables consistent `gen_ai.agent.id` attribute across all business telemetry events.

### Setup

1. **Install M365 Agents SDK packages** (already included in requirements.txt):

   ```bash
   pip install microsoft-agents-activity>=0.7.0 microsoft-agents-hosting-core>=0.7.0
   ```

2. **Configure environment variables**:
   ```bash
   # Required for unique agent ID generation
   export AZURE_TENANT_ID=your-azure-tenant-id
   export AZURE_CLIENT_ID=your-azure-client-id
   ```

### Usage with M365 Agent IDs

```python
from sdk import (
    init_telemetry,
    init_m365_agent_context,
    emit_agent_session_started,
    emit_agent_session_ended,
    emit_agent_tool_call,
    get_gen_ai_agent_id,
)

# Initialize telemetry client
await init_telemetry()

# Initialize M365 agent context for unique agent ID
provider = init_m365_agent_context(
    agent_name="customer-agent",
    agent_type="customer",
    channel_id="webchat",
)

# The agent ID is now a unique UUID
print(f"M365 Agent ID: {provider.agent_id}")
# Output: M365 Agent ID: 550e8400-e29b-41d4-a716-446655440000

# Emit events with automatic M365 agent ID
await emit_agent_session_started(
    agent_name="customer-agent",
    session_id="sess-123",
    # m365_agent_id is automatically populated from the global provider
)

# Or explicitly pass the M365 agent ID
await emit_agent_tool_call(
    tool_name="get_products",
    agent_name="customer-agent",
    session_id="sess-123",
    duration_ms=150,
    m365_agent_id=provider.agent_id,  # Explicit M365 agent ID
)

# Get the M365 agent ID anywhere in your code
agent_id = get_gen_ai_agent_id()
```

### Agent ID Generation

The M365 agent ID is a deterministic UUID generated from:

- Agent name (e.g., "customer-agent")
- Agent type (e.g., "customer", "admin", "telemetry")
- Azure Tenant ID (from `AZURE_TENANT_ID`)
- Azure Client ID (from `AZURE_CLIENT_ID`)
- Pod name or hostname (for instance uniqueness)

This ensures:

- **Consistency**: Same agent configuration produces the same ID
- **Uniqueness**: Different instances can be distinguished
- **Correlation**: Events can be correlated across services using the UUID

## Configuration Reference

| Environment Variable       | Description                                  | Default              |
| -------------------------- | -------------------------------------------- | -------------------- |
| `FABRIC_TELEMETRY_ENABLED` | Enable/disable telemetry                     | `true`               |
| `FABRIC_SINK_TYPE`         | Sink type (eventhub, onelake, console, file) | `console`            |
| `FABRIC_ENVIRONMENT`       | Environment name                             | `production`         |
| `FABRIC_SERVICE_NAME`      | Service name for event source                | `business-telemetry` |
| `FABRIC_BATCH_SIZE`        | Events per batch                             | `100`                |
| `FABRIC_FLUSH_INTERVAL`    | Seconds between flushes                      | `5.0`                |

### Event Hub Configuration

| Variable                             | Description                      |
| ------------------------------------ | -------------------------------- |
| `FABRIC_EVENT_HUB_CONNECTION_STRING` | Event Hub connection string      |
| `FABRIC_EVENT_HUB_NAME`              | Event Hub name                   |
| `FABRIC_EVENT_HUB_NAMESPACE`         | Namespace (for managed identity) |

### OneLake Configuration

| Variable                       | Description                    |
| ------------------------------ | ------------------------------ |
| `FABRIC_ONELAKE_WORKSPACE_ID`  | Fabric workspace GUID          |
| `FABRIC_ONELAKE_LAKEHOUSE_ID`  | Lakehouse GUID                 |
| `FABRIC_ONELAKE_BASE_PATH`     | Base path in OneLake           |
| `FABRIC_ONELAKE_OUTPUT_FORMAT` | Output format (jsonl, parquet) |

## API Reference

### POST /events

Submit a single business event.

**Request:**

```json
{
  "event_type": "product.viewed",
  "event_source": "customer-agent",
  "session_id": "sess-123",
  "user_id": "user-456",
  "data": {
    "product_id": "prod-789",
    "product_name": "Widget",
    "product_price": 29.99
  }
}
```

**Response:**

```json
{
  "success": true,
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Event accepted"
}
```

### POST /events/batch

Submit multiple events efficiently.

**Request:**

```json
{
  "events": [
    { "event_type": "product.viewed", "data": { "product_id": "123" } },
    { "event_type": "order.placed", "data": { "order_id": "456", "total": 99.99 } }
  ]
}
```

**Response:**

```json
{
  "success": true,
  "events_accepted": 2,
  "events_failed": 0,
  "message": "Processed 2 events"
}
```

### GET /health

Health check endpoint.

### GET /ready

Readiness check endpoint (verifies sink is connected).

### GET /metrics

Prometheus-compatible metrics.

## Microsoft Fabric Integration

### Setting Up Event Hub → Real-Time Analytics

1. Create an Event Hub in Azure
2. Create a Fabric workspace with Real-Time Analytics
3. Create an Eventstream connected to the Event Hub
4. Create a KQL Database as destination
5. Configure the service with Event Hub connection string

### Setting Up OneLake → Lakehouse

1. Create a Fabric Lakehouse
2. Configure service with workspace and lakehouse IDs
3. Events are written as partitioned files:
   ```
   Files/business_telemetry/
   └── product_viewed/
       └── year=2025/
           └── month=01/
               └── day=15/
                   └── 20250115_143022_abc123.jsonl
   ```

### Building the Ontology

Use Fabric's semantic model capabilities:

1. Create tables from the ingested data
2. Define relationships between entities
3. Create measures for business metrics
4. Build Power BI reports

Example KQL queries for Real-Time Analytics:

```kql
// Most viewed products today
BusinessEvents
| where event_type == "product.viewed"
| where event_time > ago(1d)
| summarize views = count() by product_id, product_name
| top 10 by views

// Order conversion funnel
BusinessEvents
| where event_type in ("product.viewed", "order.placed")
| summarize count() by event_type
| render piechart

// AI usage patterns
BusinessEvents
| where event_type startswith "ai."
| summarize total_tokens = sum(tolong(data.total_tokens)) by bin(event_time, 1h)
| render timechart
```

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Local Development with File Sink

```bash
export FABRIC_SINK_TYPE=file
export FABRIC_OUTPUT_DIR=./test_output
python main.py
```

### Docker

```bash
docker build -t business-telemetry:latest .
docker run -p 8080:8080 -e FABRIC_SINK_TYPE=console business-telemetry:latest
```

## Related Documentation

- [DESIGN.md](./DESIGN.md) - Detailed architecture and design decisions
- [Microsoft Fabric Documentation](https://learn.microsoft.com/en-us/fabric/)
- [Azure Event Hubs](https://learn.microsoft.com/en-us/azure/event-hubs/)
- [OneLake](https://learn.microsoft.com/en-us/fabric/onelake/)
