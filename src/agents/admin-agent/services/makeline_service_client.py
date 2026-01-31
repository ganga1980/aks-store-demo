"""
Makeline Service Client for order management operations.

This client handles all order-related admin operations including:
- Fetching pending orders
- Getting order details
- Updating order status (Pending -> Processing -> Complete)
"""

import logging
from typing import Any, Optional

import httpx

from telemetry import trace_function

logger = logging.getLogger(__name__)

# Order status mapping
ORDER_STATUS = {
    0: "Pending",
    1: "Processing",
    2: "Complete",
    "pending": 0,
    "processing": 1,
    "complete": 2,
}


class MakelineServiceClient:
    """Async client for the makeline-service backend (order management)."""

    def __init__(self, base_url: str = "http://makeline-service:3001"):
        """
        Initialize the makeline service client.

        Args:
            base_url: Base URL of the makeline service
        """
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _format_order(self, order: dict[str, Any]) -> dict[str, Any]:
        """
        Format an order for display with human-readable status.

        Args:
            order: Raw order data from the service

        Returns:
            Formatted order with status name
        """
        status_code = order.get("status", 0)
        status_name = ORDER_STATUS.get(status_code, "Unknown")

        return {
            "order_id": order.get("orderId", order.get("_id")),
            "customer_id": order.get("customerId"),
            "items": order.get("items", []),
            "total": order.get("total"),
            "status": status_name,
            "status_code": status_code,
        }

    @trace_function("fetch_orders")
    async def fetch_orders(self) -> list[dict[str, Any]]:
        """
        Fetch all pending orders from the makeline queue.

        Returns:
            List of pending orders
        """
        try:
            client = await self._get_client()
            response = await client.get("/order/fetch")
            response.raise_for_status()
            orders = response.json()

            # Format orders for display
            formatted_orders = [self._format_order(o) for o in orders]

            logger.info(f"Retrieved {len(formatted_orders)} orders")
            return formatted_orders

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch orders: {e}")
            return []

    @trace_function("get_order")
    async def get_order(self, order_id: str) -> Optional[dict[str, Any]]:
        """
        Get a specific order by ID.

        Args:
            order_id: The order ID to retrieve

        Returns:
            Order dictionary or None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/order/{order_id}")
            response.raise_for_status()
            order = response.json()

            logger.info(f"Retrieved order {order_id}")
            return self._format_order(order)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Order {order_id} not found")
                return None
            logger.error(f"Failed to get order {order_id}: {e}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None

    @trace_function("update_order_status")
    async def update_order_status(
        self,
        order_id: str,
        new_status: str,
    ) -> dict[str, Any]:
        """
        Update the status of an order.

        Args:
            order_id: The order ID to update
            new_status: The new status ("Pending", "Processing", or "Complete")

        Returns:
            Dict with success status and message
        """
        try:
            # Validate and convert status
            status_lower = new_status.lower()
            if status_lower not in ORDER_STATUS:
                return {
                    "success": False,
                    "error": "Invalid status",
                    "message": f"Status must be one of: Pending, Processing, Complete"
                }

            new_status_code = ORDER_STATUS[status_lower]

            # Get current order to verify it exists
            current_order = await self.get_order(order_id)
            if not current_order:
                return {
                    "success": False,
                    "error": "Order not found",
                    "message": f"Order {order_id} was not found"
                }

            client = await self._get_client()

            # Makeline service expects PUT /order with order data including new status
            # Build the update payload
            update_data = {
                "orderId": order_id,
                "customerId": current_order.get("customer_id", ""),
                "items": current_order.get("items", []),
                "total": current_order.get("total", 0),
                "status": new_status_code,
            }

            response = await client.put("/order", json=update_data)
            response.raise_for_status()

            old_status = current_order.get("status", "Unknown")
            new_status_name = ORDER_STATUS.get(new_status_code, "Unknown")

            logger.info(f"Updated order {order_id} status: {old_status} -> {new_status_name}")

            return {
                "success": True,
                "order_id": order_id,
                "old_status": old_status,
                "new_status": new_status_name,
                "message": f"Order {order_id} status updated: {old_status} → {new_status_name}"
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to update order {order_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to update order {order_id}"
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to update order {order_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to update order {order_id}"
            }

    @trace_function("complete_order")
    async def complete_order(self, order_id: str) -> dict[str, Any]:
        """
        Mark an order as complete.

        Args:
            order_id: The order ID to complete

        Returns:
            Dict with success status and message
        """
        return await self.update_order_status(order_id, "Complete")

    @trace_function("start_processing_order")
    async def start_processing_order(self, order_id: str) -> dict[str, Any]:
        """
        Mark an order as processing.

        Args:
            order_id: The order ID to start processing

        Returns:
            Dict with success status and message
        """
        return await self.update_order_status(order_id, "Processing")

    @trace_function("get_orders_by_status")
    async def get_orders_by_status(self, status: str) -> list[dict[str, Any]]:
        """
        Get orders filtered by status.

        Args:
            status: Status to filter by ("Pending", "Processing", "Complete")

        Returns:
            List of orders matching the status
        """
        try:
            orders = await self.fetch_orders()
            status_lower = status.lower()

            filtered = [
                o for o in orders
                if o.get("status", "").lower() == status_lower
            ]

            logger.info(f"Found {len(filtered)} orders with status '{status}'")
            return filtered

        except Exception as e:
            logger.error(f"Failed to filter orders by status: {e}")
            return []

    @trace_function("check_health")
    async def check_health(self) -> bool:
        """
        Check if the makeline service is healthy.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Makeline service health check failed: {e}")
            return False
