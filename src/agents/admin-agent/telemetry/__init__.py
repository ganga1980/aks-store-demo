"""
Telemetry module for OpenTelemetry with Gen AI semantic conventions.

This module provides comprehensive telemetry following OpenTelemetry
semantic conventions for Generative AI systems:
https://opentelemetry.io/docs/specs/semconv/gen-ai/

Components:
- otel_setup: Core OpenTelemetry configuration with Azure Monitor
- gen_ai_semantics: Gen AI semantic conventions implementation
- k8s_semantics: Kubernetes and cloud semantic conventions
- m365_agent_integration: Microsoft 365 Agents SDK integration for agent IDs

Signals implemented:
- Spans: create_agent, invoke_agent, execute_tool operations
- Metrics: gen_ai.client.token.usage, gen_ai.client.operation.duration
- Attributes: Full Gen AI attribute set per semantic conventions
- K8s Attributes: Pod, node, deployment, cluster attributes
- Cloud Attributes: Provider, platform, region, resource ID
- M365 Agent Attributes: Unique agent ID, conversation ID, activity ID
"""

from .gen_ai_semantics import (
    GenAIMetricsData,
    GenAIOperationName,
    GenAIOutputType,
    GenAIProviderName,
    GenAISpanAttributes,
    GenAITelemetry,
    GenAITokenType,
    GenAIToolType,
    create_gen_ai_tool_decorator,
    get_gen_ai_telemetry,
)
from .k8s_semantics import (
    CloudAttributes,
    K8sAttributes,
    get_all_resource_attributes,
    get_cloud_attributes,
    get_k8s_attributes,
    is_running_in_kubernetes,
    set_all_resource_attributes,
    set_cloud_attributes,
    set_k8s_attributes,
)
from .m365_agent_integration import (
    M365AgentIdentity,
    M365AgentIdProvider,
    get_m365_agent_id_provider,
    is_m365_sdk_available,
)
from .otel_setup import (
    configure_telemetry,
    get_meter,
    get_tracer,
    trace_function,
)

__all__ = [
    # Core telemetry
    "configure_telemetry",
    "get_tracer",
    "get_meter",
    "trace_function",
    # Gen AI semantic conventions
    "GenAITelemetry",
    "GenAISpanAttributes",
    "GenAIMetricsData",
    "GenAIOperationName",
    "GenAIProviderName",
    "GenAITokenType",
    "GenAIOutputType",
    "GenAIToolType",
    "get_gen_ai_telemetry",
    "create_gen_ai_tool_decorator",
    # Kubernetes semantic conventions
    "K8sAttributes",
    "CloudAttributes",
    "get_k8s_attributes",
    "get_cloud_attributes",
    "get_all_resource_attributes",
    "set_k8s_attributes",
    "set_cloud_attributes",
    "set_all_resource_attributes",
    "is_running_in_kubernetes",
    # Microsoft 365 Agents SDK integration
    "M365AgentIdentity",
    "M365AgentIdProvider",
    "get_m365_agent_id_provider",
    "is_m365_sdk_available",
]
