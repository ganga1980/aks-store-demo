"""
Business Telemetry HTTP API Service

FastAPI-based HTTP service for receiving business telemetry events from
applications that cannot use the SDK directly (e.g., frontend apps,
third-party integrations).

Endpoints:
    POST /events         - Submit single event
    POST /events/batch   - Submit batch of events
    GET  /health         - Health check
    GET  /ready          - Readiness check
    GET  /metrics        - Prometheus metrics
"""

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union

from fastapi import FastAPI, HTTPException, Depends, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

from config import get_fabric_settings, get_service_settings, FabricSettings, ServiceSettings
from business_events import (
    BaseEvent,
    ProductEvent,
    OrderEvent,
    CustomerEvent,
    AdminEvent,
    AIEvent,
    EventType,
)
from telemetry_client import BusinessTelemetryClient
from fabric_sinks import (
    EventHubSink,
    OneLakeSink,
    ConsoleSink,
    FileSink,
    CompositeSink,
    create_sink_from_config,
)

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ========================================
# Request/Response Models
# ========================================

class EventRequest(BaseModel):
    """Single event submission request."""

    event_type: str = Field(..., description="Event type (e.g., product.viewed)")
    event_source: Optional[str] = Field(None, description="Source application")

    # Context
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    correlation_id: Optional[str] = None

    # Event-specific data
    data: Dict[str, Any] = Field(default_factory=dict, description="Event-specific payload")

    # Custom properties
    custom_properties: Dict[str, Any] = Field(default_factory=dict)


class BatchEventRequest(BaseModel):
    """Batch event submission request."""

    events: List[EventRequest] = Field(..., min_length=1, max_length=1000)


class EventResponse(BaseModel):
    """Event submission response."""

    success: bool
    event_id: str
    message: str = "Event accepted"


class BatchEventResponse(BaseModel):
    """Batch event submission response."""

    success: bool
    events_accepted: int
    events_failed: int
    message: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    version: str
    timestamp: str


class MetricsResponse(BaseModel):
    """Metrics response."""

    events_received: int
    events_sent: int
    events_failed: int
    uptime_seconds: float
    buffer_size: int


# ========================================
# Application State
# ========================================

class AppState:
    """Application state container."""

    def __init__(self):
        self.telemetry_client: Optional[BusinessTelemetryClient] = None
        self.start_time: float = time.time()
        self.events_received: int = 0
        self.events_sent: int = 0
        self.events_failed: int = 0


app_state = AppState()


# ========================================
# Lifespan Management
# ========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""

    # Startup
    logger.info("Starting Business Telemetry Service...")

    settings = get_fabric_settings()

    # Create appropriate sink based on configuration
    if settings.sink_type == "eventhub" and settings.is_event_hub_configured():
        sink = EventHubSink(
            connection_string=settings.event_hub_connection_string,
            event_hub_name=settings.event_hub_name,
            batch_size=settings.batch_size,
            flush_interval_seconds=settings.flush_interval_seconds
        )
        logger.info("Configured Event Hub sink")

    elif settings.sink_type == "onelake" and settings.is_onelake_configured():
        sink = OneLakeSink(
            workspace_id=settings.onelake_workspace_id,
            lakehouse_id=settings.onelake_lakehouse_id,
            base_path=settings.onelake_base_path,
            output_format=settings.onelake_output_format,
            batch_size=settings.batch_size,
            flush_interval_seconds=settings.flush_interval_seconds
        )
        logger.info("Configured OneLake sink")

    elif settings.sink_type == "file":
        sink = FileSink(
            output_dir=settings.file_output_dir,
            batch_size=settings.batch_size,
            flush_interval_seconds=settings.flush_interval_seconds
        )
        logger.info("Configured File sink")

    elif settings.sink_type == "composite":
        sinks = []
        for sink_type in (settings.composite_sinks or "console").split(","):
            sink_type = sink_type.strip().lower()
            if sink_type == "console":
                sinks.append(ConsoleSink())
            elif sink_type == "file":
                sinks.append(FileSink(output_dir=settings.file_output_dir))
        sink = CompositeSink(sinks=sinks)
        logger.info(f"Configured Composite sink with {len(sinks)} sub-sinks")

    else:
        sink = ConsoleSink(pretty_print=True)
        logger.info("Configured Console sink (default)")

    # Initialize telemetry client
    app_state.telemetry_client = BusinessTelemetryClient(
        sink=sink,
        environment=settings.environment,
        service_version=settings.service_version,
        enabled=settings.telemetry_enabled
    )

    await app_state.telemetry_client.start()
    logger.info("Business Telemetry Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Business Telemetry Service...")

    if app_state.telemetry_client:
        await app_state.telemetry_client.stop()

    logger.info("Business Telemetry Service stopped")


# ========================================
# FastAPI Application
# ========================================

def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    settings = get_fabric_settings()
    service_settings = get_service_settings()

    app = FastAPI(
        title="Business Telemetry Service",
        description="Microsoft Fabric Business Telemetry Ingestion Service",
        version=service_settings.service_version,
        lifespan=lifespan
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


app = create_app()


# ========================================
# Authentication Dependency
# ========================================

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify API key if configured."""
    settings = get_fabric_settings()

    if settings.api_key:
        if not x_api_key or x_api_key != settings.api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return True


# ========================================
# API Endpoints
# ========================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    service_settings = get_service_settings()

    return HealthResponse(
        status="healthy",
        service=service_settings.service_name,
        version=service_settings.service_version,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/ready", response_model=HealthResponse, tags=["Health"])
async def readiness_check():
    """Readiness check endpoint."""
    service_settings = get_service_settings()

    # Check if telemetry client is ready
    if not app_state.telemetry_client or not app_state.telemetry_client._started:
        raise HTTPException(status_code=503, detail="Service not ready")

    return HealthResponse(
        status="ready",
        service=service_settings.service_name,
        version=service_settings.service_version,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@app.get("/metrics", tags=["Monitoring"])
async def get_metrics():
    """Prometheus-compatible metrics endpoint."""

    uptime = time.time() - app_state.start_time
    buffer_size = 0

    if app_state.telemetry_client and app_state.telemetry_client.sink:
        buffer_size = len(app_state.telemetry_client.sink._buffer)

    # Prometheus format
    metrics = f"""# HELP business_telemetry_events_received_total Total events received
# TYPE business_telemetry_events_received_total counter
business_telemetry_events_received_total {app_state.events_received}

# HELP business_telemetry_events_sent_total Total events sent to sink
# TYPE business_telemetry_events_sent_total counter
business_telemetry_events_sent_total {app_state.events_sent}

# HELP business_telemetry_events_failed_total Total events failed
# TYPE business_telemetry_events_failed_total counter
business_telemetry_events_failed_total {app_state.events_failed}

# HELP business_telemetry_uptime_seconds Service uptime in seconds
# TYPE business_telemetry_uptime_seconds gauge
business_telemetry_uptime_seconds {uptime:.2f}

# HELP business_telemetry_buffer_size Current buffer size
# TYPE business_telemetry_buffer_size gauge
business_telemetry_buffer_size {buffer_size}
"""

    return Response(content=metrics, media_type="text/plain")


@app.post("/events", response_model=EventResponse, tags=["Events"])
async def submit_event(
    request: EventRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Submit a single business event.

    The event will be validated, enriched with server-side metadata,
    and forwarded to the configured sink (Event Hub, OneLake, etc.).
    """

    if not app_state.telemetry_client:
        raise HTTPException(status_code=503, detail="Service not initialized")

    app_state.events_received += 1

    try:
        # Create event based on type
        event_data = {
            "event_type": request.event_type,
            "event_source": request.event_source or "http-api",
            "session_id": request.session_id,
            "user_id": request.user_id,
            "correlation_id": request.correlation_id,
            "custom_properties": request.custom_properties,
            **request.data
        }

        # Determine event class based on type
        event_type = request.event_type.lower()

        if event_type.startswith("product."):
            event = ProductEvent(**event_data)
        elif event_type.startswith("order."):
            event = OrderEvent(**event_data)
        elif event_type.startswith("customer.") or event_type.startswith("session."):
            event = CustomerEvent(**event_data)
        elif event_type.startswith("admin."):
            event = AdminEvent(**event_data)
        elif event_type.startswith("ai."):
            event = AIEvent(**event_data)
        else:
            event = BaseEvent(**event_data)

        # Emit event
        success = await app_state.telemetry_client.emit(event)

        if success:
            app_state.events_sent += 1
            return EventResponse(
                success=True,
                event_id=event.event_id,
                message="Event accepted"
            )
        else:
            app_state.events_failed += 1
            raise HTTPException(status_code=500, detail="Failed to process event")

    except HTTPException:
        raise
    except Exception as e:
        app_state.events_failed += 1
        logger.error(f"Error processing event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/events/batch", response_model=BatchEventResponse, tags=["Events"])
async def submit_batch(
    request: BatchEventRequest,
    authenticated: bool = Depends(verify_api_key)
):
    """
    Submit a batch of business events.

    More efficient than submitting events individually.
    Maximum batch size: 1000 events.
    """

    if not app_state.telemetry_client:
        raise HTTPException(status_code=503, detail="Service not initialized")

    app_state.events_received += len(request.events)

    accepted = 0
    failed = 0

    events_to_emit = []

    for event_request in request.events:
        try:
            event_data = {
                "event_type": event_request.event_type,
                "event_source": event_request.event_source or "http-api",
                "session_id": event_request.session_id,
                "user_id": event_request.user_id,
                "correlation_id": event_request.correlation_id,
                "custom_properties": event_request.custom_properties,
                **event_request.data
            }

            event_type = event_request.event_type.lower()

            if event_type.startswith("product."):
                event = ProductEvent(**event_data)
            elif event_type.startswith("order."):
                event = OrderEvent(**event_data)
            elif event_type.startswith("customer.") or event_type.startswith("session."):
                event = CustomerEvent(**event_data)
            elif event_type.startswith("admin."):
                event = AdminEvent(**event_data)
            elif event_type.startswith("ai."):
                event = AIEvent(**event_data)
            else:
                event = BaseEvent(**event_data)

            events_to_emit.append(event)
            accepted += 1

        except Exception as e:
            logger.warning(f"Failed to create event: {e}")
            failed += 1

    # Emit batch
    if events_to_emit:
        try:
            success = await app_state.telemetry_client.emit_batch(events_to_emit)
            if success:
                app_state.events_sent += accepted
            else:
                app_state.events_failed += accepted
                failed += accepted
                accepted = 0
        except Exception as e:
            logger.error(f"Failed to emit batch: {e}")
            app_state.events_failed += accepted
            failed += accepted
            accepted = 0

    return BatchEventResponse(
        success=failed == 0,
        events_accepted=accepted,
        events_failed=failed,
        message=f"Processed {accepted + failed} events"
    )


@app.post("/flush", tags=["Operations"])
async def flush_buffer(authenticated: bool = Depends(verify_api_key)):
    """Force flush the event buffer to the sink."""

    if not app_state.telemetry_client:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        result = await app_state.telemetry_client.sink.flush()
        return {
            "success": result.success,
            "events_flushed": result.events_sent,
            "message": result.error_message or "Buffer flushed successfully"
        }
    except Exception as e:
        logger.error(f"Failed to flush buffer: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Main Entry Point
# ========================================

def main():
    """Run the service."""
    settings = get_fabric_settings()

    logger.info(f"Starting server on {settings.api_host}:{settings.api_port}")

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=os.getenv("RELOAD", "false").lower() == "true",
        log_level=settings.log_level.lower()
    )


if __name__ == "__main__":
    main()
