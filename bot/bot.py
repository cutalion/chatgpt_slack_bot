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
    user = event["user"]
    channel = event["channel"]
    event_ts = event["event_ts"]

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
    bot_uid = await get_bot_user_id()
    if bot_uid:
        # Remove one or more leading mentions of the bot (e.g., "<@U123> hello")
        pattern = rf"^\s*(<@{re.escape(bot_uid)}>[:,]?\s*)+"
        user_message = re.sub(pattern, "", raw_text).strip()
    else:
        # Fallback: remove only leading generic mention tokens
        user_message = re.sub(r"^\s*(<@[^>]+>[:,]?\s*)+", "", raw_text).strip()

    prompt = build_system_prompt()

    messages = [
        {"role": "system", "content": prompt},
    ]

    # Determine the root thread timestamp: existing thread or start a new one from the event
    root_ts = event.get("thread_ts", event_ts)

    if "thread_ts" in event:
        # Intentionally quiet unless errors occur

        conversation_history = await client.conversations_replies(channel=channel, ts=root_ts, limit=config.HISTORY_LIMIT)
        history = conversation_history.get("messages", [])

        for message in history[-config.HISTORY_LIMIT:]:
            role = "assistant" if "bot_id" in message else "user"
            # Resolve author name and timestamp
            if role == "assistant":
                author = config.BOT_NAME or get_bot_name_from_message(message)
            else:
                author = await get_user_display_name(message.get("user"))
            prefix = f"{format_ts_utc(message.get('ts'))} {author}: "
            content_text = message.get("text", "")
            messages.append({"role": role, "content": prefix + content_text})

    # Prefix the current event message with author/time as well
    try:
        current_author = await get_user_display_name(user)
    except Exception:
        current_author = str(user)
    current_prefix = f"{format_ts_utc(event_ts)} {current_author}: "
    messages.append({"role": "user", "content": current_prefix + user_message })

    ai_reply = await generate_ai_reply(messages)
    if not ai_reply:
        ai_reply = "Sorry, I couldn't generate a response just now. Please try again."
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
    except Exception as e:
        logger.exception("Failed to post message to Slack: %s", e)

async def run() -> None:
    """Start the Slack Socket Mode handler until cancelled."""
    handler = AsyncSocketModeHandler(app, config.SLACK_APP_TOKEN)
    await handler.start_async()

if __name__ == "__main__":
    asyncio.run(run())
