# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

This is a Python-based Slack bot that integrates OpenAI's ChatGPT with Slack using Socket Mode. The bot responds to mentions and direct messages.

**Core Components:**
- `bot/bot.py` - Main bot logic with async event handlers for app mentions and DMs
- `bot/config.py` - Configuration loading from environment variables
- `slack.manifest.json` - Slack app configuration with required permissions
- `requirements.txt` - Python dependencies (OpenAI, Slack Bolt, etc.)

**Key Features:**
- Responds to `@bot` mentions in channels and threads
- Handles direct messages
- Maintains conversation context in threads (loads up to 20 previous messages)
- Uses OpenAI Responses API with configurable model via `GPT_MODEL` env var (no Chat Completions fallback)
- Optional: Uses `web_search` tool when `WEB_SEARCH_ENABLED=true`

## Development Commands

**Build and run:**
```bash
docker compose up --build
```

**Run locally for development:**
```bash
# Install dependencies
pip install -r requirements.txt

# Run bot directly
python bot/bot.py
```

## Configuration

Environment variables are required in `.env` file:
- `SLACK_BOT_TOKEN` - Bot User OAuth Token (starts with `xoxb-`)
- `SLACK_APP_TOKEN` - App-Level Token for Socket Mode (starts with `xapp-`)
- `OPENAI_API_KEY` - OpenAI API key
- `GPT_MODEL` - OpenAI model to use (default: gpt-3.5-turbo)
- `WEB_SEARCH_ENABLED` - enable web search tool (true/false; default: false)
- `WEB_SEARCH_STRICT` - stronger prompt guidance to use search (true/false)

Use `.env.example` as template: `cp .env.example .env`

## Slack App Setup Requirements

The bot requires these OAuth scopes:
- `app_mentions:read`
- `channels:history`
- `channels:read`
- `chat:write`
- `groups:history`
- `im:history`
- `im:read`
- `groups:read`

Must subscribe to these bot events:
- `app_mention`
- `message.im`

Socket Mode must be enabled for real-time messaging.
