"""
OpenTelemetry Gen AI Semantic Conventions implementation.

This module implements the OpenTelemetry semantic conventions for Generative AI systems
as defined at: https://opentelemetry.io/docs/specs/semconv/gen-ai/

Implements:
- Gen AI span attributes for agent operations (create_agent, invoke_agent, execute_tool)
- Gen AI metrics (gen_ai.client.token.usage, gen_ai.client.operation.duration)
- Proper span naming conventions
- Content recording (opt-in)
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar
from urllib.parse import urlparse

from opentelemetry import metrics, trace
from opentelemetry.trace import SpanKind, Status, StatusCode

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class GenAIOperationName(str, Enum):
    """Standard Gen AI operation names per semantic conventions."""

    CHAT = "chat"
    CREATE_AGENT = "create_agent"
    EMBEDDINGS = "embeddings"
    EXECUTE_TOOL = "execute_tool"
    GENERATE_CONTENT = "generate_content"
    INVOKE_AGENT = "invoke_agent"
    TEXT_COMPLETION = "text_completion"


class GenAIProviderName(str, Enum):
    """Standard Gen AI provider names per semantic conventions."""

    ANTHROPIC = "anthropic"
    AWS_BEDROCK = "aws.bedrock"
    AZURE_AI_INFERENCE = "azure.ai.inference"
    AZURE_AI_OPENAI = "azure.ai.openai"
    COHERE = "cohere"
    DEEPSEEK = "deepseek"
    GCP_GEMINI = "gcp.gemini"
    GCP_GEN_AI = "gcp.gen_ai"
    GCP_VERTEX_AI = "gcp.vertex_ai"
    GROQ = "groq"
    IBM_WATSONX_AI = "ibm.watsonx.ai"
    MISTRAL_AI = "mistral_ai"
    OPENAI = "openai"
    PERPLEXITY = "perplexity"
    X_AI = "x_ai"


class GenAITokenType(str, Enum):
    """Token types for usage metrics."""

    INPUT = "input"
    OUTPUT = "output"


class GenAIOutputType(str, Enum):
    """Output types for Gen AI responses."""

    IMAGE = "image"
    JSON = "json"
    SPEECH = "speech"
    TEXT = "text"


class GenAIToolType(str, Enum):
    """Tool types for execute_tool operations."""

    FUNCTION = "function"
    EXTENSION = "extension"
    DATASTORE = "datastore"


@dataclass
class GenAISpanAttributes:
    """
    Container for Gen AI span attributes following semantic conventions.

    See: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/
    """

    # Required attributes
    operation_name: str
    provider_name: str = GenAIProviderName.AZURE_AI_INFERENCE.value

    # Conditionally required
    error_type: Optional[str] = None
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    agent_description: Optional[str] = None
    conversation_id: Optional[str] = None  # thread_id
    request_model: Optional[str] = None
    output_type: Optional[str] = None

    # Recommended
    response_id: Optional[str] = None
    response_model: Optional[str] = None
    response_finish_reasons: Optional[list[str]] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    request_temperature: Optional[float] = None
    request_max_tokens: Optional[int] = None
    request_top_p: Optional[float] = None

    # Server attributes
    server_address: Optional[str] = None
    server_port: Optional[int] = None

    # Tool-specific (for execute_tool)
    tool_name: Optional[str] = None
    tool_type: Optional[str] = None
    tool_description: Optional[str] = None
    tool_call_id: Optional[str] = None

    # Opt-in content recording
    input_messages: Optional[Any] = None
    output_messages: Optional[Any] = None
    system_instructions: Optional[Any] = None
    tool_definitions: Optional[Any] = None
    tool_call_arguments: Optional[Any] = None
    tool_call_result: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert attributes to OpenTelemetry span attributes dict."""
        attrs = {
            "gen_ai.operation.name": self.operation_name,
            "gen_ai.provider.name": self.provider_name,
        }

        # Add optional attributes if set
        if self.error_type:
            attrs["error.type"] = self.error_type
        if self.agent_id:
            attrs["gen_ai.agent.id"] = self.agent_id
        if self.agent_name:
            attrs["gen_ai.agent.name"] = self.agent_name
        if self.agent_description:
            attrs["gen_ai.agent.description"] = self.agent_description
        if self.conversation_id:
            attrs["gen_ai.conversation.id"] = self.conversation_id
        if self.request_model:
            attrs["gen_ai.request.model"] = self.request_model
        if self.output_type:
            attrs["gen_ai.output.type"] = self.output_type
        if self.response_id:
            attrs["gen_ai.response.id"] = self.response_id
        if self.response_model:
            attrs["gen_ai.response.model"] = self.response_model
        if self.response_finish_reasons:
            attrs["gen_ai.response.finish_reasons"] = self.response_finish_reasons
        if self.input_tokens is not None:
            attrs["gen_ai.usage.input_tokens"] = self.input_tokens
        if self.output_tokens is not None:
            attrs["gen_ai.usage.output_tokens"] = self.output_tokens
        if self.request_temperature is not None:
            attrs["gen_ai.request.temperature"] = self.request_temperature
        if self.request_max_tokens is not None:
            attrs["gen_ai.request.max_tokens"] = self.request_max_tokens
        if self.request_top_p is not None:
            attrs["gen_ai.request.top_p"] = self.request_top_p
        if self.server_address:
            attrs["server.address"] = self.server_address
        if self.server_port:
            attrs["server.port"] = self.server_port

        # Tool-specific attributes
        if self.tool_name:
            attrs["gen_ai.tool.name"] = self.tool_name
        if self.tool_type:
            attrs["gen_ai.tool.type"] = self.tool_type
        if self.tool_description:
            attrs["gen_ai.tool.description"] = self.tool_description
        if self.tool_call_id:
            attrs["gen_ai.tool.call.id"] = self.tool_call_id

        return attrs


@dataclass
class GenAIMetricsData:
    """Container for Gen AI metrics data."""

    operation_name: str
    provider_name: str
    request_model: Optional[str] = None
    response_model: Optional[str] = None
    server_address: Optional[str] = None
    server_port: Optional[int] = None
    error_type: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    duration_seconds: Optional[float] = None
    # Agent identification for correlation
    agent_name: Optional[str] = None
    agent_id: Optional[str] = None
    # Conversation/session tracking
    conversation_id: Optional[str] = None


class GenAITelemetry:
    """
    OpenTelemetry Gen AI telemetry implementation.

    Provides instrumentation following OpenTelemetry semantic conventions
    for Generative AI systems.
    """

    # Metric bucket boundaries per spec
    TOKEN_USAGE_BUCKETS = [
        1, 4, 16, 64, 256, 1024, 4096, 16384, 65536,
        262144, 1048576, 4194304, 16777216, 67108864
    ]
    DURATION_BUCKETS = [
        0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28,
        2.56, 5.12, 10.24, 20.48, 40.96, 81.92
    ]

    def __init__(
        self,
        service_name: str = "customer-agent",
        provider_name: str = GenAIProviderName.AZURE_AI_INFERENCE.value,
    ):
        """
        Initialize Gen AI telemetry.

        Args:
            service_name: Name of the service for telemetry
            provider_name: Gen AI provider name (e.g., azure.ai.inference)
        """
        self.service_name = service_name
        self.provider_name = provider_name

        # Check if content recording is enabled
        self.record_content = os.environ.get(
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false"
        ).lower() == "true"

        # Cache K8s/cloud attributes for metrics (loaded lazily)
        self._k8s_cloud_attrs: dict[str, Any] = {}
        self._k8s_attrs_loaded = False

        # Get tracer and meter
        self._tracer = trace.get_tracer(
            instrumenting_module_name="gen_ai_telemetry",
            instrumenting_library_version="1.0.0",
        )
        self._meter = metrics.get_meter(
            name="gen_ai_telemetry",
            version="1.0.0",
        )

        # Initialize metrics
        self._init_metrics()

    def _init_metrics(self) -> None:
        """Initialize Gen AI metrics per semantic conventions."""
        # Token usage histogram
        self._token_usage_histogram = self._meter.create_histogram(
            name="gen_ai.client.token.usage",
            description="Number of input and output tokens used",
            unit="{token}",
        )

        # Operation duration histogram
        self._operation_duration_histogram = self._meter.create_histogram(
            name="gen_ai.client.operation.duration",
            description="GenAI operation duration",
            unit="s",
        )

        # Request counter - Golden Signal: Traffic
        self._request_counter = self._meter.create_counter(
            name="gen_ai.client.request.count",
            description="Number of GenAI requests made",
            unit="{request}",
        )

        # Error counter - Golden Signal: Errors
        self._error_counter = self._meter.create_counter(
            name="gen_ai.client.error.count",
            description="Number of GenAI requests that resulted in errors",
            unit="{error}",
        )

        # Active sessions gauge - Golden Signal: Saturation
        self._active_sessions_gauge = self._meter.create_up_down_counter(
            name="gen_ai.client.active_sessions",
            description="Number of active agent sessions",
            unit="{session}",
        )

    def _load_k8s_cloud_attrs(self) -> None:
        """Load K8s and cloud attributes once (lazy initialization).

        These attributes are cached at first access for efficiency since
        they don't change during the lifetime of the pod.
        """
        if self._k8s_attrs_loaded:
            return

        try:
            from .k8s_semantics import get_all_resource_attributes, is_running_in_kubernetes

            if is_running_in_kubernetes():
                self._k8s_cloud_attrs = get_all_resource_attributes()
                logger.debug(f"Loaded {len(self._k8s_cloud_attrs)} K8s/cloud attributes for metrics")
        except ImportError:
            logger.debug("k8s_semantics module not available for metrics")
        except Exception as e:
            logger.warning(f"Failed to load K8s/cloud attributes for metrics: {e}")

        self._k8s_attrs_loaded = True

    def _get_metric_attributes(self, data: GenAIMetricsData) -> dict[str, Any]:
        """Get common metric attributes including K8s and cloud attributes."""
        # Load K8s/cloud attributes (cached after first load)
        self._load_k8s_cloud_attrs()

        # Start with K8s/cloud attributes for infrastructure correlation
        attrs = dict(self._k8s_cloud_attrs)

        # Add Gen AI specific attributes
        attrs["gen_ai.operation.name"] = data.operation_name
        attrs["gen_ai.provider.name"] = data.provider_name

        if data.request_model:
            attrs["gen_ai.request.model"] = data.request_model
        if data.response_model:
            attrs["gen_ai.response.model"] = data.response_model
        if data.server_address:
            attrs["server.address"] = data.server_address
        if data.server_port:
            attrs["server.port"] = data.server_port
        if data.error_type:
            attrs["error.type"] = data.error_type
        # Add agent identification attributes for correlation
        if data.agent_name:
            attrs["gen_ai.agent.name"] = data.agent_name
        if data.agent_id:
            attrs["gen_ai.agent.id"] = data.agent_id
        if data.conversation_id:
            attrs["gen_ai.conversation.id"] = data.conversation_id
        return attrs

    def record_token_usage(
        self,
        data: GenAIMetricsData,
    ) -> None:
        """
        Record token usage metrics.

        Records gen_ai.client.token.usage histogram for both input and output tokens.
        """
        base_attrs = self._get_metric_attributes(data)

        if data.input_tokens is not None:
            self._token_usage_histogram.record(
                data.input_tokens,
                attributes={**base_attrs, "gen_ai.token.type": GenAITokenType.INPUT.value},
            )

        if data.output_tokens is not None:
            self._token_usage_histogram.record(
                data.output_tokens,
                attributes={**base_attrs, "gen_ai.token.type": GenAITokenType.OUTPUT.value},
            )

    def record_operation_duration(
        self,
        data: GenAIMetricsData,
    ) -> None:
        """
        Record operation duration metric.

        Records gen_ai.client.operation.duration histogram.
        """
        if data.duration_seconds is not None:
            attrs = self._get_metric_attributes(data)
            self._operation_duration_histogram.record(
                data.duration_seconds,
                attributes=attrs,
            )

    def record_request(
        self,
        data: GenAIMetricsData,
    ) -> None:
        """
        Record a request metric.

        Golden Signal: Traffic - Records gen_ai.client.request.count counter.
        Call this at the START of each request.
        """
        attrs = self._get_metric_attributes(data)
        self._request_counter.add(1, attributes=attrs)

    def record_error_metric(
        self,
        data: GenAIMetricsData,
    ) -> None:
        """
        Record an error metric.

        Golden Signal: Errors - Records gen_ai.client.error.count counter.
        Call this when an error occurs during request processing.
        """
        attrs = self._get_metric_attributes(data)
        self._error_counter.add(1, attributes=attrs)

    def record_session_start(
        self,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        """
        Record the start of an agent session.

        Golden Signal: Saturation - Increments gen_ai.client.active_sessions gauge.
        Call this when a new chat session starts.
        """
        # Load K8s/cloud attributes for infrastructure correlation
        self._load_k8s_cloud_attrs()
        attrs = dict(self._k8s_cloud_attrs)

        attrs["gen_ai.provider.name"] = self.provider_name
        if agent_name:
            attrs["gen_ai.agent.name"] = agent_name
        if agent_id:
            attrs["gen_ai.agent.id"] = agent_id
        self._active_sessions_gauge.add(1, attributes=attrs)

    def record_session_end(
        self,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> None:
        """
        Record the end of an agent session.

        Golden Signal: Saturation - Decrements gen_ai.client.active_sessions gauge.
        Call this when a chat session ends.
        """
        # Load K8s/cloud attributes for infrastructure correlation
        self._load_k8s_cloud_attrs()
        attrs = dict(self._k8s_cloud_attrs)

        attrs["gen_ai.provider.name"] = self.provider_name
        if agent_name:
            attrs["gen_ai.agent.name"] = agent_name
        if agent_id:
            attrs["gen_ai.agent.id"] = agent_id
        self._active_sessions_gauge.add(-1, attributes=attrs)

    def create_agent_span(
        self,
        agent_name: str,
        model: str,
        instructions: Optional[str] = None,
        server_endpoint: Optional[str] = None,
    ):
        """
        Create a span for agent creation operation.

        Span name: create_agent {gen_ai.agent.name}
        Span kind: CLIENT

        Args:
            agent_name: Human-readable agent name
            model: Model deployment name
            instructions: System instructions for the agent
            server_endpoint: Server endpoint URL

        Returns:
            Context manager for the span
        """
        span_name = f"{GenAIOperationName.CREATE_AGENT.value} {agent_name}"

        # Parse server endpoint
        server_address = None
        server_port = None
        if server_endpoint:
            parsed = urlparse(server_endpoint)
            server_address = parsed.hostname
            server_port = parsed.port or (443 if parsed.scheme == "https" else 80)

        attrs = GenAISpanAttributes(
            operation_name=GenAIOperationName.CREATE_AGENT.value,
            provider_name=self.provider_name,
            agent_name=agent_name,
            request_model=model,
            server_address=server_address,
            server_port=server_port,
        )

        # Add system instructions if content recording is enabled
        if self.record_content and instructions:
            attrs.system_instructions = json.dumps([
                {"type": "text", "content": instructions}
            ])

        return self._tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=attrs.to_dict(),
        )

    def invoke_agent_span(
        self,
        agent_name: str,
        agent_id: str,
        model: str,
        conversation_id: str,
        server_endpoint: Optional[str] = None,
    ):
        """
        Create a span for agent invocation operation.

        Span name: invoke_agent {gen_ai.agent.name}
        Span kind: CLIENT

        Args:
            agent_name: Human-readable agent name
            agent_id: Unique agent identifier
            model: Model deployment name
            conversation_id: Thread/conversation ID
            server_endpoint: Server endpoint URL

        Returns:
            Context manager for the span
        """
        span_name = f"{GenAIOperationName.INVOKE_AGENT.value} {agent_name}"

        # Parse server endpoint
        server_address = None
        server_port = None
        if server_endpoint:
            parsed = urlparse(server_endpoint)
            server_address = parsed.hostname
            server_port = parsed.port or (443 if parsed.scheme == "https" else 80)

        attrs = GenAISpanAttributes(
            operation_name=GenAIOperationName.INVOKE_AGENT.value,
            provider_name=self.provider_name,
            agent_id=agent_id,
            agent_name=agent_name,
            request_model=model,
            conversation_id=conversation_id,
            output_type=GenAIOutputType.TEXT.value,
            server_address=server_address,
            server_port=server_port,
        )

        return self._tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=attrs.to_dict(),
        )

    def execute_tool_span(
        self,
        tool_name: str,
        tool_description: Optional[str] = None,
        tool_type: str = GenAIToolType.FUNCTION.value,
        tool_call_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ):
        """
        Create a span for tool execution operation.

        Span name: execute_tool {gen_ai.tool.name}
        Span kind: INTERNAL

        Args:
            tool_name: Name of the tool being executed
            tool_description: Description of what the tool does
            tool_type: Type of tool (function, extension, datastore)
            tool_call_id: Unique identifier for this tool call
            conversation_id: Thread/conversation ID for correlation
            agent_id: Unique agent identifier (M365 Agent ID)
            agent_name: Human-readable name of the agent

        Returns:
            Context manager for the span
        """
        span_name = f"{GenAIOperationName.EXECUTE_TOOL.value} {tool_name}"

        attrs = GenAISpanAttributes(
            operation_name=GenAIOperationName.EXECUTE_TOOL.value,
            provider_name=self.provider_name,
            tool_name=tool_name,
            tool_type=tool_type,
            tool_description=tool_description,
            tool_call_id=tool_call_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            agent_name=agent_name,
        )

        return self._tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.INTERNAL,
            attributes=attrs.to_dict(),
        )

    def set_span_response_attributes(
        self,
        span: trace.Span,
        response_id: Optional[str] = None,
        response_model: Optional[str] = None,
        finish_reasons: Optional[list[str]] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
    ) -> None:
        """
        Set response attributes on a span.

        Args:
            span: The span to update
            response_id: Unique response identifier
            response_model: Model that generated the response
            finish_reasons: Reasons the model stopped generating
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
        """
        if response_id:
            span.set_attribute("gen_ai.response.id", response_id)
        if response_model:
            span.set_attribute("gen_ai.response.model", response_model)
        if finish_reasons:
            span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
        if input_tokens is not None:
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        if output_tokens is not None:
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)

    def set_span_input_messages(
        self,
        span: trace.Span,
        messages: list[dict[str, Any]],
    ) -> None:
        """
        Set input messages on a span (opt-in).

        Only records if OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT is enabled.

        Args:
            span: The span to update
            messages: Input messages in Gen AI semantic conventions format
        """
        if self.record_content:
            span.set_attribute("gen_ai.input.messages", json.dumps(messages))

    def set_span_output_messages(
        self,
        span: trace.Span,
        messages: list[dict[str, Any]],
    ) -> None:
        """
        Set output messages on a span (opt-in).

        Only records if OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT is enabled.

        Args:
            span: The span to update
            messages: Output messages in Gen AI semantic conventions format
        """
        if self.record_content:
            span.set_attribute("gen_ai.output.messages", json.dumps(messages))

    def set_tool_call_attributes(
        self,
        span: trace.Span,
        arguments: Optional[dict[str, Any]] = None,
        result: Optional[Any] = None,
    ) -> None:
        """
        Set tool call arguments and result on a span (opt-in).

        Only records if OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT is enabled.

        Args:
            span: The span to update
            arguments: Arguments passed to the tool
            result: Result returned by the tool
        """
        if self.record_content:
            if arguments:
                span.set_attribute("gen_ai.tool.call.arguments", json.dumps(arguments))
            if result is not None:
                if isinstance(result, str):
                    span.set_attribute("gen_ai.tool.call.result", result)
                else:
                    span.set_attribute("gen_ai.tool.call.result", json.dumps(result))

    def record_error(
        self,
        span: trace.Span,
        error: Exception,
        error_type: Optional[str] = None,
    ) -> None:
        """
        Record an error on a span following Gen AI conventions.

        Args:
            span: The span to update
            error: The exception that occurred
            error_type: Error type (defaults to exception class name)
        """
        error_type = error_type or type(error).__name__
        span.set_attribute("error.type", error_type)
        span.record_exception(error)
        span.set_status(Status(StatusCode.ERROR, str(error)))


def create_gen_ai_tool_decorator(
    telemetry: GenAITelemetry,
    tool_name: str,
    tool_description: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Callable[[F], F]:
    """
    Create a decorator for Gen AI tool functions.

    This decorator wraps tool functions with proper Gen AI telemetry
    following the execute_tool semantic conventions.

    Args:
        telemetry: GenAITelemetry instance
        tool_name: Name of the tool
        tool_description: Description of what the tool does
        conversation_id: Thread/conversation ID for correlation

    Returns:
        Decorator function
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()

            with telemetry.execute_tool_span(
                tool_name=tool_name,
                tool_description=tool_description or func.__doc__,
                conversation_id=conversation_id,
            ) as span:
                # Record arguments
                telemetry.set_tool_call_attributes(span, arguments=kwargs or None)

                try:
                    result = await func(*args, **kwargs)

                    # Record result
                    telemetry.set_tool_call_attributes(span, result=result)

                    # Record duration metric
                    duration = time.perf_counter() - start_time
                    telemetry.record_operation_duration(
                        GenAIMetricsData(
                            operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                            provider_name=telemetry.provider_name,
                            duration_seconds=duration,
                        )
                    )

                    return result

                except Exception as e:
                    telemetry.record_error(span, e)
                    raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()

            with telemetry.execute_tool_span(
                tool_name=tool_name,
                tool_description=tool_description or func.__doc__,
                conversation_id=conversation_id,
            ) as span:
                # Record arguments
                telemetry.set_tool_call_attributes(span, arguments=kwargs or None)

                try:
                    result = func(*args, **kwargs)

                    # Record result
                    telemetry.set_tool_call_attributes(span, result=result)

                    # Record duration metric
                    duration = time.perf_counter() - start_time
                    telemetry.record_operation_duration(
                        GenAIMetricsData(
                            operation_name=GenAIOperationName.EXECUTE_TOOL.value,
                            provider_name=telemetry.provider_name,
                            duration_seconds=duration,
                        )
                    )

                    return result

                except Exception as e:
                    telemetry.record_error(span, e)
                    raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


# Global telemetry instance
_gen_ai_telemetry: Optional[GenAITelemetry] = None


def get_gen_ai_telemetry(
    service_name: str = "customer-agent",
    provider_name: str = GenAIProviderName.AZURE_AI_INFERENCE.value,
) -> GenAITelemetry:
    """
    Get or create the global Gen AI telemetry instance.

    Args:
        service_name: Name of the service
        provider_name: Gen AI provider name

    Returns:
        GenAITelemetry instance
    """
    global _gen_ai_telemetry
    if _gen_ai_telemetry is None:
        _gen_ai_telemetry = GenAITelemetry(
            service_name=service_name,
            provider_name=provider_name,
        )
    return _gen_ai_telemetry
