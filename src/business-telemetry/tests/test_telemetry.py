"""
Tests for Business Telemetry Service

Run with: pytest tests/ -v
"""

import asyncio
import json
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment
os.environ["FABRIC_TELEMETRY_ENABLED"] = "true"
os.environ["FABRIC_SINK_TYPE"] = "console"
os.environ["FABRIC_ENVIRONMENT"] = "test"

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from business_events import (
    BaseEvent,
    ProductEvent,
    OrderEvent,
    CustomerEvent,
    AdminEvent,
    AIEvent,
    EventType,
    EventSource,
    create_product_viewed_event,
    create_order_placed_event,
)
from fabric_sinks import (
    BaseSink,
    ConsoleSink,
    FileSink,
    CompositeSink,
    SinkResult,
    SinkType,
)
from telemetry_client import BusinessTelemetryClient
from config import FabricSettings, get_fabric_settings, reset_settings


# ========================================
# Event Model Tests
# ========================================

class TestBaseEvent:
    """Tests for BaseEvent dataclass."""

    def test_event_creation(self):
        """Test basic event creation."""
        event = BaseEvent(
            event_type="test.event",
            event_source="test-source"
        )

        assert event.event_type == "test.event"
        assert event.event_source == "test-source"
        assert event.event_id is not None
        assert event.event_time is not None

    def test_event_to_dict(self):
        """Test event serialization to dictionary."""
        event = BaseEvent(
            event_type="test.event",
            event_source="test-source",
            session_id="sess-123"
        )

        data = event.to_dict()

        assert data["event_type"] == "test.event"
        assert data["session_id"] == "sess-123"
        assert "event_id" in data

    def test_event_to_json(self):
        """Test event serialization to JSON."""
        event = BaseEvent(
            event_type="test.event",
            event_source="test-source"
        )

        json_str = event.to_json()
        data = json.loads(json_str)

        assert data["event_type"] == "test.event"


class TestProductEvent:
    """Tests for ProductEvent dataclass."""

    def test_product_viewed_event(self):
        """Test product viewed event creation."""
        event = ProductEvent(
            event_type=EventType.PRODUCT_VIEWED.value,
            event_source=EventSource.CUSTOMER_AGENT.value,
            product_id="prod-123",
            product_name="Test Widget",
            product_price=29.99
        )

        assert event.event_type == "product.viewed"
        assert event.product_id == "prod-123"
        assert event.product_price == 29.99

    def test_product_searched_event(self):
        """Test product searched event creation."""
        event = ProductEvent(
            event_type=EventType.PRODUCT_SEARCHED.value,
            event_source=EventSource.CUSTOMER_AGENT.value,
            search_query="widget",
            search_results_count=5,
            products_listed=["prod-1", "prod-2", "prod-3"]
        )

        assert event.search_query == "widget"
        assert event.search_results_count == 5
        assert len(event.products_listed) == 3


class TestOrderEvent:
    """Tests for OrderEvent dataclass."""

    def test_order_placed_event(self):
        """Test order placed event creation."""
        items = [
            {"product_id": "prod-1", "quantity": 2, "price": 10.00},
            {"product_id": "prod-2", "quantity": 1, "price": 20.00}
        ]

        event = OrderEvent(
            event_type=EventType.ORDER_PLACED.value,
            event_source=EventSource.ORDER_SERVICE.value,
            order_id="ord-123",
            order_items=items,
            order_total=40.00,
            item_count=3
        )

        assert event.order_id == "ord-123"
        assert event.order_total == 40.00
        assert event.item_count == 3


class TestEventFactories:
    """Tests for event factory functions."""

    def test_create_product_viewed_event(self):
        """Test product viewed factory function."""
        event = create_product_viewed_event(
            product_id="prod-123",
            product_name="Widget",
            source=EventSource.CUSTOMER_AGENT,
            session_id="sess-456"
        )

        assert event.event_type == EventType.PRODUCT_VIEWED.value
        assert event.product_id == "prod-123"
        assert event.session_id == "sess-456"

    def test_create_order_placed_event(self):
        """Test order placed factory function."""
        items = [{"product_id": "prod-1", "quantity": 1}]

        event = create_order_placed_event(
            order_id="ord-123",
            items=items,
            total=99.99,
            source=EventSource.ORDER_SERVICE,
            customer_name="John Doe"
        )

        assert event.event_type == EventType.ORDER_PLACED.value
        assert event.order_id == "ord-123"
        assert event.customer_name == "John Doe"


# ========================================
# Sink Tests
# ========================================

class TestConsoleSink:
    """Tests for ConsoleSink."""

    @pytest.mark.asyncio
    async def test_console_sink_send(self, capsys):
        """Test console sink output."""
        sink = ConsoleSink(pretty_print=False, batch_size=1)
        await sink.start()

        event = {"event_type": "test.event", "data": "test"}
        await sink.send(event)
        await sink.flush()

        await sink.stop()

        captured = capsys.readouterr()
        assert "test.event" in captured.out


class TestFileSink:
    """Tests for FileSink."""

    @pytest.mark.asyncio
    async def test_file_sink_write(self, tmp_path):
        """Test file sink writes events to files."""
        output_dir = tmp_path / "test_output"

        sink = FileSink(
            output_dir=str(output_dir),
            partition_by_type=True,
            partition_by_date=False,
            batch_size=1
        )
        await sink.start()

        event = {
            "event_type": "product.viewed",
            "product_id": "prod-123"
        }
        await sink.send(event)
        await sink.flush()

        await sink.stop()

        # Check file was created
        files = list(output_dir.rglob("*.jsonl"))
        assert len(files) >= 1

        # Check content
        with open(files[0]) as f:
            content = f.read()
            assert "product.viewed" in content


class TestCompositeSink:
    """Tests for CompositeSink."""

    @pytest.mark.asyncio
    async def test_composite_sink_routes_to_all(self):
        """Test composite sink sends to all child sinks."""
        mock_sink1 = AsyncMock(spec=BaseSink)
        mock_sink1.send_batch = AsyncMock(return_value=SinkResult(
            success=True, sink_type=SinkType.CONSOLE, events_sent=1
        ))

        mock_sink2 = AsyncMock(spec=BaseSink)
        mock_sink2.send_batch = AsyncMock(return_value=SinkResult(
            success=True, sink_type=SinkType.FILE, events_sent=1
        ))

        composite = CompositeSink(sinks=[mock_sink1, mock_sink2])

        events = [{"event_type": "test.event"}]
        await composite._send_batch_impl(events)

        mock_sink1.send_batch.assert_called_once()
        mock_sink2.send_batch.assert_called_once()


# ========================================
# Client Tests
# ========================================

class TestBusinessTelemetryClient:
    """Tests for BusinessTelemetryClient."""

    @pytest.fixture
    def mock_sink(self):
        """Create a mock sink for testing."""
        sink = AsyncMock(spec=BaseSink)
        sink.send = AsyncMock(return_value=True)
        sink.start = AsyncMock()
        sink.stop = AsyncMock()
        sink._buffer = []
        return sink

    @pytest.mark.asyncio
    async def test_client_initialization(self, mock_sink):
        """Test client initialization."""
        client = BusinessTelemetryClient(
            sink=mock_sink,
            environment="test",
            enabled=True
        )

        await client.start()

        assert client._started
        mock_sink.start.assert_called_once()

        await client.stop()

    @pytest.mark.asyncio
    async def test_client_emit_event(self, mock_sink):
        """Test emitting an event."""
        client = BusinessTelemetryClient(
            sink=mock_sink,
            default_source=EventSource.CUSTOMER_AGENT,
            environment="test",
            enabled=True
        )

        await client.start()

        result = await client.emit_product_viewed(
            product_id="prod-123",
            product_name="Widget"
        )

        assert result
        mock_sink.send.assert_called_once()

        # Check event was enriched
        call_args = mock_sink.send.call_args[0][0]
        assert call_args["event_source"] == "customer-agent"
        assert call_args["environment"] == "test"

        await client.stop()

    @pytest.mark.asyncio
    async def test_client_context_propagation(self, mock_sink):
        """Test context propagation to events."""
        client = BusinessTelemetryClient(
            sink=mock_sink,
            environment="test",
            enabled=True
        )

        await client.start()

        client.set_context(
            session_id="sess-123",
            user_id="user-456"
        )

        await client.emit_product_viewed(
            product_id="prod-789",
            product_name="Widget"
        )

        call_args = mock_sink.send.call_args[0][0]
        assert call_args["session_id"] == "sess-123"
        assert call_args["user_id"] == "user-456"

        await client.stop()

    @pytest.mark.asyncio
    async def test_client_disabled(self, mock_sink):
        """Test client when disabled."""
        client = BusinessTelemetryClient(
            sink=mock_sink,
            environment="test",
            enabled=False  # Disabled
        )

        await client.start()

        result = await client.emit_product_viewed(
            product_id="prod-123",
            product_name="Widget"
        )

        assert not result
        mock_sink.send.assert_not_called()

        await client.stop()

    @pytest.mark.asyncio
    async def test_session_context_manager(self, mock_sink):
        """Test session context manager."""
        client = BusinessTelemetryClient(
            sink=mock_sink,
            environment="test",
            enabled=True
        )

        await client.start()

        async with client.session_context(
            session_id="sess-123",
            emit_session_events=True
        ):
            await client.emit_product_viewed(
                product_id="prod-456",
                product_name="Widget"
            )

        # Should have emitted: session_started, product_viewed, session_ended
        assert mock_sink.send.call_count == 3

        await client.stop()


# ========================================
# Configuration Tests
# ========================================

class TestFabricSettings:
    """Tests for FabricSettings configuration."""

    def test_default_settings(self):
        """Test default settings values."""
        reset_settings()

        with patch.dict(os.environ, {}, clear=True):
            settings = FabricSettings()

            assert settings.telemetry_enabled
            assert settings.sink_type == "console"
            assert settings.environment == "production"

    def test_environment_override(self):
        """Test settings from environment variables."""
        reset_settings()

        env_vars = {
            "FABRIC_TELEMETRY_ENABLED": "false",
            "FABRIC_SINK_TYPE": "eventhub",
            "FABRIC_ENVIRONMENT": "staging"
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = FabricSettings()

            assert not settings.telemetry_enabled
            assert settings.sink_type == "eventhub"
            assert settings.environment == "staging"

    def test_event_hub_configured(self):
        """Test Event Hub configuration check."""
        reset_settings()

        env_vars = {
            "FABRIC_EVENT_HUB_CONNECTION_STRING": "Endpoint=sb://test...",
            "FABRIC_EVENT_HUB_NAME": "test-hub"
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = FabricSettings()

            assert settings.is_event_hub_configured()

    def test_onelake_configured(self):
        """Test OneLake configuration check."""
        reset_settings()

        env_vars = {
            "FABRIC_ONELAKE_WORKSPACE_ID": "workspace-123",
            "FABRIC_ONELAKE_LAKEHOUSE_ID": "lakehouse-456"
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = FabricSettings()

            assert settings.is_onelake_configured()


# ========================================
# Integration Tests
# ========================================

class TestIntegration:
    """Integration tests with real sinks."""

    @pytest.mark.asyncio
    async def test_end_to_end_console(self, capsys):
        """Test end-to-end flow with console sink."""
        reset_settings()

        sink = ConsoleSink(pretty_print=False, batch_size=1)
        client = BusinessTelemetryClient(
            sink=sink,
            default_source=EventSource.CUSTOMER_AGENT,
            environment="integration-test",
            enabled=True
        )

        await client.start()

        # Simulate a customer session
        async with client.session_context(session_id="integration-sess") as ctx:
            await client.emit_product_searched(
                query="laptop",
                results_count=10
            )

            await client.emit_product_viewed(
                product_id="laptop-123",
                product_name="Gaming Laptop",
                price=1299.99
            )

            await client.emit_order_placed(
                order_id="ord-integration-1",
                items=[{"product_id": "laptop-123", "quantity": 1}],
                total=1299.99,
                customer_name="Integration Test"
            )

        await client.stop()

        # Verify output
        captured = capsys.readouterr()
        assert "session_started" in captured.out or "customer.session_started" in captured.out
        assert "product.searched" in captured.out
        assert "product.viewed" in captured.out
        assert "order.placed" in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
