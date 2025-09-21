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
SLACK_TOOLS_ENABLED = os.getenv("SLACK_TOOLS_ENABLED", "false").lower() in ("1", "true", "yes")

# Tuning
def _to_int(val: str, default: int) -> int:
    """Convert an environment value to `int`, returning `default` on failure."""
    try:
        return int(val)
    except Exception:
        return default

MAX_OUTPUT_TOKENS = _to_int(os.getenv("MAX_OUTPUT_TOKENS", "3072"), 3072)
HISTORY_LIMIT = _to_int(os.getenv("HISTORY_LIMIT", "20"), 20)
SLACK_TOOL_MAX_CALLS = _to_int(os.getenv("SLACK_TOOL_MAX_CALLS", "2"), 2)
# Tool-specific limits
SLACK_TOOL_HISTORY_MESSAGE_CAP = _to_int(os.getenv("SLACK_TOOL_HISTORY_MESSAGE_CAP", "200"), 200)
SLACK_TOOL_HISTORY_PAGE_SIZE = _to_int(os.getenv("SLACK_TOOL_HISTORY_PAGE_SIZE", "100"), 100)
SLACK_TOOL_HISTORY_THREAD_MESSAGE_CAP = _to_int(os.getenv("SLACK_TOOL_HISTORY_THREAD_MESSAGE_CAP", "40"), 40)
SLACK_TOOL_HISTORY_TEXT_CHAR_CAP = _to_int(os.getenv("SLACK_TOOL_HISTORY_TEXT_CHAR_CAP", "4000"), 4000)
# Default to low to reduce internal reasoning token usage
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "low")  # one of: low, medium, high

"""No ad-hoc debug flags here; keep runtime surface minimal."""
