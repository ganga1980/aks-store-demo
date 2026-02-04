"""
Microsoft 365 Agents SDK Integration Module for Business Telemetry.

This module provides integration with Microsoft 365 Agents SDK for enhanced
agent identification in business telemetry events. It generates unique agent
identifiers following the Microsoft 365 Agents SDK patterns.

The module provides:
- Unique agent ID generation using Microsoft Agent 365 SDK Activity patterns
- Integration with business telemetry for agent event correlation
- Support for conversation and activity tracking
- Compatibility with the microsoft-agents-activity and microsoft-agents-hosting-core packages

Microsoft 365 Agents SDK: https://github.com/Microsoft/Agents-for-python
"""

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)


# Check if Microsoft Agents SDK is available
_M365_AGENTS_SDK_AVAILABLE = False
_Activity = None
_TurnContext = None

try:
    from microsoft_agents.activity import Activity
    from microsoft_agents.hosting.core import TurnContext
    _M365_AGENTS_SDK_AVAILABLE = True
    _Activity = Activity
    _TurnContext = TurnContext
    logger.info("Microsoft 365 Agents SDK successfully loaded")
except ImportError as e:
    logger.warning(
        f"Microsoft 365 Agents SDK not available: {e}. "
        "Using fallback agent ID generation. "
        "Install with: pip install microsoft-agents-activity microsoft-agents-hosting-core"
    )


@dataclass
class M365AgentIdentity:
    """
    Microsoft 365 Agent Identity following the Agents SDK patterns.

    This class encapsulates agent identification attributes that can be
    used for business telemetry events and correlation across services.

    Attributes:
        agent_id: Unique identifier for the agent instance (UUID format)
        agent_name: Human-readable name of the agent
        agent_type: Type of agent (e.g., 'admin', 'customer', 'telemetry')
        channel_id: Communication channel identifier (e.g., 'webchat', 'teams')
        service_url: URL of the service hosting the agent
        tenant_id: Azure AD tenant ID (if applicable)
        app_id: Azure AD application ID (if applicable)
        conversation_id: Current conversation/thread identifier
        activity_id: Current activity identifier within conversation
    """

    agent_id: str
    agent_name: str
    agent_type: str = "telemetry"
    channel_id: str = "business-telemetry"
    service_url: Optional[str] = None
    tenant_id: Optional[str] = None
    app_id: Optional[str] = None
    conversation_id: Optional[str] = None
    activity_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_telemetry_attributes(self) -> Dict[str, Any]:
        """
        Convert agent identity to business telemetry attributes.

        Returns a dictionary of attributes following both Gen AI semantic
        conventions and Microsoft Agent 365 SDK conventions.
        """
        attrs = {
            # Gen AI semantic convention attributes
            "gen_ai.agent.id": self.agent_id,
            "gen_ai.agent.name": self.agent_name,

            # Microsoft 365 Agents SDK specific attributes
            "m365.agent.id": self.agent_id,
            "m365.agent.name": self.agent_name,
            "m365.agent.type": self.agent_type,
            "m365.channel.id": self.channel_id,
        }

        if self.service_url:
            attrs["m365.service.url"] = self.service_url
        if self.tenant_id:
            attrs["m365.tenant.id"] = self.tenant_id
        if self.app_id:
            attrs["m365.app.id"] = self.app_id
        if self.conversation_id:
            attrs["gen_ai.conversation.id"] = self.conversation_id
            attrs["m365.conversation.id"] = self.conversation_id
        if self.activity_id:
            attrs["m365.activity.id"] = self.activity_id

        return attrs


class M365AgentIdProvider:
    """
    Provider for Microsoft 365 Agent identifiers for business telemetry.

    This class generates and manages unique agent identifiers that are
    compatible with the Microsoft 365 Agents SDK Activity model and
    can be used for business telemetry event correlation.
    """

    def __init__(
        self,
        agent_name: str,
        agent_type: str = "telemetry",
        channel_id: str = "business-telemetry",
        service_url: Optional[str] = None,
        tenant_id: Optional[str] = None,
        app_id: Optional[str] = None,
    ):
        """
        Initialize the M365 Agent ID Provider.

        Args:
            agent_name: Human-readable name of the agent
            agent_type: Type of agent (e.g., 'admin', 'customer', 'telemetry')
            channel_id: Communication channel identifier
            service_url: URL of the service hosting the agent
            tenant_id: Azure AD tenant ID (from environment if not provided)
            app_id: Azure AD application ID (from environment if not provided)
        """
        self.agent_name = agent_name
        self.agent_type = agent_type
        self.channel_id = channel_id
        self.service_url = service_url

        # Try to get tenant_id and app_id from environment if not provided
        self.tenant_id = tenant_id or os.environ.get("AZURE_TENANT_ID")
        self.app_id = app_id or os.environ.get("AZURE_CLIENT_ID")

        # Generate a stable agent ID based on configuration
        self._agent_id = self._generate_agent_id()

        # Track conversation-to-activity mappings
        self._conversations: Dict[str, list] = {}

        logger.info(
            f"M365AgentIdProvider initialized: agent_id={self._agent_id}, "
            f"agent_name={self.agent_name}, sdk_available={_M365_AGENTS_SDK_AVAILABLE}"
        )

    def _generate_agent_id(self) -> str:
        """
        Generate a unique, stable agent ID.

        The ID is generated using a combination of:
        - Agent name
        - Agent type
        - Tenant ID (if available)
        - App ID (if available)
        - Pod/instance information (if in Kubernetes)

        This ensures the same agent configuration produces the same ID,
        while different instances can be distinguished.
        """
        # Build components for ID generation
        components = [
            self.agent_name,
            self.agent_type,
            self.tenant_id or "default-tenant",
            self.app_id or "default-app",
        ]

        # Add pod name if running in Kubernetes for instance uniqueness
        pod_name = os.environ.get("POD_NAME", "")
        if pod_name:
            components.append(pod_name)
        else:
            # In non-K8s environments, add a stable machine identifier
            components.append(os.environ.get("HOSTNAME", str(uuid.getnode())))

        # Create a deterministic hash
        hash_input = "|".join(components)
        hash_bytes = hashlib.sha256(hash_input.encode()).digest()

        # Convert to UUID format (using first 16 bytes)
        agent_uuid = uuid.UUID(bytes=hash_bytes[:16])

        return str(agent_uuid)

    @property
    def agent_id(self) -> str:
        """Get the unique agent ID."""
        return self._agent_id

    @property
    def is_sdk_available(self) -> bool:
        """Check if Microsoft 365 Agents SDK is available."""
        return _M365_AGENTS_SDK_AVAILABLE

    def get_identity(
        self,
        conversation_id: Optional[str] = None,
        activity_id: Optional[str] = None,
    ) -> M365AgentIdentity:
        """
        Get the agent identity with optional conversation context.

        Args:
            conversation_id: Current conversation/thread ID
            activity_id: Current activity ID within the conversation

        Returns:
            M365AgentIdentity with all relevant attributes
        """
        return M365AgentIdentity(
            agent_id=self._agent_id,
            agent_name=self.agent_name,
            agent_type=self.agent_type,
            channel_id=self.channel_id,
            service_url=self.service_url,
            tenant_id=self.tenant_id,
            app_id=self.app_id,
            conversation_id=conversation_id,
            activity_id=activity_id,
        )

    def create_conversation_id(self) -> str:
        """
        Create a new conversation ID following M365 Agents SDK patterns.

        Returns:
            A new unique conversation ID
        """
        conversation_id = str(uuid.uuid4())
        self._conversations[conversation_id] = []
        return conversation_id

    def create_activity_id(self, conversation_id: str) -> str:
        """
        Create a new activity ID within a conversation.

        Args:
            conversation_id: The conversation to add the activity to

        Returns:
            A new unique activity ID
        """
        activity_id = str(uuid.uuid4())

        if conversation_id in self._conversations:
            self._conversations[conversation_id].append(activity_id)
        else:
            self._conversations[conversation_id] = [activity_id]

        return activity_id

    def create_activity(
        self,
        conversation_id: str,
        text: str,
        from_id: str,
        activity_type: str = "message",
    ) -> Optional[Any]:
        """
        Create a Microsoft 365 Agents SDK Activity if the SDK is available.

        Args:
            conversation_id: The conversation ID
            text: The message text
            from_id: The sender's ID
            activity_type: Type of activity (default: 'message')

        Returns:
            An Activity object if SDK is available, None otherwise
        """
        if not _M365_AGENTS_SDK_AVAILABLE or _Activity is None:
            logger.debug("M365 Agents SDK not available, skipping Activity creation")
            return None

        activity_id = self.create_activity_id(conversation_id)

        try:
            # Create an Activity following M365 Agents SDK patterns
            activity = _Activity(
                type=activity_type,
                id=activity_id,
                channel_id=self.channel_id,
                conversation={"id": conversation_id},
                from_property={"id": from_id, "name": "User"},
                recipient={"id": self._agent_id, "name": self.agent_name},
                text=text,
                service_url=self.service_url,
            )
            return activity
        except Exception as e:
            logger.warning(f"Failed to create M365 Activity: {e}")
            return None


# Global instance cache for agent ID providers
_agent_id_providers: Dict[str, M365AgentIdProvider] = {}


def get_m365_agent_id_provider(
    agent_name: str,
    agent_type: str = "telemetry",
    **kwargs,
) -> M365AgentIdProvider:
    """
    Get or create an M365 Agent ID Provider.

    This function provides a cached singleton instance per agent name
    to ensure consistent agent IDs across the application.

    Args:
        agent_name: Name of the agent
        agent_type: Type of agent
        **kwargs: Additional arguments passed to M365AgentIdProvider

    Returns:
        M365AgentIdProvider instance
    """
    cache_key = f"{agent_name}:{agent_type}"

    if cache_key not in _agent_id_providers:
        _agent_id_providers[cache_key] = M365AgentIdProvider(
            agent_name=agent_name,
            agent_type=agent_type,
            **kwargs,
        )

    return _agent_id_providers[cache_key]


def get_m365_agent_id(
    agent_name: str,
    agent_type: str = "telemetry",
    **kwargs,
) -> str:
    """
    Get the M365 unique agent ID for a given agent.

    Convenience function that gets the provider and returns just the agent ID.

    Args:
        agent_name: Name of the agent
        agent_type: Type of agent
        **kwargs: Additional arguments passed to M365AgentIdProvider

    Returns:
        The unique agent ID (UUID format)
    """
    provider = get_m365_agent_id_provider(agent_name, agent_type, **kwargs)
    return provider.agent_id


def is_m365_sdk_available() -> bool:
    """Check if Microsoft 365 Agents SDK is available."""
    return _M365_AGENTS_SDK_AVAILABLE


def clear_cached_providers() -> None:
    """Clear the cached M365 agent ID providers."""
    global _agent_id_providers
    _agent_id_providers = {}
    logger.info("M365 agent ID providers cache cleared")
