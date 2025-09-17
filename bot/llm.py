"""Helpers for interacting with the OpenAI Responses API."""

from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional

import config
from openai import AsyncOpenAI


logger = logging.getLogger(__name__)

aclient = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
model = config.GPT_MODEL


def _to_responses_input(messages: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert Chat Completions-style messages into Responses API payload blocks."""
    converted: List[Dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if not isinstance(content, str):
            content = str(content)

        content_type = "output_text" if role == "assistant" else "input_text"
        converted.append(
            {
                "role": role,
                "content": [
                    {
                        "type": content_type,
                        "text": content,
                    }
                ],
            }
        )
    return converted


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Attribute-or-dict getter."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _extract_output_text(resp: Any) -> Optional[str]:
    """Robustly extract text from a Responses API result."""
    try:
        text = getattr(resp, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text
    except Exception:
        pass

    pieces: List[str] = []
    try:
        outputs: Iterable[Any] = _get(resp, "output", []) or []
        for output in outputs:
            contents: Iterable[Any] = _get(output, "content", []) or []
            for chunk in contents:
                ctype = _get(chunk, "type")
                if ctype not in ("output_text", "summary_text", "message_text", "text", None):
                    continue
                text_block = _get(chunk, "text")
                if text_block is None:
                    continue
                if isinstance(text_block, str):
                    pieces.append(text_block)
                else:
                    val = _get(text_block, "value")
                    if isinstance(val, str) and val.strip():
                        pieces.append(val)
                    else:
                        fallback = _get(text_block, "text")
                        if isinstance(fallback, str) and fallback.strip():
                            pieces.append(fallback)
    except Exception as exc:
        logger.debug("Failed to parse response.output content: %s", exc)

    joined = "\n\n".join(pieces).strip() if pieces else ""
    return joined or None


async def generate_ai_reply(messages: Iterable[Dict[str, Any]]) -> str:
    """Generate a reply using the OpenAI Responses API exclusively."""
    max_output_tokens = config.MAX_OUTPUT_TOKENS
    instructions = None
    filtered_messages = []
    for message in messages:
        if message.get("role") == "system":
            instructions = message.get("content")
            continue
        filtered_messages.append(message)

    message_count = len(filtered_messages)
    logger.info(
        "Calling OpenAI model=%s messages=%d max_output_tokens=%s",
        model,
        message_count,
        max_output_tokens,
    )

    args: Dict[str, Any] = {
        "model": model,
        "input": _to_responses_input(filtered_messages),
        "max_output_tokens": max_output_tokens,
    }
    if instructions:
        args["instructions"] = instructions
    if getattr(config, "REASONING_EFFORT", None):
        args["reasoning"] = {"effort": config.REASONING_EFFORT}
    if getattr(config, "WEB_SEARCH_ENABLED", False):
        args["tools"] = [{"type": "web_search"}]

    call_started = perf_counter()
    try:
        resp = await aclient.responses.create(**args)
        elapsed = perf_counter() - call_started
        try:
            status = _get(resp, "status")
            if status and status != "completed":
                reason = _get(_get(resp, "incomplete_details", {}), "reason")
                logger.warning("Responses status=%s reason=%s", status, reason)
        except Exception:
            pass

        status = _get(resp, "status") or "completed"
        logger.info(
            "OpenAI call finished status=%s elapsed=%.2fs messages=%d",
            status,
            elapsed,
            message_count,
        )
        logger.debug(
            "Responses API call succeeded in %.2fs (status=%s, model=%s, messages=%d)",
            elapsed,
            status,
            model,
            len(filtered_messages),
        )

        outputs = _get(resp, "output", []) or []

        text = _extract_output_text(resp)
        if text and text.strip():
            logger.debug("Extracted output_text (len=%d)", len(text.strip()))
            return text.strip()

        has_tool_use = False
        try:
            for output in outputs:
                if _get(output, "type") in ("tool_use", "web_search_call", "web.search.call"):
                    has_tool_use = True
                    break
                for chunk in _get(output, "content", []) or []:
                    if _get(chunk, "type") in ("tool_use", "web_search_call", "web.search.call"):
                        has_tool_use = True
                        break
        except Exception:
            pass

        if has_tool_use and getattr(config, "WEB_SEARCH_ENABLED", False):
            retry_args = {k: v for k, v in args.items() if k not in ("tools",)}
            retry_args["tool_choice"] = "none"
            if instructions:
                retry_args["instructions"] = instructions + "\n\nTools are unavailable; answer directly without using tools."
            resp2 = await aclient.responses.create(**retry_args)
            text2 = _extract_output_text(resp2)
            if text2 and text2.strip():
                return text2.strip()

        logger.warning("No output_text extracted from response; sending fallback")
        return "Sorry, I couldn't generate a response just now. Please try again."
    except Exception as exc:
        elapsed = perf_counter() - call_started
        logger.debug("Responses API call failed after %.2fs", elapsed)
        logger.info(
            "OpenAI call failed elapsed=%.2fs model=%s messages=%d",
            elapsed,
            model,
            message_count,
        )
        logger.exception("Responses API failed: %s", exc)
        return "Sorry, I’m having trouble reaching the model right now. Please try again in a moment."


__all__ = ["generate_ai_reply"]
