import os
import dotenv

dotenv.load_dotenv()

SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
GPT_MODEL = os.getenv("GPT_MODEL")
BOT_NAME = os.getenv("BOT_NAME")

# Feature flags / options
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "false").lower() in ("1", "true", "yes")
WEB_SEARCH_STRICT = os.getenv("WEB_SEARCH_STRICT", "false").lower() in ("1", "true", "yes")
