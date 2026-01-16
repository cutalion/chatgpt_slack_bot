"""Runtime helpers for Slack-aware OpenAI tool calls."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional

from slack_utils import (
    fetch_channel_history,
    get_user_profile,
    is_private_channel,
    is_user_member_of_channel,
    invalidate_user_channel_cache,
)

logger = logging.getLogger(__name__)


_GET_USER_INFO_DEFINITION = {
    "type": "function",
    "name": "get_user_info",
    "description": (
        "Fetch key profile attributes for the given Slack user ID. "
        "Use this to learn names, titles, time zones, or status text before replying."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "Slack user ID (e.g. U12345678).",
            }
        },
        "required": ["user_id"],
        "additionalProperties": False,
    },
}


_READ_CHANNEL_HISTORY_DEFINITION = {
    "type": "function",
    "name": "read_channel_history",
    "description": (
        "Fetch recent messages from a channel within a specified range and optionally include replies from threads. "
        "Use this before summarising extended discussions or weekly activity. "
        "If no time window is provided, the latest messages are returned automatically. "
        "When the response includes `next_cursor` and `truncated: true`, call the tool again with that cursor to continue paging."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "Slack channel ID (e.g. C12345678).",
            },
            "oldest": {
                "type": ["string", "number"],
                "description": "Inclusive lower bound timestamp (Unix epoch seconds or ISO-8601). Omit to fetch the newest messages.",
            },
            "latest": {
                "type": ["string", "number"],
                "description": "Inclusive upper bound timestamp (Unix epoch seconds or ISO-8601). Leave blank unless you need to cap the range.",
            },
            "max_messages": {
                "type": "integer",
                "minimum": 1,
                "description": "Maximum number of channel messages to return in this call (defaults to configured cap).",
            },
            "max_thread_messages": {
                "type": "integer",
                "minimum": 0,
                "description": "Maximum replies to fetch per thread root (defaults to configured cap).",
            },
            "cursor": {
                "type": "string",
                "description": "Pagination cursor from a previous read_channel_history call (`result.next_cursor`). Leave blank to start from the newest page.",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}


_REFRESH_CHANNEL_ACCESS_DEFINITION = {
    "type": "function",
    "name": "refresh_channel_access",
    "description": (
        "Re-check if the current user has access to a private channel. "
        "Use this when the user claims they were just added to a channel "
        "and a previous access check failed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel_id": {
                "type": "string",
                "description": "Slack channel ID to re-check access for (e.g. C12345678).",
            }
        },
        "required": ["channel_id"],
        "additionalProperties": False,
    },
}


class SlackToolRunner:
    """Execute Slack-specific tool calls issued by the language model."""

    def __init__(
        self,
        max_calls: int = 2,
        *,
        default_channel_id: Optional[str] = None,
        channel_descriptor: Optional[str] = None,
        requesting_user_id: Optional[str] = None,
    ) -> None:
        self.max_calls = max(1, int(max_calls or 1))
        self.default_channel_id = default_channel_id
        self.channel_descriptor = channel_descriptor
        self.requesting_user_id = requesting_user_id
        self._handlers = {
            "get_user_info": self._handle_get_user_info,
            "read_channel_history": self._handle_read_channel_history,
            "refresh_channel_access": self._handle_refresh_channel_access,
        }

    @property
    def tool_definitions(self) -> List[Dict[str, Any]]:
        definitions = [
            deepcopy(_GET_USER_INFO_DEFINITION),
            deepcopy(_READ_CHANNEL_HISTORY_DEFINITION),
            deepcopy(_REFRESH_CHANNEL_ACCESS_DEFINITION),
        ]
        if self.channel_descriptor:
            for definition in definitions:
                if definition.get("name") != "read_channel_history":
                    continue
                params = definition.get("parameters", {})
                props = params.get("properties", {})
                channel_prop = props.get("channel_id")
                if isinstance(channel_prop, dict):
                    description = channel_prop.get("description") or ""
                    note = f" Current channel: {self.channel_descriptor}."
                    if note not in description:
                        channel_prop["description"] = description + note
        return definitions

    def can_handle(self, tool_name: str | None) -> bool:
        return bool(tool_name) and tool_name in self._handlers

    async def execute(self, tool_calls: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
        outputs: List[Dict[str, str]] = []
        for call in tool_calls:
            call_id = call.get("call_id") or call.get("id") or call.get("tool_call_id") or ""
            call_id = str(call_id) if call_id is not None else ""
            name = call.get("name")
            handler = self._handlers.get(name)
            raw_args = call.get("arguments") or call.get("input")
            parsed_args = self._parse_arguments(raw_args)
            if name == "read_channel_history" and isinstance(parsed_args, dict):
                if not parsed_args.get("channel_id") and self.default_channel_id:
                    parsed_args["channel_id"] = self.default_channel_id
            logger.info("Executing Slack tool name=%s call_id=%s", name, call_id or "<missing>")
            started = perf_counter()
            if not handler:
                payload = {"error": f"Unsupported tool: {name}"}
            else:
                try:
                    payload = await handler(parsed_args)
                except Exception as exc:  # pragma: no cover - defence against unexpected failures
                    logger.exception("Slack tool %s failed: %s", name, exc)
                    payload = {"error": "internal_error"}
            elapsed_ms = (perf_counter() - started) * 1000.0
            summary = self._build_log_summary(name, call_id, parsed_args, payload, elapsed_ms)
            logger.info("Slack tool call %s", summary)
            outputs.append({
                "tool_call_id": call_id,
                "output": self._serialise_payload(payload),
            })
        return outputs

    async def _handle_get_user_info(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        user_id = arguments.get("user_id")
        if not isinstance(user_id, str) or not user_id.strip():
            return {"error": "user_id is required"}
        profile = await get_user_profile(user_id.strip())
        # Drop keys with `None` to keep responses tidy.
        return {k: v for k, v in profile.items() if v is not None}

    async def _handle_read_channel_history(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        channel_id = arguments.get("channel_id") or self.default_channel_id
        if isinstance(channel_id, str):
            channel_id = channel_id.strip()
        if not channel_id:
            return {"error": "channel_id is required"}
        
        # Access control for private channels
        access_error = await self._validate_channel_access(channel_id)
        if access_error:
            return access_error
        
        oldest = arguments.get("oldest")
        latest = arguments.get("latest")
        max_messages = arguments.get("max_messages")
        max_thread_messages = arguments.get("max_thread_messages")
        cursor = arguments.get("cursor")

        result = await fetch_channel_history(
            channel_id,
            oldest=oldest,
            latest=latest,
            limit=max_messages,
            include_threads=True,
            max_thread_messages=max_thread_messages,
            cursor=cursor,
        )

        needs_fallback = (
            isinstance(result, dict)
            and not result.get("error")
            and not result.get("messages")
            and (oldest is not None or latest is not None)
        )

        if needs_fallback:
            fallback_result = await fetch_channel_history(
                channel_id,
                oldest=None,
                latest=None,
                limit=max_messages,
                include_threads=True,
                max_thread_messages=max_thread_messages,
            )
            if isinstance(fallback_result, dict) and not fallback_result.get("error"):
                requested_info = {}
                if isinstance(result.get("requested"), dict):
                    requested_info = {
                        "oldest": result["requested"].get("oldest"),
                        "latest": result["requested"].get("latest"),
                        "cursor": result["requested"].get("cursor"),
                    }
                else:
                    requested_info = {"oldest": oldest, "latest": latest, "cursor": cursor}
                requested_info = {key: value for key, value in requested_info.items() if value is not None}

                fallback_requested = fallback_result.get("requested")
                if not isinstance(fallback_requested, dict):
                    fallback_requested = {}
                fallback_requested["fallback_from"] = requested_info
                fallback_result["requested"] = fallback_requested
                fallback_result["fallback_applied"] = True
                fallback_result["fallback_reason"] = "no_messages_in_range"
                fallback_result.setdefault(
                    "note",
                    "No messages were found for the requested time window; returning the most recent messages instead.",
                )
                return fallback_result

        return result

    async def _validate_channel_access(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Validate that the requesting user has access to the channel.
        
        Returns None if access is allowed, or an error dict if access is denied.
        """
        if not self.requesting_user_id:
            # If we don't know who's asking, we can't validate - fail open for backwards compat
            logger.debug("No requesting_user_id set, skipping access validation for %s", channel_id)
            return None
        
        try:
            is_private = await is_private_channel(channel_id)
            if not is_private:
                # Public channels don't require membership validation
                return None
            
            has_access = await is_user_member_of_channel(
                channel_id, self.requesting_user_id
            )
            if has_access:
                return None
            
            logger.info(
                "Access denied: user %s is not a member of private channel %s",
                self.requesting_user_id,
                channel_id,
            )
            return {
                "error": "access_denied",
                "message": (
                    "You don't have access to this private channel. "
                    "If you were just added, say so and I'll refresh my cache."
                ),
                "channel_id": channel_id,
            }
        except Exception as exc:
            logger.warning("Error validating channel access for %s: %s", channel_id, exc)
            # Fail-safe: deny access on error to avoid accidental exposure
            return {
                "error": "access_check_failed",
                "message": "Could not verify your access to this channel.",
                "channel_id": channel_id,
            }

    async def _handle_refresh_channel_access(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Re-check access to a private channel after cache invalidation."""
        channel_id = arguments.get("channel_id")
        if not isinstance(channel_id, str) or not channel_id.strip():
            return {"error": "channel_id is required"}
        channel_id = channel_id.strip()
        
        if not self.requesting_user_id:
            return {
                "error": "no_user_context",
                "message": "Cannot refresh access without user context.",
            }
        
        # Invalidate the cache for this user
        invalidate_user_channel_cache(self.requesting_user_id)
        
        # Re-check access with fresh data
        has_access = await is_user_member_of_channel(
            channel_id, self.requesting_user_id, bypass_cache=True
        )
        
        logger.info(
            "Refreshed channel access for user %s to channel %s: access=%s",
            self.requesting_user_id,
            channel_id,
            has_access,
        )
        
        return {
            "channel_id": channel_id,
            "access": has_access,
            "refreshed": True,
            "message": (
                "Access granted! You can now read this channel."
                if has_access
                else "Still no access. Please verify you've been added to the channel."
            ),
        }

    @staticmethod
    def _build_log_summary(
        tool_name: str | None,
        call_id: str,
        arguments: Dict[str, Any],
        payload: Any,
        elapsed_ms: float,
    ) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "tool": tool_name or "",
            "call_id": call_id,
            "status": "ok",
            "elapsed_ms": round(elapsed_ms, 2),
            "args": SlackToolRunner._summarise_arguments(tool_name, arguments),
        }
        if isinstance(payload, dict) and payload.get("error"):
            summary["status"] = "error"
            summary["error"] = payload.get("error")
        result_summary = SlackToolRunner._summarise_result(tool_name, payload)
        if result_summary:
            summary["result"] = result_summary
        return summary

    @staticmethod
    def _summarise_arguments(tool_name: str | None, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(arguments, dict):
            return {}
        if tool_name == "get_user_info":
            user_id = arguments.get("user_id")
            return {"user_id": user_id} if isinstance(user_id, str) else {}
        if tool_name == "read_channel_history":
            allowed_keys = (
                "channel_id",
                "oldest",
                "latest",
                "max_messages",
                "max_thread_messages",
                "cursor",
            )
            return {key: arguments.get(key) for key in allowed_keys if key in arguments}
        return {
            key: value
            for key, value in arguments.items()
            if isinstance(key, str) and key[:1] != "_"
        }

    @staticmethod
    def _summarise_result(tool_name: str | None, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        if tool_name == "read_channel_history":
            messages = payload.get("messages")
            message_count = len(messages) if isinstance(messages, list) else 0
            truncated = bool(payload.get("truncated"))
            requested = payload.get("requested") if isinstance(payload.get("requested"), dict) else {}
            summary = {
                "messages": message_count,
                "truncated": truncated,
                "thread_limit": requested.get("thread_limit"),
                "has_next_cursor": bool(payload.get("next_cursor")),
            }
            if payload.get("fallback_applied"):
                summary["fallback"] = payload.get("fallback_reason") or "applied"
            return summary
        if tool_name == "get_user_info":
            keys = ["user_id", "display_name", "error"]
            return {key: payload.get(key) for key in keys if payload.get(key) is not None}
        if "error" in payload:
            return {"error": payload.get("error")}
        return {}

    @staticmethod
    def _parse_arguments(raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.debug("Failed to parse tool arguments: %s", raw)
        return {}

    @staticmethod
    def _serialise_payload(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        try:
            return json.dumps(payload, ensure_ascii=False)
        except TypeError:
            return json.dumps({"error": "non_serialisable_payload"})


__all__ = ["SlackToolRunner"]
