"""Slack-specific helper utilities used by the bot."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional

import config
from slack_sdk.web.async_client import AsyncWebClient


logger = logging.getLogger(__name__)

slack_client = AsyncWebClient(token=config.SLACK_BOT_TOKEN)

_USER_NAME_CACHE: Dict[str, str] = {}
_BOT_USER_ID: Optional[str] = None
_USER_INFO_CACHE: Dict[str, Dict[str, Any]] = {}

_USER_ID_MENTION_PATTERN = re.compile(r"(?<!<)@(U|W|T)[A-Z0-9]{8,}\b")


def _normalise_ts(value: Any) -> Optional[str]:
    """Convert floats/ints/ISO 8601 strings into Slack timestamp strings."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return f"{float(value):.6f}"
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return f"{float(stripped):.6f}"
        except ValueError:
            try:
                iso = stripped.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return f"{dt.timestamp():.6f}"
            except ValueError:
                return None
    return None


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


def _trim_text(value: Optional[str], *, limit: int) -> str:
    text = value or ""
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "…"


def _simplify_files(files: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    simplified: List[Dict[str, Any]] = []
    if not isinstance(files, list):
        return simplified
    for file_obj in files:
        if not isinstance(file_obj, dict):
            continue
        simplified.append(
            {
                "id": file_obj.get("id"),
                "name": file_obj.get("name"),
                "mimetype": file_obj.get("mimetype"),
                "filetype": file_obj.get("filetype"),
                "permalink": file_obj.get("permalink"),
            }
        )
    return simplified


def _simplify_reactions(reactions: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    simplified: List[Dict[str, Any]] = []
    if not isinstance(reactions, list):
        return simplified
    for reaction in reactions:
        if not isinstance(reaction, dict):
            continue
        simplified.append(
            {
                "name": reaction.get("name"),
                "count": reaction.get("count"),
                "users": reaction.get("users"),
            }
        )
    return simplified


def _simplify_message(message: Dict[str, Any], *, text_limit: int) -> Dict[str, Any]:
    """Return a pruned message payload safe for passing to the model."""

    text = _trim_text(message.get("text"), limit=text_limit)
    base = {
        "ts": message.get("ts"),
        "user": message.get("user"),
        "bot_id": message.get("bot_id"),
        "username": message.get("username"),
        "text": text,
        "thread_ts": message.get("thread_ts"),
        "parent_user_id": message.get("parent_user_id"),
        "reply_count": message.get("reply_count"),
        "reactions": _simplify_reactions(message.get("reactions")),
        "files": _simplify_files(message.get("files")),
        "subtype": message.get("subtype"),
    }
    return base


def normalise_user_mentions(text: Optional[str]) -> str:
    """Ensure raw @USERID tokens render as Slack mentions."""

    if not isinstance(text, str) or "@" not in text:
        return text or ""

    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        user_id = token[1:]
        if user_id.lower() in {"here", "channel", "everyone"}:
            return token
        return f"<@{user_id}>"

    return _USER_ID_MENTION_PATTERN.sub(_replace, text)


async def fetch_channel_history(
    channel_id: Optional[str],
    *,
    oldest: Optional[Any] = None,
    latest: Optional[Any] = None,
    limit: Optional[int] = None,
    include_threads: bool = True,
    max_thread_messages: Optional[int] = None,
) -> Dict[str, Any]:
    """Fetch recent channel history with optional thread expansion."""

    if not channel_id or not isinstance(channel_id, str):
        return {"channel_id": channel_id or "", "error": "invalid_channel_id"}

    try:
        limit_value = int(limit) if limit is not None else config.SLACK_TOOL_HISTORY_MESSAGE_CAP
    except (TypeError, ValueError):
        limit_value = config.SLACK_TOOL_HISTORY_MESSAGE_CAP
    message_cap = max(1, min(limit_value, config.SLACK_TOOL_HISTORY_MESSAGE_CAP))
    page_size = max(1, min(config.SLACK_TOOL_HISTORY_PAGE_SIZE, message_cap))
    try:
        thread_limit_value = (
            int(max_thread_messages)
            if max_thread_messages is not None
            else config.SLACK_TOOL_HISTORY_THREAD_MESSAGE_CAP
        )
    except (TypeError, ValueError):
        thread_limit_value = config.SLACK_TOOL_HISTORY_THREAD_MESSAGE_CAP
    thread_cap = max(0, min(thread_limit_value, config.SLACK_TOOL_HISTORY_THREAD_MESSAGE_CAP))

    oldest_ts = _normalise_ts(oldest)
    latest_ts = _normalise_ts(latest)

    collected: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    truncated = False

    while len(collected) < message_cap:
        kwargs: Dict[str, Any] = {
            "channel": channel_id,
            "limit": min(page_size, message_cap - len(collected)),
            "inclusive": True,
        }
        if cursor:
            kwargs["cursor"] = cursor
        if oldest_ts:
            kwargs["oldest"] = oldest_ts
        if latest_ts:
            kwargs["latest"] = latest_ts

        try:
            history = await slack_client.conversations_history(**kwargs)
        except Exception as exc:
            logger.debug("Failed to fetch channel history for %s: %s", channel_id, exc)
            return {"channel_id": channel_id, "error": "history_fetch_failed"}

        data = getattr(history, "data", None)
        if isinstance(history, dict) and not data:
            data = history
        if not isinstance(data, dict):
            return {"channel_id": channel_id, "error": "history_fetch_failed"}

        messages: List[Dict[str, Any]] = data.get("messages") or []
        for message in messages:
            if len(collected) >= message_cap:
                truncated = True
                break
            collected.append(message)

        response_meta = data.get("response_metadata") or {}
        cursor = response_meta.get("next_cursor") or None
        has_more = bool(data.get("has_more"))
        if not cursor or not has_more:
            break

    if cursor:
        truncated = True

    simplified_messages: List[Dict[str, Any]] = []

    for message in collected:
        simplified = _simplify_message(message, text_limit=config.SLACK_TOOL_HISTORY_TEXT_CHAR_CAP)
        replies: List[Dict[str, Any]] = []
        replies_truncated = False
        is_thread_root = (
            include_threads
            and thread_cap > 0
            and isinstance(message.get("thread_ts"), str)
            and message.get("thread_ts") == message.get("ts")
            and int(message.get("reply_count") or 0) > 0
        )

        if is_thread_root:
            thread_cursor: Optional[str] = None
            fetched = 0
            parent_ts = message.get("thread_ts")

            while fetched < thread_cap:
                thread_kwargs: Dict[str, Any] = {
                    "channel": channel_id,
                    "ts": parent_ts,
                    "limit": min(page_size, thread_cap - fetched),
                    "inclusive": True,
                }
                if thread_cursor:
                    thread_kwargs["cursor"] = thread_cursor

                try:
                    thread_resp = await slack_client.conversations_replies(**thread_kwargs)
                except Exception as exc:
                    logger.debug("Failed to fetch thread %s in %s: %s", parent_ts, channel_id, exc)
                    replies.append({"error": "thread_fetch_failed", "ts": parent_ts})
                    break

                thread_data = getattr(thread_resp, "data", None)
                if isinstance(thread_resp, dict) and not thread_data:
                    thread_data = thread_resp
                if not isinstance(thread_data, dict):
                    replies.append({"error": "thread_fetch_failed", "ts": parent_ts})
                    break

                thread_messages: List[Dict[str, Any]] = thread_data.get("messages") or []
                for thread_message in thread_messages:
                    if thread_message.get("ts") == message.get("ts"):
                        continue
                    if fetched >= thread_cap:
                        replies_truncated = True
                        break
                    replies.append(_simplify_message(thread_message, text_limit=config.SLACK_TOOL_HISTORY_TEXT_CHAR_CAP))
                    fetched += 1
                if fetched >= thread_cap:
                    replies_truncated = True
                    break

                thread_meta = thread_data.get("response_metadata") or {}
                thread_cursor = thread_meta.get("next_cursor") or None
                has_more_threads = bool(thread_data.get("has_more"))
                if not thread_cursor or not has_more_threads:
                    break
            if fetched >= thread_cap and (thread_cursor or bool(message.get("reply_count", 0))):
                replies_truncated = True

        if replies:
            simplified["replies"] = replies
            simplified["replies_truncated"] = replies_truncated
        elif replies_truncated:
            simplified["replies_truncated"] = True

        if is_thread_root:
            simplified["is_thread_root"] = True

        simplified_messages.append(simplified)

    logger.info(
        "Fetched %d messages (truncated=%s) for channel %s", len(simplified_messages), truncated, channel_id
    )

    return {
        "channel_id": channel_id,
        "requested": {
            "oldest": oldest_ts,
            "latest": latest_ts,
            "limit": message_cap,
            "thread_limit": thread_cap,
        },
        "messages": simplified_messages,
        "truncated": truncated,
    }
