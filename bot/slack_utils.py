"""Slack-specific helper utilities used by the bot."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import config
from slack_sdk.web.async_client import AsyncWebClient


logger = logging.getLogger(__name__)

slack_client = AsyncWebClient(token=config.SLACK_BOT_TOKEN)

_USER_NAME_CACHE: Dict[str, str] = {}
_BOT_USER_ID: Optional[str] = None
_USER_INFO_CACHE: Dict[str, Dict[str, Any]] = {}


def format_ts_utc(ts_str: Optional[str]) -> str:
    """Format Slack timestamps to a stable `[YYYY-MM-DD HH:MMZ]` prefix."""

    try:
        ts = float(ts_str or 0)
        dt = datetime.utcfromtimestamp(ts).replace(tzinfo=timezone.utc)
        return dt.strftime("[%Y-%m-%d %H:%MZ]")
    except Exception:
        return "[0000-00-00 00:00Z]"


def _extract_display_name_from_user(user_obj: Dict[str, Any]) -> Optional[str]:
    """Return the most human-friendly display name available for a Slack user."""

    if not isinstance(user_obj, dict):
        return None
    profile = user_obj.get("profile") or {}
    for key in (
        "display_name_normalized",
        "display_name",
        "real_name_normalized",
        "real_name",
        "name",
    ):
        val = (profile.get(key) if key in profile else user_obj.get(key))
        if isinstance(val, str) and val.strip():
            return val.strip()
    uid = user_obj.get("id")
    if isinstance(uid, str) and uid:
        return uid
    return None


async def get_user_display_name(user_id: Optional[str]) -> str:
    """Resolve a Slack user ID to a cached display name, with graceful fallbacks."""

    if not user_id or not isinstance(user_id, str):
        return "Unknown"
    cached = _USER_NAME_CACHE.get(user_id)
    if isinstance(cached, str):
        return cached
    try:
        info = await slack_client.users_info(user=user_id)
        data = getattr(info, "data", None)
        if isinstance(info, dict) and not data:
            data = info
        user_obj = None
        if isinstance(data, dict):
            user_obj = data.get("user")
        name = _extract_display_name_from_user(user_obj or {}) or f"<@{user_id}>"
        _USER_NAME_CACHE[user_id] = name
        return name
    except Exception:
        return f"<@{user_id}>"


async def get_user_profile(user_id: Optional[str]) -> Dict[str, Any]:
    """Fetch a Slack user profile and return a sanitised subset of fields."""

    if not user_id or not isinstance(user_id, str):
        return {"user_id": user_id or "", "error": "invalid_user_id"}
    cached = _USER_INFO_CACHE.get(user_id)
    if isinstance(cached, dict):
        return cached
    try:
        info = await slack_client.users_info(user=user_id)
        data = getattr(info, "data", None)
        if isinstance(info, dict) and not data:
            data = info
        user_obj = {}
        if isinstance(data, dict):
            user_obj = data.get("user") or {}
    except Exception as exc:
        logger.debug("Failed to fetch user profile for %s: %s", user_id, exc)
        return {"user_id": user_id, "error": "lookup_failed"}

    profile = user_obj.get("profile") or {}
    result = {
        "user_id": user_obj.get("id") or user_id,
        "display_name": _extract_display_name_from_user(user_obj) or f"<@{user_id}>",
        "real_name": profile.get("real_name_normalized") or user_obj.get("real_name"),
        "title": profile.get("title"),
        "tz": user_obj.get("tz"),
        "tz_label": user_obj.get("tz_label"),
        "status_text": profile.get("status_text"),
        "status_emoji": profile.get("status_emoji"),
        "is_bot": bool(user_obj.get("is_bot")),
    }
    # Prime the existing display-name cache with the resolved name
    name = result.get("display_name")
    if isinstance(name, str):
        _USER_NAME_CACHE[user_id] = name
    _USER_INFO_CACHE[user_id] = result
    return result


def get_bot_name_from_message(message: Dict[str, Any]) -> str:
    """Best-effort bot display name resolution for historical thread messages."""

    bot_profile = message.get("bot_profile") or {}
    for key in ("name", "username", "app_id", "id"):
        val = bot_profile.get(key) or message.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return "Bot"


async def get_bot_user_id() -> Optional[str]:
    """Fetch and cache the bot's user ID via `auth_test`."""

    global _BOT_USER_ID
    if _BOT_USER_ID:
        return _BOT_USER_ID
    try:
        auth = await slack_client.auth_test()
        data = getattr(auth, "data", None)
        if isinstance(auth, dict) and not data:
            data = auth
        if isinstance(data, dict):
            uid = data.get("user_id")
            if isinstance(uid, str) and uid.strip():
                _BOT_USER_ID = uid
                return _BOT_USER_ID
    except Exception as exc:
        logger.debug("Failed to resolve bot user id: %s", exc)
    return None

