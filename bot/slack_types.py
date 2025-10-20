from typing import TypedDict, Optional, List, Union, Literal, Any

# Channel types as defined by Slack Events API
ChannelType = Literal["im", "channel", "group", "mpim"]

class MessageEventBase(TypedDict, total=False):
    """Base type for message events from Slack.
    
    Based on: https://api.slack.com/events/message
    """
    type: str                  # usually "message"
    subtype: str               # e.g. "bot_message", "message_changed", etc.
    event_ts: str
    ts: str                    # message timestamp
    thread_ts: str             # present when message is part of a thread
    user: str                  # user id (may be absent for some bot messages)
    bot_id: str                # present on bot-posted messages
    text: str
    channel: str
    channel_type: ChannelType
    blocks: List[Any]
    attachments: List[Any]
    files: List[Any]           # attached files
    edited: Any                # message edit information
    reactions: List[Any]       # reaction objects
    # other optional keys exist (reactions, edited, etc.)

class AppMentionEvent(TypedDict, total=False):
    """Type definition for app_mention events from Slack.
    
    Based on: https://api.slack.com/events/app_mention
    """
    type: Literal["app_mention"]
    user: str
    text: str
    ts: str
    thread_ts: str
    channel: str
    channel_type: ChannelType
    event_ts: str
    blocks: List[Any]
    attachments: List[Any]
    files: List[Any]
    edited: Any
    reactions: List[Any]
    # ... other optional fields

class MessageImEvent(MessageEventBase):
    """Type definition for message.im events from Slack (direct messages).
    
    Based on: https://api.slack.com/events/message.im
    """
    type: Literal["message"]
    channel_type: Literal["im"]  # "im" for direct messages
    # Inherits all other fields from MessageEventBase

SlackEvent = Union[AppMentionEvent, MessageImEvent]

class SlackEventBody(TypedDict):
    """Type definition for the body parameter passed to Slack event handlers."""
    token: str  # Verification token
    team_id: str  # Team/workspace ID
    api_app_id: str  # App ID
    event: SlackEvent  # The actual event data
    type: str  # "event_callback"
    event_id: str  # Unique event ID
    event_time: int  # Event timestamp (Unix epoch)
    # Different fields for different event types
    authed_teams: Optional[List[str]]  # For message.im events
    authed_users: Optional[List[str]]  # For app_mention events
