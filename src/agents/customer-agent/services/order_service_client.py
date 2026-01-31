"""
Order Service Client for communicating with the order-service backend.

This client handles all order-related operations including:
- Placing new orders
- Getting order status
- Listing orders
"""

import json
import logging
from typing import Any, Optional
import uuid

import httpx

from telemetry import trace_function

logger = logging.getLogger(__name__)


class OrderServiceClient:
    """Async client for the order-service backend."""

    def __init__(
        self,
        order_service_url: str = "http://order-service:3000",
        makeline_service_url: str = "http://makeline-service:3001",
    ):
        """
        Initialize the order service client.

        Args:
            order_service_url: Base URL of the order service (for placing orders)
            makeline_service_url: Base URL of the makeline service (for order status)
        """
        self.order_service_url = order_service_url.rstrip("/")
        self.makeline_service_url = makeline_service_url.rstrip("/")
        self._order_client: Optional[httpx.AsyncClient] = None
        self._makeline_client: Optional[httpx.AsyncClient] = None

    async def _get_order_client(self) -> httpx.AsyncClient:
        """Get or create the order service HTTP client."""
        if self._order_client is None:
            self._order_client = httpx.AsyncClient(
                base_url=self.order_service_url,
                timeout=30.0,
                headers={"Content-Type": "application/json"},
            )
        return self._order_client

    async def _get_makeline_client(self) -> httpx.AsyncClient:
        """Get or create the makeline service HTTP client."""
        if self._makeline_client is None:
            self._makeline_client = httpx.AsyncClient(
                base_url=self.makeline_service_url,
                timeout=30.0,
                headers={"Content-Type": "application/json"},
            )
        return self._makeline_client

    async def close(self) -> None:
        """Close all HTTP clients."""
        if self._order_client:
            await self._order_client.aclose()
            self._order_client = None
        if self._makeline_client:
            await self._makeline_client.aclose()
            self._makeline_client = None

    @trace_function("place_order")
    async def place_order(
        self,
        customer_id: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Place a new order.

        Args:
            customer_id: Customer identifier
            items: List of order items with product_id, name, price, quantity

        Returns:
            Order confirmation with order_id and status
        """
        try:
            client = await self._get_order_client()

            # Generate order ID
            order_id = str(uuid.uuid4())

            # Calculate total
            total = sum(
                item.get("price", 0) * item.get("quantity", 1)
                for item in items
            )

            # Prepare order payload matching order-service expected format
            # Note: status must be an integer (0=Pending, 1=Processing, 2=Complete)
            # to match makeline-service's Go struct definition
            order_payload = {
                "customerId": customer_id,
                "orderId": order_id,
                "items": [
                    {
                        "productId": item.get("product_id", item.get("productId")),
                        "productName": item.get("name", item.get("productName", "Unknown")),
                        "price": item.get("price", 0),
                        "quantity": item.get("quantity", 1),
                    }
                    for item in items
                ],
                "total": total,
                "status": 0,  # 0=Pending (matches makeline-service Status enum)
            }

            logger.info(f"Placing order {order_id} for customer {customer_id}")

            # Order service accepts POST at root endpoint
            response = await client.post("/", json=order_payload)
            response.raise_for_status()

            result = {
                "success": True,
                "order_id": order_id,
                "customer_id": customer_id,
                "items": items,
                "total": total,
                "status": "pending",
                "message": f"Order {order_id} placed successfully!"
            }

            logger.info(f"Order {order_id} placed successfully")
            return result

        except httpx.HTTPError as e:
            logger.error(f"Failed to place order: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to place order. Please try again."
            }

    @trace_function("get_order_status")
    async def get_order_status(self, order_id: str) -> Optional[dict[str, Any]]:
        """
        Get the status of an order.

        Args:
            order_id: The order ID to check

        Returns:
            Order details with status or None if not found
        """
        try:
            client = await self._get_makeline_client()
            response = await client.get(f"/order/{order_id}")
            response.raise_for_status()
            order = response.json()
            logger.info(f"Retrieved order {order_id}: status={order.get('status', 'unknown')}")
            return order
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Order {order_id} not found")
                return None
            logger.error(f"Failed to get order status: {e}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"Failed to get order status: {e}")
            return None

    @trace_function("get_pending_orders")
    async def get_pending_orders(self) -> list[dict[str, Any]]:
        """
        Get all pending orders (typically for admin/worker use).

        Returns:
            List of pending orders
        """
        try:
            client = await self._get_makeline_client()
            response = await client.get("/order/fetch")
            response.raise_for_status()
            orders = response.json()
            logger.info(f"Retrieved {len(orders)} pending orders")
            return orders
        except httpx.HTTPError as e:
            logger.error(f"Failed to get pending orders: {e}")
            return []

    @trace_function("check_health")
    async def check_health(self) -> dict[str, bool]:
        """
        Check if the order and makeline services are healthy.

        Returns:
            Dictionary with health status for each service
        """
        health = {"order_service": False, "makeline_service": False}

        try:
            order_client = await self._get_order_client()
            response = await order_client.get("/health")
            health["order_service"] = response.status_code == 200
        except Exception as e:
            logger.error(f"Order service health check failed: {e}")

        try:
            makeline_client = await self._get_makeline_client()
            response = await makeline_client.get("/health")
            health["makeline_service"] = response.status_code == 200
        except Exception as e:
            logger.error(f"Makeline service health check failed: {e}")

        return health
