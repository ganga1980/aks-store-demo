"""
OpenTelemetry setup for the Customer Agent with Azure Monitor Application Insights.

This module configures OpenTelemetry with:
- Azure Monitor exporter for Application Insights integration
- Gen AI semantic conventions for LLM observability
- Custom span processors for agent tracing
- Metrics for Gen AI operations
- Content recording based on environment configuration

Implements OpenTelemetry semantic conventions for Generative AI:
https://opentelemetry.io/docs/specs/semconv/gen-ai/
"""

import logging
import os
import sys
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)

# Type variable for generic function decoration
F = TypeVar("F", bound=Callable[..., Any])

# Global instances
_tracer: Optional[trace.Tracer] = None
_meter: Optional[metrics.Meter] = None
_configured: bool = False


class GenAISpanProcessor(SpanProcessor):
    """
    Custom span processor that enriches spans with Gen AI semantic convention attributes.

    This processor adds standard Gen AI attributes to spans based on the
    OpenTelemetry semantic conventions for Generative AI systems.

    Additionally, it adds Kubernetes and cloud resource attributes to spans
    because Azure Monitor exporter does NOT forward custom Resource attributes
    to Application Insights customDimensions - only span attributes appear there.

    See: https://opentelemetry.io/docs/specs/semconv/gen-ai/
    """

    def __init__(
        self,
        service_name: str,
        provider_name: str = "azure.ai.inference",
        agent_name: Optional[str] = None,
    ):
        """
        Initialize the Gen AI span processor.

        Args:
            service_name: Name of the service
            provider_name: Gen AI provider name per semantic conventions
            agent_name: Name of the AI agent for gen_ai.agent.name/id attributes
        """
        self.service_name = service_name
        self.provider_name = provider_name
        self.agent_name = agent_name

        # Cache K8s/cloud attributes at initialization for efficiency
        # These don't change during the lifetime of the pod
        self._k8s_cloud_attrs: dict[str, Any] = {}
        self._k8s_attrs_loaded = False

        # Cache M365 agent ID for efficiency
        self._m365_agent_id: Optional[str] = None
        self._m365_agent_id_loaded = False

    def _get_m365_agent_id(self) -> str:
        """Get M365 agent ID (UUID format) for gen_ai.agent.id attribute."""
        if self._m365_agent_id_loaded:
            return self._m365_agent_id or self.agent_name

        try:
            from .m365_agent_integration import get_m365_agent_id_provider

            provider = get_m365_agent_id_provider(
                agent_name=self.agent_name,
                agent_type="customer",
            )
            self._m365_agent_id = provider.agent_id
            logger.debug(f"M365 agent ID loaded: {self._m365_agent_id}")
        except Exception as e:
            logger.warning(f"Failed to get M365 agent ID, using agent_name: {e}")
            self._m365_agent_id = self.agent_name

        self._m365_agent_id_loaded = True
        return self._m365_agent_id or self.agent_name

    def _load_k8s_cloud_attrs(self) -> None:
        """Load K8s and cloud attributes once (lazy initialization)."""
        if self._k8s_attrs_loaded:
            return

        try:
            from .k8s_semantics import get_all_resource_attributes, is_running_in_kubernetes

            if is_running_in_kubernetes():
                self._k8s_cloud_attrs = get_all_resource_attributes()
                logger.debug(f"Loaded {len(self._k8s_cloud_attrs)} K8s/cloud attributes for span enrichment")
        except ImportError:
            logger.debug("k8s_semantics module not available")
        except Exception as e:
            logger.warning(f"Failed to load K8s/cloud attributes: {e}")

        self._k8s_attrs_loaded = True

    def on_start(
        self,
        span: trace.Span,
        parent_context: Optional[Any] = None,
    ) -> None:
        """
        Add Gen AI and K8s/cloud attributes when a span starts.

        Follows semantic conventions for span attributes based on operation type.
        Also adds K8s/cloud attributes to ensure they appear in Azure Monitor
        Application Insights customDimensions.
        """
        span_name = span.name.lower() if hasattr(span, "name") else ""

        # Add K8s and cloud attributes to span
        # Azure Monitor exporter drops custom Resource attributes, so we must
        # add them as span attributes for them to appear in customDimensions
        self._load_k8s_cloud_attrs()
        for attr_name, attr_value in self._k8s_cloud_attrs.items():
            span.set_attribute(attr_name, attr_value)

        # Set agent identification attributes for correlation
        # These are critical for agent-specific issue correlation
        if self.agent_name:
            if not span.attributes.get("gen_ai.agent.name"):
                span.set_attribute("gen_ai.agent.name", self.agent_name)
            if not span.attributes.get("gen_ai.agent.id"):
                # Use M365 agent ID for gen_ai.agent.id (UUID format)
                m365_agent_id = self._get_m365_agent_id()
                span.set_attribute("gen_ai.agent.id", m365_agent_id)

        # Set provider name if not already set
        if not span.attributes.get("gen_ai.provider.name"):
            span.set_attribute("gen_ai.provider.name", self.provider_name)

        # Infer operation type from span name and add appropriate attributes
        if "create_agent" in span_name:
            if not span.attributes.get("gen_ai.operation.name"):
                span.set_attribute("gen_ai.operation.name", "create_agent")

        elif "invoke_agent" in span_name or "process_message" in span_name:
            if not span.attributes.get("gen_ai.operation.name"):
                span.set_attribute("gen_ai.operation.name", "invoke_agent")

        elif "execute_tool" in span_name or any(
            tool in span_name
            for tool in ["get_products", "place_order", "search_products", "get_order"]
        ):
            if not span.attributes.get("gen_ai.operation.name"):
                span.set_attribute("gen_ai.operation.name", "execute_tool")

        elif "chat" in span_name:
            if not span.attributes.get("gen_ai.operation.name"):
                span.set_attribute("gen_ai.operation.name", "chat")

    def on_end(self, span: trace.Span) -> None:
        """Process span when it ends (no-op for this processor)."""
        pass

    def shutdown(self) -> None:
        """Shutdown the processor."""
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush any pending spans."""
        return True


def configure_telemetry(
    service_name: str = "customer-agent",
    application_insights_connection_string: Optional[str] = None,
    provider_name: str = "azure.ai.inference",
    agent_name: Optional[str] = None,
) -> trace.Tracer:
    """
    Configure OpenTelemetry with Azure Monitor Application Insights.

    Sets up:
    - TracerProvider with Gen AI span processor
    - MeterProvider for Gen AI metrics
    - Azure Monitor exporter (if connection string provided)
    - Console exporter for local development
    - Kubernetes resource attributes (when running in K8s)

    Args:
        service_name: Name of the service for telemetry identification
        application_insights_connection_string: Azure Application Insights connection string
        provider_name: Gen AI provider name per semantic conventions
        agent_name: Name of the AI agent for gen_ai.agent.name/id attributes

    Returns:
        Configured OpenTelemetry tracer
    """
    global _tracer, _meter, _configured

    if _configured:
        return _tracer

    # Get connection string from environment if not provided
    conn_string = application_insights_connection_string or os.environ.get(
        "APPLICATIONINSIGHTS_CONNECTION_STRING"
    )

    # Build resource attributes
    resource_attrs = {
        ResourceAttributes.SERVICE_NAME: service_name,
        ResourceAttributes.SERVICE_VERSION: os.environ.get("APP_VERSION", "1.0.0"),
        ResourceAttributes.SERVICE_NAMESPACE: "aks-store-demo",
        "service.instance.id": os.environ.get("HOSTNAME", "local"),
        # Add Gen AI specific resource attributes
        "gen_ai.system": "azure_ai_foundry",
    }

    # Add Kubernetes and cloud attributes if running in K8s
    from .k8s_semantics import get_all_resource_attributes, is_running_in_kubernetes

    if is_running_in_kubernetes():
        k8s_attrs = get_all_resource_attributes()
        resource_attrs.update(k8s_attrs)
        logger.info(f"Running in Kubernetes, added {len(k8s_attrs)} resource attributes")

    # Create resource with service information
    resource = Resource.create(resource_attrs)

    # Create tracer provider
    tracer_provider = TracerProvider(resource=resource)

    # Add Gen AI span processor
    tracer_provider.add_span_processor(
        GenAISpanProcessor(service_name=service_name, provider_name=provider_name, agent_name=agent_name)
    )

    # Configure Azure Monitor exporter if connection string is available
    if conn_string:
        try:
            from azure.monitor.opentelemetry.exporter import (
                AzureMonitorMetricExporter,
                AzureMonitorTraceExporter,
            )

            # Add Azure Monitor trace exporter
            trace_exporter = AzureMonitorTraceExporter(connection_string=conn_string)
            tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))

            # Create metric exporter and reader
            metric_exporter = AzureMonitorMetricExporter(connection_string=conn_string)
            metric_reader = PeriodicExportingMetricReader(
                exporter=metric_exporter,
                export_interval_millis=60000,  # Export every 60 seconds
            )

            # Create meter provider with Azure Monitor exporter
            meter_provider = MeterProvider(
                resource=resource,
                metric_readers=[metric_reader],
            )
            metrics.set_meter_provider(meter_provider)

            logger.info("Azure Monitor telemetry configured successfully")

        except ImportError:
            logger.warning(
                "azure-monitor-opentelemetry-exporter not installed. "
                "Install with: pip install azure-monitor-opentelemetry-exporter"
            )
            _setup_console_exporters(tracer_provider, resource)
        except Exception as e:
            logger.error(f"Failed to configure Azure Monitor: {e}")
            _setup_console_exporters(tracer_provider, resource)
    else:
        _setup_console_exporters(tracer_provider, resource)

    # Set the tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Log content recording status
    content_recording = os.environ.get(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false"
    ).lower() == "true"

    if content_recording:
        logger.info("Gen AI content recording is ENABLED (may contain sensitive data)")
    else:
        logger.info("Gen AI content recording is DISABLED (default)")

    # Get tracer and meter
    _tracer = trace.get_tracer(
        instrumenting_module_name=service_name,
        instrumenting_library_version="1.0.0",
    )
    _meter = metrics.get_meter(
        name=service_name,
        version="1.0.0",
    )

    # Enable Azure AI Agents SDK telemetry if available
    try:
        from azure.ai.agents.telemetry import enable_telemetry

        enable_telemetry(destination=sys.stdout)
        logger.info("Azure AI Agents SDK telemetry enabled")
    except ImportError:
        logger.debug("Azure AI Agents SDK telemetry not available")
    except Exception as e:
        logger.warning(f"Failed to enable Azure AI Agents SDK telemetry: {e}")

    _configured = True
    return _tracer


def _setup_console_exporters(
    tracer_provider: TracerProvider,
    resource: Resource,
) -> None:
    """Set up console exporters for local development."""
    try:
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        # Add console span exporter
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        # Create meter provider with console exporter
        metric_reader = PeriodicExportingMetricReader(
            exporter=ConsoleMetricExporter(),
            export_interval_millis=60000,
        )
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )
        metrics.set_meter_provider(meter_provider)

        logger.info("Using console exporters (no Application Insights configured)")
    except Exception as e:
        logger.warning(f"Failed to configure console exporters: {e}")


def get_tracer() -> trace.Tracer:
    """
    Get the configured tracer instance.

    Returns:
        The configured OpenTelemetry tracer

    Raises:
        RuntimeError: If telemetry has not been configured
    """
    global _tracer
    if _tracer is None:
        _tracer = configure_telemetry()
    return _tracer


def get_meter() -> metrics.Meter:
    """
    Get the configured meter instance.

    Returns:
        The configured OpenTelemetry meter
    """
    global _meter
    if _meter is None:
        configure_telemetry()
    return _meter


def trace_function(name: Optional[str] = None) -> Callable[[F], F]:
    """
    Decorator to trace function calls with OpenTelemetry.

    This decorator creates spans for function calls and records:
    - Function parameters as span attributes
    - Return values as span attributes
    - M365 Agent ID as gen_ai.agent.id attribute
    - Exceptions as span events with proper error handling

    Args:
        name: Optional custom name for the span (defaults to function name)

    Returns:
        Decorated function with tracing enabled

    Example:
        @trace_function("process_order")
        async def place_order(customer_id: str, items: list) -> dict:
            ...
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                # Record function parameters (basic types only)
                _record_function_params(span, args, kwargs)
                # Add M365 agent ID for correlation
                _set_m365_agent_attributes(span)

                try:
                    result = await func(*args, **kwargs)
                    _record_function_result(span, result)
                    return result

                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute("error.type", type(e).__name__)
                    raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                # Record function parameters (basic types only)
                _record_function_params(span, args, kwargs)
                # Add M365 agent ID for correlation
                _set_m365_agent_attributes(span)

                try:
                    result = func(*args, **kwargs)
                    _record_function_result(span, result)
                    return result

                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute("error.type", type(e).__name__)
                    raise

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def _set_m365_agent_attributes(span: trace.Span) -> None:
    """Set M365 agent ID attributes on a span for correlation."""
    try:
        from .m365_agent_integration import get_m365_agent_id_provider
        from config import get_settings

        settings = get_settings()
        provider = get_m365_agent_id_provider(
            agent_name=settings.agent_name,
            agent_type="customer",
        )
        span.set_attribute("gen_ai.agent.id", provider.agent_id)
        span.set_attribute("gen_ai.agent.name", settings.agent_name)
    except Exception:
        # Silently ignore if M365 integration not available
        pass


def _record_function_params(span: trace.Span, args: tuple, kwargs: dict) -> None:
    """Record function parameters as span attributes."""
    for i, arg in enumerate(args):
        if isinstance(arg, (str, int, float, bool)):
            span.set_attribute(f"code.function.parameter.arg_{i}", str(arg))

    for key, value in kwargs.items():
        if isinstance(value, (str, int, float, bool)):
            span.set_attribute(f"code.function.parameter.{key}", str(value))


def _record_function_result(span: trace.Span, result: Any) -> None:
    """Record function result as span attributes."""
    if isinstance(result, (str, int, float, bool)):
        span.set_attribute("code.function.return.value", str(result))
    elif isinstance(result, dict):
        span.set_attribute("code.function.return.type", "dict")
        span.set_attribute("code.function.return.keys", str(list(result.keys())))
