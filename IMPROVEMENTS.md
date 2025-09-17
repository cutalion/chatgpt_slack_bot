# Improvements for bot/bot.py

Ordered by complexity and impact: refactors (no behavior change if done correctly), then behavior-changing items.

## Medium Complexity — Refactors (No Intended Behavior Change)

1. **Parallelize user info lookups**  
   - Gather unique user IDs when building history, resolve them via `asyncio.gather`, and cache the results.  
   - Benefit: performance optimization without altering behaviour.

2. **Enforce full-coverage testing**  
   - Build out a pytest suite covering prompt generation, Slack utilities, and LLM helpers.  
   - Benefit: configure coverage tooling for 100 % statement/branch coverage to catch regressions early.

## Higher Complexity — Behavior Changes (Be Careful)

1. **Filter non-actionable events**  
   - Return early for events from bots or with subtypes like `message_changed` / `message_deleted`.  
   - Impact: prevents reply loops and reduces noise.

2. **Deduplicate current message**  
   - Include only history items with `ts < event_ts` when loading `conversations_replies`.  
   - Impact: avoids echoing the triggering message in the prompt.

3. **Chunk long replies**  
   - Split lengthy model outputs into Slack-safe chunks and post follow-ups in-thread.  
   - Impact: improves UX for extended answers.

4. **Retry on Slack 429s**  
   - Wrap Web API calls with backoff using `Retry-After` headers.  
   - Impact: boosts reliability under rate limits.

5. **Timeout OpenAI calls**  
   - Guard `aclient.responses.create(...)` with `asyncio.wait_for(..., timeout=OPENAI_TIMEOUT_SECONDS)`.  
   - Impact: protects against hangs from upstream latency.

6. **Default GPT model safely**  
   - Fall back to `gpt-4o-mini` in config when `GPT_MODEL` is unset.  
   - Impact: smoother DX while retaining Responses API support.

7. **Expand mentions to display names**  
   - Replace `<@U…>` tokens with cached display names in history prompts.  
   - Impact: friendlier context for the model.

8. **Handle empty inputs**  
   - Detect effectively blank user messages and send a gentle clarification prompt.  
   - Impact: better guidance for users in edge cases.

9. **Manage history by tokens**  
   - Truncate or summarise history to stay within token budgets.  
   - Impact: improves reliability and controls cost.

10. **Migrate to `slack_sdk`**  
    - Switch imports and drop legacy `slackclient` dependency.  
    - Impact: modernises dependencies; requires careful testing.

11. **Validate env at startup**  
    - Fail fast when required env vars are missing or malformed.  
    - Impact: clearer operational errors.

12. **Graceful shutdown**  
    - Handle `CancelledError`, close clients, and log termination details.  
    - Impact: cleaner shutdown semantics.

13. **Agentic multi-step tooling**  
    - Let the assistant plan tool calls (history pagination, web search, future utilities) before responding.  
    - Impact: major behaviour change requiring orchestration and guardrails.
