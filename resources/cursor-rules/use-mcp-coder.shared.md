<!-- @shared: included by use-mcp-coder.default.mdc and use-mcp-coder.strict.mdc at sync time -->

## Spec location (required)

- **Never** create `specs/` at the **repo root** (no `specs/tasks/`, `specs/epics/`, `specs/reports/` next to `src/` or project files).
- All planner specs live under **`.mcp-coder/specs/`** only (gitignored MCP workspace metadata).
- When calling `delegate_to_agent`, `spec_path` must be under `.mcp-coder/specs/tasks/` — use shorthand `tasks/foo.md` **or** full `.mcp-coder/specs/tasks/foo.md` (both accepted by MCP).

## Session / step summary (required)

- List **every** delegate attempt for the step — **including failures** — with `delegation_id`, `success`, and error/outcome.
- Quote **`prior_failed_attempts`** when present before describing the latest success.
- After a retry: **failed attempts first**, then latest outcome. Use `list_delegations(spec_path=…)` when unsure.

## Server freshness check (automatic startup step)

- At the **start of every new chat/session**, call `get_server_status()` automatically before any planning or delegation work (do this even if the user did not ask).
- Post a one-line startup status to the user that includes at least: `source_revision`, `started_at`, and whether `stale_vs_local_changes` is `true/false`.
- If `stale_vs_local_changes` is `true`: stop and ask the user to restart MCP connection in Cursor; re-check with `get_server_status()` before continuing.
- Treat this as a required safety gate, not optional guidance.
- `delegate_to_agent` responses also include `server_status` so freshness remains visible during normal workflow.

## Spec validation (`clarification_needed`)

When `clarification_needed` is non-empty: answer each item in Cursor chat, update the spec (`revision++`) if needed, then retry `delegate_to_agent`. Do **not** implement on disk yourself.

## Clarity check (automatic — never disable)

A pre-delegation clarity check runs before every `delegate_to_agent` call. **When it has questions, execution pauses** — the host must answer them in the spec file and re-delegate.

**You must not** disable or bypass it (no `clarity_pass: false` in config, no `MCP_CODER_CLARITY_PASS=0` in env).

**Hard cap:** after 2 blocked rounds on the same spec, the check auto-passes and execution proceeds regardless.

When `delegate_to_agent` returns `success: false` and `outcome: needs_input` with clarity questions in the `output`:
- The questions have already been written to the `## Q&A` section of the spec file (open items with `[answer here]`).
- **Fill in the answers** in the spec's `## Q&A` section directly — replace each `[answer here]` with the real answer.
- Re-call `delegate_to_agent` — do **not** implement yourself.
- You may also include a brief `context_summary` restating key decisions, but the spec Q&A is the canonical record.

`clarification_needed` (from spec validation) is **advisory** — execution ran, just note the questions for your next delegation.

## Supervisor escalation (`needs_input` + human gate)

When `delegate_to_agent` returns `ok: false` and the response includes a `question` field (or `needs_input: true` with question text), the supervisor paused the executor mid-run waiting for a human decision.

**While the delegation is still running** (you will see a `[gate]` progress notification with the `delegation_id` and the question): call `answer_delegation_question(delegation_id=…, answer="yes"/"no")` immediately. If you do not answer within ~120 s the delegation times out and returns `human_gate_timeout`.

After a timeout, re-delegate with `delegate_to_agent` — you cannot resume a timed-out delegation.

## Pre-flight dry run (`inspect_context`)

Before a complex or risky `delegate_to_agent` call, use `inspect_context(task=…, target_files=…, context_summary=…, spec_path=…)` to verify:
- Which files are in the executor's read set (`adapter_preview.fnames`)
- Estimated prompt size (avoid token-limit failures)
- That the spec's read-deps are resolved correctly

This is read-only — no files are edited. Use `include_prompt=true` for the full executor prompt text.
