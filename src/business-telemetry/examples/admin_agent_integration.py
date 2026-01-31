"""
Example: Integrating Business Telemetry with Admin Agent

This example shows how to integrate the business telemetry SDK
with the admin-agent service for tracking administrative actions.
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
    emit_inventory_updated,
    emit_product_created,
    emit_product_updated,
    emit_products_listed,
    emit_ai_content_generated,
    emit_session_started,
    emit_session_ended,
)
from business_events import EventSource


async def simulate_admin_session():
    """Simulate a typical admin management session."""

    # Initialize telemetry
    os.environ["FABRIC_SINK_TYPE"] = "console"  # Use console for demo
    os.environ["FABRIC_SERVICE_NAME"] = "admin-agent"

    await init_telemetry(source=EventSource.ADMIN_AGENT)

    # Start admin session
    session_id = "admin-session-001"
    await emit_session_started(session_id=session_id, user_id="admin-user")

    set_telemetry_context(session_id=session_id, user_id="admin-user")

    print("\n🔧 Starting admin session simulation...\n")

    # Admin lists products
    await emit_products_listed(
        product_ids=["prod-001", "prod-002", "prod-003", "prod-004", "prod-005"],
        page=1,
        page_size=10
    )
    print("📋 Emitted: product.listed (5 products)")
    await asyncio.sleep(0.5)

    # Admin updates inventory
    await emit_inventory_updated(
        product_id="prod-001",
        product_name="Wireless Mouse",
        previous_qty=50,
        new_qty=100,
        admin_user="admin-user",
        reason="Restocking"
    )
    print("📦 Emitted: admin.inventory_updated (+50 units)")
    await asyncio.sleep(0.5)

    # Admin creates new product with AI-generated description
    await emit_ai_content_generated(
        model_name="gpt-4o",
        content_type="product_description",
        input_tokens=80,
        output_tokens=150,
        content_used=True,
        latency_ms=200
    )
    print("🤖 Emitted: ai.description_generated")
    await asyncio.sleep(0.3)

    await emit_product_created(
        product_id="prod-new-001",
        product_name="Ultra HD Webcam Pro",
        admin_user="admin-user",
        ai_assisted=True,
        ai_content="Professional 4K webcam with advanced low-light correction..."
    )
    print("✨ Emitted: admin.product_created (AI-assisted)")
    await asyncio.sleep(0.5)

    # Admin updates product pricing
    await emit_product_updated(
        product_id="prod-002",
        product_name="Mechanical Keyboard",
        changes={"price": {"old": 79.99, "new": 69.99}},
        admin_user="admin-user",
        ai_assisted=False
    )
    print("✏️ Emitted: admin.product_updated (price change)")
    await asyncio.sleep(0.5)

    # End admin session
    await emit_session_ended(
        session_id=session_id,
        user_id="admin-user",
        duration_ms=30000,
        interaction_count=5
    )
    print("👋 Emitted: admin.session_ended")

    # Shutdown
    await shutdown_telemetry()

    print("\n✅ Admin session simulation complete!")
    print("\nBusiness insights that can be derived:")
    print("  - Inventory turnover rates")
    print("  - AI adoption in content creation")
    print("  - Admin productivity metrics")
    print("  - Price change impact analysis")


if __name__ == "__main__":
    asyncio.run(simulate_admin_session())
