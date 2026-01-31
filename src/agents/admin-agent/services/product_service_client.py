"""
Product Service Client for administrative operations.

This client handles all product-related admin operations including:
- Listing products
- Getting product details
- Adding new products
- Updating existing products
- Deleting products
"""

import logging
from typing import Any, Optional

import httpx

from telemetry import trace_function

logger = logging.getLogger(__name__)


class ProductServiceClient:
    """Async client for the product-service backend (admin operations)."""

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
        Get all products from the catalog.

        Returns:
            List of product dictionaries
        """
        try:
            client = await self._get_client()
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

    @trace_function("add_product")
    async def add_product(
        self,
        name: str,
        price: float,
        description: str = "",
        image: str = "",
    ) -> dict[str, Any]:
        """
        Add a new product to the catalog.

        Args:
            name: Product name
            price: Product price
            description: Product description
            image: Product image URL

        Returns:
            Dict with success status and product data or error
        """
        try:
            client = await self._get_client()

            # Product service expects POST / with product data
            product_data = {
                "name": name,
                "price": price,
                "description": description,
                "image": image,
            }

            response = await client.post("/", json=product_data)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Added product: {name}")

            return {
                "success": True,
                "product": result,
                "message": f"Product '{name}' added successfully"
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to add product: {e}")
            error_detail = ""
            try:
                error_detail = e.response.text
            except:
                pass
            return {
                "success": False,
                "error": str(e),
                "detail": error_detail,
                "message": f"Failed to add product '{name}'"
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to add product: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to add product '{name}'"
            }

    @trace_function("update_product")
    async def update_product(
        self,
        product_id: int,
        name: Optional[str] = None,
        price: Optional[float] = None,
        description: Optional[str] = None,
        image: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Update an existing product.

        Args:
            product_id: The product ID to update
            name: New product name (optional)
            price: New product price (optional)
            description: New product description (optional)
            image: New product image URL (optional)

        Returns:
            Dict with success status and updated product data or error
        """
        try:
            # First get the existing product
            existing = await self.get_product_by_id(product_id)
            if not existing:
                return {
                    "success": False,
                    "error": "Product not found",
                    "message": f"Product with ID {product_id} was not found"
                }

            client = await self._get_client()

            # Build update data, keeping existing values for unspecified fields
            update_data = {
                "id": product_id,
                "name": name if name is not None else existing.get("name"),
                "price": price if price is not None else existing.get("price"),
                "description": description if description is not None else existing.get("description", ""),
                "image": image if image is not None else existing.get("image", ""),
            }

            # Product service expects PUT / with full product data
            response = await client.put("/", json=update_data)
            response.raise_for_status()

            result = response.json()
            logger.info(f"Updated product {product_id}")

            return {
                "success": True,
                "product": result,
                "message": f"Product '{update_data['name']}' updated successfully"
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to update product {product_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to update product {product_id}"
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to update product {product_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to update product {product_id}"
            }

    @trace_function("delete_product")
    async def delete_product(self, product_id: int) -> dict[str, Any]:
        """
        Delete a product from the catalog.

        Args:
            product_id: The product ID to delete

        Returns:
            Dict with success status and message
        """
        try:
            # First check if product exists
            existing = await self.get_product_by_id(product_id)
            if not existing:
                return {
                    "success": False,
                    "error": "Product not found",
                    "message": f"Product with ID {product_id} was not found"
                }

            client = await self._get_client()

            # Product service expects DELETE /{id}
            response = await client.delete(f"/{product_id}")
            response.raise_for_status()

            logger.info(f"Deleted product {product_id}")

            return {
                "success": True,
                "product_id": product_id,
                "message": f"Product '{existing.get('name', product_id)}' deleted successfully"
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to delete product {product_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to delete product {product_id}"
            }
        except httpx.HTTPError as e:
            logger.error(f"Failed to delete product {product_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to delete product {product_id}"
            }

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
