"""
Agent provider abstraction for multi-provider LLM support.

This module defines the interface contract that all agent providers must implement,
enabling the Slack bot to work with different LLM providers (OpenAI, Anthropic, etc.)
without changing the bot integration logic.
"""

from typing import Protocol, Dict, Any, List, Optional


class AgentProvider(Protocol):
    """
    Protocol defining the interface that all agent providers must implement.

    This abstraction allows the Slack bot to be provider-agnostic, supporting
    multiple LLM backends (OpenAI direct API, OpenAI Agents SDK, Anthropic Agent SDK, etc.)
    through a unified interface.

    Design principles:
    - Messages are passed as a list of dicts with 'role' and 'content' keys
    - System messages can be included in messages list (role='system')
    - Context provides provider-agnostic metadata (channel, thread, etc.)
    - Return value is always a string ready to post to Slack
    - Errors are handled internally; never raise exceptions to caller
    """

    async def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        *,
        slack_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate a reply from the agent based on conversation history.

        Args:
            messages: Conversation history as a list of message dicts.
                     Each dict must have 'role' (system/user/assistant) and 'content' keys.
                     System messages are typically first in the list and contain instructions.
            slack_context: Optional Slack-specific context including:
                          - channel_id: Slack channel ID
                          - channel_type: Type of channel (im, mpim, channel, group)
                          - channel_descriptor: Human-readable channel description
                          - root_thread_ts: Thread timestamp if in a thread

        Returns:
            Response text ready to post to Slack. Must be non-empty string.
            If generation fails, should return a user-friendly error message,
            never an empty string or None.

        Notes:
            - This method must never raise exceptions; all errors should be caught
              and converted to user-friendly error messages
            - System messages (role='system') should be extracted and used as instructions
            - Provider-specific tool execution should happen transparently within this call
            - Response should be normalized for Slack (mention format, length limits, etc.)
        """
        ...


def get_agent_provider() -> AgentProvider:
    """
    Factory function to get the configured agent provider.

    Returns the appropriate agent provider based on configuration.
    Currently returns OpenAIDirectAgent (existing implementation).
    Future versions will support selection via AGENT_PROVIDER env var.

    Returns:
        Configured agent provider instance.

    Example:
        agent = get_agent_provider()
        response = await agent.generate_reply(messages, slack_context=context)
    """
    from llm_openai_direct import OpenAIDirectAgent

    # Future: support configuration-driven provider selection
    # provider_type = config.AGENT_PROVIDER  # e.g., "openai-direct", "openai-sdk", "anthropic"
    # if provider_type == "openai-sdk":
    #     return OpenAISDKAgent()
    # elif provider_type == "anthropic":
    #     return AnthropicAgent()

    return OpenAIDirectAgent()


__all__ = ["AgentProvider", "get_agent_provider"]