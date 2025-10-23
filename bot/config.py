import os
import sys
import dotenv

dotenv.load_dotenv()

SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-5-mini")
BOT_NAME = os.getenv("BOT_NAME")

def _validate_config() -> None:
    """Validate required configuration at startup and fail fast with clear errors."""
    errors = []

    if not SLACK_BOT_TOKEN or not SLACK_BOT_TOKEN.startswith("xoxb-"):
        errors.append("SLACK_BOT_TOKEN is missing or invalid (should start with 'xoxb-')")

    if not SLACK_APP_TOKEN or not SLACK_APP_TOKEN.startswith("xapp-"):
        errors.append("SLACK_APP_TOKEN is missing or invalid (should start with 'xapp-')")

    if not OPENAI_API_KEY or not OPENAI_API_KEY.strip():
        errors.append("OPENAI_API_KEY is missing or empty")

    if not GPT_MODEL or not GPT_MODEL.strip():
        errors.append("GPT_MODEL is missing or empty")

    if errors:
        print("Configuration validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

_validate_config()

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
SLACK_TOOL_MAX_CALLS = _to_int(os.getenv("SLACK_TOOL_MAX_CALLS", "5"), 5)
# OpenAI call timeout and retry configuration
OPENAI_TIMEOUT_SECONDS = _to_int(os.getenv("OPENAI_TIMEOUT_SECONDS", "120"), 120)
OPENAI_MAX_RETRIES = _to_int(os.getenv("OPENAI_MAX_RETRIES", "3"), 3)
# Tool-specific limits
SLACK_TOOL_HISTORY_MESSAGE_CAP = _to_int(os.getenv("SLACK_TOOL_HISTORY_MESSAGE_CAP", "200"), 200)
SLACK_TOOL_HISTORY_PAGE_SIZE = _to_int(os.getenv("SLACK_TOOL_HISTORY_PAGE_SIZE", "100"), 100)
SLACK_TOOL_HISTORY_THREAD_MESSAGE_CAP = _to_int(os.getenv("SLACK_TOOL_HISTORY_THREAD_MESSAGE_CAP", "40"), 40)
SLACK_TOOL_HISTORY_TEXT_CHAR_CAP = _to_int(os.getenv("SLACK_TOOL_HISTORY_TEXT_CHAR_CAP", "4000"), 4000)
# Default to low to reduce internal reasoning token usage
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "low")  # one of: low, medium, high

"""No ad-hoc debug flags here; keep runtime surface minimal."""

# Pricing per 1M tokens for supported GPT-5 models (input | cached input | output).
# Cached input is the discounted rate applied when tokens are served from cache.
OPENAI_PRICING_PER_M_TOKEN = {
    "gpt-5": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.00},
    "gpt-5-nano": {"input": 0.05, "cached_input": 0.005, "output": 0.40},
    "gpt-5-chat-latest": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5-codex": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5-pro": {"input": 15.00, "output": 120.00},
}
