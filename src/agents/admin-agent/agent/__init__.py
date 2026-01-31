"""Agent module containing tools and the admin agent implementation."""

from .tools import (
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
    get_agent_tools,
    user_functions,
)
from .admin_agent import AdminAgent

__all__ = [
    "AdminAgent",
    "get_products",
    "get_product_details",
    "add_product",
    "update_product",
    "delete_product",
    "get_orders",
    "get_order_details",
    "update_order_status",
    "complete_order",
    "start_processing_order",
    "get_agent_tools",
    "user_functions",
]
