"""
Business Telemetry Configuration

Pydantic-based settings for Microsoft Fabric business telemetry service.
Supports configuration via environment variables, .env files, or programmatic setup.
"""

import os
from typing import Optional, List, Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class FabricSettings(BaseSettings):
    """
    Configuration settings for Microsoft Fabric integration.

    All settings can be configured via environment variables with
    FABRIC_ prefix (e.g., FABRIC_TELEMETRY_ENABLED).
    """

    # General settings
    telemetry_enabled: bool = Field(
        default=True,
        description="Enable or disable business telemetry collection"
    )

    environment: str = Field(
        default="production",
        description="Environment name (development, staging, production)"
    )

    service_name: str = Field(
        default="business-telemetry",
        description="Service name for event source identification"
    )

    service_version: str = Field(
        default="1.0.0",
        description="Service version"
    )

    # Sink configuration
    sink_type: Literal["eventhub", "onelake", "console", "file", "composite"] = Field(
        default="console",
        description="Primary sink type for telemetry output"
    )

    composite_sinks: Optional[str] = Field(
        default=None,
        description="Comma-separated list of sink types for composite sink"
    )

    # Event Hub settings
    event_hub_connection_string: Optional[str] = Field(
        default=None,
        description="Azure Event Hub connection string"
    )

    event_hub_name: Optional[str] = Field(
        default=None,
        description="Event Hub name"
    )

    event_hub_namespace: Optional[str] = Field(
        default=None,
        description="Event Hub namespace (for managed identity auth)"
    )

    # OneLake settings
    onelake_workspace_id: Optional[str] = Field(
        default=None,
        description="Fabric workspace ID"
    )

    onelake_lakehouse_id: Optional[str] = Field(
        default=None,
        description="Fabric lakehouse ID"
    )

    onelake_base_path: str = Field(
        default="Files/business_telemetry",
        description="Base path in OneLake for telemetry files"
    )

    onelake_output_format: Literal["jsonl", "parquet"] = Field(
        default="jsonl",
        description="Output format for OneLake files"
    )

    # File sink settings
    file_output_dir: str = Field(
        default="./business_telemetry_output",
        description="Output directory for file sink"
    )

    # Batching settings
    batch_size: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Number of events to batch before sending"
    )

    flush_interval_seconds: float = Field(
        default=5.0,
        ge=0.1,
        le=300.0,
        description="Seconds between automatic flushes"
    )

    # API settings (for HTTP endpoint)
    api_host: str = Field(
        default="0.0.0.0",
        description="API server host"
    )

    api_port: int = Field(
        default=8080,
        ge=1,
        le=65535,
        description="API server port"
    )

    api_key: Optional[str] = Field(
        default=None,
        description="API key for authentication (optional)"
    )

    cors_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins"
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )

    # Azure Identity
    use_managed_identity: bool = Field(
        default=False,
        description="Use Azure Managed Identity for authentication"
    )

    azure_client_id: Optional[str] = Field(
        default=None,
        description="Azure client ID for workload identity"
    )

    model_config = {
        "env_prefix": "FABRIC_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }

    @field_validator("cors_origins")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        """Validate CORS origins format."""
        if v and v != "*":
            # Validate each origin
            for origin in v.split(","):
                origin = origin.strip()
                if not origin.startswith(("http://", "https://")):
                    raise ValueError(f"Invalid CORS origin: {origin}")
        return v

    def get_cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list."""
        if self.cors_origins == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def is_event_hub_configured(self) -> bool:
        """Check if Event Hub is properly configured."""
        return bool(
            (self.event_hub_connection_string and self.event_hub_name) or
            (self.event_hub_namespace and self.event_hub_name and self.use_managed_identity)
        )

    def is_onelake_configured(self) -> bool:
        """Check if OneLake is properly configured."""
        return bool(self.onelake_workspace_id and self.onelake_lakehouse_id)


class ServiceSettings(BaseSettings):
    """
    Service-level settings for the business telemetry HTTP API.
    """

    # Service identity
    service_name: str = Field(
        default="business-telemetry-service",
        description="Service name"
    )

    service_version: str = Field(
        default="1.0.0",
        description="Service version"
    )

    # Health check
    health_check_path: str = Field(
        default="/health",
        description="Health check endpoint path"
    )

    ready_check_path: str = Field(
        default="/ready",
        description="Readiness check endpoint path"
    )

    # Metrics
    metrics_enabled: bool = Field(
        default=True,
        description="Enable Prometheus metrics endpoint"
    )

    metrics_path: str = Field(
        default="/metrics",
        description="Metrics endpoint path"
    )

    # Rate limiting
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting"
    )

    rate_limit_requests: int = Field(
        default=1000,
        description="Maximum requests per window"
    )

    rate_limit_window_seconds: int = Field(
        default=60,
        description="Rate limit window in seconds"
    )

    model_config = {
        "env_prefix": "SERVICE_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }


# Singleton instances
_fabric_settings: Optional[FabricSettings] = None
_service_settings: Optional[ServiceSettings] = None


def get_fabric_settings() -> FabricSettings:
    """Get or create Fabric settings singleton."""
    global _fabric_settings
    if _fabric_settings is None:
        _fabric_settings = FabricSettings()
    return _fabric_settings


def get_service_settings() -> ServiceSettings:
    """Get or create service settings singleton."""
    global _service_settings
    if _service_settings is None:
        _service_settings = ServiceSettings()
    return _service_settings


def reset_settings():
    """Reset settings singletons (useful for testing)."""
    global _fabric_settings, _service_settings
    _fabric_settings = None
    _service_settings = None
