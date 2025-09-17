# Improvements for bot/bot.py

Ordered by complexity and impact: refactors (no behavior change if done correctly), then behavior-changing items.

## Medium Complexity — Refactors (No Intended Behavior Change)
1) Parallelize user info lookups where applicable:
    - When building history, gather unique user IDs and resolve with `asyncio.gather` once, then cache.
    - Rationale: performance optimization without changing behavior.

2) Add unit tests with strict coverage targets:
    - Introduce pytest-based test suite covering prompt building, Slack utilities, and LLM integration helpers.
    - Configure coverage tooling to enforce 100% statement/branch coverage to catch regressions.


## Higher Complexity — Behavior Changes (Be Careful)
1) Filter out bot/edited/deleted events early:
    - In the handler, return early for `event.get("bot_id")`, or `subtype` in `{"bot_message","message_changed","message_deleted"}`.
    - Impact: prevents reply loops and noise; changes which events are processed.

2) Deduplicate the current message from thread history:
    - When loading `conversations_replies`, include only messages with `ts < event_ts`.
    - Impact: avoids double-including the current message in the prompt; improves model context.

3) Implement long-reply chunking for Slack posts:
    - Split `ai_reply` into safe chunks and post subsequent parts as threaded replies.
    - Impact: better UX for lengthy outputs; changes message shape in Slack.

4) Add Slack rate-limit (429) retry with backoff:
    - Wrap Slack Web API calls; on 429, sleep `Retry-After` then retry a few times.
    - Impact: higher reliability; changes timing/error-handling behavior.

5) Add timeouts around OpenAI calls:
    - Wrap `aclient.responses.create(...)` with `asyncio.wait_for(..., timeout=OPENAI_TIMEOUT_SECONDS)` (env-configurable).
    - Impact: avoids hanging; affects timeout behavior.

6) Set a safe default for `GPT_MODEL` in `config.py`:
    - Default to `gpt-4o-mini` if unset, ensuring Responses API support.
    - Impact: changes behavior when env is missing; safer DX but different from “fail if unset”.

7) Expand `<@U...>` mentions in history to `@display_name`:
    - Replace raw mentions with cached display names for readability in model context.
    - Impact: changes the exact prompt text sent to the model.

8) Handle empty user input gracefully:
    - If message after mention stripping is empty, send a brief nudge (e.g., “How can I help?”).
    - Impact: changes interaction in edge cases.

9) Token/length-aware history management:
    - Pre-truncate/summarize older history to stay within token budgets; optionally summarize very long threads.
    - Impact: changes the context content; improves reliability and cost control.

10) Dependency migration to `slack_sdk` (optional but recommended):
    - Switch imports to `slack_sdk` and drop legacy `slackclient` from requirements.
    - Impact: runtime dependency change; risk if not tested end-to-end.

11) Env validation and fail-fast startup:
    - Validate presence/format of Slack tokens and `OPENAI_API_KEY`; log clear errors and exit on missing.
    - Impact: start-up behavior changes (fail fast instead of failing later).

12) Graceful shutdown handling:
    - Handle `CancelledError`, close clients cleanly, and log shutdown summary.
    - Impact: runtime behavior on shutdown.
