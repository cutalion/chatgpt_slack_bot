"""Runtime helpers for Slack-aware OpenAI tool calls."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from time import perf_counter
from typing import Any, Dict, Iterable, List

from slack_utils import fetch_channel_history, get_user_profile

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
        "Use this before summarising extended discussions or weekly activity."
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
                "description": "Inclusive lower bound timestamp (Unix epoch seconds or ISO-8601).",
            },
            "latest": {
                "type": ["string", "number"],
                "description": "Inclusive upper bound timestamp (Unix epoch seconds or ISO-8601).",
            },
            "max_messages": {
                "type": "integer",
                "minimum": 1,
                "description": "Maximum number of channel messages to return (defaults to configured cap).",
            },
            "max_thread_messages": {
                "type": "integer",
                "minimum": 0,
                "description": "Maximum replies to fetch per thread root (defaults to configured cap).",
            },
        },
        "required": ["channel_id"],
        "additionalProperties": False,
    },
}


class SlackToolRunner:
    """Execute Slack-specific tool calls issued by the language model."""

    def __init__(self, max_calls: int = 2) -> None:
        self.max_calls = max(1, int(max_calls or 1))
        self._handlers = {
            "get_user_info": self._handle_get_user_info,
            "read_channel_history": self._handle_read_channel_history,
        }

    @property
    def tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            deepcopy(_GET_USER_INFO_DEFINITION),
            deepcopy(_READ_CHANNEL_HISTORY_DEFINITION),
        ]

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
        channel_id = arguments.get("channel_id")
        oldest = arguments.get("oldest")
        latest = arguments.get("latest")
        max_messages = arguments.get("max_messages")
        max_thread_messages = arguments.get("max_thread_messages")

        result = await fetch_channel_history(
            channel_id,
            oldest=oldest,
            latest=latest,
            limit=max_messages,
            include_threads=True,
            max_thread_messages=max_thread_messages,
        )

        return result

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
            allowed_keys = ("channel_id", "oldest", "latest", "max_messages", "max_thread_messages")
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
            return {
                "messages": message_count,
                "truncated": truncated,
                "thread_limit": requested.get("thread_limit"),
            }
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
