"""
Product Service Client for communicating with the product-service backend.

This client handles all product-related operations including:
- Listing available products
- Getting product details
- Searching products
"""

import logging
from typing import Any, Optional

import httpx

from telemetry import trace_function

logger = logging.getLogger(__name__)


class ProductServiceClient:
    """Async client for the product-service backend."""

    def __init__(self, base_url: str = "http://product-service:3002"):
        """
        Initialize the product service client.

        Args:
            base_url: Base URL of the product service
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

    @trace_function("get_all_products")
    async def get_all_products(self) -> list[dict[str, Any]]:
        """
        Get all available products.

        Returns:
            List of product dictionaries
        """
        try:
            client = await self._get_client()
            # Product service returns all products at root endpoint
            response = await client.get("/")
            response.raise_for_status()
            products = response.json()
            logger.info(f"Retrieved {len(products)} products")
            return products
        except httpx.HTTPError as e:
            logger.error(f"Failed to get products: {e}")
            return []

    @trace_function("get_product_by_id")
    async def get_product_by_id(self, product_id: int) -> Optional[dict[str, Any]]:
        """
        Get a specific product by ID.

        Args:
            product_id: The product ID to retrieve

        Returns:
            Product dictionary or None if not found
        """
        try:
            client = await self._get_client()
            # Product service uses /{id} endpoint
            response = await client.get(f"/{product_id}")
            response.raise_for_status()
            product = response.json()
            logger.info(f"Retrieved product: {product.get('name', 'Unknown')}")
            return product
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Product {product_id} not found")
                return None
            logger.error(f"Failed to get product {product_id}: {e}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"Failed to get product {product_id}: {e}")
            return None

    @trace_function("search_products")
    async def search_products(self, query: str) -> list[dict[str, Any]]:
        """
        Search products by name or description.

        Args:
            query: Search query string

        Returns:
            List of matching products
        """
        try:
            # Get all products and filter locally
            # (product-service may not have search endpoint)
            products = await self.get_all_products()
            query_lower = query.lower()

            matching = [
                p for p in products
                if query_lower in p.get("name", "").lower()
                or query_lower in p.get("description", "").lower()
            ]

            logger.info(f"Found {len(matching)} products matching '{query}'")
            return matching
        except Exception as e:
            logger.error(f"Failed to search products: {e}")
            return []

    @trace_function("check_health")
    async def check_health(self) -> bool:
        """
        Check if the product service is healthy.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Product service health check failed: {e}")
            return False
