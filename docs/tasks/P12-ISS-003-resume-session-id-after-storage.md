# Worker spec: P12-ISS-003 — Resume path should use acquired MCP session id

**Task ID:** P12-ISS-003  
**Issue:** [PHASE12_ISSUES.md](../PHASE12_ISSUES.md) § P12-ISS-003  
**PM doc:** [PHASE12_MVP.md](../PHASE12_MVP.md)  
**Depends on:** P12-ISS-002, P12-003, P12-004, P12-005 (all committed)

> **Worker**: implement only what this spec defines. Report in § Results when done.  
> Do not edit PM docs, BACKLOG, PHASES, IDEA, or sibling task specs.

---

## Files policy

### May edit
- `server/mcp_server.py`
- `tests/test_supervisor_state_p12_001.py`

### Must not touch
- `core/engine/*` (including `supervisor_agent.py`, `supervisor_tool_runner.py`)
- `core/state/*`
- `core/context/*`
- `docs/` except `§ Results` in this file
- Any sibling `docs/tasks/*.md`

---

## Goal

Fix the resume ordering bug where `delegate_to_agent()` detects paused state and calls
`_handle_resume(...)` **before** `SessionStore().acquire(...)`, causing
`mcp_session_id=None` to be passed to the resume executor path even when `align_host`
could reuse a warm session.

After this fix:
- Paused-state detection happens **after** session acquisition.
- `_handle_resume(...)` receives `mcp_session_id=storage.mcp_session_id`.
- Existing implicit resume semantics remain unchanged (`answer`, `start_fresh`, paused reminder).
- No behavior changes to normal (non-paused) delegation path.

---

## Scope

### 1) `server/mcp_server.py` — reorder paused-state branch

In `delegate_to_agent(...)`, move the paused-state logic block currently near:
- `_project_key = ProjectKeyResolver.from_spec_path(spec_path)`
- `_paused_state = SupervisorState.find_latest(_project_key)`
- `start_fresh / paused reminder / _handle_resume(...)`

to a point **after**:
- `ws = obs.default_workspace_path()`
- `policy = resolve_session_policy(ws)`
- `host_hint = get_host_provider().resolve_active_session(ws)` (with current try/except)
- `storage = SessionStore().acquire(ws, policy, host_hint)`

but **before** heavy compile/planner/reviewer/executor work continues.

Keep behavior exactly the same:
- `start_fresh=True` and paused state exists: abandon paused state and continue fresh.
- paused state exists + `answer is None`: return paused reminder payload.
- paused state exists + `answer is not None`: call `_handle_resume(...)` and return early.

When calling `_handle_resume(...)`, pass:

```python
return _handle_resume(
    state=_paused_state,
    answer=answer,
    task=task,
    ctx=ctx,
    mcp_session_id=storage.mcp_session_id,   # required fix
)
```

### 2) Keep metrics/trace shape stable

Do not change payload schema.  
Do not remove/rename existing events.

It is acceptable that paused reminder / resume calls now have a real acquired storage
context first (this is the point of the fix).

---

## Tests

Add tests in `tests/test_supervisor_state_p12_001.py` (or update existing ones) to cover:

1. **Resume path passes acquired session id**
   - Mock `SupervisorState.find_latest` to return paused state.
   - Mock `SessionStore.acquire` to return a storage object with `mcp_session_id="abc123"`.
   - Mock `_handle_resume`.
   - Call `delegate_to_agent(..., answer="continue")`.
   - Assert `_handle_resume` called with `mcp_session_id="abc123"`.

2. **Paused reminder path still returns early and does not run pipeline**
   - paused state exists, `answer=None`.
   - Assert outcome is `needs_input` / `paused_awaiting_answer`.
   - Assert planner/clarity/executor heavy path is not invoked (existing guards can be reused).

3. **start_fresh path still abandons paused state**
   - Reuse existing `start_fresh` test expectations.
   - Confirm stale paused file removed and fresh delegation continues.

Run:

```bash
pytest -q tests/test_supervisor_state_p12_001.py tests/test_delegate_tool.py
```

---

## Acceptance checklist

- [ ] Paused-state detection runs after `SessionStore().acquire(...)`.
- [ ] Resume call passes `mcp_session_id=storage.mcp_session_id` into `_handle_resume(...)`.
- [ ] Implicit resume behavior unchanged (`answer` resumes, no-answer reminds, `start_fresh` abandons).
- [ ] No payload schema changes.
- [ ] Tests updated/added for the session-id pass-through and all pass.

---

## § Results

*(Worker fills this in when done.)*

**Date completed:**  
**Tests:**  
**Notes / blockers:**
