"""
Example: Integrating Business Telemetry with Customer Agent

This example shows how to integrate the business telemetry SDK
with the customer-agent service.
"""

import asyncio
import os
import sys
import time

# Add the business-telemetry module to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sdk import (
    init_telemetry,
    shutdown_telemetry,
    set_telemetry_context,
    emit_product_viewed,
    emit_product_searched,
    emit_order_placed,
    emit_customer_query,
    emit_session_started,
    emit_session_ended,
    emit_ai_recommendation,
)
from business_events import EventSource


async def simulate_customer_session():
    """Simulate a typical customer interaction session."""

    # Initialize telemetry
    os.environ["FABRIC_SINK_TYPE"] = "console"  # Use console for demo
    os.environ["FABRIC_SERVICE_NAME"] = "customer-agent"

    await init_telemetry(source=EventSource.CUSTOMER_AGENT)

    # Start session
    session_id = "demo-session-001"
    await emit_session_started(session_id=session_id, user_id="demo-user")

    # Set context for subsequent events
    set_telemetry_context(session_id=session_id, user_id="demo-user")

    print("\n🛒 Starting customer session simulation...\n")

    # Customer asks about products
    start_time = time.time()
    await emit_customer_query(
        query_text="What laptops do you have?",
        response_time_ms=int((time.time() - start_time) * 1000) + 150,  # Simulated
        ai_model="gpt-4o",
        ai_tokens=250,
        intent="product_search"
    )
    print("📝 Emitted: customer.query (laptop search)")
    await asyncio.sleep(0.5)

    # AI provides recommendation
    await emit_ai_recommendation(
        model_name="gpt-4o",
        request_type="product_recommendation",
        input_tokens=150,
        output_tokens=200,
        recommendation_accepted=True,
        latency_ms=180
    )
    print("🤖 Emitted: ai.recommendation")
    await asyncio.sleep(0.5)

    # Customer searches for products
    await emit_product_searched(
        query="gaming laptop",
        results_count=5,
        product_ids=["laptop-001", "laptop-002", "laptop-003", "laptop-004", "laptop-005"],
        ai_assisted=True
    )
    print("🔍 Emitted: product.searched (5 results)")
    await asyncio.sleep(0.5)

    # Customer views a product
    await emit_product_viewed(
        product_id="laptop-001",
        product_name="Pro Gaming Laptop 15",
        category="Electronics",
        price=1499.99,
        ai_assisted=True
    )
    print("👀 Emitted: product.viewed (Pro Gaming Laptop)")
    await asyncio.sleep(0.5)

    # Customer places an order
    await emit_order_placed(
        order_id="order-demo-001",
        items=[
            {"product_id": "laptop-001", "product_name": "Pro Gaming Laptop 15", "quantity": 1, "price": 1499.99}
        ],
        total=1499.99,
        customer_name="Demo Customer",
        ai_assisted=True
    )
    print("💰 Emitted: order.placed ($1499.99)")
    await asyncio.sleep(0.5)

    # End session
    await emit_session_ended(
        session_id=session_id,
        user_id="demo-user",
        duration_ms=15000,
        interaction_count=5
    )
    print("👋 Emitted: customer.session_ended")

    # Shutdown
    await shutdown_telemetry()

    print("\n✅ Customer session simulation complete!")
    print("\nIn production, these events would be sent to:")
    print("  - Azure Event Hubs → Fabric Real-Time Analytics")
    print("  - OneLake → Fabric Lakehouse")


if __name__ == "__main__":
    asyncio.run(simulate_customer_session())
