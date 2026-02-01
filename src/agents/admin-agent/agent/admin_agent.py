"""
Admin Agent implementation using Microsoft Agent Framework.

This module provides the main agent class that:
- Uses Microsoft Agent Framework with AzureAIProjectAgentProvider for Azure AI Foundry
- Connects to Azure AI Foundry with Workload Identity or Azure CLI authentication
- Creates and manages the AI agent with function tools for admin operations
- Handles conversation threads and message processing
- Integrates with OpenTelemetry Gen AI semantic conventions for observability

Microsoft Agent Framework: https://github.com/microsoft/agent-framework
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
)

from .tools import get_agent_tools

logger = logging.getLogger(__name__)


class AdminAgent:
    """
    Administrative AI Agent for the AKS Pet Store.

    This agent uses Microsoft Agent Framework with AzureAIProjectAgentProvider to provide:
    - Product management (add, update, delete, list)
    - Order management (view, update status, complete)

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
        Initialize the Admin Agent.

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
                await self._provider.__aenter__()

                self._agent = await self._provider.create_agent(
                    name=self.settings.agent_name,
                    model=self.settings.azure_ai_model_deployment_name,
                    instructions=self.settings.agent_instructions,
                    tools=tools,
                )

                logger.info(f"Agent created with Microsoft Agent Framework: {self.settings.agent_name}")

                # Set response attributes
                span.set_attribute("gen_ai.agent.id", self.settings.agent_name)
                span.set_attribute(
                    "gen_ai.agent.description",
                    "Manages store operations including product inventory, product updates, order fulfillment, and order completion. Impacts inventory levels and operational efficiency.",
                )

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

        with self.gen_ai_telemetry.invoke_agent_span(
            agent_name=self.settings.agent_name,
            agent_id=self.settings.agent_name,
            model=self.settings.azure_ai_model_deployment_name,
            conversation_id=thread_id,
            server_endpoint=self.settings.azure_ai_project_endpoint,
        ) as span:
            # Set agent description for observability
            span.set_attribute(
                "gen_ai.agent.description",
                "Manages store operations including product inventory, product updates, order fulfillment, and order completion. Impacts inventory levels and operational efficiency.",
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
                # AgentResponse has usage_details with input_token_count/output_token_count
                input_tokens = None
                output_tokens = None
                if hasattr(result, 'usage_details') and result.usage_details:
                    input_tokens = result.usage_details.get('input_token_count')
                    output_tokens = result.usage_details.get('output_token_count')
                    logger.info(f"Token usage - input: {input_tokens}, output: {output_tokens}")

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
                    )
                )

                # Record token usage metrics separately
                if input_tokens is not None or output_tokens is not None:
                    self.gen_ai_telemetry.record_token_usage(
                        GenAIMetricsData(
                            operation_name=GenAIOperationName.INVOKE_AGENT.value,
                            provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                            request_model=self.settings.azure_ai_model_deployment_name,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
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
                agent_id=self.settings.agent_name,
                conversation_id=thread_id,
            )
        )
        # ==============================================

        with self.gen_ai_telemetry.invoke_agent_span(
            agent_name=self.settings.agent_name,
            agent_id=self.settings.agent_name,
            model=self.settings.azure_ai_model_deployment_name,
            conversation_id=thread_id,
            server_endpoint=self.settings.azure_ai_project_endpoint,
        ) as span:
            # Set agent description for observability
            span.set_attribute(
                "gen_ai.agent.description",
                "Manages store operations including product inventory, product updates, order fulfillment, and order completion. Impacts inventory levels and operational efficiency.",
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
                if last_chunk and hasattr(last_chunk, 'usage_details') and last_chunk.usage_details:
                    input_tokens = last_chunk.usage_details.get('input_token_count')
                    output_tokens = last_chunk.usage_details.get('output_token_count')
                    logger.info(f"Stream token usage - input: {input_tokens}, output: {output_tokens}")

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
                    )
                )

                # Record token usage metrics separately
                if input_tokens is not None or output_tokens is not None:
                    self.gen_ai_telemetry.record_token_usage(
                        GenAIMetricsData(
                            operation_name=GenAIOperationName.INVOKE_AGENT.value,
                            provider_name=GenAIProviderName.AZURE_AI_INFERENCE.value,
                            request_model=self.settings.azure_ai_model_deployment_name,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
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
                        agent_id=self.settings.agent_name,
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
                        agent_id=self.settings.agent_name,
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
