"""
Application settings and configuration for the Customer Agent.

This module uses pydantic-settings to manage environment variables
and configuration for Azure AI Foundry, OpenTelemetry, and service endpoints.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Azure AI Foundry / Agent Service Configuration
    azure_ai_project_endpoint: str = ""
    azure_ai_model_deployment_name: str = "gpt-4o-mini"
    azure_openai_api_version: str = "2024-12-01-preview"

    # Workload Identity - when running on AKS with managed identity
    use_workload_identity_auth: bool = True

    # Azure OpenAI API Key (optional - for local development)
    azure_openai_api_key: Optional[str] = None

    # Application Insights for OpenTelemetry
    applicationinsights_connection_string: Optional[str] = None
    otel_service_name: str = "customer-agent"
    otel_instrumentation_genai_capture_message_content: bool = True

    # Backend Service URLs
    order_service_url: str = "http://order-service:3000"
    product_service_url: str = "http://product-service:3002"
    makeline_service_url: str = "http://makeline-service:3001"

    # Agent Configuration
    agent_name: str = "pet-store-customer-assistant"
    agent_display_name: str = "Pet Store Customer Assistant"
    agent_instructions: str = """You are a friendly and helpful customer service agent for the AKS Pet Store.

Your capabilities include:
1. **Product Information**: Help customers browse and find products, provide product details, and answer questions about pet supplies.
2. **Order Management**: Help customers place new orders, check order status, and view order history.
3. **Recommendations**: Suggest products based on customer needs and preferences.

Guidelines:
- Always be polite, professional, and helpful
- If you don't know something, be honest and offer to help find the information
- When placing orders, confirm the details with the customer before submitting
- Provide order IDs and confirmations after successful order placement
- Format product information clearly with prices and descriptions

Remember: You're here to make the pet shopping experience delightful!"""

    # Chainlit Configuration
    chainlit_host: str = "0.0.0.0"
    chainlit_port: int = 8000

    # Application version
    app_version: str = "1.0.0"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
