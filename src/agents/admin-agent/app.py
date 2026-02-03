"""
Chainlit application for the Admin Agent conversational UI.

This module provides the Chainlit-based chat interface that:
- Handles user authentication and session management
- Manages conversation threads with the Azure AI Agent
- Provides a rich conversational experience with streaming responses
- Integrates with OpenTelemetry for observability with Gen AI semantic conventions
"""

import logging
import os
import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chainlit as cl
from chainlit import Message, User
from chainlit.server import app
from fastapi.responses import JSONResponse
from opentelemetry import trace

from config import get_settings
from telemetry import configure_telemetry, get_tracer, get_gen_ai_telemetry
from telemetry.k8s_semantics import get_k8s_attributes, get_cloud_attributes, is_running_in_kubernetes
from agent import AdminAgent
from agent.tools import set_business_context

# Add business-telemetry SDK to path
# In container: /app/business_telemetry_sdk (copied via Dockerfile)
# In development: ../business-telemetry (relative path)
_business_telemetry_paths = [
    "/app/business_telemetry_sdk",  # Container path
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "business-telemetry")),  # Dev path
]
for _path in _business_telemetry_paths:
    if os.path.exists(_path):
        sys.path.insert(0, _path)
        break

try:
    from sdk import (
        init_telemetry as init_business_telemetry,
        shutdown_telemetry as shutdown_business_telemetry,
        set_infrastructure_context,
        emit_session_started,
        emit_session_ended,
        emit_customer_query,
        emit_agent_session_started,
        emit_agent_session_ended,
        emit_agent_tool_call,
    )
    BUSINESS_TELEMETRY_AVAILABLE = True
except ImportError as e:
    BUSINESS_TELEMETRY_AVAILABLE = False
    logging.warning(f"Business telemetry SDK not available: {e}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize settings and telemetry
settings = get_settings()
tracer = configure_telemetry(
    service_name=settings.otel_service_name,
    application_insights_connection_string=settings.applicationinsights_connection_string,
    agent_name=settings.agent_name,
)
gen_ai_telemetry = get_gen_ai_telemetry()

# Global agent instance (shared across sessions, each session has its own thread)
_agent: AdminAgent | None = None
_business_telemetry_initialized = False

# Cache K8s context for business events (loaded once at startup)
_k8s_business_context: dict = {}


def _load_k8s_business_context() -> dict:
    """
    Load K8s context for Fabric-Pulse business events.

    Returns dict with:
    - cluster_id: cloud.resource_id (CLUSTER_RESOURCE_ID env var)
    - namespace: k8s.namespace.name (POD_NAMESPACE env var)
    - pod_name: k8s.pod.name (POD_NAME env var)
    - node_name: k8s.node.name (NODE_NAME env var)
    - replicaset_name: k8s.replicaset.name (derived from pod name)
    - deployment_name: k8s.deployment.name (DEPLOYMENT_NAME or derived)
    """
    global _k8s_business_context
    if _k8s_business_context:
        return _k8s_business_context

    if is_running_in_kubernetes():
        k8s_attrs = get_k8s_attributes()
        cloud_attrs = get_cloud_attributes()

        _k8s_business_context = {
            "cluster_id": cloud_attrs.get("cloud.resource_id", os.getenv("CLUSTER_RESOURCE_ID")),
            "namespace": k8s_attrs.get("k8s.namespace.name", os.getenv("POD_NAMESPACE")),
            "pod_name": k8s_attrs.get("k8s.pod.name", os.getenv("POD_NAME")),
            "node_name": k8s_attrs.get("k8s.node.name", os.getenv("NODE_NAME")),
            "replicaset_name": k8s_attrs.get("k8s.replicaset.name"),
            "deployment_name": k8s_attrs.get("k8s.deployment.name", os.getenv("DEPLOYMENT_NAME")),
        }
    else:
        # Development mode - use placeholder values
        _k8s_business_context = {
            "cluster_id": "local-dev",
            "namespace": "default",
            "pod_name": "admin-agent-dev",
            "node_name": "local-node",
            "replicaset_name": None,
            "deployment_name": "admin-agent",
        }

    logger.debug(f"K8s business context loaded: {_k8s_business_context}")
    return _k8s_business_context


# -----------------------------------------------------------------------------
#                               HEALTH CHECK ENDPOINT
# -----------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """
    Health check endpoint for Kubernetes probes.

    Returns:
        200: Service is healthy and ready to accept requests
        503: Service is unhealthy (agent initialization failed)
    """
    try:
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "service": settings.otel_service_name,
                "version": "1.0.0"
            }
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@app.get("/ready")
async def readiness_check():
    """
    Readiness check endpoint for Kubernetes.

    Checks if the agent is initialized and ready to process requests.

    Returns:
        200: Service is ready to accept traffic
        503: Service is not ready (agent not initialized)
    """
    global _agent
    try:
        if _agent is not None:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "ready",
                    "agent_initialized": True
                }
            )
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "agent_initialized": False,
                    "message": "Agent not yet initialized"
                }
            )
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "error": str(e)
            }
        )


async def get_agent() -> AdminAgent:
    """Get or create the global agent instance."""
    global _agent, _business_telemetry_initialized
    if _agent is None:
        _agent = AdminAgent(settings)
        await _agent.initialize()
        logger.info("Admin Agent initialized")

    # Initialize business telemetry (once)
    if not _business_telemetry_initialized and BUSINESS_TELEMETRY_AVAILABLE:
        try:
            await init_business_telemetry()

            # Set infrastructure context for all business events (Fabric-Pulse correlation)
            k8s_ctx = _load_k8s_business_context()
            agent_id = f"{k8s_ctx.get('cluster_id', 'unknown')}/{k8s_ctx.get('namespace', 'default')}/agents/{settings.agent_name}"
            workload_id = f"{k8s_ctx.get('cluster_id', 'unknown')}/{k8s_ctx.get('namespace', 'default')}/{k8s_ctx.get('deployment_name', settings.agent_name)}"

            set_infrastructure_context(
                agent_id=agent_id,
                workload_id=workload_id,
                cluster_id=k8s_ctx.get("cluster_id"),
                namespace=k8s_ctx.get("namespace"),
                pod_name=k8s_ctx.get("pod_name"),
                deployment_name=k8s_ctx.get("deployment_name"),
            )

            _business_telemetry_initialized = True
            logger.info(f"Business telemetry initialized with infrastructure context: agent_id={agent_id}")
        except Exception as e:
            logger.warning(f"Failed to initialize business telemetry: {e}")

    return _agent


@cl.on_chat_start
async def on_chat_start():
    """
    Handle the start of a new chat session.

    Creates a new conversation thread and sends a welcome message.
    """
    with tracer.start_as_current_span("chat_session_start") as span:
        # Set agent identification attributes for correlation
        span.set_attribute("gen_ai.agent.name", settings.agent_name)
        span.set_attribute("gen_ai.agent.id", settings.agent_name)

        try:
            # Get or create the agent
            agent = await get_agent()

            # Create a new thread for this session
            thread_id = await agent.create_thread()

            # Store thread ID and session start time in user session
            cl.user_session.set("thread_id", thread_id)
            cl.user_session.set("session_start_time", time.time())
            cl.user_session.set("interaction_count", 0)

            # Set business telemetry context for tools
            set_business_context(
                session_id=thread_id,
                correlation_id=thread_id,
                admin_user="admin",  # Could be extracted from auth if available
            )

            span.set_attribute("thread.id", thread_id)
            span.set_attribute("gen_ai.conversation.id", thread_id)
            logger.info(f"New chat session started with thread: {thread_id}")

            # === GOLDEN SIGNAL: Session Started (Saturation) ===
            gen_ai_telemetry.record_session_start(
                agent_name=settings.agent_name,
                agent_id=settings.agent_name,
            )
            # ===================================================

            # === BUSINESS TELEMETRY: Admin Session Started ===
            if BUSINESS_TELEMETRY_AVAILABLE:
                try:
                    # Get K8s context for proper foreign key generation
                    k8s_ctx = _load_k8s_business_context()
                    trace_id = None
                    current_span = trace.get_current_span()
                    if current_span and current_span.get_span_context().is_valid:
                        trace_id = format(current_span.get_span_context().trace_id, '032x')

                    # Emit new Fabric-Pulse compliant event
                    await emit_agent_session_started(
                        agent_name=settings.agent_name,
                        session_id=thread_id,
                        cluster_id=k8s_ctx.get("cluster_id"),
                        namespace=k8s_ctx.get("namespace"),
                        pod_name=k8s_ctx.get("pod_name"),
                        node_name=k8s_ctx.get("node_name"),
                        replicaset_name=k8s_ctx.get("replicaset_name"),
                        deployment_name=k8s_ctx.get("deployment_name"),
                        customer_id="admin",  # Admin sessions don't have customer_id
                        trace_id=trace_id,
                    )
                    # Also emit legacy event for backward compatibility
                    await emit_session_started(session_id=thread_id, user_id="admin")
                except Exception as e:
                    logger.debug(f"Business telemetry session_started skipped: {e}")
            # =========================================================================

            # Send welcome message
            welcome_message = """# 🛠️ Pet Store Admin Console

Welcome to the Admin Console! I'm your AI assistant for managing the Pet Store.

## What I Can Help With

### 📦 Product Management
- **List Products** - View all products in the catalog
- **Add Product** - Create new products with name, price, description
- **Update Product** - Modify existing product details
- **Delete Product** - Remove products from the catalog

### 📋 Order Management
- **View Orders** - See all orders and their status
- **Update Status** - Change order status (Pending → Processing → Complete)
- **Complete Orders** - Mark orders as fulfilled

## Quick Commands

Try asking me:
- "Show me all products"
- "Add a new product called 'Premium Cat Food' priced at $24.99"
- "Update the price of product 1 to $19.99"
- "Show me pending orders"
- "Mark order abc123 as complete"

**How can I help you manage the store today?**
"""
            await Message(content=welcome_message).send()

        except Exception as e:
            logger.error(f"Error starting chat session: {e}")
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            await Message(
                content="Sorry, I'm having trouble starting up. Please try refreshing the page."
            ).send()


@cl.on_message
async def on_message(message: cl.Message):
    """
    Handle incoming user messages.

    Processes the message through the AI agent and streams the response.
    """
    with tracer.start_as_current_span("process_user_message") as span:
        # Set agent identification attributes for correlation
        span.set_attribute("gen_ai.agent.name", settings.agent_name)
        span.set_attribute("gen_ai.agent.id", settings.agent_name)
        span.set_attribute("message.content_length", len(message.content))
        query_start_time = time.time()

        # Get thread ID from session
        thread_id = cl.user_session.get("thread_id")

        if not thread_id:
            # Session expired or invalid, create new thread
            agent = await get_agent()
            thread_id = await agent.create_thread()
            cl.user_session.set("thread_id", thread_id)
            cl.user_session.set("session_start_time", time.time())
            cl.user_session.set("interaction_count", 0)
            set_business_context(session_id=thread_id, correlation_id=thread_id, admin_user="admin")
            logger.info(f"Created new thread for session: {thread_id}")

        # Increment interaction count
        interaction_count = cl.user_session.get("interaction_count", 0) + 1
        cl.user_session.set("interaction_count", interaction_count)

        span.set_attribute("thread.id", thread_id)
        span.set_attribute("gen_ai.conversation.id", thread_id)

        try:
            agent = await get_agent()

            # Create a message placeholder for streaming
            response_message = cl.Message(content="")
            await response_message.send()

            # Stream the response
            full_response = ""
            async for chunk in agent.stream_message(thread_id, message.content):
                full_response += chunk
                await response_message.stream_token(chunk)

            # Finalize the message
            await response_message.update()

            span.set_attribute("response.content_length", len(full_response))
            logger.info(f"Processed message in thread {thread_id}")

            # === BUSINESS TELEMETRY: Admin Query ===
            if BUSINESS_TELEMETRY_AVAILABLE:
                try:
                    response_time_ms = int((time.time() - query_start_time) * 1000)
                    await emit_customer_query(
                        query_text=message.content[:500],  # Truncate for privacy
                        response_time_ms=response_time_ms,
                    )
                except Exception as e:
                    logger.debug(f"Business telemetry admin_query skipped: {e}")
            # =======================================

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

            # Send error message
            error_msg = cl.Message(
                content="I apologize, but I encountered an error processing your request. "
                       "Please try again, or start a new conversation."
            )
            await error_msg.send()


@cl.on_chat_end
async def on_chat_end():
    """Handle the end of a chat session."""
    thread_id = cl.user_session.get("thread_id")
    if thread_id:
        logger.info(f"Chat session ended for thread: {thread_id}")

        # === GOLDEN SIGNAL: Session Ended (Saturation) ===
        gen_ai_telemetry.record_session_end(
            agent_name=settings.agent_name,
            agent_id=settings.agent_name,
        )
        # =================================================

        # === BUSINESS TELEMETRY: Admin Session Ended ===
        if BUSINESS_TELEMETRY_AVAILABLE:
            try:
                session_start = cl.user_session.get("session_start_time")
                interaction_count = cl.user_session.get("interaction_count", 0)
                duration_ms = int((time.time() - session_start) * 1000) if session_start else None

                # Get K8s context for proper foreign key generation
                k8s_ctx = _load_k8s_business_context()

                # Get session metrics if tracked
                tool_call_count = cl.user_session.get("tool_call_count", 0)
                model_invocation_count = cl.user_session.get("model_invocation_count", 0)
                total_input_tokens = cl.user_session.get("total_input_tokens", 0)
                total_output_tokens = cl.user_session.get("total_output_tokens", 0)
                inventory_updates = cl.user_session.get("inventory_updates", 0)
                error_occurred = cl.user_session.get("error_occurred", False)
                error_type = cl.user_session.get("error_type")

                # Emit new Fabric-Pulse compliant event with business outcomes
                await emit_agent_session_ended(
                    agent_name=settings.agent_name,
                    session_id=thread_id,
                    duration_ms=duration_ms,
                    status="Completed" if not error_occurred else "Error",
                    cluster_id=k8s_ctx.get("cluster_id"),
                    namespace=k8s_ctx.get("namespace"),
                    pod_name=k8s_ctx.get("pod_name"),
                    # Business outcomes
                    tool_call_count=tool_call_count,
                    model_invocation_count=model_invocation_count,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                    message_count=interaction_count,
                    inventory_updates=inventory_updates,
                    # Error info
                    error_occurred=error_occurred,
                    error_type=error_type,
                )

                # Also emit legacy event for backward compatibility
                await emit_session_ended(
                    session_id=thread_id,
                    duration_ms=duration_ms,
                    interaction_count=interaction_count,
                    user_id="admin",
                )
            except Exception as e:
                logger.debug(f"Business telemetry session_ended skipped: {e}")
        # ======================================================================


@cl.on_stop
async def on_stop():
    """Handle when the user stops a response generation."""
    logger.info("User stopped response generation")
