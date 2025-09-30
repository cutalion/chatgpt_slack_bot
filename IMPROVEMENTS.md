# Improvement Backlog

Curated backlog of reliability and maintainability work across the Slack bot.
Grouped roughly by priority (highest first) and area of impact.

## High-Priority Stabilisations

- **Skip duplicate prompt entries.** Filter history items so the triggering message is not added twice (`conversations_replies` already returns it). Prevents confusing the LLM and trimming useful context earlier.
- **Filter non-actionable events.** Ignore events with subtypes (edits, deletions, bot messages) and messages authored by this bot before doing any lookups. Avoids reply loops and `KeyError` on missing fields.
- **Batch user lookups.** Reuse author data embedded in history payloads, cache aggressively, and parallelise any remaining `users_info` requests. Cuts latency and rate-limit risk when threads are long.
- **Fail fast on bad configuration.** Validate `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `OPENAI_API_KEY`, and `GPT_MODEL` during startup with explicit errors and safe defaults (e.g. default model `gpt-4o-mini`).
- **Timeout and retry OpenAI calls.** Wrap `aclient.responses.create` with `asyncio.wait_for` and add retry/backoff on transient network failures.

## Prompt & Event Handling

- **Harden thread history fetch.** Catch `SlackApiError`, log structured details, and fall back to replying without history rather than crashing.
- **Lean on message metadata first.** Prefer `user_profile` / `username` fields already present on history entries before reaching out to the Web API.
- **Attribute assistant messages precisely.** Treat messages as assistant replies only when their `user` matches the bot user ID to avoid adopting other bots' content.
- **Handle blank inputs.** Detect effectively empty user messages and respond with a polite clarification request instead of empty prompts to the model.
- **Manage context by budget.** Trim history by tokens (or summarise) instead of raw message count to stay within OpenAI limits.
- **Internationalization and language detection.** Detect conversation language from thread history and respond in the same language. For hardcoded messages (blank input responses, error messages, etc.), either infer language from user's recent messages or let the LLM generate the response instead of using English-only hardcoded strings.

## Testing & Quality Gates

- **Async handler coverage.** Add pytest-asyncio tests for `handle_mention` covering DMs, threads, subtype filtering, Slack failures, and duplicate-message prevention.
- **Slack utility tests.** Extend unit tests around `get_user_display_name`, caching behaviour, and failure paths in `slack_utils`.
- **Tooling regression tests.** Cover `_extract_output_text`, `_extract_tool_calls`, and `_run_slack_tools` branches for unsupported/partial tool calls.
- **Enforce coverage targets.** Configure coverage tooling (or CI) to enforce minimum statement/branch coverage so regressions surface quickly.
- **LLM module tests.** Add tests for `llm.py` covering tool execution logic, response parsing, and error handling paths.
- **Bot event handler tests.** Add tests for `bot.py` main event handler covering mention handling, thread context, and error scenarios.
- **Prompt builder tests.** Add tests for `prompt.py` covering different configuration combinations and context injection.

## Observability & Logging

- **Localise logging configuration.** Move `logging.basicConfig` behind the module entrypoint to avoid clobbering host logging when modules are imported.
- **Structured diagnostics.** Standardise log payloads (channel, thread, Slack response metadata) to simplify filtering and alerting.

## Operations & Tooling

- **Modernise the container.** Bump the base image to Python 3.10+, remove redundant apt packages, and keep builds lean.
- **Prune unused dependencies.** Drop `PyYAML`, `aiohttp`, and any other unused libraries to reduce attack surface and update burden.
- **Fix Docker volume usage.** Replace the `VOLUME ./bot:/code/bot` directive with explicit bind mounts in `docker-compose.yml` (or document how to mount for local dev) so containers start predictably.
- **Start-up diagnostics.** On launch, emit checks for Slack/Web auth and OpenAI reachability to surface misconfiguration before handling events.
- **Retry Slack 429s.** Add backoff around Slack Web API calls using `Retry-After` headers to improve resilience under bursty loads.

## Code Quality & Consistency

- **Standardise type hints.** Use consistent union syntax throughout (prefer `Optional[T]` over `T | None` for Python 3.9 compatibility, or upgrade to 3.10+ and use modern syntax everywhere).
- **Extract magic strings.** Move format strings (timestamp formats, regex patterns) to module-level constants for maintainability.
- **Specific exception handling.** Replace generic `except Exception` catches with specific exception types where possible (network errors, API errors).
- **Precise message type hints.** Use `List[Dict[str, Any]]` instead of `Iterable[Dict[str, Any]]` for message parameters that are iterated multiple times.

## Agentic Architecture (Anthropic Agent SDK Patterns)

- **Implement "Verify Work" stage.** Add output validation before posting to Slack: check for malformed mentions, excessive length, and tone appropriateness. Consider self-correction loop where the model reviews its own response.
- **Enable self-correction and error recovery.** When Slack post fails or LLM returns unsatisfactory output, feed errors back to the model for reformulation instead of posting generic error messages.
- **Increase tool iteration limits.** Raise `SLACK_TOOL_MAX_CALLS` from 2 to support multi-step workflows (read history → identify users → get user info → synthesize). Consider making this dynamic based on task complexity.
- **Add context compaction strategy.** Implement sliding window with summarization for long threads. Use token-based budgeting instead of raw message count to stay within model limits while preserving key context.
- **Multi-step planning capability.** Allow the bot to plan and execute complex workflows iteratively rather than single-shot execution. Enable gather context → take action → verify loops.
- **Relax prescriptive tool guidance.** Replace rigid tool usage instructions in prompts (e.g., "limit to 2-4 results", "do not use for...") with principles that encourage exploration and self-correction.
- **Output validation layer.** Before posting, run lightweight checks: mention format validation, length limits, presence of required context, and alignment with user intent.
- **Iterative refinement for complex requests.** For multi-part questions or summaries, let the bot gather context iteratively, verify completeness, then formulate the final response.

## Provider-Agnostic Agent Architecture

**Goal:** Decouple Slack integration from LLM provider, enabling multi-provider support and vendor flexibility.

**Approach:**
1. Define standard `AgentProvider` interface with common I/O contract (messages, instructions, tools, context → response)
2. Keep existing Slack tools as-is initially (MCP migration can come later)
3. Implement adapters for different agent providers (OpenAI Agents SDK, Anthropic Agent SDK, direct API)
4. Enable runtime provider selection via configuration

**Benefits:**
- Cost optimization by routing to appropriate provider based on task complexity
- Redundancy and failover across providers
- Best-of-breed model selection per task type (e.g., Claude for reasoning, GPT for factual)
- Future-proof against vendor lock-in
- A/B testing different providers in production

**Prerequisites:**
- Complete Phase 5-6 (stable context management and self-correction patterns)
- Research OpenAI Agents SDK and Anthropic Agent SDK compatibility with current architecture
- Design provider interface contract that works for both SDKs

**Implementation Phases:**
1. **Design `AgentProvider` protocol** - Define standard interface (messages, instructions, tools, context → response)
2. **Wrap existing implementation** - Refactor `llm.py` as `OpenAIDirectAgent` implementing the protocol (no behavior change)
3. **Add OpenAI Agents SDK** - Implement `OpenAISDKAgent` and compare behavior/performance/cost
4. **Add Anthropic Agent SDK** - Implement `AnthropicAgent` sharing same tool definitions
5. **Provider selection infrastructure** - Config-driven provider selection, fallback logic, A/B testing support
6. **Optional: MCP migration** - Later, convert tools to MCP servers for even better provider portability

**Key Design Decisions:**
- Start with self-written tools (current Slack tools work fine)
- MCP can be added later as an optimization, not a requirement
- Interface must support both SDK patterns (OpenAI's multi-agent handoffs, Anthropic's verify-work loop)
- Keep Slack integration layer (bot.py) unchanged during migration

## Future Enhancements (Careful Changes)

- **Chunk long Slack replies.** Split oversized model outputs into Slack-safe chunks and thread follow-ups automatically.
- **Expand Slack toolset.** Introduce additional safe Slack helpers (channel info, list members, reactions) once guardrails and audit logging are in place.
- **GitHub context integration.** Allow the bot scoped, read-only GitHub access so it can retrieve source snippets when explaining repository behaviour (e.g. GitHub App with `contents:read`, environment-stored tokens, and an allowlisted repo list).
