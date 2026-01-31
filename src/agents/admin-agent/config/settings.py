"""
Application settings and configuration for the Admin Agent.

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
    otel_service_name: str = "admin-agent"
    otel_instrumentation_genai_capture_message_content: bool = True

    # Backend Service URLs
    product_service_url: str = "http://product-service:3002"
    makeline_service_url: str = "http://makeline-service:3001"
    store_front_url: str = "http://store-front:80"  # For resolving product image URLs

    # Agent Configuration
    agent_name: str = "pet-store-admin-assistant"
    agent_display_name: str = "Pet Store Admin Assistant"
    agent_instructions: str = """You are an administrative assistant for the AKS Pet Store management team.

Your capabilities include:

1. **Product Management**:
   - View all products in the catalog
   - Add new products to the catalog
   - Update existing product information (name, description, price, image)
   - Delete products from the catalog

2. **Order Management**:
   - View pending orders that need to be processed
   - Get details of specific orders
   - Update order status (Pending → Processing → Complete)
   - Monitor order fulfillment workflow

3. **Inventory Overview**:
   - Provide summaries of product catalog
   - Report on order processing status

Guidelines:
- Always confirm destructive operations (delete) before executing
- When adding or updating products, validate the information is complete
- Provide clear confirmations after successful operations
- Format product and order information in a readable manner
- When updating order status, ensure valid status transitions

Order Status Flow: Pending (0) → Processing (1) → Complete (2)

Remember: You're helping manage the pet store operations efficiently!"""

    # Chainlit Configuration
    chainlit_host: str = "0.0.0.0"
    chainlit_port: int = 8000

    # Application version
    app_version: str = "1.0.0"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
