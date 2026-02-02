"""
Business Event Models

CDM (Common Data Model) compatible event definitions for Microsoft Fabric Ontology.
These events represent business transactions and customer interactions that flow
through the AKS Store Demo application.

Event Categories:
- Product Events: Views, searches, listings
- Order Events: Placements, status checks, completions
- Customer Events: Sessions, queries, interactions
- Admin Events: Inventory, product management
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid
import json


class EventType(str, Enum):
    """Business event type enumeration."""

    # Product Events
    PRODUCT_VIEWED = "product.viewed"
    PRODUCT_SEARCHED = "product.searched"
    PRODUCT_LISTED = "product.listed"

    # Order Events
    ORDER_PLACED = "order.placed"
    ORDER_STATUS_CHECKED = "order.status_checked"
    ORDER_COMPLETED = "order.completed"
    ORDER_FAILED = "order.failed"

    # Customer Events
    SESSION_STARTED = "customer.session_started"
    SESSION_ENDED = "customer.session_ended"
    CUSTOMER_QUERY = "customer.query"
    CUSTOMER_FEEDBACK = "customer.feedback"

    # Admin Events
    INVENTORY_UPDATED = "admin.inventory_updated"
    PRODUCT_CREATED = "admin.product_created"
    PRODUCT_UPDATED = "admin.product_updated"
    PRODUCT_DELETED = "admin.product_deleted"

    # AI Events
    AI_RECOMMENDATION = "ai.recommendation"
    AI_DESCRIPTION_GENERATED = "ai.description_generated"

    # Agent Session Events (Fabric-Pulse Ontology)
    # These events track agent session lifecycle for business correlation
    AGENT_SESSION_STARTED = "agent.session_started"
    AGENT_SESSION_ENDED = "agent.session_ended"
    AGENT_TASK_STARTED = "agent.task_started"
    AGENT_TASK_COMPLETED = "agent.task_completed"
    AGENT_MODEL_INVOCATION = "agent.model_invocation"
    AGENT_TOOL_CALL = "agent.tool_call"


class EventSource(str, Enum):
    """Source application/service enumeration."""
    CUSTOMER_AGENT = "customer-agent"
    ADMIN_AGENT = "admin-agent"
    STORE_FRONT = "store-front"
    STORE_ADMIN = "store-admin"
    ORDER_SERVICE = "order-service"
    PRODUCT_SERVICE = "product-service"
    MAKELINE_SERVICE = "makeline-service"


@dataclass
class BaseEvent:
    """
    Base event class with common fields for all business events.

    Follows Microsoft CDM (Common Data Model) conventions for
    compatibility with Fabric Ontology.
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    event_source: str = ""
    event_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Correlation fields for distributed tracing
    correlation_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None

    # Environment context
    environment: str = "production"
    service_version: str = "1.0.0"

    # Custom properties for extensibility
    custom_properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        data = asdict(self)
        # Remove None values for cleaner output
        return {k: v for k, v in data.items() if v is not None}

    def to_json(self) -> str:
        """Serialize event to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseEvent":
        """Create event from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ProductEvent(BaseEvent):
    """
    Product-related business event.

    Captures interactions with products including views, searches,
    and catalog browsing activities.
    """

    # Product identification
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    product_category: Optional[str] = None
    product_price: Optional[float] = None

    # Search context
    search_query: Optional[str] = None
    search_results_count: Optional[int] = None
    search_position: Optional[int] = None  # Position in search results

    # Listing context
    products_listed: Optional[List[str]] = None  # List of product IDs
    listing_page: Optional[int] = None
    listing_page_size: Optional[int] = None

    # AI context
    ai_assisted: bool = False
    ai_model: Optional[str] = None

    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.PRODUCT_VIEWED.value


@dataclass
class OrderEvent(BaseEvent):
    """
    Order-related business event.

    Captures the complete order lifecycle from placement through
    completion or failure.
    """

    # Order identification
    order_id: Optional[str] = None
    order_status: Optional[str] = None

    # Order details
    order_items: Optional[List[Dict[str, Any]]] = None
    order_total: Optional[float] = None
    item_count: Optional[int] = None

    # Customer context
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None

    # Timing
    order_placed_at: Optional[str] = None
    order_completed_at: Optional[str] = None
    processing_duration_ms: Optional[int] = None

    # Fulfillment
    store_id: Optional[str] = None
    fulfillment_method: Optional[str] = None  # pickup, delivery

    # AI context
    ai_assisted: bool = False

    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.ORDER_PLACED.value


@dataclass
class CustomerEvent(BaseEvent):
    """
    Customer interaction event.

    Captures customer sessions, queries, and general interactions
    with the store applications.
    """

    # Session context
    session_duration_ms: Optional[int] = None
    interaction_count: Optional[int] = None

    # Query context
    query_text: Optional[str] = None
    query_intent: Optional[str] = None  # Detected intent
    query_sentiment: Optional[str] = None  # positive, negative, neutral

    # Response context
    response_text: Optional[str] = None
    response_time_ms: Optional[int] = None
    response_helpful: Optional[bool] = None

    # AI context
    ai_model: Optional[str] = None
    ai_tokens_used: Optional[int] = None

    # Feedback
    feedback_rating: Optional[int] = None  # 1-5 scale
    feedback_text: Optional[str] = None

    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.CUSTOMER_QUERY.value


@dataclass
class AdminEvent(BaseEvent):
    """
    Administrative action event.

    Captures inventory management, product updates, and other
    administrative operations performed through admin interfaces.
    """

    # Admin context
    admin_user: Optional[str] = None
    action_type: Optional[str] = None

    # Product context
    product_id: Optional[str] = None
    product_name: Optional[str] = None

    # Inventory context
    previous_quantity: Optional[int] = None
    new_quantity: Optional[int] = None
    quantity_change: Optional[int] = None

    # Price context
    previous_price: Optional[float] = None
    new_price: Optional[float] = None

    # Metadata
    change_reason: Optional[str] = None
    change_description: Optional[str] = None

    # AI context
    ai_assisted: bool = False
    ai_generated_content: Optional[str] = None

    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.INVENTORY_UPDATED.value


@dataclass
class AIEvent(BaseEvent):
    """
    AI-specific business event.

    Captures AI-assisted operations such as recommendations,
    content generation, and intelligent search.
    """

    # AI model context
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    model_provider: str = "azure-openai"

    # Token usage (business impact, not observability)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None

    # Request context
    request_type: Optional[str] = None  # recommendation, generation, analysis
    request_prompt_summary: Optional[str] = None  # Summarized, not full prompt

    # Response context
    response_quality_score: Optional[float] = None  # 0-1 if available
    response_latency_ms: Optional[int] = None

    # Business outcome
    recommendation_accepted: Optional[bool] = None
    content_used: Optional[bool] = None

    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.AI_RECOMMENDATION.value


@dataclass
class AgentSessionEvent(BaseEvent):
    """
    Agent Session business event following Fabric-Pulse Ontology.

    Foreign Key Conventions (per Entities.md):
    - AgentId: {ClusterId}/{Namespace}/agents/{AgentName}
    - AgentSessionId: {AgentId}/sessions/{SessionId}
    - WorkloadId: {ClusterId}/{Namespace}/{ControllerName}

    This event tracks agent session lifecycle for business correlation
    with infrastructure and business entities.

    See: https://github.com/ganga1980/Fabric-Pulse/blob/main/ontology/Entities.md
    """

    # === MANDATORY ENTITY FOREIGN KEYS (Fabric-Pulse format) ===
    # AgentId format: {ClusterId}/{Namespace}/agents/{AgentName}
    agent_id: Optional[str] = None
    # AgentSessionId format: {AgentId}/sessions/{SessionId}
    agent_session_id: Optional[str] = None
    # WorkloadId format: {ClusterId}/{Namespace}/{ControllerName}
    workload_id: Optional[str] = None

    # === AGENT IDENTIFICATION ===
    agent_name: Optional[str] = None
    agent_description: Optional[str] = None

    # === INFRASTRUCTURE CONTEXT (for correlation) ===
    cluster_id: Optional[str] = None  # cloud.resource_id
    namespace: Optional[str] = None  # k8s.namespace.name
    pod_name: Optional[str] = None  # k8s.pod.name
    pod_id: Optional[str] = None  # {ClusterId}/{Namespace}/{PodName}
    node_name: Optional[str] = None  # k8s.node.name
    replicaset_name: Optional[str] = None  # k8s.replicaset.name
    deployment_name: Optional[str] = None  # k8s.deployment.name

    # === SESSION LIFECYCLE ===
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    status: Optional[str] = None  # Active, Completed, Abandoned, Error, Timeout

    # === BUSINESS CONTEXT ===
    customer_id: Optional[str] = None  # For customer-agent sessions
    channel: Optional[str] = None  # CustomerAgent, AdminAgent, Web

    # === INTERACTION METRICS ===
    tool_call_count: Optional[int] = None
    model_invocation_count: Optional[int] = None
    total_input_tokens: Optional[int] = None
    total_output_tokens: Optional[int] = None
    message_count: Optional[int] = None

    # === BUSINESS OUTCOMES ===
    orders_placed: Optional[int] = None
    revenue_generated: Optional[float] = None
    products_viewed: Optional[int] = None
    products_searched: Optional[int] = None
    inventory_updates: Optional[int] = None

    # === ERROR TRACKING ===
    error_occurred: bool = False
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    # === TRACING ===
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.AGENT_SESSION_STARTED.value

    @staticmethod
    def build_agent_id(cluster_id: str, namespace: str, agent_name: str) -> str:
        """
        Build AgentId following Fabric-Pulse convention.

        Format: {ClusterId}/{Namespace}/agents/{AgentName}
        Example: /subscriptions/.../aks-cluster/default/agents/customer-agent
        """
        return f"{cluster_id}/{namespace}/agents/{agent_name}"

    @staticmethod
    def build_agent_session_id(agent_id: str, session_id: str) -> str:
        """
        Build AgentSessionId following Fabric-Pulse convention.

        Format: {AgentId}/sessions/{SessionId}
        Example: .../agents/customer-agent/sessions/abc-123
        """
        return f"{agent_id}/sessions/{session_id}"

    @staticmethod
    def build_workload_id(cluster_id: str, namespace: str, controller_name: str) -> str:
        """
        Build WorkloadId following Fabric-Pulse convention.

        Format: {ClusterId}/{Namespace}/{ControllerName}
        Example: /subscriptions/.../aks-cluster/default/customer-agent
        """
        return f"{cluster_id}/{namespace}/{controller_name}"

    @staticmethod
    def build_pod_id(cluster_id: str, namespace: str, pod_name: str) -> str:
        """
        Build PodId following Fabric-Pulse convention.

        Format: {ClusterId}/{Namespace}/{PodName}
        """
        return f"{cluster_id}/{namespace}/{pod_name}"


@dataclass
class AgentTaskEvent(BaseEvent):
    """
    Agent Task business event following Fabric-Pulse Ontology.

    Tracks discrete tasks executed by agents (queries, tool executions, etc.)
    for correlation with model invocations and MCP tool calls.
    """

    # === ENTITY FOREIGN KEYS ===
    agent_id: Optional[str] = None
    agent_session_id: Optional[str] = None
    task_id: Optional[str] = None

    # === TASK DETAILS ===
    task_type: Optional[str] = None  # Query, ToolExecution, Analysis, etc.
    task_description: Optional[str] = None
    status: Optional[str] = None  # Pending, InProgress, Completed, Failed

    # === TIMING ===
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None

    # === TOKEN USAGE ===
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    # === INVOCATION COUNTS ===
    model_invocation_count: Optional[int] = None
    tool_call_count: Optional[int] = None

    # === ERROR INFO ===
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    # === TRACING ===
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.AGENT_TASK_STARTED.value


@dataclass
class AgentModelInvocationEvent(BaseEvent):
    """
    Agent Model Invocation business event following Fabric-Pulse Ontology.

    Tracks LLM inference calls for business impact analysis (cost, latency, tokens).
    """

    # === ENTITY FOREIGN KEYS ===
    invocation_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_session_id: Optional[str] = None
    task_id: Optional[str] = None

    # === MODEL INFO ===
    model_name: Optional[str] = None
    model_provider: Optional[str] = None
    operation_type: Optional[str] = None  # chat, text_completion, embeddings

    # === TOKEN USAGE ===
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    # === PERFORMANCE ===
    duration_ms: Optional[int] = None
    time_to_first_token_ms: Optional[int] = None

    # === STATUS ===
    status: Optional[str] = None  # Success, RateLimited, Error, Timeout
    error_type: Optional[str] = None
    result_code: Optional[str] = None

    # === COST ===
    estimated_cost_usd: Optional[float] = None

    # === TRACING ===
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.AGENT_MODEL_INVOCATION.value


@dataclass
class AgentToolCallEvent(BaseEvent):
    """
    Agent MCP Tool Call business event following Fabric-Pulse Ontology.

    Tracks tool executions for business impact analysis.
    """

    # === ENTITY FOREIGN KEYS ===
    tool_call_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_session_id: Optional[str] = None
    task_id: Optional[str] = None

    # === TOOL INFO ===
    tool_name: Optional[str] = None
    tool_server: Optional[str] = None
    tool_category: Optional[str] = None  # ProductService, OrderService, etc.

    # === PERFORMANCE ===
    duration_ms: Optional[int] = None
    status: Optional[str] = None  # Success, Failed, Timeout

    # === BUSINESS IMPACT ===
    # What entity was affected
    affected_entity_type: Optional[str] = None  # Product, Order, Inventory
    affected_entity_id: Optional[str] = None

    # === ERROR INFO ===
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    # === TRACING ===
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_type:
            self.event_type = EventType.AGENT_TOOL_CALL.value


# Event factory functions for convenience
def create_product_viewed_event(
    product_id: str,
    product_name: str,
    source: EventSource,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    **kwargs
) -> ProductEvent:
    """Create a product viewed event."""
    return ProductEvent(
        event_type=EventType.PRODUCT_VIEWED.value,
        event_source=source.value,
        product_id=product_id,
        product_name=product_name,
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
        **kwargs
    )


def create_product_searched_event(
    search_query: str,
    results_count: int,
    source: EventSource,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    product_ids: Optional[List[str]] = None,
    **kwargs
) -> ProductEvent:
    """Create a product searched event."""
    return ProductEvent(
        event_type=EventType.PRODUCT_SEARCHED.value,
        event_source=source.value,
        search_query=search_query,
        search_results_count=results_count,
        products_listed=product_ids,
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
        **kwargs
    )


def create_order_placed_event(
    order_id: str,
    items: List[Dict[str, Any]],
    total: float,
    source: EventSource,
    customer_name: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    **kwargs
) -> OrderEvent:
    """Create an order placed event."""
    return OrderEvent(
        event_type=EventType.ORDER_PLACED.value,
        event_source=source.value,
        order_id=order_id,
        order_items=items,
        order_total=total,
        item_count=len(items),
        customer_name=customer_name,
        order_placed_at=datetime.now(timezone.utc).isoformat(),
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
        **kwargs
    )


def create_session_started_event(
    session_id: str,
    source: EventSource,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    **kwargs
) -> CustomerEvent:
    """Create a session started event."""
    return CustomerEvent(
        event_type=EventType.SESSION_STARTED.value,
        event_source=source.value,
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
        **kwargs
    )


def create_customer_query_event(
    query_text: str,
    source: EventSource,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    response_time_ms: Optional[int] = None,
    ai_model: Optional[str] = None,
    ai_tokens: Optional[int] = None,
    **kwargs
) -> CustomerEvent:
    """Create a customer query event."""
    return CustomerEvent(
        event_type=EventType.CUSTOMER_QUERY.value,
        event_source=source.value,
        query_text=query_text,
        session_id=session_id,
        user_id=user_id,
        correlation_id=correlation_id,
        response_time_ms=response_time_ms,
        ai_model=ai_model,
        ai_tokens_used=ai_tokens,
        **kwargs
    )


def create_inventory_updated_event(
    product_id: str,
    product_name: str,
    previous_qty: int,
    new_qty: int,
    source: EventSource,
    admin_user: Optional[str] = None,
    session_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    **kwargs
) -> AdminEvent:
    """Create an inventory updated event."""
    return AdminEvent(
        event_type=EventType.INVENTORY_UPDATED.value,
        event_source=source.value,
        product_id=product_id,
        product_name=product_name,
        previous_quantity=previous_qty,
        new_quantity=new_qty,
        quantity_change=new_qty - previous_qty,
        admin_user=admin_user,
        session_id=session_id,
        correlation_id=correlation_id,
        **kwargs
    )


# ========================================
# Agent Session Event Factory Functions
# (Fabric-Pulse Ontology format)
# ========================================

def create_agent_session_started_event(
    agent_name: str,
    session_id: str,
    source: EventSource,
    cluster_id: Optional[str] = None,
    namespace: Optional[str] = None,
    pod_name: Optional[str] = None,
    node_name: Optional[str] = None,
    replicaset_name: Optional[str] = None,
    deployment_name: Optional[str] = None,
    customer_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    **kwargs
) -> AgentSessionEvent:
    """
    Create an agent session started event with proper Fabric-Pulse foreign keys.

    Args:
        agent_name: Human-readable agent name (e.g., "customer-agent")
        session_id: Unique session identifier
        source: Event source
        cluster_id: Kubernetes cluster resource ID (cloud.resource_id)
        namespace: Kubernetes namespace
        pod_name: Pod name
        node_name: Node name
        replicaset_name: ReplicaSet name
        deployment_name: Deployment name
        customer_id: Customer identifier (for customer-agent)
        trace_id: OpenTelemetry trace ID

    Returns:
        AgentSessionEvent with properly formatted foreign keys
    """
    # Build entity foreign keys
    agent_id = None
    agent_session_id = None
    workload_id = None
    pod_id = None

    if cluster_id and namespace:
        agent_id = AgentSessionEvent.build_agent_id(cluster_id, namespace, agent_name)
        agent_session_id = AgentSessionEvent.build_agent_session_id(agent_id, session_id)

        # Derive controller name for WorkloadId
        controller_name = replicaset_name or deployment_name
        if not controller_name and pod_name:
            # Extract from pod name: deployment-replicaset-hash-pod-hash
            parts = pod_name.rsplit("-", 1)
            if len(parts) >= 2:
                controller_name = parts[0]  # replicaset name
        if controller_name:
            workload_id = AgentSessionEvent.build_workload_id(cluster_id, namespace, controller_name)

        if pod_name:
            pod_id = AgentSessionEvent.build_pod_id(cluster_id, namespace, pod_name)

    return AgentSessionEvent(
        event_type=EventType.AGENT_SESSION_STARTED.value,
        event_source=source.value,
        session_id=session_id,
        # Foreign keys
        agent_id=agent_id,
        agent_session_id=agent_session_id,
        workload_id=workload_id,
        # Agent info
        agent_name=agent_name,
        # Infrastructure context
        cluster_id=cluster_id,
        namespace=namespace,
        pod_name=pod_name,
        pod_id=pod_id,
        node_name=node_name,
        replicaset_name=replicaset_name,
        deployment_name=deployment_name,
        # Business context
        customer_id=customer_id,
        channel=source.value,
        # Lifecycle
        start_time=datetime.now(timezone.utc).isoformat(),
        status="Active",
        # Tracing
        trace_id=trace_id,
        **kwargs
    )


def create_agent_session_ended_event(
    agent_name: str,
    session_id: str,
    source: EventSource,
    duration_ms: int,
    status: str = "Completed",
    cluster_id: Optional[str] = None,
    namespace: Optional[str] = None,
    pod_name: Optional[str] = None,
    # Business outcomes
    tool_call_count: Optional[int] = None,
    model_invocation_count: Optional[int] = None,
    total_input_tokens: Optional[int] = None,
    total_output_tokens: Optional[int] = None,
    message_count: Optional[int] = None,
    orders_placed: Optional[int] = None,
    revenue_generated: Optional[float] = None,
    products_viewed: Optional[int] = None,
    inventory_updates: Optional[int] = None,
    # Error info
    error_occurred: bool = False,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    trace_id: Optional[str] = None,
    **kwargs
) -> AgentSessionEvent:
    """
    Create an agent session ended event with business outcomes.

    This event captures the complete session lifecycle including
    business impact metrics (orders, revenue, etc.) for correlation.
    """
    # Build entity foreign keys
    agent_id = None
    agent_session_id = None

    if cluster_id and namespace:
        agent_id = AgentSessionEvent.build_agent_id(cluster_id, namespace, agent_name)
        agent_session_id = AgentSessionEvent.build_agent_session_id(agent_id, session_id)

    return AgentSessionEvent(
        event_type=EventType.AGENT_SESSION_ENDED.value,
        event_source=source.value,
        session_id=session_id,
        # Foreign keys
        agent_id=agent_id,
        agent_session_id=agent_session_id,
        # Agent info
        agent_name=agent_name,
        # Infrastructure context
        cluster_id=cluster_id,
        namespace=namespace,
        pod_name=pod_name,
        # Lifecycle
        end_time=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
        status=status,
        # Interaction metrics
        tool_call_count=tool_call_count,
        model_invocation_count=model_invocation_count,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        message_count=message_count,
        # Business outcomes
        orders_placed=orders_placed,
        revenue_generated=revenue_generated,
        products_viewed=products_viewed,
        inventory_updates=inventory_updates,
        # Error info
        error_occurred=error_occurred,
        error_type=error_type,
        error_message=error_message,
        # Tracing
        trace_id=trace_id,
        **kwargs
    )


def create_agent_tool_call_event(
    tool_name: str,
    agent_name: str,
    session_id: str,
    source: EventSource,
    duration_ms: int,
    status: str = "Success",
    cluster_id: Optional[str] = None,
    namespace: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    tool_server: Optional[str] = None,
    tool_category: Optional[str] = None,
    affected_entity_type: Optional[str] = None,
    affected_entity_id: Optional[str] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    **kwargs
) -> AgentToolCallEvent:
    """
    Create an agent tool call event for business impact tracking.
    """
    # Build entity foreign keys
    agent_id = None
    agent_session_id = None

    if cluster_id and namespace:
        agent_id = AgentSessionEvent.build_agent_id(cluster_id, namespace, agent_name)
        agent_session_id = AgentSessionEvent.build_agent_session_id(agent_id, session_id)

    return AgentToolCallEvent(
        event_type=EventType.AGENT_TOOL_CALL.value,
        event_source=source.value,
        session_id=session_id,
        # Foreign keys
        tool_call_id=tool_call_id or str(uuid.uuid4()),
        agent_id=agent_id,
        agent_session_id=agent_session_id,
        # Tool info
        tool_name=tool_name,
        tool_server=tool_server,
        tool_category=tool_category,
        # Performance
        duration_ms=duration_ms,
        status=status,
        # Business impact
        affected_entity_type=affected_entity_type,
        affected_entity_id=affected_entity_id,
        # Error info
        error_type=error_type,
        error_message=error_message,
        # Tracing
        trace_id=trace_id,
        span_id=span_id,
        **kwargs
    )
