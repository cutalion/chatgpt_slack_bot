"""Helpers for interacting with the OpenAI Responses API."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

import config
from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError
from slack_tools import SlackToolRunner


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


def _extract_tool_calls(resp: Any) -> List[Dict[str, Any]]:
    """Return every tool call payload present on a Responses API object."""

    def _normalise_call(payload: Any) -> Optional[Dict[str, Any]]:
        if not payload:
            return None
        function_block = _get(payload, "function")
        name = _get(payload, "name") or _get(function_block, "name")
        if not name:
            return None
        arguments = (
            _get(payload, "arguments")
            or _get(payload, "input")
            or _get(function_block, "arguments")
        )
        identifier = (
            _get(payload, "id")
            or _get(payload, "tool_call_id")
            or _get(payload, "call_id")
        )
        call_id = _get(payload, "call_id") or identifier
        return {
            "id": identifier,
            "call_id": call_id,
            "name": name,
            "arguments": arguments,
        }

    calls: List[Dict[str, Any]] = []
    required_action = _get(resp, "required_action")
    submit_section = _get(required_action, "submit_tool_outputs")
    for call in _get(submit_section, "tool_calls", []) or []:
        normalised = _normalise_call(call)
        if normalised:
            calls.append(normalised)

    tool_like_types = {"tool_use", "function_call", "function", "tool_call"}
    for output in _get(resp, "output", []) or []:
        if (_get(output, "type") or "").lower() in tool_like_types:
            normalised = _normalise_call(output)
            if normalised:
                calls.append(normalised)
        for chunk in _get(output, "content", []) or []:
            if (_get(chunk, "type") or "").lower() in tool_like_types:
                normalised = _normalise_call(chunk)
                if normalised:
                    calls.append(normalised)
    return calls


async def _run_slack_tools(
    resp: Any,
    runner: SlackToolRunner,
    *,
    instructions: Optional[str],
    max_output_tokens: int,
    tool_definitions: List[Dict[str, Any]],
) -> Tuple[Any, bool, List[str]]:
    """Execute supported Slack tools until completion or exhaustion."""

    if runner is None:
        return resp, False, []

    handled_any = False
    pending_unhandled: List[str] = []
    remaining = runner.max_calls
    current = resp

    while remaining > 0:
        calls = _extract_tool_calls(current)
        if not calls:
            break
        supported = [call for call in calls if runner.can_handle(call.get("name"))]
        unsupported = [call for call in calls if not runner.can_handle(call.get("name"))]
        if unsupported:
            pending_unhandled = [call.get("name") or "" for call in unsupported]
            logger.debug("Encountered unsupported tool calls: %s", pending_unhandled)
            break
        outputs = await runner.execute(supported)
        if not outputs:
            logger.debug("Slack tool runner produced no outputs; stopping")
            break
        response_id = _get(current, "id")
        if not response_id:
            logger.warning("Missing response_id when submitting tool outputs")
            break
        formatted_outputs = []
        for output in outputs:
            call_id = (
                output.get("tool_call_id")
                or output.get("call_id")
                or output.get("id")
            )
            result = output.get("output")
            if not call_id:
                logger.debug("Skipping tool output without call_id: %s", output)
                continue
            if not isinstance(result, str):
                result = str(result)
            formatted_outputs.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": result,
            })
        if not formatted_outputs:
            logger.debug("No valid formatted tool outputs to submit; stopping")
            break
        request_kwargs: Dict[str, Any] = {
            "model": model,
            "input": formatted_outputs,
            "previous_response_id": response_id,
            "max_output_tokens": max_output_tokens,
        }
        if instructions:
            request_kwargs["instructions"] = instructions
        if tool_definitions:
            request_kwargs["tools"] = tool_definitions
        current = await aclient.responses.create(**request_kwargs)
        handled_any = True
        remaining -= 1
    return current, handled_any, pending_unhandled




async def generate_ai_reply(
    messages: Iterable[Dict[str, Any]],
    *,
    slack_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a reply using the OpenAI Responses API exclusively."""
    context = slack_context or {}
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

    runner: Optional[SlackToolRunner] = None
    tool_definitions: List[Dict[str, Any]] = []
    if getattr(config, "WEB_SEARCH_ENABLED", False):
        tool_definitions.append({"type": "web_search"})
    if getattr(config, "SLACK_TOOLS_ENABLED", False):
        runner = SlackToolRunner(
            max_calls=config.SLACK_TOOL_MAX_CALLS,
            default_channel_id=context.get("channel_id"),
            channel_descriptor=context.get("channel_descriptor"),
        )
        tool_definitions.extend(runner.tool_definitions)
    if tool_definitions:
        args["tools"] = tool_definitions

    call_started = perf_counter()
    logger.debug('OpenAI request payload: %s', {k: v for k, v in args.items() if k != 'input'})

    # Retry loop with exponential backoff for transient failures
    max_retries = config.OPENAI_MAX_RETRIES
    timeout_seconds = config.OPENAI_TIMEOUT_SECONDS

    for attempt in range(max_retries):
        try:
            resp = await asyncio.wait_for(
                aclient.responses.create(**args),
                timeout=timeout_seconds
            )

            logger.debug('OpenAI response object: %s', type(resp))
            tools_handled = False
            pending_unhandled: List[str] = []
            if runner:
                resp, tools_handled, pending_unhandled = await _run_slack_tools(
                    resp,
                    runner,
                    instructions=instructions,
                    max_output_tokens=max_output_tokens,
                    tool_definitions=tool_definitions,
                )

            elapsed = perf_counter() - call_started
            logger.debug('OpenAI raw response: %s', getattr(resp, 'model_dump', lambda: resp)())
            status = _get(resp, "status") or "completed"
            if status and status != "completed":
                reason = _get(_get(resp, "incomplete_details", {}), "reason")
                logger.warning("Responses status=%s reason=%s", status, reason)
            logger.info(
                "OpenAI call finished status=%s elapsed=%.2fs messages=%d tools_handled=%s",
                status,
                elapsed,
                message_count,
                tools_handled,
            )
            logger.debug(
                "Responses API call succeeded in %.2fs (status=%s, model=%s, messages=%d)",
                elapsed,
                status,
                model,
                len(filtered_messages),
            )

            text = _extract_output_text(resp)
            if text and text.strip():
                logger.debug("Extracted output_text (len=%d)", len(text.strip()))
                return text.strip()

            if status != "completed":
                if pending_unhandled:
                    logger.warning("OpenAI response still requires unsupported tools: %s", pending_unhandled)
                retry_args = {k: v for k, v in args.items() if k not in ("tools", "tool_choice")}
                retry_args["tool_choice"] = "none"
                if instructions:
                    retry_args["instructions"] = instructions + "\n\nTools are unavailable; answer directly without calling tools."
                resp2 = await aclient.responses.create(**retry_args)
                text2 = _extract_output_text(resp2)
                if text2 and text2.strip():
                    return text2.strip()

            debug_payload = None
            try:
                if hasattr(resp, 'model_dump'):
                    debug_payload = resp.model_dump()
                elif isinstance(resp, dict):
                    debug_payload = resp
            except Exception as dump_exc:
                logger.debug('Failed to dump response payload: %s', dump_exc)
            logger.error('No output text; raw response payload=%s', debug_payload)
            return "Sorry, I couldn't generate a response just now. Please try again."

        except asyncio.TimeoutError:
            elapsed = perf_counter() - call_started
            if attempt < max_retries - 1:
                backoff = 2 ** attempt
                logger.warning(
                    "OpenAI call timed out after %.2fs (attempt %d/%d), retrying in %ds",
                    elapsed,
                    attempt + 1,
                    max_retries,
                    backoff,
                )
                await asyncio.sleep(backoff)
                continue
            else:
                logger.error(
                    "OpenAI call timed out after %.2fs (attempt %d/%d), giving up",
                    elapsed,
                    attempt + 1,
                    max_retries,
                )
                return "Sorry, the request timed out. Please try again."

        except (APITimeoutError, RateLimitError) as exc:
            elapsed = perf_counter() - call_started
            if attempt < max_retries - 1:
                backoff = 2 ** attempt
                logger.warning(
                    "OpenAI transient error %s after %.2fs (attempt %d/%d), retrying in %ds",
                    type(exc).__name__,
                    elapsed,
                    attempt + 1,
                    max_retries,
                    backoff,
                )
                await asyncio.sleep(backoff)
                continue
            else:
                logger.error(
                    "OpenAI transient error %s after %.2fs (attempt %d/%d), giving up: %s",
                    type(exc).__name__,
                    elapsed,
                    attempt + 1,
                    max_retries,
                    exc,
                )
                return "Sorry, I'm having trouble reaching the model right now. Please try again in a moment."

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
            return "Sorry, I'm having trouble reaching the model right now. Please try again in a moment."

    # Should never reach here, but just in case
    return "Sorry, I couldn't complete the request after multiple attempts. Please try again."


__all__ = ["generate_ai_reply"]
