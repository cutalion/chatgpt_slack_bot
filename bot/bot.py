import os
import logging
import config
import asyncio
import re
import json
from typing import Any, Dict, Iterable, List, Optional
from openai import AsyncOpenAI
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack import WebClient, AsyncWebClient
from slack_bolt import App
from slack_bolt.async_app import AsyncApp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = AsyncApp(token=config.SLACK_BOT_TOKEN) 
client = AsyncWebClient(config.SLACK_BOT_TOKEN)
model = config.GPT_MODEL

OPENAI_COMPLETION_OPTIONS = {
    "temperature": 0.7,
    "max_completion_tokens": config.MAX_OUTPUT_TOKENS,
    "top_p": 1,
    "frequency_penalty": 0,
    "presence_penalty": 0
}

aclient = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


def _to_responses_input(messages):
    """Convert chat-completions style messages to Responses API input format."""
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


def _get(obj: Any, key: str, default=None):
    """Attribute-or-dict getter."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _jsonify(obj: Any) -> Any:
    """Best-effort conversion of SDK objects to JSON-serializable types for logging."""
    # Primitive types
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    # Bytes: summarize
    if isinstance(obj, (bytes, bytearray)):
        return {"__type__": "bytes", "len": len(obj)}
    # Lists / tuples
    if isinstance(obj, (list, tuple)):
        return [ _jsonify(x) for x in obj ]
    # Dicts
    if isinstance(obj, dict):
        return { str(k): _jsonify(v) for k, v in obj.items() }
    # Try common helpers on SDK models
    for attr in ("to_dict", "model_dump", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return _jsonify(fn())
            except Exception:
                pass
    # Fallback: repr
    try:
        return repr(obj)
    except Exception:
        return str(type(obj))


def _extract_output_text(resp) -> Optional[str]:
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


async def generate_ai_reply(messages):
    """Generate a reply using the OpenAI Responses API exclusively.

    - Uses web_search tool when enabled via env.
    - Does not fall back to Chat Completions (legacy).
    """
    max_output_tokens = OPENAI_COMPLETION_OPTIONS.get("max_completion_tokens")
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

    # Debug: summarize request
    try:
        logger.info(
            "Responses.create: model=%s, inputs=%d, tools=%s, instr_len=%s, max_out=%s",
            model,
            len(filtered_messages),
            bool(getattr(config, "WEB_SEARCH_ENABLED", False)),
            (len(instructions) if isinstance(instructions, str) else None),
            max_output_tokens,
        )
        # Log full request body (excluding auth headers)
        try:
            logger.info("Responses.create.request args=%s", json.dumps(_jsonify(args), ensure_ascii=False))
        except Exception as e:
            logger.debug("Failed to serialize request args: %s", e)
    except Exception:
        pass
    if getattr(config, "WEB_SEARCH_ENABLED", False):
        args["tools"] = [{"type": "web_search"}]

    try:
        resp = await aclient.responses.create(**args)
        # Log the raw response body for full visibility
        try:
            if hasattr(resp, "to_json") and callable(getattr(resp, "to_json")):
                raw = resp.to_json()
            elif hasattr(resp, "model_dump_json") and callable(getattr(resp, "model_dump_json")):
                raw = resp.model_dump_json()
            else:
                raw = json.dumps(_jsonify(resp), ensure_ascii=False)
            logger.info("Responses.create.response raw=%s", raw)
        except Exception as e:
            logger.debug("Failed to serialize raw response: %s", e)
        # Minimal diagnostics to help debug empty replies
        try:
            outs = _get(resp, 'output', []) or []
            # Summarize content types for debugging, including tool usage
            type_counts: Dict[str, int] = {}
            samples: List[Dict[str, Any]] = []
            for out in outs:
                contents = _get(out, 'content', []) or []
                summary = {
                    'out_type': _get(out, 'type'),
                    'role': _get(out, 'role'),
                    'content_types': [],
                }
                for c in contents:
                    ctype = _get(c, 'type')
                    summary['content_types'].append(ctype)
                    key = ctype or 'None'
                    type_counts[key] = type_counts.get(key, 0) + 1
                samples.append(summary)
            logger.info("Responses output items: %d types=%s samples=%s", len(outs), type_counts, samples[:3])
        except Exception as e:
            logger.debug("Failed to summarize outputs: %s", e)

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
            logger.info("No text yet after tool_use; retrying without tools (tool_choice=none)")
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
async def handle_mention(body, logger):
    logger.info(f"New event: {body}")

    event = body["event"]
    user = event["user"]
    channel = event["channel"]
    event_ts = event["event_ts"]

    # Clean up Slack mention tokens like <@U12345>
    raw_text = str(event.get("text", ""))
    user_message = re.sub(r"<@[^>]+>", "", raw_text).strip()

    logger.info(f"User: {user}")
    logger.info(f"User message: {user_message}")
    # Build dynamic mention instruction
    mention_instruction = ""
    if config.BOT_NAME:
        mention_instruction = f"- Users mention you with @{config.BOT_NAME} or message you directly\n"
    else:
        mention_instruction = "- Users can mention you or message you directly\n"

    # Optional Tools section (only if web search is enabled)
    tools_section = ""
    if getattr(config, "WEB_SEARCH_ENABLED", False):
        strict_hint = "- When in doubt, use web_search to verify claims.\n" if getattr(config, "WEB_SEARCH_STRICT", False) else ""
        tools_section = f"""

<tools>
- You can call a tool named "web_search" to query the public web.
- Use it for time-sensitive or unknown facts, verification, or when users ask for sources or provide URLs/domains to investigate.
- Prefer authoritative sources; limit to 2–4 results; include dates when available.
- After using web_search, answer first, then brief rationale, then a short "Sources:" list (title, domain, clean URL). Avoid long quotes and tracking parameters.
- If web_search returns nothing useful or fails, say so and answer with best-known information, noting uncertainty.
- Do not use web_search for internal Slack/process questions, general opinions, or static knowledge unlikely to have changed.
</tools>
{strict_hint}"""

    prompt = f"""You are an AI assistant integrated into this Slack workspace to help users with questions, tasks, and information.

<core_instructions>
- Provide clear, accurate, and helpful responses
- Keep responses concise but complete - aim for 1-3 paragraphs unless more detail is explicitly requested
- Maintain context in threaded conversations by referencing relevant previous messages
- Use a professional yet friendly tone appropriate for workplace communication
- When uncertain, clearly state your uncertainty rather than guessing
- Avoid asking unnecessary clarification questions - work with the information provided
</core_instructions>

<slack_environment>
- You're responding in a Slack channel or direct message
{mention_instruction}- In threaded conversations, build naturally on the existing discussion
- Multiple users may participate in channel discussions
- Prioritize being helpful over being verbose
</slack_environment>

<response_guidelines>
- For simple questions: Give direct, concise answers
- For complex requests: Use clear structure with headings or bullet points
- For technical topics: Be precise and include relevant details
- Always aim to be immediately actionable and valuable
</response_guidelines>
{tools_section}
"""

    messages = [
        {"role": "system", "content": prompt},
    ]

    # Determine the root thread timestamp: existing thread or start a new one from the event
    root_ts = event.get("thread_ts", event_ts)

    if "thread_ts" in event:
        logger.info(f"Reply in thread {root_ts}:")

        conversation_history = await client.conversations_replies(channel=channel, ts=root_ts, limit=config.HISTORY_LIMIT)
        history = conversation_history.get("messages", [])

        for message in history[-config.HISTORY_LIMIT:]:
            role = "assistant" if "bot_id" in message else "user"
            messages.append({"role": role, "content": message.get("text", "")})

    messages.append({"role": "user", "content": user_message })

    ai_reply = await generate_ai_reply(messages)
    logger.info(f"AI reply length: {len(ai_reply) if ai_reply else 0}")
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
        logger.info(f"Slack post ok={ok} ts={ts} raw_type={type(result).__name__}")
    except Exception as e:
        logger.exception("Failed to post message to Slack: %s", e)

async def run():
    handler = AsyncSocketModeHandler(app, config.SLACK_APP_TOKEN)
    await handler.start_async()

if __name__ == "__main__":
    asyncio.run(run())
