"""
Business Telemetry Client

Main client interface for emitting business telemetry events to Microsoft Fabric.
Provides both synchronous and asynchronous APIs for easy integration with
various application frameworks.

Usage:
    # Initialize client
    client = BusinessTelemetryClient.from_env()
    await client.start()

    # Emit events
    await client.emit_product_viewed(product_id="123", product_name="Widget")
    await client.emit_order_placed(order_id="456", items=[...], total=99.99)

    # Shutdown
    await client.stop()
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from functools import wraps
import threading

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
    create_product_searched_event,
    create_order_placed_event,
    create_session_started_event,
    create_customer_query_event,
    create_inventory_updated_event,
)
from fabric_sinks import (
    BaseSink,
    EventHubSink,
    OneLakeSink,
    ConsoleSink,
    FileSink,
    CompositeSink,
    SinkType,
    create_sink_from_config,
)

logger = logging.getLogger(__name__)


class BusinessTelemetryClient:
    """
    Main client for business telemetry collection and ingestion.

    Features:
    - Multiple sink support (Event Hub, OneLake, Console, File)
    - Automatic batching and flushing
    - Context propagation (session_id, correlation_id, user_id)
    - Async-first with sync wrappers
    - Graceful shutdown with buffer flush

    Configuration via environment variables:
        FABRIC_TELEMETRY_ENABLED: Enable/disable telemetry (default: true)
        FABRIC_SINK_TYPE: Sink type (eventhub, onelake, console, file)
        FABRIC_EVENT_HUB_CONNECTION_STRING: Event Hub connection string
        FABRIC_EVENT_HUB_NAME: Event Hub name
        FABRIC_ONELAKE_WORKSPACE_ID: OneLake workspace ID
        FABRIC_ONELAKE_LAKEHOUSE_ID: OneLake lakehouse ID
        FABRIC_ENVIRONMENT: Environment name (default: production)
        FABRIC_SERVICE_NAME: Service name for event source
        FABRIC_SERVICE_VERSION: Service version
    """

    _instance: Optional["BusinessTelemetryClient"] = None
    _lock = threading.Lock()

    def __init__(
        self,
        sink: BaseSink,
        default_source: Optional[EventSource] = None,
        environment: str = "production",
        service_version: str = "1.0.0",
        enabled: bool = True
    ):
        self.sink = sink
        self.default_source = default_source
        self.environment = environment
        self.service_version = service_version
        self.enabled = enabled

        # Context for correlation
        self._session_id: Optional[str] = None
        self._user_id: Optional[str] = None
        self._correlation_id: Optional[str] = None

        # Customer context for KQL entity correlation
        self._customer_id: Optional[str] = None
        self._customer_name: Optional[str] = None
        self._customer_email: Optional[str] = None
        self._channel: Optional[str] = None

        # Fabric-Pulse infrastructure context for correlation
        self._agent_id: Optional[str] = None
        self._agent_session_id: Optional[str] = None
        self._workload_id: Optional[str] = None
        self._cluster_id: Optional[str] = None
        self._namespace: Optional[str] = None
        self._pod_name: Optional[str] = None
        self._deployment_name: Optional[str] = None

        self._started = False

    @classmethod
    def get_instance(cls) -> Optional["BusinessTelemetryClient"]:
        """Get the singleton instance if initialized."""
        return cls._instance

    @classmethod
    def from_env(cls) -> "BusinessTelemetryClient":
        """
        Create client from environment variables.

        Returns singleton instance - subsequent calls return same instance.
        """
        with cls._lock:
            if cls._instance is not None:
                return cls._instance

            enabled = os.getenv("FABRIC_TELEMETRY_ENABLED", "true").lower() == "true"
            sink_type = os.getenv("FABRIC_SINK_TYPE", "console").lower()
            environment = os.getenv("FABRIC_ENVIRONMENT", "production")
            service_name = os.getenv("FABRIC_SERVICE_NAME", "unknown")
            service_version = os.getenv("FABRIC_SERVICE_VERSION", "1.0.0")

            # Determine default source from service name
            source_map = {
                "customer-agent": EventSource.CUSTOMER_AGENT,
                "admin-agent": EventSource.ADMIN_AGENT,
                "store-front": EventSource.STORE_FRONT,
                "store-admin": EventSource.STORE_ADMIN,
                "order-service": EventSource.ORDER_SERVICE,
                "product-service": EventSource.PRODUCT_SERVICE,
            }
            default_source = source_map.get(service_name)

            # Create appropriate sink
            if sink_type == "eventhub":
                connection_string = os.getenv("FABRIC_EVENT_HUB_CONNECTION_STRING")
                event_hub_name = os.getenv("FABRIC_EVENT_HUB_NAME")

                if not connection_string:
                    logger.warning("Event Hub connection string not set, falling back to console")
                    sink = ConsoleSink()
                else:
                    sink = EventHubSink(
                        connection_string=connection_string,
                        event_hub_name=event_hub_name,
                        batch_size=int(os.getenv("FABRIC_BATCH_SIZE", "100")),
                        flush_interval_seconds=float(os.getenv("FABRIC_FLUSH_INTERVAL", "5.0"))
                    )

            elif sink_type == "onelake":
                workspace_id = os.getenv("FABRIC_ONELAKE_WORKSPACE_ID")
                lakehouse_id = os.getenv("FABRIC_ONELAKE_LAKEHOUSE_ID")

                if not workspace_id or not lakehouse_id:
                    logger.warning("OneLake workspace/lakehouse not set, falling back to console")
                    sink = ConsoleSink()
                else:
                    sink = OneLakeSink(
                        workspace_id=workspace_id,
                        lakehouse_id=lakehouse_id,
                        batch_size=int(os.getenv("FABRIC_BATCH_SIZE", "1000")),
                        flush_interval_seconds=float(os.getenv("FABRIC_FLUSH_INTERVAL", "60.0"))
                    )

            elif sink_type == "file":
                sink = FileSink(
                    output_dir=os.getenv("FABRIC_OUTPUT_DIR", "./business_telemetry_output"),
                    batch_size=int(os.getenv("FABRIC_BATCH_SIZE", "100")),
                    flush_interval_seconds=float(os.getenv("FABRIC_FLUSH_INTERVAL", "10.0"))
                )

            elif sink_type == "composite":
                # Parse comma-separated sink configs
                sinks = []
                for sub_type in os.getenv("FABRIC_COMPOSITE_SINKS", "console").split(","):
                    sub_type = sub_type.strip().lower()
                    if sub_type == "console":
                        sinks.append(ConsoleSink())
                    elif sub_type == "file":
                        sinks.append(FileSink())
                    # Add more as needed
                sink = CompositeSink(sinks=sinks)

            else:
                sink = ConsoleSink(
                    pretty_print=os.getenv("FABRIC_PRETTY_PRINT", "true").lower() == "true"
                )

            cls._instance = cls(
                sink=sink,
                default_source=default_source,
                environment=environment,
                service_version=service_version,
                enabled=enabled
            )

            return cls._instance

    async def start(self):
        """Start the telemetry client and underlying sink."""
        if not self.enabled:
            logger.info("Business telemetry is disabled")
            return

        if self._started:
            return

        await self.sink.start()
        self._started = True
        logger.info(f"Business telemetry client started (sink: {self.sink.sink_type.value})")

    async def stop(self):
        """Stop the client and flush remaining events."""
        if not self._started:
            return

        await self.sink.stop()
        self._started = False
        logger.info("Business telemetry client stopped")

    def set_context(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        correlation_id: Optional[str] = None
    ):
        """Set context for subsequent events."""
        if session_id is not None:
            self._session_id = session_id
        if user_id is not None:
            self._user_id = user_id
        if correlation_id is not None:
            self._correlation_id = correlation_id

    def set_infrastructure_context(
        self,
        agent_id: Optional[str] = None,
        agent_session_id: Optional[str] = None,
        workload_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        namespace: Optional[str] = None,
        pod_name: Optional[str] = None,
        deployment_name: Optional[str] = None,
    ):
        """
        Set Fabric-Pulse infrastructure context for correlation.

        These fields enable correlation between business events and
        infrastructure/agent entities in Fabric-Pulse Ontology.

        Args:
            agent_id: AgentId format: {ClusterId}/{Namespace}/agents/{AgentName}
            agent_session_id: AgentSessionId format: {AgentId}/sessions/{SessionId}
            workload_id: WorkloadId format: {ClusterId}/{Namespace}/{ControllerName}
            cluster_id: Azure resource ID of the AKS cluster (cloud.resource_id)
            namespace: Kubernetes namespace (k8s.namespace.name)
            pod_name: Kubernetes pod name (k8s.pod.name)
            deployment_name: Kubernetes deployment name (k8s.deployment.name)
        """
        if agent_id is not None:
            self._agent_id = agent_id
        if agent_session_id is not None:
            self._agent_session_id = agent_session_id
        if workload_id is not None:
            self._workload_id = workload_id
        if cluster_id is not None:
            self._cluster_id = cluster_id
        if namespace is not None:
            self._namespace = namespace
        if pod_name is not None:
            self._pod_name = pod_name
        if deployment_name is not None:
            self._deployment_name = deployment_name

    def set_customer_context(
        self,
        customer_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        channel: Optional[str] = None,
    ):
        """
        Set customer context for all business events.

        These fields are automatically added to ALL events for KQL entity correlation.

        Args:
            customer_id: Unique customer identifier
            customer_name: Customer display name
            customer_email: Customer email address
            channel: Channel identifier (Web, CustomerAgent, AdminAgent, API)
        """
        if customer_id is not None:
            self._customer_id = customer_id
        if customer_name is not None:
            self._customer_name = customer_name
        if customer_email is not None:
            self._customer_email = customer_email
        if channel is not None:
            self._channel = channel

    def clear_context(self):
        """Clear the current context."""
        self._session_id = None
        self._user_id = None
        self._correlation_id = None

    def clear_customer_context(self):
        """Clear the customer context."""
        self._customer_id = None
        self._customer_name = None
        self._customer_email = None
        self._channel = None

    def clear_infrastructure_context(self):
        """Clear the infrastructure context."""
        self._agent_id = None
        self._agent_session_id = None
        self._workload_id = None
        self._cluster_id = None
        self._namespace = None
        self._pod_name = None
        self._deployment_name = None

    @asynccontextmanager
    async def session_context(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        emit_session_events: bool = True
    ):
        """
        Context manager for session-scoped telemetry.

        Automatically emits session_started and session_ended events.
        """
        self.set_context(session_id=session_id, user_id=user_id)

        if emit_session_events:
            await self.emit_session_started(session_id=session_id, user_id=user_id)

        start_time = datetime.now(timezone.utc)
        try:
            yield self
        finally:
            if emit_session_events:
                duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                await self.emit_session_ended(
                    session_id=session_id,
                    user_id=user_id,
                    duration_ms=duration_ms
                )
            self.clear_context()

    def _enrich_event(self, event: BaseEvent) -> BaseEvent:
        """Add context and defaults to event."""
        # Session/user context
        if not event.session_id and self._session_id:
            event.session_id = self._session_id
        if not event.user_id and self._user_id:
            event.user_id = self._user_id
        if not event.correlation_id and self._correlation_id:
            event.correlation_id = self._correlation_id
        if not event.event_source and self.default_source:
            event.event_source = self.default_source.value

        # Customer context (applied to ALL events for KQL entity correlation)
        if not event.customer_id and self._customer_id:
            event.customer_id = self._customer_id
        if not event.customer_name and self._customer_name:
            event.customer_name = self._customer_name
        if not event.customer_email and self._customer_email:
            event.customer_email = self._customer_email
        if not event.channel and self._channel:
            event.channel = self._channel

        # Fabric-Pulse infrastructure context
        if not event.agent_id and self._agent_id:
            event.agent_id = self._agent_id
        if not event.agent_session_id and self._agent_session_id:
            event.agent_session_id = self._agent_session_id
        if not event.workload_id and self._workload_id:
            event.workload_id = self._workload_id
        if not event.cluster_id and self._cluster_id:
            event.cluster_id = self._cluster_id
        if not event.namespace and self._namespace:
            event.namespace = self._namespace
        if not event.pod_name and self._pod_name:
            event.pod_name = self._pod_name
        if not event.deployment_name and self._deployment_name:
            event.deployment_name = self._deployment_name

        event.environment = self.environment
        event.service_version = self.service_version

        return event

    async def emit(self, event: BaseEvent) -> bool:
        """
        Emit a business event.

        Args:
            event: Event to emit

        Returns:
            True if event was queued successfully
        """
        if not self.enabled:
            return False

        event = self._enrich_event(event)
        return await self.sink.send(event.to_dict())

    async def emit_batch(self, events: List[BaseEvent]) -> bool:
        """Emit a batch of events."""
        if not self.enabled:
            return False

        enriched = [self._enrich_event(e).to_dict() for e in events]
        result = await self.sink.send_batch(enriched)
        return result.success

    # ========================================
    # Product Events
    # ========================================

    async def emit_product_viewed(
        self,
        product_id: str,
        product_name: str,
        category: Optional[str] = None,
        price: Optional[float] = None,
        ai_assisted: bool = False,
        **kwargs
    ) -> bool:
        """Emit product viewed event."""
        event = ProductEvent(
            event_type=EventType.PRODUCT_VIEWED.value,
            product_id=product_id,
            product_name=product_name,
            product_category=category,
            product_price=price,
            ai_assisted=ai_assisted,
            **kwargs
        )
        return await self.emit(event)

    async def emit_product_searched(
        self,
        query: str,
        results_count: int,
        product_ids: Optional[List[str]] = None,
        ai_assisted: bool = False,
        **kwargs
    ) -> bool:
        """Emit product searched event."""
        event = ProductEvent(
            event_type=EventType.PRODUCT_SEARCHED.value,
            search_query=query,
            search_results_count=results_count,
            products_listed=product_ids,
            ai_assisted=ai_assisted,
            **kwargs
        )
        return await self.emit(event)

    async def emit_products_listed(
        self,
        product_ids: List[str],
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        **kwargs
    ) -> bool:
        """Emit products listed event."""
        event = ProductEvent(
            event_type=EventType.PRODUCT_LISTED.value,
            products_listed=product_ids,
            listing_page=page,
            listing_page_size=page_size,
            **kwargs
        )
        return await self.emit(event)

    # ========================================
    # Order Events
    # ========================================

    async def emit_order_placed(
        self,
        order_id: str,
        items: List[Dict[str, Any]],
        total: float,
        customer_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        channel: Optional[str] = None,
        ai_assisted: bool = False,
        **kwargs
    ) -> bool:
        """Emit order placed event with full customer and channel context."""
        event = OrderEvent(
            event_type=EventType.ORDER_PLACED.value,
            order_id=order_id,
            order_items=items,
            order_total=total,
            item_count=len(items),
            customer_id=customer_id,
            customer_name=customer_name,
            customer_email=customer_email,
            channel=channel,
            order_placed_at=datetime.now(timezone.utc).isoformat(),
            ai_assisted=ai_assisted,
            **kwargs
        )
        return await self.emit(event)

    async def emit_order_status_checked(
        self,
        order_id: str,
        status: str,
        **kwargs
    ) -> bool:
        """Emit order status checked event."""
        event = OrderEvent(
            event_type=EventType.ORDER_STATUS_CHECKED.value,
            order_id=order_id,
            order_status=status,
            **kwargs
        )
        return await self.emit(event)

    async def emit_order_completed(
        self,
        order_id: str,
        processing_duration_ms: Optional[int] = None,
        **kwargs
    ) -> bool:
        """Emit order completed event."""
        event = OrderEvent(
            event_type=EventType.ORDER_COMPLETED.value,
            order_id=order_id,
            order_status="completed",
            order_completed_at=datetime.now(timezone.utc).isoformat(),
            processing_duration_ms=processing_duration_ms,
            **kwargs
        )
        return await self.emit(event)

    # ========================================
    # Customer Events
    # ========================================

    async def emit_session_started(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Emit session started event."""
        event = CustomerEvent(
            event_type=EventType.SESSION_STARTED.value,
            session_id=session_id,
            user_id=user_id,
            **kwargs
        )
        return await self.emit(event)

    async def emit_session_ended(
        self,
        session_id: str,
        duration_ms: Optional[int] = None,
        interaction_count: Optional[int] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Emit session ended event."""
        event = CustomerEvent(
            event_type=EventType.SESSION_ENDED.value,
            session_id=session_id,
            user_id=user_id,
            session_duration_ms=duration_ms,
            interaction_count=interaction_count,
            **kwargs
        )
        return await self.emit(event)

    async def emit_customer_query(
        self,
        query_text: str,
        response_time_ms: Optional[int] = None,
        ai_model: Optional[str] = None,
        ai_tokens: Optional[int] = None,
        intent: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Emit customer query event."""
        event = CustomerEvent(
            event_type=EventType.CUSTOMER_QUERY.value,
            query_text=query_text,
            response_time_ms=response_time_ms,
            ai_model=ai_model,
            ai_tokens_used=ai_tokens,
            query_intent=intent,
            **kwargs
        )
        return await self.emit(event)

    # ========================================
    # Admin Events
    # ========================================

    async def emit_inventory_updated(
        self,
        product_id: str,
        product_name: str,
        previous_qty: int,
        new_qty: int,
        admin_user: Optional[str] = None,
        reason: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Emit inventory updated event."""
        event = AdminEvent(
            event_type=EventType.INVENTORY_UPDATED.value,
            product_id=product_id,
            product_name=product_name,
            previous_quantity=previous_qty,
            new_quantity=new_qty,
            quantity_change=new_qty - previous_qty,
            admin_user=admin_user,
            change_reason=reason,
            **kwargs
        )
        return await self.emit(event)

    async def emit_product_created(
        self,
        product_id: str,
        product_name: str,
        admin_user: Optional[str] = None,
        ai_assisted: bool = False,
        ai_content: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Emit product created event."""
        event = AdminEvent(
            event_type=EventType.PRODUCT_CREATED.value,
            product_id=product_id,
            product_name=product_name,
            admin_user=admin_user,
            ai_assisted=ai_assisted,
            ai_generated_content=ai_content,
            **kwargs
        )
        return await self.emit(event)

    async def emit_product_creation_failed(
        self,
        product_name: str,
        error_message: str,
        error_code: Optional[str] = None,
        admin_user: Optional[str] = None,
        ai_assisted: bool = False,
        **kwargs
    ) -> bool:
        """Emit product creation failed event."""
        event = AdminEvent(
            event_type=EventType.PRODUCT_CREATION_FAILED.value,
            product_name=product_name,
            admin_user=admin_user,
            ai_assisted=ai_assisted,
            change_reason=error_message,
            change_description=f"Error Code: {error_code}" if error_code else None,
            **kwargs
        )
        return await self.emit(event)

    async def emit_product_updated(
        self,
        product_id: str,
        product_name: str,
        changes: Optional[Dict[str, Any]] = None,
        admin_user: Optional[str] = None,
        ai_assisted: bool = False,
        **kwargs
    ) -> bool:
        """Emit product updated event."""
        event = AdminEvent(
            event_type=EventType.PRODUCT_UPDATED.value,
            product_id=product_id,
            product_name=product_name,
            admin_user=admin_user,
            ai_assisted=ai_assisted,
            change_description=str(changes) if changes else None,
            **kwargs
        )
        return await self.emit(event)

    # ========================================
    # AI Events
    # ========================================

    async def emit_ai_recommendation(
        self,
        model_name: str,
        request_type: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        recommendation_accepted: Optional[bool] = None,
        latency_ms: Optional[int] = None,
        **kwargs
    ) -> bool:
        """Emit AI recommendation event."""
        total_tokens = None
        if input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens

        event = AIEvent(
            event_type=EventType.AI_RECOMMENDATION.value,
            model_name=model_name,
            request_type=request_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            recommendation_accepted=recommendation_accepted,
            response_latency_ms=latency_ms,
            **kwargs
        )
        return await self.emit(event)

    async def emit_ai_content_generated(
        self,
        model_name: str,
        content_type: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        content_used: Optional[bool] = None,
        latency_ms: Optional[int] = None,
        **kwargs
    ) -> bool:
        """Emit AI content generation event."""
        total_tokens = None
        if input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens

        event = AIEvent(
            event_type=EventType.AI_DESCRIPTION_GENERATED.value,
            model_name=model_name,
            request_type=content_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            content_used=content_used,
            response_latency_ms=latency_ms,
            **kwargs
        )
        return await self.emit(event)


# Synchronous wrapper for non-async code
class SyncBusinessTelemetryClient:
    """
    Synchronous wrapper for BusinessTelemetryClient.

    Useful for integration with synchronous frameworks or
    callback-based code.
    """

    def __init__(self, async_client: BusinessTelemetryClient):
        self._client = async_client
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop for sync operations."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run(self, coro):
        """Run coroutine synchronously."""
        loop = self._get_loop()
        return loop.run_until_complete(coro)

    def start(self):
        """Start the client."""
        self._run(self._client.start())

    def stop(self):
        """Stop the client."""
        self._run(self._client.stop())

    def emit_product_viewed(self, **kwargs) -> bool:
        return self._run(self._client.emit_product_viewed(**kwargs))

    def emit_product_searched(self, **kwargs) -> bool:
        return self._run(self._client.emit_product_searched(**kwargs))

    def emit_order_placed(self, **kwargs) -> bool:
        return self._run(self._client.emit_order_placed(**kwargs))

    def emit_customer_query(self, **kwargs) -> bool:
        return self._run(self._client.emit_customer_query(**kwargs))

    def emit_inventory_updated(self, **kwargs) -> bool:
        return self._run(self._client.emit_inventory_updated(**kwargs))


# Global helper functions for easy access
_global_client: Optional[BusinessTelemetryClient] = None


def init_business_telemetry() -> BusinessTelemetryClient:
    """Initialize global business telemetry client from environment."""
    global _global_client
    _global_client = BusinessTelemetryClient.from_env()
    return _global_client


def get_business_telemetry() -> Optional[BusinessTelemetryClient]:
    """Get the global business telemetry client."""
    return _global_client or BusinessTelemetryClient.get_instance()


async def emit_business_event(event: BaseEvent) -> bool:
    """Emit a business event using the global client."""
    client = get_business_telemetry()
    if client:
        return await client.emit(event)
    return False
