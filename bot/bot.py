import logging
import asyncio
import re
from typing import Any, Dict, cast
import config
from prompt import build_system_prompt
import llm
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient
from slack_types import SlackEventBody, SlackEvent
from slack_utils import (
    format_ts_utc,
    get_bot_name_from_message,
    get_bot_user_id,
    get_user_display_name,
    normalise_user_mentions,
    slack_client,
    is_supported_event,
    clean_user_message,
    build_conversation_messages,
)
from slack_utils import get_channel_descriptor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Reduce noisy third-party INFO logs
try:
    logging.getLogger("httpx").setLevel(logging.WARNING)
except Exception:
    pass

app = AsyncApp(token=config.SLACK_BOT_TOKEN)
client = slack_client

async def request_clarification(client: AsyncWebClient, channel: str, thread_ts: str, logger: logging.Logger) -> None:
    """Request clarification from the user."""
    try:
        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="I received your message, but it appears to be empty. Could you please let me know how I can help you?"
        )
    except Exception as e:
        logger.exception("Failed to post clarification request: %s", e)

@app.event("app_mention")
@app.event({"type": "message", "channel_type": "im"})
async def handle_mention(body: SlackEventBody, logger: logging.Logger) -> None:
    """Handle mentions and direct messages routed through the Slack Bolt app."""

    event: SlackEvent = body["event"]

    # Check if this is a supported event type
    if not is_supported_event(event, logger):
        return  # Event not supported, ignore it

    # Extract essential data from the event
    user = event["user"]
    channel = event["channel"]
    event_ts = event["event_ts"]
    thread_ts = event.get("thread_ts")
    root_ts = thread_ts if thread_ts else event_ts
    channel_type = event.get("channel_type")
    raw_text = event.get("text", "").strip()

    channel_descriptor = get_channel_descriptor(channel, channel_type)

    logger.info(
        "Slack event type=%s channel=%s event_ts=%s thread_ts=%s user=%s text_preview=%s",
        event.get("type"),
        channel,
        event_ts,
        thread_ts,
        user,
        raw_text[:120],
    )

    bot_uid = await get_bot_user_id()
    user_message = clean_user_message(raw_text, bot_uid)

    # Handle blank inputs - respond with clarification request
    if not user_message:
        logger.info("Received empty message from user=%s, requesting clarification", user)
        await request_clarification(client, channel, thread_ts, logger)
        return

    prompt = build_system_prompt(
        current_channel_descriptor=channel_descriptor,
        current_channel_id=channel,
        current_thread_ts=root_ts,
    )

    # Prepare thread history if this is part of a thread
    thread_history = []
    if "thread_ts" in event:
        try:
            conversation_history = await client.conversations_replies(
                channel=channel,
                ts=root_ts,
                limit=config.HISTORY_LIMIT,
            )
            raw_history = conversation_history.get("messages", [])
            
            # Pre-format history messages with resolved author names
            for message in raw_history:
                role = "assistant" if "bot_id" in message else "user"
                user_id = message.get("user") if role == "user" else None
                
                # Resolve author name
                if role == "assistant":
                    author = config.BOT_NAME or get_bot_name_from_message(message)
                else:
                    author = await get_user_display_name(user_id)
                
                # Create pre-formatted message with author name
                prefix = f"{format_ts_utc(message.get('ts'))} {author}"
                if user_id:
                    prefix += f" (<@{user_id}>)"
                prefix += ": "
                
                formatted_message = {
                    "ts": message.get("ts"),
                    "user": message.get("user"),
                    "bot_id": message.get("bot_id"),
                    "text": prefix + message.get("text", ""),
                }
                thread_history.append(formatted_message)
                
        except Exception as exc:
            logger.debug("Failed to fetch thread history for %s: %s", channel, exc)
            # Continue without history rather than crashing

    # Get current user display name
    try:
        current_author = await get_user_display_name(user)
    except Exception:
        current_author = str(user)

    # Build messages using the pure function
    messages = build_conversation_messages(
        system_prompt=prompt,
        thread_history=thread_history,
        current_event_ts=event_ts,
        current_user_display=current_author,
        current_user_id=user,
        current_message_text=user_message,
        bot_name=config.BOT_NAME or "Bot",
        history_limit=config.HISTORY_LIMIT,
    )

    slack_context = {
        "channel_id": channel,
        "channel_type": channel_type,
        "channel_descriptor": channel_descriptor,
        "root_thread_ts": root_ts,
        "requesting_user_id": user,
    }

    ai_reply = await llm.generate_ai_reply(messages, slack_context=slack_context)
    if not ai_reply:
        ai_reply = "Sorry, I couldn't generate a response just now. Please try again."
    else:
        ai_reply = normalise_user_mentions(ai_reply)

    try:
        result = await client.chat_postMessage(channel=channel, thread_ts=root_ts, text=ai_reply)
        # Slack client often returns a SlackResponse with a .data dict
        data = getattr(result, "data", None)
        if isinstance(result, dict) and not data:
            data = result

        ok = None
        ts = None
        if isinstance(data, dict):
            ok = data.get("ok")
            ts = data.get("ts") or (data.get("message") or {}).get("ts")
        if ok is not True:
            logger.warning(f"Slack post failed or uncertain ok={ok} ts={ts} type={type(result).__name__}")
        else:
            logger.info("Replied to Slack channel=%s thread_ts=%s ts=%s", channel, root_ts, ts)
    except Exception as e:
        logger.exception("Failed to post message to Slack: %s", e)

async def run() -> None:
    """Start the Slack Socket Mode handler until cancelled."""
    handler = AsyncSocketModeHandler(app, config.SLACK_APP_TOKEN)
    await handler.start_async()

if __name__ == "__main__":
    asyncio.run(run())
