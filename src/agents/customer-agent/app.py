"""
Chainlit application for the Customer Agent conversational UI.

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
from agent import CustomerAgent
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
        emit_session_started,
        emit_session_ended,
        emit_customer_query,
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
)
gen_ai_telemetry = get_gen_ai_telemetry()

# Global agent instance (shared across sessions, each session has its own thread)
_agent: CustomerAgent | None = None
_business_telemetry_initialized = False


# -----------------------------------------------------------------------------
#                               HEALTH CHECK ENDPOINT
# -----------------------------------------------------------------------------
# Kubernetes probes use this endpoint to determine container health
# This is separate from Chainlit's HEAD / status check

@app.get("/health")
async def health_check():
    """
    Health check endpoint for Kubernetes probes.

    Returns:
        200: Service is healthy and ready to accept requests
        503: Service is unhealthy (agent initialization failed)
    """
    try:
        # Basic health check - verify the service is running
        # We don't check agent initialization here as it may not be ready yet
        # during startup (handled by startupProbe)
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


async def get_agent() -> CustomerAgent:
    """Get or create the global agent instance."""
    global _agent, _business_telemetry_initialized
    if _agent is None:
        _agent = CustomerAgent(settings)
        await _agent.initialize()
        logger.info("Customer Agent initialized")

    # Initialize business telemetry (once)
    if not _business_telemetry_initialized and BUSINESS_TELEMETRY_AVAILABLE:
        try:
            await init_business_telemetry()
            _business_telemetry_initialized = True
            logger.info("Business telemetry initialized")
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
            set_business_context(session_id=thread_id, correlation_id=thread_id)

            span.set_attribute("thread.id", thread_id)
            span.set_attribute("gen_ai.conversation.id", thread_id)
            logger.info(f"New chat session started with thread: {thread_id}")

            # === BUSINESS TELEMETRY: Session Started ===
            if BUSINESS_TELEMETRY_AVAILABLE:
                try:
                    await emit_session_started(session_id=thread_id)
                except Exception as e:
                    logger.debug(f"Business telemetry session_started skipped: {e}")
            # ============================================

            # Send welcome message
            welcome_message = """# 🐾 Welcome to the Pet Store!

I'm your AI assistant, here to help you with:

- **🔍 Browse Products** - Explore our catalog of pet supplies
- **🛒 Place Orders** - Order products for your furry friends
- **📦 Track Orders** - Check the status of your orders
- **❓ Get Help** - Answer questions about our products and services

**How can I help you today?**

*Try saying: "Show me all products" or "I'd like to place an order"*
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
            set_business_context(session_id=thread_id, correlation_id=thread_id)
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

            # === BUSINESS TELEMETRY: Customer Query ===
            if BUSINESS_TELEMETRY_AVAILABLE:
                try:
                    response_time_ms = int((time.time() - query_start_time) * 1000)
                    await emit_customer_query(
                        query_text=message.content[:500],  # Truncate for privacy
                        response_time_ms=response_time_ms,
                    )
                except Exception as e:
                    logger.debug(f"Business telemetry customer_query skipped: {e}")
            # ==========================================

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

        # === BUSINESS TELEMETRY: Session Ended ===
        if BUSINESS_TELEMETRY_AVAILABLE:
            try:
                session_start = cl.user_session.get("session_start_time")
                interaction_count = cl.user_session.get("interaction_count", 0)
                duration_ms = int((time.time() - session_start) * 1000) if session_start else None
                await emit_session_ended(
                    session_id=thread_id,
                    duration_ms=duration_ms,
                    interaction_count=interaction_count,
                )
            except Exception as e:
                logger.debug(f"Business telemetry session_ended skipped: {e}")
        # =========================================


@cl.on_stop
async def on_stop():
    """Handle when the user stops a response generation."""
    logger.info("User stopped response generation")


# Health check endpoint (used by Kubernetes)
@cl.on_chat_resume
async def on_chat_resume(thread: dict):
    """Handle resuming a chat session."""
    thread_id = thread.get("id")
    if thread_id:
        cl.user_session.set("thread_id", thread_id)
        logger.info(f"Resumed chat session: {thread_id}")


# Main entry point for running with uvicorn
def main():
    """Main entry point for the application."""
    import uvicorn

    logger.info(f"Starting Customer Agent on {settings.chainlit_host}:{settings.chainlit_port}")

    # Run the Chainlit app
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)


if __name__ == "__main__":
    main()
