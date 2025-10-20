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

class ThreadHistoryMessage(TypedDict, total=False):
    """Message format returned by conversations.replies API.
    
    Based on: https://api.slack.com/methods/conversations.replies
    This matches the structure Slack returns in thread history.
    """
    ts: str                    # message timestamp (required in practice)
    user: str                  # user id who posted
    bot_id: str                # present on bot messages
    username: str              # display name (on bot messages)
    text: str                  # message text content
    thread_ts: str             # parent thread timestamp
    parent_user_id: str        # user who started the thread
    reply_count: int           # number of replies (on parent)
    reactions: List[Any]       # reactions to this message
    files: List[Any]           # attached files
    subtype: Optional[str]     # message subtype if any
    bot_profile: Optional[Any] # bot profile data

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
