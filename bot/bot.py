import logging
import asyncio
import re
from typing import Any, Dict
import config
from prompt import build_system_prompt
from llm import generate_ai_reply
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_utils import (
    format_ts_utc,
    get_bot_name_from_message,
    get_bot_user_id,
    get_user_display_name,
    normalise_user_mentions,
    slack_client,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Reduce noisy third-party INFO logs
try:
    logging.getLogger("httpx").setLevel(logging.WARNING)
except Exception:
    pass

app = AsyncApp(token=config.SLACK_BOT_TOKEN)
client = slack_client

@app.event("app_mention")
@app.event({"type": "message", "channel_type": "im"})
async def handle_mention(body: Dict[str, Any], logger: logging.Logger) -> None:
    """Handle mentions and direct messages routed through the Slack Bolt app."""

    event = body["event"]

    # Filter non-actionable events early to avoid unnecessary processing
    subtype = event.get("subtype")
    if subtype in ("message_changed", "message_deleted", "bot_message"):
        logger.debug("Ignoring event with subtype=%s", subtype)
        return

    # Skip events from this bot to prevent reply loops
    bot_id = event.get("bot_id")
    if bot_id:
        logger.debug("Ignoring message from bot_id=%s", bot_id)
        return

    user = event.get("user")
    if not user:
        logger.debug("Ignoring event without user field")
        return

    channel = event["channel"]
    event_ts = event["event_ts"]
    channel_type = event.get("channel_type")

    channel_descriptor = None
    if isinstance(channel, str):
        descriptor = channel
        if isinstance(channel_type, str):
            type_map = {
                "im": "direct message",
                "mpim": "multi-person DM",
                "group": "private channel",
                "channel": "public channel",
            }
            human_label = type_map.get(channel_type, channel_type)
            if human_label:
                descriptor = f"{channel} ({human_label})"
        channel_descriptor = descriptor

    # Clean up only our bot's leading mention token(s), preserving other mentions
    raw_text = str(event.get("text", ""))
    logger.debug(
        "Slack event type=%s channel=%s thread_ts=%s user=%s text_preview=%s",
        event.get("type"),
        channel,
        event.get("thread_ts"),
        user,
        raw_text[:120],
    )
    logger.info(
        "Incoming Slack message channel=%s thread_ts=%s user=%s text_preview=%s",
        channel,
        event.get("thread_ts", ""),
        user,
        raw_text[:120],
    )

    bot_uid = await get_bot_user_id()
    if bot_uid:
        # Remove one or more leading mentions of the bot (e.g., "<@U123> hello")
        pattern = rf"^\s*(<@{re.escape(bot_uid)}>[:,]?\s*)+"
        user_message = re.sub(pattern, "", raw_text).strip()
    else:
        # Fallback: remove only leading generic mention tokens
        user_message = re.sub(r"^\s*(<@[^>]+>[:,]?\s*)+", "", raw_text).strip()

    root_ts = event.get("thread_ts", event_ts)

    prompt = build_system_prompt(
        current_channel_descriptor=channel_descriptor,
        current_channel_id=channel if isinstance(channel, str) else None,
        current_thread_ts=root_ts if isinstance(root_ts, str) else None,
    )

    messages = [
        {"role": "system", "content": prompt},
    ]

    # If this is part of a thread, load recent replies for additional context
    if "thread_ts" in event:
        # Intentionally quiet unless errors occur

        conversation_history = await client.conversations_replies(channel=channel, ts=root_ts, limit=config.HISTORY_LIMIT)
        history = conversation_history.get("messages", [])

        for message in history[-config.HISTORY_LIMIT:]:
            # Skip the triggering message - it will be added separately below
            if message.get("ts") == event_ts:
                continue

            role = "assistant" if "bot_id" in message else "user"
            user_id = message.get("user") if role == "user" else None
            # Resolve author name and timestamp
            if role == "assistant":
                author = config.BOT_NAME or get_bot_name_from_message(message)
            else:
                author = await get_user_display_name(user_id)
            prefix = f"{format_ts_utc(message.get('ts'))} {author}"
            if user_id:
                prefix += f" (<@{user_id}>)"
            prefix += ": "
            content_text = message.get("text", "")
            messages.append({"role": role, "content": prefix + content_text})

    # Prefix the current event message with author/time as well
    try:
        current_author = await get_user_display_name(user)
    except Exception:
        current_author = str(user)
    current_prefix = f"{format_ts_utc(event_ts)} {current_author}"
    if isinstance(user, str) and user.strip():
        current_prefix += f" (<@{user}>)"
    current_prefix += ": "
    messages.append({"role": "user", "content": current_prefix + user_message })

    slack_context = {
        "channel_id": channel,
        "channel_type": channel_type,
        "channel_descriptor": channel_descriptor,
        "root_thread_ts": root_ts,
    }

    ai_reply = await generate_ai_reply(messages, slack_context=slack_context)
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
