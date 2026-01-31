"""Services module for backend service clients."""

from .order_service_client import OrderServiceClient
from .product_service_client import ProductServiceClient

__all__ = ["OrderServiceClient", "ProductServiceClient"]
