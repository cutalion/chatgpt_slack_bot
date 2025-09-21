# Slack Tooling Roadmap

## Goals
- Let the assistant request Slack context (user details, channel history, files) when it improves answers.
- Maintain user trust by enforcing least privilege, tight quotas, and clear observability.
- Keep the implementation incremental so we can ship, learn, and expand safely.

## Guardrails & Design Principles
- **Opt-in enablement**: gate the feature behind configuration flags so workspaces can disable it entirely.
- **Least privilege**: introduce new OAuth scopes only when the corresponding tool ships.
- **Transparency**: log every tool invocation (name, channel, arguments, elapsed time, truncated result) for auditing.
- **Cost & rate awareness**: hard-stop the model after a small number of tool uses per response and respect Slack rate limits/backoff.
- **Data minimisation**: redact or summarise sensitive payloads before handing results to the model.

## Tool Inventory (proposed)
1. `get_user_info` — fetches a user’s display name, title, tz, and status text.
2. `read_channel_history` — returns channel messages within a requested window and automatically expands thread replies up to a cap.
3. `summarise_thread_batch` — server-side helper that accepts thread IDs, aggregates messages, and returns compact summaries to keep token usage manageable.
4. `fetch_file_content` — downloads text-based attachments and images that stay under size/MIME limits and redacts sensitive metadata.
5. `analyse_image` — calls an OpenAI vision-capable model on Slack-hosted images, returning OCR/description snippets for downstream reasoning.
6. (Future) `list_recent_threads`, `search_messages`, `post_ephemeral_notice` for proactive follow-ups once the core recap workflow is stable.

## Implementation Phases
1. **Tool harness**
   - Extend `llm.generate_ai_reply` to register tool schemas, detect tool calls, execute them, and feed tool outputs back into the Responses API.
   - Introduce a `SlackToolRunner` abstraction with per-tool config (timeouts, max payload size) and shared logging.
2. **Phase 1 tool: `get_user_info`**
   - Uses Slack Web API `users.info`.
   - Cache results using existing `_USER_NAME_CACHE` backing.
   - Mask fields (email, presence) unless explicitly whitelisted.
3. **Phase 2 tools**
   - `read_channel_history`: add pagination helpers in `slack_utils`, respect time ranges, expand thread replies, and normalise authors/timestamps.
   - `summarise_thread_batch`: reuse the channel history helper, chunk long threads, and leverage an internal summariser before handing results to the model.
4. **Phase 3 tools**
   - `fetch_file_content`: stream text files <= size limit, log MIME type, and reject binaries unless we add specialised handlers.
   - `analyse_image`: obtain signed URLs or temporary downloads, invoke vision models, and redact sensitive image metadata before returning results.
5. **Experience polish**
   - Update prompts to explain tool availability and when to narrate tool usage.
   - Add monitoring metrics (counts, errors) before enabling in production.

## Open Questions
- Should the assistant announce tool use back to the channel, or is silent execution acceptable?
- How do we prevent the assistant from repeatedly fetching the same large history in long threads?
- What sanitisation policy do we apply to private channel/file data before sending to OpenAI?
- Do we need additional review gates before enabling image analysis in workspaces with strict data policies?

## Next Steps
1. Ship `read_channel_history` as the next tool (scope: channel ID + timeframe, thread expansion, paging caps).
2. Capture structured logs for tool executions.
3. Draft user-facing messaging documenting opt-in behaviour.
4. Prototype `summarise_thread_batch` once channel history retrieval feels solid.
