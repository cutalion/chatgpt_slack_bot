import logging
import asyncio
import re
from typing import Any, Dict, Iterable, List, Optional
import config
from prompt import build_system_prompt
from openai import AsyncOpenAI
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
model = config.GPT_MODEL

aclient = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


def _to_responses_input(messages: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert Chat Completions-style messages into Responses API payload blocks."""
    converted = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        # Normalize content to string
        if not isinstance(content, str):
            content = str(content)

        # Map to Responses API content types
        # - user/system inputs -> "input_text"
        # - assistant prior outputs -> "output_text"
        content_type = "output_text" if role == "assistant" else "input_text"

        converted.append({
            "role": role,
            "content": [
                {
                    "type": content_type,
                    "text": content,
                }
            ],
        })
    return converted


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Attribute-or-dict getter."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)



def _extract_output_text(resp: Any) -> Optional[str]:
    """Robustly extract text from a Responses API result.

    Handles SDK objects where content.text may be a structured object
    with a `.value` field, not a raw string.
    """
    # Fast path provided by SDK
    try:
        text = getattr(resp, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text
    except Exception:
        pass

    pieces: List[str] = []
    try:
        outputs: Iterable[Any] = _get(resp, "output", []) or []
        for out in outputs:
            contents: Iterable[Any] = _get(out, "content", []) or []
            for c in contents:
                # prioritize textual content blocks
                ctype = _get(c, "type")
                if ctype not in ("output_text", "summary_text", "message_text", "text", None):
                    continue
                t = _get(c, "text")
                if t is None:
                    continue
                # SDK may return a Text object with `.value` or a dict
                if isinstance(t, str):
                    pieces.append(t)
                else:
                    val = _get(t, "value")
                    if isinstance(val, str) and val.strip():
                        pieces.append(val)
                    else:
                        # Some shapes use {"text": "..."}
                        val2 = _get(t, "text")
                        if isinstance(val2, str) and val2.strip():
                            pieces.append(val2)
    except Exception as e:
        logger.debug(f"Failed to parse response.output content: {e}")

    joined = "\n\n".join(pieces).strip() if pieces else ""
    return joined if joined else None


async def generate_ai_reply(messages: Iterable[Dict[str, Any]]) -> str:
    """Generate a reply using the OpenAI Responses API exclusively.

    - Uses web_search tool when enabled via env.
    - Does not fall back to Chat Completions (legacy).
    """
    max_output_tokens = config.MAX_OUTPUT_TOKENS
    # Extract a system prompt and pass via `instructions` per Responses API best practices
    instructions = None
    filtered_messages = []
    for m in messages:
        if m.get("role") == "system":
            # Keep the last seen system message as instructions
            instructions = m.get("content") if isinstance(m.get("content"), str) else str(m.get("content"))
        else:
            filtered_messages.append(m)

    args = {
        "model": model,
        "input": _to_responses_input(filtered_messages),
        # Only pass widely-supported params to avoid model-specific 400s
        "max_output_tokens": max_output_tokens,
    }
    if instructions:
        args["instructions"] = instructions
    if getattr(config, "REASONING_EFFORT", None):
        args["reasoning"] = {"effort": config.REASONING_EFFORT}

    # Keep logs minimal; only log on errors below
    if getattr(config, "WEB_SEARCH_ENABLED", False):
        args["tools"] = [{"type": "web_search"}]

    try:
        resp = await aclient.responses.create(**args)
        # If status not completed, log warning with details
        try:
            status = _get(resp, 'status')
            if status and status != 'completed':
                reason = _get(_get(resp, 'incomplete_details', {}), 'reason')
                logger.warning("Responses status=%s reason=%s", status, reason)
        except Exception:
            pass

        # Prepare outs for tool detection, but avoid verbose logs
        outs = _get(resp, 'output', []) or []

        text = _extract_output_text(resp)
        if text and text.strip():
            logger.debug("Extracted output_text (len=%d)", len(text.strip()))
            return text.strip()
        # Fallback: if tools were used and no text, try a single retry without tools
        has_tool_use = False
        try:
            for out in outs:
                if _get(out, 'type') in ('tool_use', 'web_search_call', 'web.search.call'):
                    has_tool_use = True
                    break
                for c in _get(out, 'content', []) or []:
                    if _get(c, 'type') in ('tool_use', 'web_search_call', 'web.search.call'):
                        has_tool_use = True
                        break
        except Exception:
            pass

        if has_tool_use and getattr(config, "WEB_SEARCH_ENABLED", False):
            retry_args = {
                k: v for k, v in args.items() if k not in ("tools",)
            }
            retry_args["tool_choice"] = "none"
            # Nudge the model to answer directly
            if instructions:
                retry_args["instructions"] = instructions + "\n\nTools are unavailable; answer directly without using tools."
            resp2 = await aclient.responses.create(**retry_args)
            text2 = _extract_output_text(resp2)
            if text2 and text2.strip():
                return text2.strip()

        logger.warning("No output_text extracted from response; sending fallback")
        return "Sorry, I couldn't generate a response just now. Please try again."
    except Exception as e:
        logger.exception("Responses API failed: %s", e)
        return "Sorry, I’m having trouble reaching the model right now. Please try again in a moment."

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
