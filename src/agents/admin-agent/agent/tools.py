"""
Function tools for the Admin Agent using Microsoft Agent Framework.

These tools enable the AI agent to perform administrative operations on the AKS Store Demo:
- Product Management: Add, update, delete, list products
- Order Management: View orders, update order status

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
from typing import Annotated, Optional

from pydantic import Field

from config import get_settings
from services import ProductServiceClient, MakelineServiceClient
from telemetry import (
    GenAIMetricsData,
    GenAIOperationName,
    GenAIProviderName,
    get_gen_ai_telemetry,
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
        emit_products_listed,
        emit_product_created,
        emit_product_creation_failed,
        emit_product_updated,
        emit_order_status_checked,
        emit_order_completed,
    )
    BUSINESS_TELEMETRY_AVAILABLE = True
except ImportError as e:
    BUSINESS_TELEMETRY_AVAILABLE = False
    logging.warning(f"Business telemetry SDK not available: {e}")

logger = logging.getLogger(__name__)

# Global service clients (initialized lazily)
_product_client: ProductServiceClient | None = None
_makeline_client: MakelineServiceClient | None = None
_store_front_url: str | None = None

# Get Gen AI telemetry instance
_gen_ai_telemetry = None

# Business telemetry context
_business_context = {
    "session_id": None,
    "user_id": None,
    "admin_user": None,
    "correlation_id": None,
}


def _get_telemetry():
    """Get or create Gen AI telemetry instance."""
    global _gen_ai_telemetry
    if _gen_ai_telemetry is None:
        _gen_ai_telemetry = get_gen_ai_telemetry()
    return _gen_ai_telemetry


def set_business_context(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    admin_user: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """Set context for business telemetry events."""
    if session_id:
        _business_context["session_id"] = session_id
    if user_id:
        _business_context["user_id"] = user_id
    if admin_user:
        _business_context["admin_user"] = admin_user
    if correlation_id:
        _business_context["correlation_id"] = correlation_id

    # Also set on the SDK client if available
    if BUSINESS_TELEMETRY_AVAILABLE:
        set_telemetry_context(
            session_id=session_id,
            user_id=user_id or admin_user,
            correlation_id=correlation_id,
        )


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


def _get_store_front_url() -> str:
    """Get the store front URL for building image URLs."""
    global _store_front_url
    if _store_front_url is None:
        settings = get_settings()
        _store_front_url = settings.store_front_url.rstrip("/")
    return _store_front_url


def _build_image_url(image_path: str) -> str:
    """
    Build a full image URL from a relative path.

    Product images are stored as relative paths (e.g., /catnip.jpg)
    and are served by the store-front service.
    """
    if not image_path:
        return ""

    # If already a full URL, return as-is
    if image_path.startswith(("http://", "https://")):
        return image_path

    # Build full URL from store-front base URL
    store_front = _get_store_front_url()
    if image_path.startswith("/"):
        return f"{store_front}{image_path}"
    return f"{store_front}/{image_path}"


def _get_product_client() -> ProductServiceClient:
    """Get or create the product service client."""
    global _product_client
    if _product_client is None:
        settings = get_settings()
        _product_client = ProductServiceClient(base_url=settings.product_service_url)
    return _product_client


def _get_makeline_client() -> MakelineServiceClient:
    """Get or create the makeline service client."""
    global _makeline_client
    if _makeline_client is None:
        settings = get_settings()
        _makeline_client = MakelineServiceClient(base_url=settings.makeline_service_url)
    return _makeline_client


# =============================================================================
# Product Management Tools
# =============================================================================


def get_products() -> str:
    """
    Get all products from the pet store catalog.

    Returns a JSON string containing a list of all products with their
    details including ID, name, description, price, and image URL.
    Use this to show administrators the current product catalog.
    """
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="get_products",
        tool_description="Get all products from the pet store catalog",
        conversation_id=_business_context.get("session_id"),
    ) as span:
        try:
            import asyncio
            client = _get_product_client()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            products = asyncio.run(client.get_all_products())

            if not products:
                result = json.dumps({
                    "success": True,
                    "products": [],
                    "message": "No products currently in the catalog."
                })
                telemetry.set_tool_call_attributes(span, result=result)
                return result

            formatted_products = [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "description": p.get("description", ""),
                    "price": p.get("price"),
                    "image": _build_image_url(p.get("image", "")),
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

            # === BUSINESS TELEMETRY: Products Listed (Admin) ===
            _emit_business_event_sync(
                emit_products_listed(
                    product_ids=[str(p.get("id")) for p in products],
                    page=1,
                    page_size=len(products),
                )
            )
            # ===================================================

            return result

        except Exception as e:
            logger.error(f"Error getting products: {e}")
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
                "message": "Failed to retrieve products."
            })


def get_product_details(
    product_id: Annotated[int, Field(description="The unique identifier of the product to retrieve")]
) -> str:
    """Get detailed information about a specific product by its ID."""
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="get_product_details",
        tool_description="Get detailed information about a specific product",
        conversation_id=_business_context.get("session_id"),
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

            result = json.dumps({
                "success": True,
                "product": {
                    "id": product.get("id"),
                    "name": product.get("name"),
                    "description": product.get("description", ""),
                    "price": product.get("price"),
                    "image": _build_image_url(product.get("image", "")),
                },
                "message": f"Product details for '{product.get('name')}'."
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

            # === BUSINESS TELEMETRY: Product Viewed (Admin) ===
            _emit_business_event_sync(
                emit_product_viewed(
                    product_id=str(product.get("id")),
                    product_name=product.get("name", ""),
                    price=float(product.get("price", 0)),
                    ai_assisted=True,
                )
            )
            # ==================================================

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
                "message": f"Failed to retrieve product {product_id}."
            })


def add_product(
    name: Annotated[str, Field(description="The name of the new product")],
    price: Annotated[float, Field(description="The price of the product in dollars")],
    description: Annotated[str, Field(description="A description of the product")] = "",
    image: Annotated[str, Field(description="URL to the product image")] = "",
) -> str:
    """
    Add a new product to the pet store catalog.

    Creates a new product with the specified name, price, description, and optional image URL.
    """
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="add_product",
        tool_description="Add a new product to the catalog",
        conversation_id=_business_context.get("session_id"),
    ) as span:
        telemetry.set_tool_call_attributes(
            span,
            arguments={"name": name, "price": price, "description": description, "image": image}
        )

        try:
            import asyncio
            client = _get_product_client()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()

            result_data = asyncio.run(client.add_product(
                name=name,
                price=price,
                description=description,
                image=image,
            ))

            if result_data.get("success"):
                product = result_data.get("product", {})
                # Build full image URL if product has an image
                if product.get("image"):
                    product = dict(product)
                    product["image"] = _build_image_url(product["image"])
                result = json.dumps({
                    "success": True,
                    "product": product,
                    "message": f"✅ Product '{name}' added successfully with price ${price:.2f}."
                })

                # === BUSINESS TELEMETRY: Product Created ===
                _emit_business_event_sync(
                    emit_product_created(
                        product_id=str(product.get("id", "")),
                        product_name=name,
                        admin_user=_business_context.get("admin_user"),
                        ai_assisted=True,
                    )
                )
                # ===========================================
            else:
                error_msg = result_data.get("error", "Unknown error")
                error_detail = result_data.get("detail", "")
                result = json.dumps({
                    "success": False,
                    "error": error_msg,
                    "message": f"❌ Failed to add product '{name}'."
                })

                # === BUSINESS TELEMETRY: Product Creation Failed ===
                _emit_business_event_sync(
                    emit_product_creation_failed(
                        product_name=name,
                        error_message=f"{error_msg}: {error_detail}" if error_detail else error_msg,
                        error_code="500" if "500" in str(error_msg) else None,
                        admin_user=_business_context.get("admin_user"),
                        ai_assisted=True,
                    )
                )
                # ==================================================

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
            logger.error(f"Error adding product: {e}")
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
                "message": f"Failed to add product '{name}'."
            })


def update_product(
    product_id: Annotated[int, Field(description="The ID of the product to update")],
    name: Annotated[Optional[str], Field(description="New name for the product")] = None,
    price: Annotated[Optional[float], Field(description="New price for the product")] = None,
    description: Annotated[Optional[str], Field(description="New description for the product")] = None,
    image: Annotated[Optional[str], Field(description="New image URL for the product")] = None,
) -> str:
    """
    Update an existing product in the catalog.

    You can update any combination of: name, price, description, image.
    Only the fields you specify will be updated.
    """
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="update_product",
        tool_description="Update an existing product in the catalog",
        conversation_id=_business_context.get("session_id"),
    ) as span:
        args = {"product_id": product_id}
        if name is not None:
            args["name"] = name
        if price is not None:
            args["price"] = price
        if description is not None:
            args["description"] = description
        if image is not None:
            args["image"] = image
        telemetry.set_tool_call_attributes(span, arguments=args)

        try:
            import asyncio
            client = _get_product_client()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()

            result_data = asyncio.run(client.update_product(
                product_id=product_id,
                name=name,
                price=price,
                description=description,
                image=image,
            ))

            if result_data.get("success"):
                product = result_data.get("product", {})
                # Build full image URL if product has an image
                if product.get("image"):
                    product = dict(product)
                    product["image"] = _build_image_url(product["image"])
                result = json.dumps({
                    "success": True,
                    "product": product,
                    "message": f"✅ Product {product_id} updated successfully."
                })

                # === BUSINESS TELEMETRY: Product Updated ===
                _emit_business_event_sync(
                    emit_product_updated(
                        product_id=str(product_id),
                        product_name=product.get("name", ""),
                        changes=args,
                        admin_user=_business_context.get("admin_user"),
                        ai_assisted=True,
                    )
                )
                # ===========================================
            else:
                result = json.dumps({
                    "success": False,
                    "error": result_data.get("error", "Unknown error"),
                    "message": result_data.get("message", f"Failed to update product {product_id}.")
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
            logger.error(f"Error updating product: {e}")
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
                "message": f"Failed to update product {product_id}."
            })


def delete_product(
    product_id: Annotated[int, Field(description="The ID of the product to delete")]
) -> str:
    """
    Delete a product from the catalog.

    Permanently removes the product with the specified ID. This action cannot be undone.
    """
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="delete_product",
        tool_description="Delete a product from the catalog",
        conversation_id=_business_context.get("session_id"),
    ) as span:
        telemetry.set_tool_call_attributes(span, arguments={"product_id": product_id})

        try:
            import asyncio
            client = _get_product_client()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()

            result_data = asyncio.run(client.delete_product(product_id))

            if result_data.get("success"):
                result = json.dumps({
                    "success": True,
                    "product_id": product_id,
                    "message": f"✅ Product {product_id} deleted successfully."
                })
            else:
                result = json.dumps({
                    "success": False,
                    "error": result_data.get("error", "Unknown error"),
                    "message": result_data.get("message", f"Failed to delete product {product_id}.")
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
            logger.error(f"Error deleting product: {e}")
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
                "message": f"Failed to delete product {product_id}."
            })


# =============================================================================
# Order Management Tools
# =============================================================================


def get_orders() -> str:
    """
    Get all orders from the makeline queue.

    Returns a list of orders with their details including customer ID, items,
    total, and current status (Pending, Processing, or Complete).
    """
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="get_orders",
        tool_description="Get all orders from the makeline queue",
        conversation_id=_business_context.get("session_id"),
    ) as span:
        try:
            import asyncio
            client = _get_makeline_client()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            orders = asyncio.run(client.fetch_orders())

            if not orders:
                result = json.dumps({
                    "success": True,
                    "orders": [],
                    "message": "No orders in the queue."
                })
                telemetry.set_tool_call_attributes(span, result=result)
                return result

            # Summarize orders
            pending = len([o for o in orders if o.get("status") == "Pending"])
            processing = len([o for o in orders if o.get("status") == "Processing"])
            complete = len([o for o in orders if o.get("status") == "Complete"])

            result = json.dumps({
                "success": True,
                "orders": orders,
                "count": len(orders),
                "summary": {
                    "pending": pending,
                    "processing": processing,
                    "complete": complete,
                },
                "message": f"Found {len(orders)} orders: {pending} pending, {processing} processing, {complete} complete."
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
            logger.error(f"Error getting orders: {e}")
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
                "message": "Failed to retrieve orders."
            })


def get_order_details(
    order_id: Annotated[str, Field(description="The unique identifier of the order to retrieve")]
) -> str:
    """Get detailed information about a specific order by its ID."""
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="get_order_details",
        tool_description="Get detailed information about a specific order",
        conversation_id=_business_context.get("session_id"),
    ) as span:
        telemetry.set_tool_call_attributes(span, arguments={"order_id": order_id})

        try:
            import asyncio
            client = _get_makeline_client()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            order = asyncio.run(client.get_order(order_id))

            if order is None:
                result = json.dumps({
                    "success": False,
                    "message": f"Order {order_id} was not found."
                })
                telemetry.set_tool_call_attributes(span, result=result)
                return result

            status_emoji = {
                "Pending": "⏳",
                "Processing": "🔄",
                "Complete": "✅",
            }.get(order.get("status", ""), "❓")

            result = json.dumps({
                "success": True,
                "order": order,
                "message": f"{status_emoji} Order {order_id}: {order.get('status', 'Unknown')}"
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

            # === BUSINESS TELEMETRY: Order Status Checked (Admin) ===
            _emit_business_event_sync(
                emit_order_status_checked(
                    order_id=order_id,
                    status=order.get("status", "unknown"),
                )
            )
            # ========================================================

            return result

        except Exception as e:
            logger.error(f"Error getting order details: {e}")
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
                "message": f"Failed to retrieve order {order_id}."
            })


def update_order_status(
    order_id: Annotated[str, Field(description="The ID of the order to update")],
    new_status: Annotated[str, Field(description="The new status: 'Pending', 'Processing', or 'Complete'")]
) -> str:
    """
    Update the status of an order.

    Valid statuses are:
    - Pending: Order received, waiting to be processed
    - Processing: Order is being prepared
    - Complete: Order has been fulfilled
    """
    telemetry = _get_telemetry()
    start_time = time.perf_counter()

    with telemetry.execute_tool_span(
        tool_name="update_order_status",
        tool_description="Update the status of an order",
        conversation_id=_business_context.get("session_id"),
    ) as span:
        telemetry.set_tool_call_attributes(
            span,
            arguments={"order_id": order_id, "new_status": new_status}
        )

        try:
            import asyncio
            client = _get_makeline_client()

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()

            result_data = asyncio.run(client.update_order_status(order_id, new_status))

            if result_data.get("success"):
                result = json.dumps({
                    "success": True,
                    "order_id": order_id,
                    "old_status": result_data.get("old_status"),
                    "new_status": result_data.get("new_status"),
                    "message": f"✅ {result_data.get('message')}"
                })

                # === BUSINESS TELEMETRY: Order Status Updated ===
                if result_data.get("new_status", "").lower() == "complete":
                    _emit_business_event_sync(
                        emit_order_completed(order_id=order_id)
                    )
                else:
                    _emit_business_event_sync(
                        emit_order_status_checked(
                            order_id=order_id,
                            status=result_data.get("new_status", new_status),
                        )
                    )
                # ================================================
            else:
                result = json.dumps({
                    "success": False,
                    "error": result_data.get("error", "Unknown error"),
                    "message": f"❌ {result_data.get('message', 'Failed to update order status.')}"
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
            logger.error(f"Error updating order status: {e}")
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
                "message": f"Failed to update order {order_id}."
            })


def complete_order(
    order_id: Annotated[str, Field(description="The ID of the order to mark as complete")]
) -> str:
    """Mark an order as complete. This indicates the order has been fulfilled."""
    return update_order_status(order_id, "Complete")


def start_processing_order(
    order_id: Annotated[str, Field(description="The ID of the order to start processing")]
) -> str:
    """Mark an order as processing. This indicates work has begun on the order."""
    return update_order_status(order_id, "Processing")


# =============================================================================
# Tool Registration
# =============================================================================


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
        # Product management
        get_products,
        get_product_details,
        add_product,
        update_product,
        delete_product,
        # Order management
        get_orders,
        get_order_details,
        update_order_status,
        complete_order,
        start_processing_order,
    ]


# Legacy export for backwards compatibility
user_functions = {
    get_products,
    get_product_details,
    add_product,
    update_product,
    delete_product,
    get_orders,
    get_order_details,
    update_order_status,
    complete_order,
    start_processing_order,
}
