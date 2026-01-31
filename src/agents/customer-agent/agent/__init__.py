"""Agent module containing tools and the customer agent implementation."""

from .tools import (
    get_products,
    get_product_details,
    search_products,
    place_order,
    get_order_status,
    get_agent_tools,
    user_functions,
)
from .customer_agent import CustomerAgent

__all__ = [
    "CustomerAgent",
    "get_products",
    "get_product_details",
    "search_products",
    "place_order",
    "get_order_status",
    "get_agent_tools",
    "user_functions",
]
