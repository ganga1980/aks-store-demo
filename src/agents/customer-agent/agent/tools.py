"""
Function tools for the Customer Agent using Microsoft Agent Framework.

These tools enable the AI agent to interact with the AKS Store Demo backend services.
Each tool is instrumented with OpenTelemetry Gen AI semantic conventions
for the execute_tool operation.

Microsoft Agent Framework uses Annotated types with Pydantic Field for tool parameters.
See: https://github.com/microsoft/agent-framework
See: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/#execute-tool-span
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Annotated, List, Optional

from pydantic import Field

from config import get_settings
from services import OrderServiceClient, ProductServiceClient
from telemetry import (
    GenAIMetricsData,
    GenAIOperationName,
    GenAIProviderName,
    get_gen_ai_telemetry,
    get_m365_agent_id_provider,
)

# Add business-telemetry SDK to path
# In container: /app/business_telemetry_sdk (copied via Dockerfile)
# In development: ../../../business-telemetry (relative path)
_business_telemetry_paths = [
    "/app/business_telemetry_sdk",  # Container path
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "business-telemetry")),  # Dev path
]
for _path in _business_telemetry_paths:
    if os.path.exists(_path):
        sys.path.insert(0, _path)
        break

try:
    from sdk import (
        init_telemetry as init_business_telemetry,
        shutdown_telemetry as shutdown_business_telemetry,
        get_telemetry_client as get_business_telemetry_client,
        set_telemetry_context,
        emit_product_viewed,
        emit_product_searched,
        emit_products_listed,
        emit_order_placed,
        emit_order_status_checked,
    )
    BUSINESS_TELEMETRY_AVAILABLE = True
except ImportError as e:
    BUSINESS_TELEMETRY_AVAILABLE = False
    logging.warning(f"Business telemetry SDK not available: {e}")

logger = logging.getLogger(__name__)

# Global service clients (initialized lazily)
_product_client: ProductServiceClient | None = None
_order_client: OrderServiceClient | None = None

# Get Gen AI telemetry instance
_gen_ai_telemetry = None

# M365 Agent ID provider for unique agent identification
_m365_agent_provider = None

# Business telemetry context
_business_context = {
    "session_id": None,
    "user_id": None,
    "correlation_id": None,
}

# Customer context for the current session
_customer_context = {
    "customer_id": None,
    "customer_name": None,
    "customer_email": None,
}

# Channel identifier for customer-agent
CUSTOMER_AGENT_CHANNEL = "CustomerAgent"


def _get_telemetry():
    """Get or create Gen AI telemetry instance."""
    global _gen_ai_telemetry
    if _gen_ai_telemetry is None:
        _gen_ai_telemetry = get_gen_ai_telemetry()
    return _gen_ai_telemetry


def _get_m365_agent_provider():
    """Get or create M365 Agent ID provider instance."""
    global _m365_agent_provider
    if _m365_agent_provider is None:
        settings = get_settings()
        _m365_agent_provider = get_m365_agent_id_provider(
            agent_name=settings.agent_name,
            agent_type="customer",
            channel_id="webchat",
            service_url=settings.azure_ai_project_endpoint,
        )
    return _m365_agent_provider


def _get_agent_id() -> str:
    """Get the M365 unique agent ID for telemetry."""
    return _get_m365_agent_provider().agent_id


def _get_agent_name() -> str:
    """Get the agent name for telemetry."""
    settings = get_settings()
    return settings.agent_name


def set_business_context(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """Set context for business telemetry events."""
    if session_id:
        _business_context["session_id"] = session_id
    if user_id:
        _business_context["user_id"] = user_id
    if correlation_id:
        _business_context["correlation_id"] = correlation_id

    # Also set on the SDK client if available
    if BUSINESS_TELEMETRY_AVAILABLE:
        set_telemetry_context(
            session_id=session_id,
            user_id=user_id,
            correlation_id=correlation_id,
        )


def set_customer_context(
    customer_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    customer_email: Optional[str] = None,
) -> None:
    """Set customer context for business telemetry events (per session)."""
    if customer_id:
        _customer_context["customer_id"] = customer_id
    if customer_name:
        _customer_context["customer_name"] = customer_name
    if customer_email:
        _customer_context["customer_email"] = customer_email


def get_customer_context() -> dict:
    """Get current customer context."""
    return _customer_context.copy()


def _derive_product_category(product_name: str) -> str:
    """
    Derive product category from product name for pet store products.

    Args:
        product_name: Product name (lowercase)

    Returns:
        Category string (Food, Toys, Accessories, Health, Housing, Other)
    """
    product_name = product_name.lower()

    # Food category keywords
    food_keywords = ["food", "treat", "kibble", "feed", "snack", "chew", "biscuit", "meal"]
    if any(kw in product_name for kw in food_keywords):
        return "Food"

    # Toys category keywords
    toy_keywords = ["toy", "ball", "frisbee", "rope", "squeaky", "plush", "interactive", "puzzle"]
    if any(kw in product_name for kw in toy_keywords):
        return "Toys"

    # Health category keywords
    health_keywords = ["vitamin", "supplement", "medicine", "flea", "tick", "shampoo", "grooming", "brush"]
    if any(kw in product_name for kw in health_keywords):
        return "Health"

    # Housing category keywords
    housing_keywords = ["bed", "crate", "kennel", "cage", "aquarium", "tank", "house", "carrier"]
    if any(kw in product_name for kw in housing_keywords):
        return "Housing"

    # Accessories category keywords
    accessory_keywords = ["collar", "leash", "harness", "bowl", "feeder", "tag", "coat", "sweater"]
    if any(kw in product_name for kw in accessory_keywords):
        return "Accessories"

    return "Other"


def _emit_business_event_sync(coro):
    """Helper to run async business telemetry emission synchronously."""
    if not BUSINESS_TELEMETRY_AVAILABLE:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule as task, don't block
            asyncio.ensure_future(coro)
        else:
            asyncio.run(coro)
    except Exception as e:
        logger.debug(f"Business telemetry emission skipped: {e}")


def _get_product_client() -> ProductServiceClient:
    """Get or create the product service client."""
    global _product_client
    if _product_client is None:
        settings = get_settings()
        _product_client = ProductServiceClient(base_url=settings.product_service_url)
    return _product_client


def _get_order_client() -> OrderServiceClient:
    """Get or create the order service client."""
    global _order_client
    if _order_client is None:
        settings = get_settings()
        _order_client = OrderServiceClient(
            order_service_url=settings.order_service_url,
            makeline_service_url=settings.makeline_service_url,
        )
    return _order_client


# =============================================================================
# Function Tools for Microsoft Agent Framework
# =============================================================================
# Microsoft Agent Framework uses plain functions with Annotated types for parameters.
# The framework automatically converts these to tool definitions.
# =============================================================================


def get_products() -> str:
    """
    Get all available products from the pet store catalog.

    Returns a JSON string containing a list of all products with their
    details including name, description, price, and availability.
    """
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="get_products",
        tool_description="Get all available products from the pet store catalog",
        conversation_id=_business_context.get("session_id"),
        agent_id=_get_agent_id(),
        agent_name=_get_agent_name(),
    ) as span:
        try:
            import asyncio
            client = _get_product_client()

            # Run async code synchronously (Microsoft Agent Framework calls sync functions)
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            products = asyncio.run(client.get_all_products())

            if not products:
                result = json.dumps({
                    "success": True,
                    "products": [],
                    "message": "No products currently available in the catalog."
                })
                telemetry.set_tool_call_attributes(span, result=result)
                return result

            formatted_products = [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "description": p.get("description", ""),
                    "price": p.get("price"),
                    "image": p.get("image", ""),
                }
                for p in products
            ]

            result = json.dumps({
                "success": True,
                "products": formatted_products,
                "count": len(formatted_products),
                "message": f"Found {len(formatted_products)} products in the catalog."
            })

            telemetry.set_tool_call_attributes(span, result=result)
            duration = time.perf_counter() - start_time
            telemetry.record_operation_duration(
                GenAIMetricsData(
                    operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                    provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                    duration_seconds=duration,
                )
            )

            # === BUSINESS TELEMETRY: Products Listed ===
            _emit_business_event_sync(
                emit_products_listed(
                    product_ids=[str(p.get("id")) for p in products],
                    page=1,
                    page_size=len(products),
                )
            )
            # ============================================

            return result

        except Exception as e:
            logger.error(f"Error getting products: {e}")
            telemetry.record_error(span, e)
            # Record duration metric with error_type
            duration = time.perf_counter() - start_time
            telemetry.record_operation_duration(
                GenAIMetricsData(
                    operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                    provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                    duration_seconds=duration,
                    error_type=type(e).__name__,
                )
            )
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": "Sorry, I couldn't retrieve the product catalog. Please try again."
            })


def get_product_details(
    product_id: Annotated[int, Field(description="The unique identifier of the product to retrieve")]
) -> str:
    """Get detailed information about a specific product."""
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="get_product_details",
        tool_description="Get detailed information about a specific product",
        conversation_id=_business_context.get("session_id"),
        agent_id=_get_agent_id(),
        agent_name=_get_agent_name(),
    ) as span:
        telemetry.set_tool_call_attributes(span, arguments={"product_id": product_id})

        try:
            import asyncio
            client = _get_product_client()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            product = asyncio.run(client.get_product_by_id(product_id))

            if product is None:
                result = json.dumps({
                    "success": False,
                    "message": f"Product with ID {product_id} was not found."
                })
                telemetry.set_tool_call_attributes(span, result=result)
                return result

            # Derive product category from name (pet store products)
            product_name = product.get("name", "").lower()
            category = _derive_product_category(product_name)

            result = json.dumps({
                "success": True,
                "product": {
                    "id": product.get("id"),
                    "name": product.get("name"),
                    "description": product.get("description", ""),
                    "price": product.get("price"),
                    "image": product.get("image", ""),
                    "category": category,
                },
                "message": f"Here are the details for {product.get('name')}."
            })

            telemetry.set_tool_call_attributes(span, result=result)
            duration = time.perf_counter() - start_time
            telemetry.record_operation_duration(
                GenAIMetricsData(
                    operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                    provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                    duration_seconds=duration,
                )
            )

            # === BUSINESS TELEMETRY: Product Viewed ===
            _emit_business_event_sync(
                emit_product_viewed(
                    product_id=str(product.get("id")),
                    product_name=product.get("name", ""),
                    category=category,
                    price=float(product.get("price", 0)),
                    ai_assisted=True,
                )
            )
            # ==========================================

            return result

        except Exception as e:
            logger.error(f"Error getting product details: {e}")
            telemetry.record_error(span, e)
            duration = time.perf_counter() - start_time
            telemetry.record_operation_duration(
                GenAIMetricsData(
                    operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                    provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                    duration_seconds=duration,
                    error_type=type(e).__name__,
                )
            )
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"Sorry, I couldn't retrieve details for product {product_id}."
            })


def search_products(
    query: Annotated[str, Field(description="The search term to look for in product names and descriptions")]
) -> str:
    """Search for products by name or description."""
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="search_products",
        tool_description="Search for products by name or description",
        conversation_id=_business_context.get("session_id"),
        agent_id=_get_agent_id(),
        agent_name=_get_agent_name(),
    ) as span:
        telemetry.set_tool_call_attributes(span, arguments={"query": query})

        try:
            import asyncio
            client = _get_product_client()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            products = asyncio.run(client.search_products(query))

            if not products:
                result = json.dumps({
                    "success": True,
                    "products": [],
                    "message": f"No products found matching '{query}'. Try a different search term."
                })
                telemetry.set_tool_call_attributes(span, result=result)
                return result

            formatted_products = [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "description": p.get("description", ""),
                    "price": p.get("price"),
                }
                for p in products
            ]

            result = json.dumps({
                "success": True,
                "products": formatted_products,
                "count": len(formatted_products),
                "message": f"Found {len(formatted_products)} products matching '{query}'."
            })

            telemetry.set_tool_call_attributes(span, result=result)
            duration = time.perf_counter() - start_time
            telemetry.record_operation_duration(
                GenAIMetricsData(
                    operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                    provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                    duration_seconds=duration,
                )
            )

            # === BUSINESS TELEMETRY: Product Searched ===
            _emit_business_event_sync(
                emit_product_searched(
                    query=query,
                    results_count=len(formatted_products),
                    product_ids=[str(p.get("id")) for p in products],
                    ai_assisted=True,
                )
            )
            # ============================================

            return result

        except Exception as e:
            logger.error(f"Error searching products: {e}")
            telemetry.record_error(span, e)
            duration = time.perf_counter() - start_time
            telemetry.record_operation_duration(
                GenAIMetricsData(
                    operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                    provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                    duration_seconds=duration,
                    error_type=type(e).__name__,
                )
            )
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"Sorry, I couldn't search for '{query}'. Please try again."
            })


def place_order(
    items: Annotated[str, Field(
        description="JSON string containing a list of items to order. "
                    "Each item should have: product_id, name, price, quantity. "
                    "Example: '[{\"product_id\": 1, \"name\": \"Dog Food\", \"price\": 29.99, \"quantity\": 2}]'"
    )],
    customer_id: Annotated[Optional[str], Field(
        description="Optional customer identifier. If not provided, uses the current session's customer."
    )] = None
) -> str:
    """Place a new order for a customer. Uses session customer details unless explicitly specified."""
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    # Get session customer context - use generated customer unless explicitly provided
    cust_ctx = get_customer_context()
    effective_customer_id = customer_id if customer_id else cust_ctx.get("customer_id", "guest")
    effective_customer_name = cust_ctx.get("customer_name", "Guest Customer")
    effective_customer_email = cust_ctx.get("customer_email")

    with telemetry.execute_tool_span(
        tool_name="place_order",
        tool_description="Place a new order for a customer",
        conversation_id=_business_context.get("session_id"),
        agent_id=_get_agent_id(),
        agent_name=_get_agent_name(),
    ) as span:
        telemetry.set_tool_call_attributes(
            span,
            arguments={"customer_id": effective_customer_id, "items": items}
        )

        try:
            # Parse items from JSON string
            try:
                items_list = json.loads(items)
            except json.JSONDecodeError as e:
                result = json.dumps({
                    "success": False,
                    "error": f"Invalid items format: {e}",
                    "message": "The order items couldn't be parsed. Please provide valid item details."
                })
                telemetry.set_tool_call_attributes(span, result=result)
                return result

            if not items_list:
                result = json.dumps({
                    "success": False,
                    "message": "No items provided. Please specify at least one item to order."
                })
                telemetry.set_tool_call_attributes(span, result=result)
                return result

            import asyncio
            client = _get_order_client()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            order_result = asyncio.run(client.place_order(customer_id=effective_customer_id, items=items_list))

            if order_result.get("success"):
                items_summary = ", ".join(
                    f"{item.get('quantity', 1)}x {item.get('name', 'Item')}"
                    for item in items_list
                )

                result = json.dumps({
                    "success": True,
                    "order_id": order_result.get("order_id"),
                    "customer_id": effective_customer_id,
                    "customer_name": effective_customer_name,
                    "total": order_result.get("total"),
                    "status": "pending",
                    "items_summary": items_summary,
                    "message": f"🎉 Order placed successfully! Your order ID is {order_result.get('order_id')}. "
                              f"Customer: {effective_customer_name} (ID: {effective_customer_id}). "
                              f"Order total: ${order_result.get('total', 0):.2f}. "
                              f"Items: {items_summary}"
                })

                # === BUSINESS TELEMETRY: Order Placed ===
                # Include full customer context and channel for KQL entity creation
                _emit_business_event_sync(
                    emit_order_placed(
                        order_id=str(order_result.get("order_id")),
                        items=items_list,
                        total=float(order_result.get("total", 0)),
                        customer_id=effective_customer_id,
                        customer_name=effective_customer_name,
                        customer_email=effective_customer_email,
                        channel=CUSTOMER_AGENT_CHANNEL,
                        ai_assisted=True,
                    )
                )
                # ========================================
            else:
                result = json.dumps({
                    "success": False,
                    "error": order_result.get("error", "Unknown error"),
                    "message": order_result.get("message", "Failed to place order.")
                })

            telemetry.set_tool_call_attributes(span, result=result)
            duration = time.perf_counter() - start_time
            telemetry.record_operation_duration(
                GenAIMetricsData(
                    operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                    provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                    duration_seconds=duration,
                )
            )

            return result

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            telemetry.record_error(span, e)
            duration = time.perf_counter() - start_time
            telemetry.record_operation_duration(
                GenAIMetricsData(
                    operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                    provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                    duration_seconds=duration,
                    error_type=type(e).__name__,
                )
            )
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": "Sorry, I couldn't place your order. Please try again."
            })


def get_order_status(
    order_id: Annotated[str, Field(description="The unique identifier of the order to check")]
) -> str:
    """Check the status of an existing order."""
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="get_order_status",
        tool_description="Check the status of an existing order",
        conversation_id=_business_context.get("session_id"),
        agent_id=_get_agent_id(),
        agent_name=_get_agent_name(),
    ) as span:
        telemetry.set_tool_call_attributes(span, arguments={"order_id": order_id})

        try:
            import asyncio
            client = _get_order_client()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            order = asyncio.run(client.get_order_status(order_id))

            if order is None:
                result = json.dumps({
                    "success": False,
                    "message": f"Order {order_id} was not found. Please check the order ID and try again."
                })
                telemetry.set_tool_call_attributes(span, result=result)
                return result

            status = order.get("status", "unknown")
            status_emoji = {
                "pending": "⏳",
                "processing": "🔄",
                "completed": "✅",
                "cancelled": "❌",
            }.get(status, "❓")

            result = json.dumps({
                "success": True,
                "order_id": order_id,
                "status": status,
                "items": order.get("items", []),
                "total": order.get("total"),
                "message": f"{status_emoji} Order {order_id} status: {status.upper()}"
            })

            telemetry.set_tool_call_attributes(span, result=result)
            duration = time.perf_counter() - start_time
            telemetry.record_operation_duration(
                GenAIMetricsData(
                    operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                    provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                    duration_seconds=duration,
                )
            )

            # === BUSINESS TELEMETRY: Order Status Checked ===
            _emit_business_event_sync(
                emit_order_status_checked(
                    order_id=order_id,
                    status=status,
                )
            )
            # ================================================

            return result

        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            telemetry.record_error(span, e)
            duration = time.perf_counter() - start_time
            telemetry.record_operation_duration(
                GenAIMetricsData(
                    operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                    provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                    duration_seconds=duration,
                    error_type=type(e).__name__,
                )
            )
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"Sorry, I couldn't retrieve the status for order {order_id}."
            })


def get_agent_tools() -> list:
    """
    Get the list of function tools for the Microsoft Agent Framework.

    Microsoft Agent Framework accepts plain functions as tools.
    The framework automatically converts them to tool definitions
    using the function signatures and docstrings.

    Returns:
        List of function tools for the agent
    """
    return [
        get_products,
        get_product_details,
        search_products,
        place_order,
        get_order_status,
    ]


# Legacy export for backwards compatibility
user_functions = {
    get_products,
    get_product_details,
    search_products,
    place_order,
    get_order_status,
}
