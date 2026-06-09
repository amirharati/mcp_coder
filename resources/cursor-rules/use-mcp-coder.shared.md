<!-- @shared: included by use-mcp-coder.default.mdc and use-mcp-coder.strict.mdc at sync time -->

## Spec location (required)

- **Never** create `specs/` at the **repo root** (no `specs/tasks/`, `specs/epics/`, `specs/reports/` next to `src/` or project files).
- All planner specs live under **`.mcp-coder/specs/`** only (gitignored MCP workspace metadata).
- When calling `delegate_to_agent`, `spec_path` must be under `.mcp-coder/specs/tasks/` — use shorthand `tasks/foo.md` **or** full `.mcp-coder/specs/tasks/foo.md` (both accepted by MCP).

## Session / step summary (required)

- List **every** delegate attempt for the step — **including failures** — with `delegation_id`, `success`, and error/outcome.
- Quote **`prior_failed_attempts`** when present before describing the latest success.
- After a retry: **failed attempts first**, then latest outcome. Use `list_delegations(spec_path=…)` when unsure.

## Spec validation (`clarification_needed`)

When `clarification_needed` is non-empty: answer each item in Cursor chat, update the spec (`revision++`) if needed, then retry `delegate_to_agent`. Do **not** implement on disk yourself.
