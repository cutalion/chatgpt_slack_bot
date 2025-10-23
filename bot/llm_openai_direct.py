"""
OpenAI Direct API agent provider implementation.

This module wraps the existing OpenAI Responses API implementation
as an AgentProvider, enabling it to work within the provider-agnostic
agent architecture.
"""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple, Iterable, Set

import config
from openai import AsyncOpenAI, APITimeoutError, RateLimitError
from slack_tools import SlackToolRunner


logger = logging.getLogger(__name__)


class OpenAIDirectAgent:
    """
    Agent provider that uses OpenAI Responses API directly.

    This is the original implementation, now wrapped as an AgentProvider
    to enable multi-provider support. It provides direct access to OpenAI's
    Responses API with full tool execution support.
    """

    def __init__(self):
        """Initialize the OpenAI client."""
        self.aclient = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.GPT_MODEL

    async def generate_reply(
        self,
        messages: List[Dict[str, Any]],
        *,
        slack_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate a reply using the OpenAI Responses API.

        This implementation matches the original generate_ai_reply function,
        now wrapped as an AgentProvider method.
        """
        context = slack_context or {}
        max_output_tokens = config.MAX_OUTPUT_TOKENS
        instructions = None
        filtered_messages = []

        # Extract system message as instructions (Responses API pattern)
        for message in messages:
            if message.get("role") == "system":
                instructions = message.get("content")
                continue
            filtered_messages.append(message)

        message_count = len(filtered_messages)
        logger.info(
            "Calling OpenAI model=%s messages=%d max_output_tokens=%s",
            self.model,
            message_count,
            max_output_tokens,
        )

        args: Dict[str, Any] = {
            "model": self.model,
            "input": self._to_responses_input(filtered_messages),
            "max_output_tokens": max_output_tokens,
        }
        if instructions:
            args["instructions"] = instructions
        if getattr(config, "REASONING_EFFORT", None):
            args["reasoning"] = {"effort": config.REASONING_EFFORT}

        # Configure tools if enabled
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
                    self.aclient.responses.create(**args),
                    timeout=timeout_seconds
                )

                self._log_usage_metrics(resp, context=f"attempt-{attempt + 1}")
                logger.debug('OpenAI response object: %s', type(resp))
                tools_handled = False
                pending_unhandled: List[str] = []
                if runner:
                    resp, tools_handled, pending_unhandled = await self._run_slack_tools(
                        resp,
                        runner,
                        instructions=instructions,
                        max_output_tokens=max_output_tokens,
                        tool_definitions=tool_definitions,
                    )

                elapsed = perf_counter() - call_started
                logger.debug('OpenAI raw response: %s', getattr(resp, 'model_dump', lambda: resp)())
                status = self._get(resp, "status") or "completed"
                if status and status != "completed":
                    reason = self._get(self._get(resp, "incomplete_details", {}), "reason")
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
                    self.model,
                    len(filtered_messages),
                )

                text = self._extract_output_text(resp)
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
                    resp2 = await self.aclient.responses.create(**retry_args)
                    self._log_usage_metrics(resp2, context="tool-fallback")
                    text2 = self._extract_output_text(resp2)
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
                    self.model,
                    message_count,
                )
                logger.exception("Responses API failed: %s", exc)
                return "Sorry, I'm having trouble reaching the model right now. Please try again in a moment."

        # Should never reach here, but just in case
        return "Sorry, I couldn't complete the request after multiple attempts. Please try again."

    def _to_responses_input(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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

    def _get(self, obj: Any, key: str, default: Any = None) -> Any:
        """Attribute-or-dict getter."""
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _extract_output_text(self, resp: Any) -> Optional[str]:
        """Robustly extract text from a Responses API result."""
        try:
            text = getattr(resp, "output_text", None)
            if isinstance(text, str) and text.strip():
                return text
        except Exception:
            pass

        pieces: List[str] = []
        try:
            outputs = self._get(resp, "output", []) or []
            for output in outputs:
                contents = self._get(output, "content", []) or []
                for chunk in contents:
                    ctype = self._get(chunk, "type")
                    if ctype not in ("output_text", "summary_text", "message_text", "text", None):
                        continue
                    text_block = self._get(chunk, "text")
                    if text_block is None:
                        continue
                    if isinstance(text_block, str):
                        pieces.append(text_block)
                    else:
                        val = self._get(text_block, "value")
                        if isinstance(val, str) and val.strip():
                            pieces.append(val)
                        else:
                            fallback = self._get(text_block, "text")
                            if isinstance(fallback, str) and fallback.strip():
                                pieces.append(fallback)
        except Exception as exc:
            logger.debug("Failed to parse response.output content: %s", exc)

        joined = "\n\n".join(pieces).strip() if pieces else ""
        return joined or None

    def _extract_tool_calls(self, resp: Any) -> List[Dict[str, Any]]:
        """Return every tool call payload present on a Responses API object."""

        def _normalise_call(payload: Any) -> Optional[Dict[str, Any]]:
            if not payload:
                return None
            function_block = self._get(payload, "function")
            name = self._get(payload, "name") or self._get(function_block, "name")
            if not name:
                return None
            arguments = (
                self._get(payload, "arguments")
                or self._get(payload, "input")
                or self._get(function_block, "arguments")
            )
            identifier = (
                self._get(payload, "id")
                or self._get(payload, "tool_call_id")
                or self._get(payload, "call_id")
            )
            call_id = self._get(payload, "call_id") or identifier
            return {
                "id": identifier,
                "call_id": call_id,
                "name": name,
                "arguments": arguments,
            }

        calls: List[Dict[str, Any]] = []
        required_action = self._get(resp, "required_action")
        submit_section = self._get(required_action, "submit_tool_outputs")
        for call in self._get(submit_section, "tool_calls", []) or []:
            normalised = _normalise_call(call)
            if normalised:
                calls.append(normalised)

        tool_like_types = {"tool_use", "function_call", "function", "tool_call"}
        for output in self._get(resp, "output", []) or []:
            if (self._get(output, "type") or "").lower() in tool_like_types:
                normalised = _normalise_call(output)
                if normalised:
                    calls.append(normalised)
            for chunk in self._get(output, "content", []) or []:
                if (self._get(chunk, "type") or "").lower() in tool_like_types:
                    normalised = _normalise_call(chunk)
                    if normalised:
                        calls.append(normalised)
        return calls

    def _log_usage_metrics(self, resp: Any, *, context: str) -> None:
        """Log token usage and estimated cost for a given Responses API call."""

        if resp is None:
            return

        usage = self._get(resp, "usage")
        if not usage:
            logger.debug("No usage metrics available for context=%s", context)
            return

        metrics = self._extract_usage_counts(usage)
        if not metrics:
            logger.debug("Usage payload missing token counts for context=%s", context)
            return

        raw_model = self._get(resp, "model") or self.model or ""
        model_name = str(raw_model).strip()
        cost, cached_input_tokens = self._estimate_cost(model_name, metrics)

        log_parts = [
            f"context={context}",
            f"model={model_name or 'unknown'}",
            f"input_tokens={metrics.get('input_tokens', 0)}",
            f"output_tokens={metrics.get('output_tokens', 0)}",
            f"total_tokens={metrics.get('total_tokens', 0)}",
        ]

        reasoning_tokens = metrics.get("reasoning_tokens")
        if reasoning_tokens:
            log_parts.append(f"reasoning_tokens={reasoning_tokens}")

        cache_creation = metrics.get("cache_creation_input_tokens")
        if cache_creation:
            log_parts.append(f"cache_creation_input_tokens={cache_creation}")

        cache_read = metrics.get("cache_read_input_tokens")
        if cache_read:
            log_parts.append(f"cache_read_input_tokens={cache_read}")

        if cached_input_tokens:
            log_parts.append(f"effective_cached_input_tokens={cached_input_tokens}")

        if cost is not None:
            log_parts.append(f"cost_usd={cost:.6f}")
        else:
            log_parts.append("cost_usd=unavailable")

        logger.info("OpenAI usage %s", " ".join(log_parts))

    def _extract_usage_counts(self, usage: Any) -> Dict[str, int]:
        """Normalise usage payload into a dictionary of token counts."""

        metrics: Dict[str, int] = {}

        input_tokens = self._coerce_int(self._get(usage, "input_tokens"))
        if input_tokens is None:
            input_tokens = self._coerce_int(self._get(usage, "prompt_tokens"))
        if input_tokens is None:
            input_tokens = self._sum_usage_tokens(usage, prefix="input_", exclude={"input_tokens"})
        output_tokens = self._coerce_int(self._get(usage, "output_tokens"))
        if output_tokens is None:
            output_tokens = self._coerce_int(self._get(usage, "completion_tokens"))
        if output_tokens is None:
            output_tokens = self._sum_usage_tokens(usage, prefix="output_", exclude={"output_tokens"})
        total_tokens = self._coerce_int(self._get(usage, "total_tokens"))
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens

        if input_tokens is not None:
            metrics["input_tokens"] = input_tokens
        if output_tokens is not None:
            metrics["output_tokens"] = output_tokens
        if total_tokens is not None:
            metrics["total_tokens"] = total_tokens

        reasoning_tokens = self._coerce_int(self._get(usage, "reasoning_tokens"))
        if reasoning_tokens is None:
            reasoning_tokens = self._sum_usage_tokens(usage, prefix="reasoning_", exclude={"reasoning_tokens"})
        if reasoning_tokens:
            metrics["reasoning_tokens"] = reasoning_tokens

        cache_creation = self._coerce_int(self._get(usage, "cache_creation_input_tokens"))
        if cache_creation:
            metrics["cache_creation_input_tokens"] = cache_creation

        cache_read = self._coerce_int(self._get(usage, "cache_read_input_tokens"))
        if cache_read:
            metrics["cache_read_input_tokens"] = cache_read

        return metrics

    def _sum_usage_tokens(
        self,
        usage: Any,
        *,
        prefix: str,
        exclude: Optional[Set[str]] = None,
    ) -> Optional[int]:
        """Sum token counts matching the given prefix when explicit totals are absent."""

        total = 0
        found = False
        for key, value in self._iter_usage_items(usage):
            if exclude and key in exclude:
                continue
            if not key.startswith(prefix):
                continue
            if not key.endswith("_tokens"):
                continue
            coerced = self._coerce_int(value)
            if coerced is None:
                continue
            total += coerced
            found = True
        return total if found else None

    def _iter_usage_items(self, usage: Any) -> Iterable[Tuple[str, Any]]:
        """Yield key/value pairs from an OpenAI usage payload regardless of type."""

        if usage is None:
            return []

        if isinstance(usage, dict):
            return list(usage.items())

        if hasattr(usage, "model_dump"):
            try:
                dumped = usage.model_dump()
                if isinstance(dumped, dict):
                    return list(dumped.items())
            except Exception:
                pass

        if hasattr(usage, "to_dict"):
            try:
                dumped = usage.to_dict()
                if isinstance(dumped, dict):
                    return list(dumped.items())
            except Exception:
                pass

        items: List[Tuple[str, Any]] = []
        for attr in dir(usage):
            if attr.startswith("_"):
                continue
            try:
                value = getattr(usage, attr)
            except Exception:
                continue
            if callable(value):
                continue
            items.append((attr, value))
        return items

    def _coerce_int(self, value: Any) -> Optional[int]:
        """Convert a usage value to int when possible."""

        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return int(float(text))
            except ValueError:
                return None
        return None

    def _estimate_cost(self, model: Optional[str], metrics: Dict[str, int]) -> Tuple[Optional[float], Optional[int]]:
        """Estimate USD cost for token usage when pricing data is known.

        Returns:
            (total_cost, cached_token_count) where cached_token_count represents
            the number of input tokens charged at the cached-input rate.
        """

        pricing = self._lookup_pricing(model)
        if not pricing:
            return None, None

        input_price = pricing.get("input")
        cached_input_price = pricing.get("cached_input")
        output_price = pricing.get("output")

        input_tokens = metrics.get("input_tokens")
        output_tokens = metrics.get("output_tokens")
        cache_read_tokens = metrics.get("cache_read_input_tokens") or 0
        cache_creation_tokens = metrics.get("cache_creation_input_tokens")

        cached_tokens = cache_read_tokens if cache_read_tokens > 0 else None

        # Determine the quantity of tokens billed at the standard input rate.
        non_cached_input_tokens: Optional[int]
        if input_tokens is not None:
            non_cached_input_tokens = input_tokens - cache_read_tokens
        elif cache_creation_tokens is not None:
            non_cached_input_tokens = cache_creation_tokens
        else:
            non_cached_input_tokens = None

        if non_cached_input_tokens is not None and non_cached_input_tokens < 0:
            non_cached_input_tokens = 0

        cost = 0.0

        if non_cached_input_tokens and input_price:
            cost += (non_cached_input_tokens / 1_000_000.0) * input_price

        if cache_read_tokens and cached_input_price:
            cost += (cache_read_tokens / 1_000_000.0) * cached_input_price

        if output_tokens and output_price:
            cost += (output_tokens / 1_000_000.0) * output_price

        total_cost = cost if cost > 0.0 else None
        return total_cost, cached_tokens

    def _lookup_pricing(self, model: Optional[str]) -> Optional[Dict[str, float]]:
        """Return pricing data for the provided model name when available."""

        pricing_table = getattr(config, "OPENAI_PRICING_PER_M_TOKEN", None)
        if not pricing_table:
            return None

        if not model:
            return None

        normalized = str(model).lower()
        for key, value in pricing_table.items():
            if normalized == key or normalized.startswith(f"{key}-"):
                return value
        return None

    async def _run_slack_tools(
        self,
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
            calls = self._extract_tool_calls(current)
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
            response_id = self._get(current, "id")
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
                "model": self.model,
                "input": formatted_outputs,
                "previous_response_id": response_id,
                "max_output_tokens": max_output_tokens,
            }
            if instructions:
                request_kwargs["instructions"] = instructions
            if tool_definitions:
                request_kwargs["tools"] = tool_definitions
            call_number = runner.max_calls - remaining + 1
            current = await self.aclient.responses.create(**request_kwargs)
            self._log_usage_metrics(current, context=f"tool-followup-{call_number}")
            handled_any = True
            remaining -= 1
        return current, handled_any, pending_unhandled


__all__ = ["OpenAIDirectAgent"]
