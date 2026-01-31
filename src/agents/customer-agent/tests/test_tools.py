"""Tests for the Customer Agent tools."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestGetProducts:
    """Tests for the get_products function."""

    @pytest.mark.asyncio
    async def test_get_products_success(self):
        """Test successful product retrieval."""
        from agent.tools import get_products

        mock_products = [
            {"id": 1, "name": "Dog Food", "price": 29.99, "description": "Premium dog food"},
            {"id": 2, "name": "Cat Toy", "price": 9.99, "description": "Interactive cat toy"},
        ]

        with patch("agent.tools._get_product_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_all_products.return_value = mock_products
            mock_get_client.return_value = mock_client

            result = await get_products()
            data = json.loads(result)

            assert data["success"] is True
            assert data["count"] == 2
            assert len(data["products"]) == 2

    @pytest.mark.asyncio
    async def test_get_products_empty(self):
        """Test when no products are available."""
        from agent.tools import get_products

        with patch("agent.tools._get_product_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_all_products.return_value = []
            mock_get_client.return_value = mock_client

            result = await get_products()
            data = json.loads(result)

            assert data["success"] is True
            assert data["products"] == []


class TestPlaceOrder:
    """Tests for the place_order function."""

    @pytest.mark.asyncio
    async def test_place_order_success(self):
        """Test successful order placement."""
        from agent.tools import place_order

        items = json.dumps([
            {"product_id": 1, "name": "Dog Food", "price": 29.99, "quantity": 2}
        ])

        mock_result = {
            "success": True,
            "order_id": "test-order-123",
            "total": 59.98,
        }

        with patch("agent.tools._get_order_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.place_order.return_value = mock_result
            mock_get_client.return_value = mock_client

            result = await place_order("customer-1", items)
            data = json.loads(result)

            assert data["success"] is True
            assert "order_id" in data

    @pytest.mark.asyncio
    async def test_place_order_invalid_items(self):
        """Test order placement with invalid items format."""
        from agent.tools import place_order

        result = await place_order("customer-1", "invalid json")
        data = json.loads(result)

        assert data["success"] is False
        assert "error" in data


class TestSearchProducts:
    """Tests for the search_products function."""

    @pytest.mark.asyncio
    async def test_search_products_found(self):
        """Test search with matching products."""
        from agent.tools import search_products

        mock_products = [
            {"id": 1, "name": "Dog Food", "price": 29.99, "description": "Premium dog food"},
        ]

        with patch("agent.tools._get_product_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.search_products.return_value = mock_products
            mock_get_client.return_value = mock_client

            result = await search_products("dog")
            data = json.loads(result)

            assert data["success"] is True
            assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_search_products_not_found(self):
        """Test search with no matching products."""
        from agent.tools import search_products

        with patch("agent.tools._get_product_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.search_products.return_value = []
            mock_get_client.return_value = mock_client

            result = await search_products("nonexistent")
            data = json.loads(result)

            assert data["success"] is True
            assert data["products"] == []
