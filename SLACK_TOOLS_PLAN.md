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
2. `read_channel_messages` — paginated retrieval with message cap + summarisation hook.
3. `download_attachment` — retrieves small text-based files, rejects binaries by default.
4. (Future) `list_recent_threads`, `search_messages`, `post_ephemeral_notice` for follow-ups.

## Implementation Phases
1. **Tool harness**
   - Extend `llm.generate_ai_reply` to register tool schemas, detect tool calls, execute them, and feed tool outputs back into the Responses API.
   - Introduce a `SlackToolRunner` abstraction with per-tool config (timeouts, max payload size) and shared logging.
2. **Phase 1 tool: `get_user_info`**
   - Uses Slack Web API `users.info`.
   - Cache results using existing `_USER_NAME_CACHE` backing.
   - Mask fields (email, presence) unless explicitly whitelisted.
3. **Phase 2 tools**
   - `read_channel_messages`: add pagination helpers in `slack_utils`, impose token/length ceilings, and optionally summarise client-side.
   - `download_attachment`: stream text files <= size limit, log MIME type, and refuse unknown or binary formats.
4. **Experience polish**
   - Update prompts to explain tool availability and when to narrate tool usage.
   - Add monitoring metrics (counts, errors) before enabling in production.

## Open Questions
- Should the assistant announce tool use back to the channel, or is silent execution acceptable?
- How do we prevent the assistant from repeatedly fetching the same large history in long threads?
- What sanitisation policy do we apply to private channel/file data before sending to OpenAI?

## Next Steps
1. Land the tool harness with `get_user_info`.
2. Capture structured logs for tool executions.
3. Draft user-facing messaging documenting opt-in behaviour.
