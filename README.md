# ChatGPT Slack Bot

## Usage
Mention bot to start dialog. Mentioning in thread will add previuos messages as a context for ChatGPT.

## Setup

0. You'll need docker compose.

1. Register slack app/bot.
Go to [slack api](https://api.slack.com/apps?new_app=1) and create new app.
Use manifest from this repo or create app from scratch.

2. Make sure bot has permissions
Features > OAuth & Permissions:  
`app_mentions:read`  
`channels:history`  
`channels:read`  
`chat:write`  
`groups:history`

3.  Copy "Bot User OAuth Token" (starts with `xoxb-`)

4. Make sure socket mode is enabled
Add and copy token from "Basic Information", "App-Level Tokens" section (token starts with `xapp-`)
Enable and token on "Settins > Socket Mode" page if it is not enabled.

5. Enable event subscriptions and subscribe to `app_mention`
Go to "Basic Information > Event Subscriptions", enable subscriptions and subscribe to `app_mention`


6. Get your [OpenAI API](https://openai.com/api/) key

7. Add tokens to .env
Copy `.env.example` and replace tokens

```bash
mv .env.example .env
```

8. Build and run bot
```bash
docker compose up --build
```

## Optional: Web Search Tool

- Enable web search: set `WEB_SEARCH_ENABLED=true` in `.env`.
- The bot uses the OpenAI Responses API exclusively (no Chat Completions fallback). Choose a model that supports the Responses API, and web_search if you enable it.
- Behavior: The bot answers normally, but when web search is needed (time-sensitive facts, requested sources, or verification), it may search and include a brief Sources list.
- Strict mode: set `WEB_SEARCH_STRICT=true` to encourage using search more aggressively (prompt-level guidance only).

## Kudos
1. to [@Alexandre-tKint](https://github.com/Alexandre-tKint) for [Integrate OpenAI’s ChatGPT within Slack: a step-by-step approach!](https://medium.com/@alexandre.tkint/integrate-openais-chatgpt-within-slack-a-step-by-step-approach-bea43400d311)
2. to [@karfly](https://github.com/karfly) for [chatgpt_telegram_bot](https://github.com/karfly/chatgpt_telegram_bot)
