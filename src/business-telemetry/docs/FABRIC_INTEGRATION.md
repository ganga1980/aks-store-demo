# Microsoft Fabric Integration Guide

This guide provides step-by-step instructions for setting up Microsoft Fabric to ingest and analyze business telemetry data from the AKS Store Demo.

## Prerequisites

- Azure subscription with Microsoft Fabric capacity
- Azure Event Hubs namespace (for real-time streaming)
- Fabric workspace with appropriate permissions

## Architecture Options

### Option 1: Real-Time Analytics (Recommended for Dashboards)

```
Business Telemetry Service → Event Hubs → Eventstream → KQL Database
```

**Best for:**

- Live dashboards
- Real-time KPIs
- Alerting on business metrics
- Operational monitoring

### Option 2: Batch Analytics (Recommended for Reports)

```
Business Telemetry Service → OneLake → Delta Tables → Power BI
```

**Best for:**

- Historical analysis
- Trend reports
- Data science/ML
- Complex queries

### Option 3: Hybrid (Recommended for Production)

```
Business Telemetry Service → Event Hubs ─┬→ Eventstream → KQL Database
                                         └→ Copy to OneLake → Lakehouse
```

## Setup Guide: Real-Time Analytics

### Step 1: Create Azure Event Hub

```bash
# Create Event Hub namespace
az eventhubs namespace create \
  --name aks-store-telemetry-ns \
  --resource-group your-resource-group \
  --location eastus \
  --sku Standard

# Create Event Hub
az eventhubs eventhub create \
  --name business-telemetry \
  --namespace-name aks-store-telemetry-ns \
  --resource-group your-resource-group \
  --partition-count 4

# Get connection string
az eventhubs namespace authorization-rule keys list \
  --namespace-name aks-store-telemetry-ns \
  --resource-group your-resource-group \
  --name RootManageSharedAccessKey \
  --query primaryConnectionString -o tsv
```

### Step 2: Configure Business Telemetry Service

```yaml
# Kubernetes ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: business-telemetry-config
data:
  FABRIC_TELEMETRY_ENABLED: "true"
  FABRIC_SINK_TYPE: "eventhub"
  FABRIC_EVENT_HUB_NAME: "business-telemetry"
  FABRIC_BATCH_SIZE: "100"
  FABRIC_FLUSH_INTERVAL: "5.0"
---
apiVersion: v1
kind: Secret
metadata:
  name: business-telemetry-secrets
type: Opaque
stringData:
  FABRIC_EVENT_HUB_CONNECTION_STRING: "Endpoint=sb://aks-store-telemetry-ns.servicebus.windows.net/;SharedAccessKeyName=..."
```

### Step 3: Create Fabric Eventstream

1. Go to Microsoft Fabric workspace
2. Create new **Eventstream**
3. Add source: **Azure Event Hubs**
4. Configure connection to your Event Hub
5. Add destination: **KQL Database**

### Step 4: Create KQL Database Tables

```kql
// Create table for all business events
.create table BusinessEvents (
    event_id: string,
    event_type: string,
    event_source: string,
    event_time: datetime,
    correlation_id: string,
    session_id: string,
    user_id: string,
    environment: string,
    service_version: string,
    custom_properties: dynamic,
    // Product fields
    product_id: string,
    product_name: string,
    product_category: string,
    product_price: real,
    search_query: string,
    search_results_count: int,
    // Order fields
    order_id: string,
    order_status: string,
    order_total: real,
    item_count: int,
    customer_name: string,
    // AI fields
    ai_assisted: bool,
    ai_model: string,
    ai_tokens_used: int
)

// Create ingestion mapping
.create table BusinessEvents ingestion json mapping 'BusinessEventsMapping' '[
    {"column": "event_id", "path": "$.event_id"},
    {"column": "event_type", "path": "$.event_type"},
    {"column": "event_source", "path": "$.event_source"},
    {"column": "event_time", "path": "$.event_time"},
    {"column": "correlation_id", "path": "$.correlation_id"},
    {"column": "session_id", "path": "$.session_id"},
    {"column": "user_id", "path": "$.user_id"},
    {"column": "environment", "path": "$.environment"},
    {"column": "service_version", "path": "$.service_version"},
    {"column": "custom_properties", "path": "$.custom_properties"},
    {"column": "product_id", "path": "$.product_id"},
    {"column": "product_name", "path": "$.product_name"},
    {"column": "product_category", "path": "$.product_category"},
    {"column": "product_price", "path": "$.product_price"},
    {"column": "search_query", "path": "$.search_query"},
    {"column": "search_results_count", "path": "$.search_results_count"},
    {"column": "order_id", "path": "$.order_id"},
    {"column": "order_status", "path": "$.order_status"},
    {"column": "order_total", "path": "$.order_total"},
    {"column": "item_count", "path": "$.item_count"},
    {"column": "customer_name", "path": "$.customer_name"},
    {"column": "ai_assisted", "path": "$.ai_assisted"},
    {"column": "ai_model", "path": "$.ai_model"},
    {"column": "ai_tokens_used", "path": "$.ai_tokens_used"}
]'
```

## Setup Guide: Batch Analytics (OneLake)

### Step 1: Create Fabric Lakehouse

1. Go to Microsoft Fabric workspace
2. Create new **Lakehouse**
3. Note the workspace ID and lakehouse ID from the URL

### Step 2: Configure Business Telemetry Service

```yaml
# Kubernetes ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: business-telemetry-config
data:
  FABRIC_TELEMETRY_ENABLED: "true"
  FABRIC_SINK_TYPE: "onelake"
  FABRIC_ONELAKE_WORKSPACE_ID: "<workspace-guid>"
  FABRIC_ONELAKE_LAKEHOUSE_ID: "<lakehouse-guid>"
  FABRIC_ONELAKE_BASE_PATH: "Files/business_telemetry"
  FABRIC_ONELAKE_OUTPUT_FORMAT: "parquet" # or "jsonl"
  FABRIC_BATCH_SIZE: "1000"
  FABRIC_FLUSH_INTERVAL: "60.0"
```

### Step 3: Create Delta Tables from Files

In a Fabric Spark notebook:

```python
# Read events from OneLake files
df = spark.read.parquet("Files/business_telemetry/product_viewed/")

# Create Delta table
df.write.format("delta").mode("overwrite").saveAsTable("product_events")

# Or use MERGE for incremental updates
spark.sql("""
    MERGE INTO product_events target
    USING new_events source
    ON target.event_id = source.event_id
    WHEN NOT MATCHED THEN INSERT *
""")
```

### Step 4: Create Shortcut for DirectLake

1. Open Lakehouse
2. Create shortcut to Delta tables
3. Use in Power BI with DirectLake mode

## Sample KQL Queries

### Business KPIs Dashboard

```kql
// Orders per hour
BusinessEvents
| where event_type == "order.placed"
| summarize orders = count(), revenue = sum(order_total) by bin(event_time, 1h)
| render timechart

// Top products by views
BusinessEvents
| where event_type == "product.viewed"
| summarize views = count() by product_id, product_name
| top 10 by views
| render barchart

// Search conversion rate
let searches = BusinessEvents | where event_type == "product.searched" | summarize searches = count();
let orders = BusinessEvents | where event_type == "order.placed" | summarize orders = count();
searches | join orders on 1==1
| project conversion_rate = todouble(orders) / todouble(searches) * 100

// AI assistance usage
BusinessEvents
| where ai_assisted == true
| summarize count() by event_type
| render piechart
```

### Customer Journey Analysis

```kql
// Session funnel analysis
BusinessEvents
| where session_id != ""
| summarize
    sessions = dcount(session_id),
    product_views = countif(event_type == "product.viewed"),
    searches = countif(event_type == "product.searched"),
    orders = countif(event_type == "order.placed")
| project
    sessions,
    view_rate = todouble(product_views) / todouble(sessions) * 100,
    search_rate = todouble(searches) / todouble(sessions) * 100,
    conversion_rate = todouble(orders) / todouble(sessions) * 100

// Average session duration
BusinessEvents
| where event_type in ("customer.session_started", "customer.session_ended")
| extend is_end = event_type == "customer.session_ended"
| summarize
    start_time = minif(event_time, not is_end),
    end_time = maxif(event_time, is_end),
    duration_ms = maxif(toint(custom_properties.session_duration_ms), is_end)
    by session_id
| summarize avg_duration_minutes = avg(duration_ms) / 60000
```

### AI Cost Analysis

```kql
// Token usage by model
BusinessEvents
| where event_type startswith "ai."
| summarize
    total_tokens = sum(ai_tokens_used),
    request_count = count()
    by ai_model
| extend estimated_cost_usd = total_tokens * 0.00002  // Adjust rate

// AI adoption trend
BusinessEvents
| where ai_assisted == true
| summarize ai_assisted_count = count() by bin(event_time, 1d)
| render timechart
```

## Building the Semantic Model (Ontology)

### Entity Definitions

Create a semantic model in Power BI with these entities:

#### Customers

- Session-based identification
- Behavior patterns (views, searches, orders)
- AI interaction preferences

#### Products

- Product catalog attributes
- View/search popularity
- Category hierarchies

#### Orders

- Transaction details
- Line items relationship
- Customer relationship

#### Sessions

- Temporal boundaries
- Interaction sequences
- Conversion outcomes

### Relationships

```
Customer (session_id) ─1:N─► Session
Session (session_id) ─1:N─► Product_View
Session (session_id) ─1:N─► Order
Order (order_id) ─1:N─► Order_Item
Product (product_id) ◄─N:1─ Order_Item
Product (product_id) ◄─N:1─ Product_View
```

### Measures (DAX)

```dax
// Conversion Rate
Conversion Rate =
DIVIDE(
    COUNTROWS(FILTER(BusinessEvents, BusinessEvents[event_type] = "order.placed")),
    COUNTROWS(FILTER(BusinessEvents, BusinessEvents[event_type] = "customer.session_started")),
    0
)

// Average Order Value
AOV =
AVERAGEX(
    FILTER(BusinessEvents, BusinessEvents[event_type] = "order.placed"),
    BusinessEvents[order_total]
)

// AI Assisted Revenue
AI Revenue =
SUMX(
    FILTER(BusinessEvents,
        BusinessEvents[event_type] = "order.placed" &&
        BusinessEvents[ai_assisted] = TRUE()),
    BusinessEvents[order_total]
)
```

## Monitoring & Alerting

### Create Alerts in Fabric

1. Create a scheduled KQL query
2. Set threshold conditions
3. Configure email/Teams notifications

Example alert query:

```kql
// Alert if order rate drops below threshold
BusinessEvents
| where event_type == "order.placed"
| where event_time > ago(1h)
| summarize orders = count()
| where orders < 10  // Alert threshold
```

## Troubleshooting

### Events Not Appearing

1. Check service logs: `kubectl logs -l app=business-telemetry`
2. Verify Event Hub connection string
3. Check Eventstream ingestion status
4. Verify Fabric capacity isn't paused

### High Latency

1. Reduce `FABRIC_FLUSH_INTERVAL` for faster delivery
2. Increase `FABRIC_BATCH_SIZE` for better throughput
3. Scale service replicas horizontally

### Missing Fields

1. Verify event schema in business_events.py
2. Check KQL mapping covers all fields
3. Update table schema if needed

## Best Practices

1. **Partition by event_type** for efficient querying
2. **Use materialized views** for common aggregations
3. **Set retention policies** to manage costs
4. **Enable compression** for OneLake storage
5. **Use workload identity** instead of connection strings in production
