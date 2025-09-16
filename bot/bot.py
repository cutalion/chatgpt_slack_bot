import os
import logging
import config
import asyncio
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
    "max_completion_tokens": 1000,
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
        if isinstance(content, str):
            converted.append({
                "role": role,
                "content": [{"type": "text", "text": content}],
            })
        else:
            # Fallback: best-effort stringify
            converted.append({
                "role": role,
                "content": [{"type": "text", "text": str(content)}],
            })
    return converted


async def generate_ai_reply(messages):
    """Generate a reply using the OpenAI Responses API exclusively.

    - Uses web_search tool when enabled via env.
    - Does not fall back to Chat Completions (legacy).
    """
    max_output_tokens = OPENAI_COMPLETION_OPTIONS.get("max_completion_tokens")
    args = {
        "model": model,
        "input": _to_responses_input(messages),
        "temperature": OPENAI_COMPLETION_OPTIONS.get("temperature"),
        "top_p": OPENAI_COMPLETION_OPTIONS.get("top_p"),
        "max_output_tokens": max_output_tokens,
    }
    if getattr(config, "WEB_SEARCH_ENABLED", False):
        args["tools"] = [{"type": "web_search"}]

    try:
        resp = await aclient.responses.create(**args)
        text = getattr(resp, "output_text", None)
        if not text:
            try:
                pieces = []
                for out in getattr(resp, "output", []) or []:
                    for c in getattr(out, "content", []) or []:
                        t = getattr(c, "text", None)
                        if t:
                            pieces.append(t)
                text = "\n\n".join(pieces) if pieces else None
            except Exception:
                text = None

        if text:
            return text
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

    user_message = str(event["text"]).replace(f"<{user}>", "")

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

    if "thread_ts" in event:
        thread_ts = event["thread_ts"]
        logger.info(f"Reply in thread {thread_ts}:")

        conversation_history = await client.conversations_replies(channel=channel, ts=thread_ts, limit=100)
        history = conversation_history["messages"]

        for message in history:
            role = "assistant" if "bot_id" in message else "user"
            messages.append({"role": role, "content": message["text"]})
    else:
        await client.chat_postMessage(channel=channel, thread_ts=event_ts, text="...")

    messages.append({"role": "user", "content": user_message })

    ai_reply = await generate_ai_reply(messages)
    await client.chat_postMessage(channel=channel, thread_ts=event_ts, text=ai_reply)

async def run():
    handler = AsyncSocketModeHandler(app, config.SLACK_APP_TOKEN)
    await handler.start_async()

if __name__ == "__main__":
    asyncio.run(run())
