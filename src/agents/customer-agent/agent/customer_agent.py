"""
Customer Agent implementation using Microsoft Agent Framework.

This module provides the main agent class that:
- Uses Microsoft Agent Framework with AzureAIProjectAgentProvider for Azure AI Foundry
- Connects to Azure AI Foundry with Workload Identity or Azure CLI authentication
- Creates and manages the AI agent with function tools
- Handles conversation threads and message processing
- Integrates with OpenTelemetry Gen AI semantic conventions for observability
- Integrates with Microsoft 365 Agents SDK for unique agent identification

Microsoft Agent Framework: https://github.com/microsoft/agent-framework
Microsoft 365 Agents SDK: https://github.com/Microsoft/Agents-for-python
OpenTelemetry Gen AI Semantic Conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
"""

import logging
import time
import uuid
from typing import Any, AsyncIterator, Optional

from agent_framework import AgentResponse
from agent_framework.azure import AzureAIProjectAgentProvider
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential

from config import Settings, get_settings
from telemetry import (
    GenAIMetricsData,
    GenAIOperationName,
    GenAIProviderName,
    get_gen_ai_telemetry,
    get_tracer,
    get_m365_agent_id_provider,
    is_m365_sdk_available,
)

from .tools import get_agent_tools

logger = logging.getLogger(__name__)


class CustomerAgent:
    """
    Customer-facing AI Agent for the AKS Pet Store.

    This agent uses Microsoft Agent Framework with AzureAIProjectAgentProvider to provide:
    - Product browsing and search
    - Order placement and status checking
    - Customer service interactions

    Authentication is handled via Workload Identity when running on AKS,
    or Azure CLI for local development.

    Telemetry follows OpenTelemetry Gen AI semantic conventions for:
    - create_agent spans (agent initialization)
    - invoke_agent spans (message processing)
    - execute_tool spans (function tool calls)
    - Gen AI metrics (token usage, operation duration)
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize the Customer Agent.

        Args:
            settings: Application settings (uses defaults if not provided)
        """
        self.settings = settings or get_settings()
        self._provider: Optional[AzureAIProjectAgentProvider] = None
        self._agent: Optional[Any] = None
        self._credential: Optional[Any] = None
        self._threads: dict[str, str] = {}  # Map thread_id to conversation_id

        # Initialize telemetry
        self.tracer = get_tracer()
        self.gen_ai_telemetry = get_gen_ai_telemetry(
            service_name=self.settings.otel_service_name,
            provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
        )

        # Initialize Microsoft 365 Agents SDK integration for unique agent ID
        self.m365_agent_provider = get_m365_agent_id_provider(
            agent_name=self.settings.agent_name,
            agent_type="customer",
            channel_id="webchat",
            service_url=self.settings.azure_ai_project_endpoint,
        )

        # Log the unique agent ID from M365 SDK integration
        logger.info(
            f"Customer Agent initialized with M365 Agent ID: {self.m365_agent_provider.agent_id}, "
            f"M365 SDK available: {is_m365_sdk_available()}"
        )

    @property
    def agent_id(self) -> str:
        """
        Get the unique agent ID from Microsoft 365 Agents SDK integration.

        This ID is stable across restarts and unique per agent configuration.
        """
        return self.m365_agent_provider.agent_id

    def _get_credential(self) -> Any:
        """
        Get Azure credential for authentication.

        Uses DefaultAzureCredential for Workload Identity or AzureCliCredential for local dev.
        """
        if self._credential is None:
            if self.settings.use_workload_identity_auth:
                logger.info("Using Workload Identity authentication (DefaultAzureCredential)")
                self._credential = DefaultAzureCredential()
            else:
                logger.info("Using AzureCliCredential for local development")
                self._credential = AzureCliCredential()

        return self._credential

    async def initialize(self) -> None:
        """
        Initialize the agent using Microsoft Agent Framework with AzureAIProjectAgentProvider.

        This creates the provider and the AI agent with function tools.

        Creates a span following Gen AI semantic conventions:
        - Span name: create_agent {agent_name}
        - Span kind: CLIENT
        - Attributes: gen_ai.operation.name, gen_ai.agent.name, gen_ai.request.model
        """
        start_time = time.perf_counter()

        with self.gen_ai_telemetry.create_agent_span(
            agent_name=self.settings.agent_name,
            model=self.settings.azure_ai_model_deployment_name,
            instructions=self.settings.agent_instructions,
            server_endpoint=self.settings.azure_ai_project_endpoint,
        ) as span:
            try:
                credential = self._get_credential()

                # Create the AzureAIProjectAgentProvider from Microsoft Agent Framework
                # This is the correct provider for Azure AI Foundry endpoints
                self._provider = AzureAIProjectAgentProvider(
                    credential=credential,
                    project_endpoint=self.settings.azure_ai_project_endpoint,
                    model=self.settings.azure_ai_model_deployment_name,
                )

                logger.info(
                    f"Connected to Azure AI Foundry via Microsoft Agent Framework: "
                    f"{self.settings.azure_ai_project_endpoint}"
                )

                # Get the function tools for the agent
                tools = get_agent_tools()

                # Create the agent using AzureAIProjectAgentProvider
                # Use async context manager pattern
                await self._provider.__aenter__()

                self._agent = await self._provider.create_agent(
                    name=self.settings.agent_name,
                    model=self.settings.azure_ai_model_deployment_name,
                    instructions=self.settings.agent_instructions,
                    tools=tools,
                )

                logger.info(f"Agent created with Microsoft Agent Framework: {self.settings.agent_name}")

                # Set response attributes with M365 Agent ID
                span.set_attribute("gen_ai.agent.id", self.agent_id)
                span.set_attribute("gen_ai.agent.name", self.settings.agent_name)
                span.set_attribute(
                    "gen_ai.agent.description",
                    "Handles customer interactions including product search, product recommendations, order placement, and order status inquiries. Impacts revenue and customer satisfaction.",
                )

                # Add M365 Agents SDK specific attributes to span
                self.m365_agent_provider.set_otel_span_attributes(span)

                # Record operation duration metric
                duration = time.perf_counter() - start_time
                self.gen_ai_telemetry.record_operation_duration(
                    GenAIMetricsData(
                        operation_name=GenAIOperationName.CREATE_AGENT.value,
                        provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                        request_model=self.settings.azure_ai_model_deployment_name,
                        duration_seconds=duration,
                    )
                )

            except Exception as e:
                logger.error(f"Failed to initialize agent: {e}")
                self.gen_ai_telemetry.record_error(span, e)
                # Record duration metric with error
                duration = time.perf_counter() - start_time
                self.gen_ai_telemetry.record_operation_duration(
                    GenAIMetricsData(
                        operation_name=GenAIOperationName.CREATE_AGENT.value,
                        provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                        request_model=self.settings.azure_ai_model_deployment_name,
                        duration_seconds=duration,
                        error_type=type(e).__name__,
                    )
                )
                raise

    async def create_thread(self) -> str:
        """
        Create a new conversation thread.

        Returns:
            The thread ID for the new conversation
        """
        if self._agent is None:
            await self.initialize()

        thread_id = str(uuid.uuid4())
        # For AzureAIProjectAgentProvider, threads are managed automatically
        # We just track our own thread IDs
        self._threads[thread_id] = thread_id
        logger.info(f"Created thread: {thread_id}")
        return thread_id

    async def process_message(self, thread_id: str, user_message: str) -> str:
        """
        Process a user message and return the agent's response.

        Creates a span following Gen AI semantic conventions:
        - Span name: invoke_agent {agent_name}
        - Span kind: CLIENT
        - Attributes: gen_ai.conversation.id, gen_ai.usage.input_tokens, etc.

        Args:
            thread_id: The conversation thread ID
            user_message: The user's message text

        Returns:
            The agent's response text
        """
        if self._agent is None:
            await self.initialize()

        start_time = time.perf_counter()

        # Create activity ID for this message using M365 SDK integration
        activity_id = self.m365_agent_provider.create_activity_id(thread_id)

        with self.gen_ai_telemetry.invoke_agent_span(
            agent_name=self.settings.agent_name,
            agent_id=self.agent_id,  # Use M365 unique agent ID
            model=self.settings.azure_ai_model_deployment_name,
            conversation_id=thread_id,
            server_endpoint=self.settings.azure_ai_project_endpoint,
        ) as span:
            # Set agent description for observability
            span.set_attribute(
                "gen_ai.agent.description",
                "Handles customer interactions including product search, product recommendations, order placement, and order status inquiries. Impacts revenue and customer satisfaction.",
            )

            # Add M365 Agents SDK specific attributes for this activity
            self.m365_agent_provider.set_otel_span_attributes(
                span,
                conversation_id=thread_id,
                activity_id=activity_id,
            )

            try:
                # Record input message (opt-in based on env var)
                self.gen_ai_telemetry.set_span_input_messages(
                    span,
                    [
                        {
                            "role": "user",
                            "parts": [{"type": "text", "content": user_message}],
                        }
                    ],
                )

                # Run the agent using Microsoft Agent Framework
                result: AgentResponse = await self._agent.run(user_message)
                response_text = str(result)

                logger.info(f"Processed message in thread {thread_id}")

                # Extract token usage from AgentResponse
                # Try multiple possible attribute names and structures
                input_tokens = None
                output_tokens = None

                # Debug: Log available attributes on the result
                logger.debug(f"AgentResponse attributes: {dir(result)}")

                # Try usage_details first (Microsoft Agent Framework)
                if hasattr(result, 'usage_details') and result.usage_details:
                    usage = result.usage_details
                    logger.debug(f"usage_details content: {usage}")
                    # Try different field names
                    input_tokens = (
                        usage.get('input_token_count') or
                        usage.get('input_tokens') or
                        usage.get('prompt_tokens')
                    )
                    output_tokens = (
                        usage.get('output_token_count') or
                        usage.get('output_tokens') or
                        usage.get('completion_tokens')
                    )

                # Try usage attribute (OpenAI-style)
                elif hasattr(result, 'usage') and result.usage:
                    usage = result.usage
                    logger.debug(f"usage content: {usage}")
                    if hasattr(usage, 'prompt_tokens'):
                        input_tokens = usage.prompt_tokens
                    if hasattr(usage, 'completion_tokens'):
                        output_tokens = usage.completion_tokens
                    # Also try dict-style access
                    if isinstance(usage, dict):
                        input_tokens = input_tokens or usage.get('prompt_tokens') or usage.get('input_tokens')
                        output_tokens = output_tokens or usage.get('completion_tokens') or usage.get('output_tokens')

                if input_tokens is not None or output_tokens is not None:
                    logger.info(f"Token usage - input: {input_tokens}, output: {output_tokens}")
                else:
                    logger.warning(f"No token usage data available from AgentResponse. Check SDK version and response structure.")

                # Record token usage on span
                self.gen_ai_telemetry.set_span_response_attributes(
                    span,
                    response_model=self.settings.azure_ai_model_deployment_name,
                    finish_reasons=["stop"],
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

                # Record output message (opt-in)
                self.gen_ai_telemetry.set_span_output_messages(
                    span,
                    [
                        {
                            "role": "assistant",
                            "parts": [{"type": "text", "content": response_text}],
                            "finish_reason": "stop",
                        }
                    ],
                )

                # Record operation duration metric
                duration = time.perf_counter() - start_time
                self.gen_ai_telemetry.record_operation_duration(
                    GenAIMetricsData(
                        operation_name=GenAIOperationName.INVOKE_AGENT.value,
                        provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                        request_model=self.settings.azure_ai_model_deployment_name,
                        duration_seconds=duration,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        agent_name=self.settings.agent_name,
                        agent_id=self.agent_id,
                        conversation_id=thread_id,
                    )
                )

                # Record token usage metrics (always record, even if tokens are 0/unavailable)
                # This ensures the metric is visible in monitoring dashboards
                self.gen_ai_telemetry.record_token_usage(
                    GenAIMetricsData(
                        operation_name=GenAIOperationName.INVOKE_AGENT.value,
                        provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                        request_model=self.settings.azure_ai_model_deployment_name,
                        input_tokens=input_tokens or 0,
                        output_tokens=output_tokens or 0,
                        agent_name=self.settings.agent_name,
                        agent_id=self.agent_id,
                        conversation_id=thread_id,
                    )
                )

                return response_text

            except Exception as e:
                logger.error(f"Error processing message: {e}")
                self.gen_ai_telemetry.record_error(span, e)
                # Record duration metric with error
                duration = time.perf_counter() - start_time
                self.gen_ai_telemetry.record_operation_duration(
                    GenAIMetricsData(
                        operation_name=GenAIOperationName.INVOKE_AGENT.value,
                        provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                        request_model=self.settings.azure_ai_model_deployment_name,
                        duration_seconds=duration,
                        error_type=type(e).__name__,
                    )
                )
                return f"I encountered an error: {str(e)}. Please try again."

    async def stream_message(
        self, thread_id: str, user_message: str
    ) -> AsyncIterator[str]:
        """
        Process a user message with streaming response.

        Creates a span following Gen AI semantic conventions for invoke_agent.

        Args:
            thread_id: The conversation thread ID
            user_message: The user's message text

        Yields:
            Chunks of the agent's response text
        """
        if self._agent is None:
            await self.initialize()

        start_time = time.perf_counter()

        # === GOLDEN SIGNAL: Request Count (Traffic) ===
        self.gen_ai_telemetry.record_request(
            GenAIMetricsData(
                operation_name=GenAIOperationName.INVOKE_AGENT.value,
                provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                request_model=self.settings.azure_ai_model_deployment_name,
                agent_name=self.settings.agent_name,
                agent_id=self.agent_id,
                conversation_id=thread_id,
            )
        )
        # ==============================================

        with self.gen_ai_telemetry.invoke_agent_span(
            agent_name=self.settings.agent_name,
            agent_id=self.agent_id,
            model=self.settings.azure_ai_model_deployment_name,
            conversation_id=thread_id,
            server_endpoint=self.settings.azure_ai_project_endpoint,
        ) as span:
            # Set agent description for observability
            span.set_attribute(
                "gen_ai.agent.description",
                "Handles customer interactions including product search, product recommendations, order placement, and order status inquiries. Impacts revenue and customer satisfaction.",
            )

            try:
                # Record input message (opt-in)
                self.gen_ai_telemetry.set_span_input_messages(
                    span,
                    [
                        {
                            "role": "user",
                            "parts": [{"type": "text", "content": user_message}],
                        }
                    ],
                )

                # Stream response using Microsoft Agent Framework's run_stream method
                full_response = ""
                input_tokens = None
                output_tokens = None
                last_chunk = None

                async for chunk in self._agent.run_stream(user_message):
                    last_chunk = chunk
                    if hasattr(chunk, 'text') and chunk.text:
                        full_response += chunk.text
                        yield chunk.text
                    elif isinstance(chunk, str):
                        full_response += chunk
                        yield chunk

                # Try to extract token usage from the last chunk (AgentResponseUpdate)
                # Try multiple possible attribute names and structures
                if last_chunk:
                    logger.debug(f"Last chunk type: {type(last_chunk)}, attributes: {dir(last_chunk)}")

                    # Try usage_details first (Microsoft Agent Framework)
                    if hasattr(last_chunk, 'usage_details') and last_chunk.usage_details:
                        usage = last_chunk.usage_details
                        logger.debug(f"Stream usage_details content: {usage}")
                        input_tokens = (
                            usage.get('input_token_count') or
                            usage.get('input_tokens') or
                            usage.get('prompt_tokens')
                        )
                        output_tokens = (
                            usage.get('output_token_count') or
                            usage.get('output_tokens') or
                            usage.get('completion_tokens')
                        )

                    # Try usage attribute (OpenAI-style)
                    elif hasattr(last_chunk, 'usage') and last_chunk.usage:
                        usage = last_chunk.usage
                        logger.debug(f"Stream usage content: {usage}")
                        if hasattr(usage, 'prompt_tokens'):
                            input_tokens = usage.prompt_tokens
                        if hasattr(usage, 'completion_tokens'):
                            output_tokens = usage.completion_tokens
                        if isinstance(usage, dict):
                            input_tokens = input_tokens or usage.get('prompt_tokens') or usage.get('input_tokens')
                            output_tokens = output_tokens or usage.get('completion_tokens') or usage.get('output_tokens')

                    if input_tokens is not None or output_tokens is not None:
                        logger.info(f"Stream token usage - input: {input_tokens}, output: {output_tokens}")
                    else:
                        logger.warning(f"No token usage data available from streaming response. Check SDK version.")

                # Record token usage on span
                self.gen_ai_telemetry.set_span_response_attributes(
                    span,
                    response_model=self.settings.azure_ai_model_deployment_name,
                    finish_reasons=["stop"],
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

                # Record output message (opt-in)
                if full_response:
                    self.gen_ai_telemetry.set_span_output_messages(
                        span,
                        [
                            {
                                "role": "assistant",
                                "parts": [{"type": "text", "content": full_response}],
                                "finish_reason": "stop",
                            }
                        ],
                    )

                # Record operation duration metric
                duration = time.perf_counter() - start_time
                self.gen_ai_telemetry.record_operation_duration(
                    GenAIMetricsData(
                        operation_name=GenAIOperationName.INVOKE_AGENT.value,
                        provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                        request_model=self.settings.azure_ai_model_deployment_name,
                        duration_seconds=duration,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        agent_name=self.settings.agent_name,
                        agent_id=self.agent_id,
                        conversation_id=thread_id,
                    )
                )

                # Record token usage metrics (always record, even if tokens are 0/unavailable)
                # This ensures the metric is visible in monitoring dashboards
                self.gen_ai_telemetry.record_token_usage(
                    GenAIMetricsData(
                        operation_name=GenAIOperationName.INVOKE_AGENT.value,
                        provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                        request_model=self.settings.azure_ai_model_deployment_name,
                        input_tokens=input_tokens or 0,
                        output_tokens=output_tokens or 0,
                        agent_name=self.settings.agent_name,
                        agent_id=self.agent_id,
                        conversation_id=thread_id,
                    )
                )

            except Exception as e:
                logger.error(f"Error streaming message: {e}")
                self.gen_ai_telemetry.record_error(span, e)
                # Record duration metric with error
                duration = time.perf_counter() - start_time
                self.gen_ai_telemetry.record_operation_duration(
                    GenAIMetricsData(
                        operation_name=GenAIOperationName.INVOKE_AGENT.value,
                        provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                        request_model=self.settings.azure_ai_model_deployment_name,
                        duration_seconds=duration,
                        error_type=type(e).__name__,
                        agent_name=self.settings.agent_name,
                        agent_id=self.agent_id,
                        conversation_id=thread_id,
                    )
                )
                # === GOLDEN SIGNAL: Error Count ===
                self.gen_ai_telemetry.record_error_metric(
                    GenAIMetricsData(
                        operation_name=GenAIOperationName.INVOKE_AGENT.value,
                        provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                        request_model=self.settings.azure_ai_model_deployment_name,
                        error_type=type(e).__name__,
                        agent_name=self.settings.agent_name,
                        agent_id=self.agent_id,
                        conversation_id=thread_id,
                    )
                )
                # ==================================
                yield f"Error: {str(e)}"

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self._provider:
            try:
                await self._provider.__aexit__(None, None, None)
                logger.info("Cleaned up agent provider")
            except Exception as e:
                logger.warning(f"Error during cleanup: {e}")

        if self._credential:
            try:
                await self._credential.close()
            except Exception as e:
                logger.warning(f"Error closing credential: {e}")

        self._agent = None
        self._provider = None
        self._credential = None
        self._threads.clear()
        logger.info("Cleaned up agent resources")
