# Business Telemetry Service - High-Level Design

## Executive Summary

The Business Telemetry Service provides a centralized solution for capturing, processing, and ingesting business events from the AKS Store Demo application ecosystem into Microsoft Fabric. This enables advanced analytics, business intelligence, and semantic modeling (ontology) capabilities.

## Design Goals

### Primary Goals

1. **Separation of Concerns**: Clearly separate business telemetry from operational observability (OpenTelemetry)
2. **Microsoft Fabric Native**: Design for optimal integration with Fabric's analytics capabilities
3. **CDM Compatibility**: Use Common Data Model conventions for semantic interoperability
4. **Low Latency**: Support real-time analytics via Event Hubs streaming
5. **High Throughput**: Handle high-volume event ingestion with batching and buffering

### Non-Goals

- Replacing OpenTelemetry for operational observability
- Real-time alerting (use Azure Monitor for that)
- Complex event processing (use Azure Stream Analytics if needed)

## Architecture Overview

### Component Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Source Layer                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  Customer   │  │   Admin     │  │   Store     │  │   Order     │  ...     │
│  │   Agent     │  │   Agent     │  │   Front     │  │  Service    │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│         │SDK             │SDK             │HTTP            │HTTP              │
└─────────┼────────────────┼────────────────┼────────────────┼──────────────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Collection Layer                                    │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                    BusinessTelemetryClient                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │  │
│  │  │   Context    │  │    Event     │  │   Batching   │                  │  │
│  │  │  Management  │  │  Enrichment  │  │   & Buffer   │                  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                         FastAPI HTTP Service                            │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │  │
│  │  │  /events     │  │ /events/batch│  │  /metrics    │                  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                  │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────┬──────────────────────────────────┘
                                            │
                                            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Sink Layer                                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐            │
│  │   EventHubSink   │  │   OneLakeSink    │  │    FileSink      │            │
│  │   (Real-time)    │  │    (Batch)       │  │  (Development)   │            │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────────────┘            │
│           │                     │                                            │
│  ┌────────┴─────────────────────┴────────┐                                   │
│  │            CompositeSink              │  (Multi-destination routing)      │
│  └───────────────────────────────────────┘                                   │
└───────────────────────────────────────────┬──────────────────────────────────┘
                                            │
                                            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Destination Layer                                    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                         Microsoft Fabric                                 │ │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                │ │
│  │  │  Real-Time    │  │   Lakehouse   │  │   Semantic    │                │ │
│  │  │  Analytics    │  │  (Delta Lake) │  │    Model      │                │ │
│  │  │    (KQL)      │  │               │  │  (Ontology)   │                │ │
│  │  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘                │ │
│  │          │                  │                  │                         │ │
│  │          └──────────────────┴──────────────────┘                         │ │
│  │                              │                                           │ │
│  │                    ┌─────────┴─────────┐                                 │ │
│  │                    │     Power BI      │                                 │ │
│  │                    │    (Reports)      │                                 │ │
│  │                    └───────────────────┘                                 │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Data Model

### Event Schema (CDM-Compatible)

All events follow a common base schema with type-specific extensions:

```
BaseEvent
├── event_id: string (UUID)
├── event_type: string (e.g., "product.viewed")
├── event_source: string (e.g., "customer-agent")
├── event_time: ISO8601 timestamp
├── correlation_id: string (optional)
├── session_id: string (optional)
├── user_id: string (optional)
├── environment: string
├── service_version: string
└── custom_properties: object

ProductEvent extends BaseEvent
├── product_id: string
├── product_name: string
├── product_category: string
├── product_price: decimal
├── search_query: string
├── search_results_count: integer
└── ai_assisted: boolean

OrderEvent extends BaseEvent
├── order_id: string
├── order_status: string
├── order_items: array
├── order_total: decimal
├── customer_name: string
└── processing_duration_ms: integer

CustomerEvent extends BaseEvent
├── query_text: string
├── query_intent: string
├── response_time_ms: integer
├── ai_model: string
└── ai_tokens_used: integer

AdminEvent extends BaseEvent
├── admin_user: string
├── product_id: string
├── previous_quantity: integer
├── new_quantity: integer
└── ai_generated_content: string

AIEvent extends BaseEvent
├── model_name: string
├── input_tokens: integer
├── output_tokens: integer
├── estimated_cost_usd: decimal
└── recommendation_accepted: boolean
```

### Entity Relationships (Ontology)

```
┌─────────────┐     places      ┌─────────────┐
│   Customer  │────────────────▶│    Order    │
└─────────────┘                 └──────┬──────┘
       │                               │
       │ views/searches                │ contains
       ▼                               ▼
┌─────────────┐                 ┌─────────────┐
│   Product   │◀────────────────│  OrderItem  │
└─────────────┘                 └─────────────┘
       │
       │ managed_by
       ▼
┌─────────────┐
│    Admin    │
└─────────────┘
```

## Design Decisions

### 1. Async-First Architecture

**Decision**: Use async/await throughout the codebase.

**Rationale**:

- Python AI agents are already async (Microsoft Agent Framework)
- Event Hub and OneLake clients are async
- Better resource utilization under high load

**Trade-off**: Complexity for synchronous integrations (mitigated with sync wrappers)

### 2. Pluggable Sink Architecture

**Decision**: Implement sinks as pluggable components with a common interface.

**Rationale**:

- Easy to add new destinations (e.g., future Fabric features)
- Development/testing without cloud dependencies
- Gradual migration between sink types

**Implementation**:

```python
class BaseSink(ABC):
    async def start(self): ...
    async def stop(self): ...
    async def send(self, event: Dict): ...
    async def send_batch(self, events: List[Dict]): ...
    async def flush(self): ...
```

### 3. Automatic Batching with Time-Based Flush

**Decision**: Buffer events and flush on batch size OR time interval.

**Rationale**:

- Reduces API calls to Event Hub/OneLake
- Prevents unbounded memory growth
- Balances latency vs. efficiency

**Configuration**:

- `batch_size`: Events per batch (default: 100)
- `flush_interval`: Seconds between flushes (default: 5.0)

### 4. HTTP API for Non-Python Services

**Decision**: Provide FastAPI-based HTTP endpoint alongside SDK.

**Rationale**:

- Frontend apps (Vue.js) cannot use Python SDK
- Third-party integrations
- Language-agnostic event submission

### 5. CDM-Compatible Event Schema

**Decision**: Model events following Microsoft Common Data Model conventions.

**Rationale**:

- Native compatibility with Fabric semantic models
- Standard naming conventions (snake_case)
- Rich metadata for analytics

### 6. Separation from Observability

**Decision**: Keep business telemetry completely separate from OpenTelemetry.

**Rationale**:

- Different consumers (business analysts vs. SREs)
- Different retention requirements
- Different access patterns
- Simpler querying for business users

## Data Flow Patterns

### Pattern 1: Real-Time Streaming (Event Hub)

```
Service → BusinessTelemetryClient → Buffer → EventHubSink → Event Hub
                                                              ↓
                                                        Eventstream
                                                              ↓
                                                      KQL Database
                                                              ↓
                                                      Real-Time Dashboard
```

**Use Case**: Live KPIs, operational dashboards, instant alerts

**Latency**: ~1-5 seconds end-to-end

### Pattern 2: Batch Analytics (OneLake)

```
Service → BusinessTelemetryClient → Buffer → OneLakeSink → OneLake Files
                                                              ↓
                                                        Delta Tables
                                                              ↓
                                                      Lakehouse SQL
                                                              ↓
                                                      Power BI Report
```

**Use Case**: Historical analysis, trend reports, ML training data

**Latency**: ~1-60 seconds (configurable)

### Pattern 3: Hybrid (Composite Sink)

```
Service → BusinessTelemetryClient → Buffer → CompositeSink
                                                   │
                                      ┌────────────┼────────────┐
                                      ▼            ▼            ▼
                                 EventHub     OneLake      Console
                                   (RT)       (Batch)       (Dev)
```

**Use Case**: Real-time + historical in single deployment

## Security Considerations

### Authentication

1. **Event Hub**: Connection string or Managed Identity
2. **OneLake**: Azure AD / Managed Identity (DefaultAzureCredential)
3. **HTTP API**: Optional API key authentication

### Data Privacy

- No PII in default event fields
- Customer identifiers use internal IDs, not email/names
- Query text may be summarized/truncated for privacy
- Configurable data masking (future enhancement)

### Network Security

- HTTPS only for HTTP API
- Private endpoints for Event Hub/OneLake (recommended)
- Kubernetes NetworkPolicy for pod-to-pod traffic

## Scalability

### Horizontal Scaling

- HTTP API: Multiple replicas behind load balancer
- SDK: Each service instance has own client
- Sinks: Connection pooling, partition key routing

### Throughput Estimates

| Sink      | Throughput        | Latency |
| --------- | ----------------- | ------- |
| Event Hub | 1M events/sec     | <1s     |
| OneLake   | 100K events/batch | ~5s     |
| Console   | N/A               | Instant |

### Resource Requirements

| Component  | CPU         | Memory     | Notes                |
| ---------- | ----------- | ---------- | -------------------- |
| HTTP API   | 0.5-2 cores | 256-512 MB | Scale with replicas  |
| SDK Client | Minimal     | ~50 MB     | Embedded in services |
| Event Hub  | N/A         | N/A        | Managed service      |
| OneLake    | N/A         | N/A        | Managed service      |

## Monitoring

### Service Metrics (Prometheus)

```
business_telemetry_events_received_total{source, event_type}
business_telemetry_events_sent_total{sink_type}
business_telemetry_events_failed_total{sink_type, error_type}
business_telemetry_buffer_size{sink_type}
business_telemetry_flush_duration_seconds{sink_type}
```

### Business Metrics (Fabric)

Query directly from KQL Database:

```kql
// Events per minute by type
BusinessEvents
| summarize count() by event_type, bin(event_time, 1m)
| render timechart

// Error rate
BusinessEvents
| where event_type endswith ".failed"
| summarize errors = count() by bin(event_time, 5m)
```

## Future Enhancements

1. **Schema Registry**: Centralized schema management with versioning
2. **Data Quality**: Validation rules, anomaly detection
3. **Transformation Pipeline**: Event enrichment, aggregation
4. **Multi-Region**: Geo-distributed ingestion
5. **Replay Capability**: Re-process historical events
6. **Cost Tracking**: Per-event cost attribution

## Related Documents

- [README.md](./README.md) - Quick start guide
- [Microsoft Fabric Documentation](https://learn.microsoft.com/en-us/fabric/)
- [Azure Event Hubs Best Practices](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-best-practices)
- [OneLake Architecture](https://learn.microsoft.com/en-us/fabric/onelake/onelake-overview)
