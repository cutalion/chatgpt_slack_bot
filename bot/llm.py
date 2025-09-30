"""
Backward-compatible wrapper for agent provider interface.

This module maintains the original generate_ai_reply() function signature
while delegating to the new provider-agnostic agent architecture.
"""

from typing import Any, Dict, Iterable, Optional

from agent_provider import get_agent_provider


async def generate_ai_reply(
    messages: Iterable[Dict[str, Any]],
    *,
    slack_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate a reply using the configured agent provider.

    This function maintains backward compatibility with the original interface
    while delegating to the provider-agnostic agent architecture.

    Args:
        messages: Conversation history (role/content dicts)
        slack_context: Optional Slack metadata (channel, thread, etc.)

    Returns:
        Response text ready to post to Slack
    """
    agent = get_agent_provider()
    # Convert Iterable to List for protocol compliance
    message_list = list(messages)
    return await agent.generate_reply(message_list, slack_context=slack_context)


__all__ = ["generate_ai_reply"]