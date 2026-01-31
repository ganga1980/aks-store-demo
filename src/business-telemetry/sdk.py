"""
Business Telemetry SDK Integration Module

Provides easy integration helpers for AKS Store Demo services to emit
business telemetry events. This module can be imported by customer-agent,
admin-agent, and other Python services.

Usage:
    from business_telemetry_sdk import (
        init_telemetry,
        emit_product_viewed,
        emit_order_placed,
        get_telemetry_client,
    )

    # Initialize at startup
    await init_telemetry()

    # Emit events
    await emit_product_viewed(product_id="123", product_name="Widget")
"""

import asyncio
import logging
import os
import sys
from typing import Optional, List, Dict, Any
from functools import wraps

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from business_events import (
    BaseEvent,
    ProductEvent,
    OrderEvent,
    CustomerEvent,
    AdminEvent,
    AIEvent,
    EventType,
    EventSource,
)
from telemetry_client import BusinessTelemetryClient
from fabric_sinks import ConsoleSink, FileSink, EventHubSink, OneLakeSink

logger = logging.getLogger(__name__)

# Global client instance
_client: Optional[BusinessTelemetryClient] = None


async def init_telemetry(
    sink_type: Optional[str] = None,
    source: Optional[EventSource] = None,
    **kwargs
) -> BusinessTelemetryClient:
    """
    Initialize the global telemetry client.

    Args:
        sink_type: Override sink type (eventhub, onelake, console, file)
        source: Default event source
        **kwargs: Additional client configuration

    Returns:
        Initialized BusinessTelemetryClient
    """
    global _client

    if _client is not None:
        return _client

    _client = BusinessTelemetryClient.from_env()

    if source:
        _client.default_source = source

    await _client.start()
    logger.info("Business telemetry SDK initialized")

    return _client


async def shutdown_telemetry():
    """Shutdown the telemetry client and flush remaining events."""
    global _client

    if _client:
        await _client.stop()
        _client = None
        logger.info("Business telemetry SDK shutdown")


def get_telemetry_client() -> Optional[BusinessTelemetryClient]:
    """Get the global telemetry client instance."""
    return _client


def set_telemetry_context(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None
):
    """Set context for subsequent events."""
    if _client:
        _client.set_context(
            session_id=session_id,
            user_id=user_id,
            correlation_id=correlation_id
        )


def clear_telemetry_context():
    """Clear the current telemetry context."""
    if _client:
        _client.clear_context()


# ========================================
# Convenience Functions for Product Events
# ========================================

async def emit_product_viewed(
    product_id: str,
    product_name: str,
    category: Optional[str] = None,
    price: Optional[float] = None,
    ai_assisted: bool = False,
    **kwargs
) -> bool:
    """
    Emit a product viewed event.

    Call when a user views product details.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_product_viewed(
        product_id=product_id,
        product_name=product_name,
        category=category,
        price=price,
        ai_assisted=ai_assisted,
        **kwargs
    )


async def emit_product_searched(
    query: str,
    results_count: int,
    product_ids: Optional[List[str]] = None,
    ai_assisted: bool = False,
    **kwargs
) -> bool:
    """
    Emit a product searched event.

    Call when a user searches for products.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_product_searched(
        query=query,
        results_count=results_count,
        product_ids=product_ids,
        ai_assisted=ai_assisted,
        **kwargs
    )


async def emit_products_listed(
    product_ids: List[str],
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    **kwargs
) -> bool:
    """
    Emit a products listed event.

    Call when products are displayed to the user.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_products_listed(
        product_ids=product_ids,
        page=page,
        page_size=page_size,
        **kwargs
    )


# ========================================
# Convenience Functions for Order Events
# ========================================

async def emit_order_placed(
    order_id: str,
    items: List[Dict[str, Any]],
    total: float,
    customer_name: Optional[str] = None,
    customer_email: Optional[str] = None,
    ai_assisted: bool = False,
    **kwargs
) -> bool:
    """
    Emit an order placed event.

    Call when an order is successfully placed.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_order_placed(
        order_id=order_id,
        items=items,
        total=total,
        customer_name=customer_name,
        customer_email=customer_email,
        ai_assisted=ai_assisted,
        **kwargs
    )


async def emit_order_status_checked(
    order_id: str,
    status: str,
    **kwargs
) -> bool:
    """
    Emit an order status checked event.

    Call when a user checks their order status.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_order_status_checked(
        order_id=order_id,
        status=status,
        **kwargs
    )


async def emit_order_completed(
    order_id: str,
    processing_duration_ms: Optional[int] = None,
    **kwargs
) -> bool:
    """
    Emit an order completed event.

    Call when an order is fulfilled.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_order_completed(
        order_id=order_id,
        processing_duration_ms=processing_duration_ms,
        **kwargs
    )


# ========================================
# Convenience Functions for Customer Events
# ========================================

async def emit_session_started(
    session_id: str,
    user_id: Optional[str] = None,
    **kwargs
) -> bool:
    """
    Emit a session started event.

    Call when a customer session begins.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_session_started(
        session_id=session_id,
        user_id=user_id,
        **kwargs
    )


async def emit_session_ended(
    session_id: str,
    duration_ms: Optional[int] = None,
    interaction_count: Optional[int] = None,
    user_id: Optional[str] = None,
    **kwargs
) -> bool:
    """
    Emit a session ended event.

    Call when a customer session ends.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_session_ended(
        session_id=session_id,
        duration_ms=duration_ms,
        interaction_count=interaction_count,
        user_id=user_id,
        **kwargs
    )


async def emit_customer_query(
    query_text: str,
    response_time_ms: Optional[int] = None,
    ai_model: Optional[str] = None,
    ai_tokens: Optional[int] = None,
    intent: Optional[str] = None,
    **kwargs
) -> bool:
    """
    Emit a customer query event.

    Call when a customer asks a question.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_customer_query(
        query_text=query_text,
        response_time_ms=response_time_ms,
        ai_model=ai_model,
        ai_tokens=ai_tokens,
        intent=intent,
        **kwargs
    )


# ========================================
# Convenience Functions for Admin Events
# ========================================

async def emit_inventory_updated(
    product_id: str,
    product_name: str,
    previous_qty: int,
    new_qty: int,
    admin_user: Optional[str] = None,
    reason: Optional[str] = None,
    **kwargs
) -> bool:
    """
    Emit an inventory updated event.

    Call when inventory is changed.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_inventory_updated(
        product_id=product_id,
        product_name=product_name,
        previous_qty=previous_qty,
        new_qty=new_qty,
        admin_user=admin_user,
        reason=reason,
        **kwargs
    )


async def emit_product_created(
    product_id: str,
    product_name: str,
    admin_user: Optional[str] = None,
    ai_assisted: bool = False,
    ai_content: Optional[str] = None,
    **kwargs
) -> bool:
    """
    Emit a product created event.

    Call when a new product is created.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_product_created(
        product_id=product_id,
        product_name=product_name,
        admin_user=admin_user,
        ai_assisted=ai_assisted,
        ai_content=ai_content,
        **kwargs
    )


async def emit_product_updated(
    product_id: str,
    product_name: str,
    changes: Optional[Dict[str, Any]] = None,
    admin_user: Optional[str] = None,
    ai_assisted: bool = False,
    **kwargs
) -> bool:
    """
    Emit a product updated event.

    Call when a product is modified.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_product_updated(
        product_id=product_id,
        product_name=product_name,
        changes=changes,
        admin_user=admin_user,
        ai_assisted=ai_assisted,
        **kwargs
    )


# ========================================
# Convenience Functions for AI Events
# ========================================

async def emit_ai_recommendation(
    model_name: str,
    request_type: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    recommendation_accepted: Optional[bool] = None,
    latency_ms: Optional[int] = None,
    **kwargs
) -> bool:
    """
    Emit an AI recommendation event.

    Call when AI provides a recommendation.
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_ai_recommendation(
        model_name=model_name,
        request_type=request_type,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        recommendation_accepted=recommendation_accepted,
        latency_ms=latency_ms,
        **kwargs
    )


async def emit_ai_content_generated(
    model_name: str,
    content_type: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    content_used: Optional[bool] = None,
    latency_ms: Optional[int] = None,
    **kwargs
) -> bool:
    """
    Emit an AI content generation event.

    Call when AI generates content (descriptions, etc.).
    """
    if not _client:
        logger.warning("Telemetry client not initialized")
        return False

    return await _client.emit_ai_content_generated(
        model_name=model_name,
        content_type=content_type,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        content_used=content_used,
        latency_ms=latency_ms,
        **kwargs
    )


# ========================================
# Decorator for automatic event emission
# ========================================

def track_event(event_type: str, **event_kwargs):
    """
    Decorator to automatically emit events on function completion.

    Usage:
        @track_event("product.viewed", ai_assisted=True)
        async def get_product(product_id: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            if _client:
                event = BaseEvent(
                    event_type=event_type,
                    custom_properties={
                        "function": func.__name__,
                        **event_kwargs
                    }
                )
                await _client.emit(event)

            return result
        return wrapper
    return decorator
