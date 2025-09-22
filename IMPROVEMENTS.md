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

## Testing & Quality Gates

- **Async handler coverage.** Add pytest-asyncio tests for `handle_mention` covering DMs, threads, subtype filtering, Slack failures, and duplicate-message prevention.
- **Slack utility tests.** Extend unit tests around `get_user_display_name`, caching behaviour, and failure paths in `slack_utils`.
- **Tooling regression tests.** Cover `_extract_output_text`, `_extract_tool_calls`, and `_run_slack_tools` branches for unsupported/partial tool calls.
- **Enforce coverage targets.** Configure coverage tooling (or CI) to enforce minimum statement/branch coverage so regressions surface quickly.

## Observability & Logging

- **Localise logging configuration.** Move `logging.basicConfig` behind the module entrypoint to avoid clobbering host logging when modules are imported.
- **Structured diagnostics.** Standardise log payloads (channel, thread, Slack response metadata) to simplify filtering and alerting.

## Operations & Tooling

- **Modernise the container.** Bump the base image to Python 3.10+, remove redundant apt packages, and keep builds lean.
- **Prune unused dependencies.** Drop `PyYAML`, `aiohttp`, and any other unused libraries to reduce attack surface and update burden.
- **Fix Docker volume usage.** Replace the `VOLUME ./bot:/code/bot` directive with explicit bind mounts in `docker-compose.yml` (or document how to mount for local dev) so containers start predictably.
- **Start-up diagnostics.** On launch, emit checks for Slack/Web auth and OpenAI reachability to surface misconfiguration before handling events.
- **Retry Slack 429s.** Add backoff around Slack Web API calls using `Retry-After` headers to improve resilience under bursty loads.

## Future Enhancements (Careful Changes)

- **Chunk long Slack replies.** Split oversized model outputs into Slack-safe chunks and thread follow-ups automatically.
- **Agentic multi-step tooling.** Allow the model to plan multiple tool calls (history pagination, web search, more Slack utilities) with guardrails.
- **Expand Slack toolset.** Introduce additional safe Slack helpers (channel info, list members) once guardrails and audit logging are in place.

