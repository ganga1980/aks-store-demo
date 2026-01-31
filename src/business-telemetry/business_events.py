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
