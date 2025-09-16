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
    prompt = "As an advanced chatbot named ChatGPT, your primary goal is to assist users to the best of your ability. This may involve answering questions, providing helpful information, or completing tasks based on user input. In order to effectively assist users, it is important to be detailed and thorough in your responses. Use examples and evidence to support your points and justify your recommendations or solutions. Remember to always prioritize the needs and satisfaction of the user. Your ultimate goal is to provide a helpful and enjoyable experience for the user."

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

    ai_response = await aclient.chat.completions.create(
            model=model,
            messages=messages,
            **OPENAI_COMPLETION_OPTIONS)

    ai_reply = ai_response.choices[0].message.content
    await client.chat_postMessage(channel=channel, thread_ts=event_ts, text=ai_reply)

async def run():
    handler = AsyncSocketModeHandler(app, config.SLACK_APP_TOKEN)
    await handler.start_async()

if __name__ == "__main__":
    asyncio.run(run())
