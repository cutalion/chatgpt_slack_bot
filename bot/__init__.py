"""Package-level exports for the bot package.

This module re-exports commonly used functions and variables from
`bot.bot` and `bot.slack_utils` so consumers (and tests) can import them
directly from `bot` (e.g. `import bot; bot.get_bot_user_id`).
"""

from __future__ import annotations

"""
This package module re-exports useful symbols and also provides lightweight
wrappers so tests (and callers) can monkeypatch attributes on the `bot`
package (e.g. `bot.client`, `bot.get_bot_user_id`) and have those patches
observed by the implementation in `bot.bot` at call time.

The implementation synchronises selected attributes from this package
namespace into the underlying `bot.bot` module immediately before calling
the real functions.
"""

from importlib import import_module
from typing import Any, Callable

# Import the implementation module
_impl = import_module("bot.bot")

# Re-export a few stable objects from the implementation module
app = _impl.app
logger = _impl.logger
run = _impl.run

# Default client and helper bindings come from the implementation module and
# can be overridden by tests by assigning to attributes on this package.
client = getattr(_impl, "client", None)
format_ts_utc = getattr(_impl, "format_ts_utc", None)
get_bot_name_from_message = getattr(_impl, "get_bot_name_from_message", None)
get_bot_user_id = getattr(_impl, "get_bot_user_id", None)
get_user_display_name = getattr(_impl, "get_user_display_name", None)
normalise_user_mentions = getattr(_impl, "normalise_user_mentions", None)
clean_user_message = getattr(_impl, "clean_user_message", None)
get_channel_descriptor = getattr(_impl, "get_channel_descriptor", None)

__all__ = [
    "app",
    "client",
    "logger",
    "run",
    "format_ts_utc",
    "get_bot_name_from_message",
    "get_bot_user_id",
    "get_user_display_name",
    "normalise_user_mentions",
    "clean_user_message",
    "get_channel_descriptor",
]


def _sync_impl_namespace() -> None:
    """Copy selected attributes from this package into the implementation
    module so that runtime lookups inside `bot.bot` pick up patches made on
    the `bot` package (used extensively by the test-suite).
    """
    names = [
        "client",
        "format_ts_utc",
        "get_bot_name_from_message",
        "get_bot_user_id",
        "get_user_display_name",
        "normalise_user_mentions",
        "clean_user_message",
        "get_channel_descriptor",
    ]
    for n in names:
        if n in globals():
            setattr(_impl, n, globals()[n])


async def handle_mention(*args: Any, **kwargs: Any) -> Any:
    """Wrapper around the real handler that ensures the implementation
    module observes any package-level monkeypatches before invocation.
    """
    _sync_impl_namespace()
    return await _impl.handle_mention(*args, **kwargs)


async def request_clarification(*args: Any, **kwargs: Any) -> Any:
    _sync_impl_namespace()
    return await _impl.request_clarification(*args, **kwargs)



