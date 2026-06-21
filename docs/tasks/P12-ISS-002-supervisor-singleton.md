# Worker spec: P12-ISS-002 — SupervisorAgent singleton per project_key

**Task ID:** P12-ISS-002  
**Issue:** [PHASE12_ISSUES.md](../PHASE12_ISSUES.md) § P12-ISS-002  
**PM doc:** [PHASE12_MVP.md](../PHASE12_MVP.md)  
**Depends on:** P12-001, P12-002, P12-ISS-001 — all must be committed first

> **Worker**: implement only what this spec defines. Report in § Results when done.  
> Do not edit PM docs, BACKLOG, PHASES, IDEA, or sibling task specs.

---

## Files policy

### May edit
- `core/engine/supervisor_agent.py` — add `begin_delegation()` instance method
- `server/mcp_server.py` — add module-level registry + factory; wire into `delegate_to_agent` and `_handle_resume`
- `tests/test_supervisor_state_p12_001.py` — extend with singleton / begin_delegation tests

### Must not touch
- `core/state/supervisor_state.py` — not in scope
- `core/state/project_state.py` — not in scope
- `core/config/`, `core/context/`, `core/specs/` — not in scope
- `docs/` except `§ Results` in this file
- Any sibling `docs/tasks/*.md`

---

## Goal

Make `SupervisorAgent` a **long-lived singleton per project_key** within an MCP server
process. Today the agent is created fresh on every `delegate_to_agent` call and destroyed
when the delegation completes. This forces a disk round-trip to restore `project_state` on
every call and prevents the agent from accumulating in-memory context across delegations.

After this change:
- The first `delegate_to_agent` for a given `project_key` creates the agent and loads
  `project_state.json` from disk.
- Every subsequent call **reuses the same agent object** — no recreation, no disk reload.
- `project_state` accumulates in memory across delegations; disk writes happen at the end
  of each delegation (already implemented in `finish()`) for crash recovery.
- If the MCP server restarts, the agent is recreated and loads from disk seamlessly — same
  observable result as before, but without the per-call overhead.
- `_handle_resume` also uses the registry: after resuming, the agent stays in the registry.

This is the correct architecture: **Supervisor is the mind that persists; Aider is the
ephemeral tool it uses per delegation**. (See
[supervisor-orchestration-layer.md](../notes/supervisor-orchestration-layer.md) § "The
Supervisor is the mind".)

---

## Background: what changes and why

### Current flow (wrong)
```
delegate_to_agent() called
  → SupervisorAgent(delegation_id=…) created   ← new object, cold
  → begin()                                     ← loads project_state from disk EVERY TIME
  → run() / finish()
  → SupervisorAgent object GC'd                 ← gone
```

### Target flow (correct)
```
delegate_to_agent() called
  → _get_or_create_supervisor(project_key)      ← module-level registry lookup
      if missing: create + load project_state from disk (first call / after restart only)
      if present: reuse — project_state already warm in memory
  → agent.begin_delegation(delegation_id, …)    ← resets only per-delegation fields
  → agent.begin()                               ← skips disk load (already loaded)
  → agent.run() / agent.finish()
  → agent stays in _SUPERVISOR_REGISTRY         ← ready for next call
```

---

## Scope

### 1. `core/engine/supervisor_agent.py` — add `begin_delegation()`

Add an instance method that resets all **per-delegation** fields while keeping all
**cross-delegation** fields intact.

```python
def begin_delegation(
    self,
    *,
    delegation_id: str | None,
    executor_fn: ExecutorFn,
    reviewer_fn: ReviewerFn | None = None,
    decision_fn: DecisionFn | None = None,
    max_turns: int = 1,
    event_sink: EventSink | None = None,
    supervisor_model: str | None = None,
    spec_path: str | None = None,
    plan: str | None = None,
) -> None:
    """Reset per-delegation state. Call before begin() for each new delegation.

    Keeps cross-delegation state intact: _project_state, _workspace_path.
    """
```

**Per-delegation fields to reset** (set to the new delegation's values or cleared):
```
_delegation_id          ← new value
_executor_fn            ← new value
_reviewer_fn            ← new value
_decision_fn            ← new value
_max_turns              ← new value (clamped to max(1, …))
_event_sink             ← new value
_supervisor_model       ← new value
_plan                   ← new value
_spec_path              ← new value (may update within same project_key)
_loop_id                ← derive from new delegation_id
_loop_start_emitted     ← False
_loop_end_emitted       ← False
_cur_turn               ← 0
_turn_t0                ← None
_decisions              ← []
_last_result            ← None
_completed_turn_artifacts ← []
_pending_host_clarification ← None
```

**Cross-delegation fields to preserve** (do not touch):
```
_project_state                  ← already loaded; skip disk reload in begin()
_project_state_trace_enabled    ← keep (re-enabled per begin() logic below)
_workspace_path                 ← immutable for the agent's lifetime
```

**`begin()` already guards against double-load:** it has `if self._project_state is None`.
With a warm agent, `_project_state` is already set so `begin()` skips the disk read and
`ProjectState.load()` is not called again. No change to `begin()` needed.

**`_project_state_trace_enabled`:** reset it to `False` in `begin_delegation()`, let
`begin()` re-enable it when `spec_path is not None`. This preserves the existing guard.

---

### 2. `server/mcp_server.py` — registry + factory

#### 2a. Module-level registry

Add near the top of `mcp_server.py`, after imports:

```python
# Keyed by project_key. Long-lived per MCP server process lifetime.
_SUPERVISOR_REGISTRY: dict[str, "SupervisorAgent"] = {}
```

#### 2b. Factory function

```python
def _get_or_create_supervisor(
    project_key: str,
    workspace_path: str,
    spec_path: str | None,
) -> "SupervisorAgent":
    """Return the existing SupervisorAgent for this project_key, or create a fresh one.

    Creation loads project_state from disk (first call or after server restart).
    The returned agent has NOT had begin_delegation() called yet — caller must do that.
    """
    from core.engine.supervisor_agent import SupervisorAgent

    agent = _SUPERVISOR_REGISTRY.get(project_key)
    if agent is None:
        agent = SupervisorAgent(
            delegation_id=None,            # will be set by begin_delegation()
            workspace_path=workspace_path,
            executor_fn=lambda _t, _c: None,  # placeholder; overwritten by begin_delegation
            spec_path=spec_path,
        )
        _SUPERVISOR_REGISTRY[project_key] = agent
    return agent
```

#### 2c. Wire into the normal delegation path

In `delegate_to_agent`, replace the current `SupervisorAgent(…)` constructor call with:

```python
from core.state.project_key import ProjectKeyResolver
_project_key = ProjectKeyResolver.from_spec_path(spec_rel_path)

supervisor_agent = _get_or_create_supervisor(
    _project_key, ws, spec_rel_path
)
supervisor_agent.begin_delegation(
    delegation_id=delegation_id,
    executor_fn=lambda _turn, _correction: result,
    max_turns=_supervisor_max_turns,
    event_sink=_supervisor_event_sink,
    spec_path=spec_rel_path,
    plan=architect_plan,
)
```

The existing `supervisor_agent.begin()` / `begin_turn()` / `complete_turn()` / `finish()`
calls below remain unchanged.

#### 2d. Wire into `_handle_resume`

After `SupervisorAgent.resume()` creates the agent, store it in the registry so subsequent
calls after a resumed delegation see the same agent:

```python
agent = SupervisorAgent.resume(state, answer, …)
from core.state.project_key import ProjectKeyResolver
_pk = ProjectKeyResolver.from_spec_path(state.spec_path)
_SUPERVISOR_REGISTRY[_pk] = agent
```

The `SupervisorAgent.resume()` classmethod itself is unchanged — it already correctly
restores all per-delegation + cross-delegation state from `SupervisorState`.

---

## Trace events

No new trace events required. Existing `supervisor_loop_start`, `supervisor_loop_end`,
`project_state_loaded`, `project_state_saved` events are already sufficient. The
`project_state_loaded` event will only fire on the first delegation for a project_key
(cold start) since `begin()` skips the disk load on warm agents.

---

### 3. `server/mcp_server.py` — fix stale Aider session on pause/resume (BL-545 interim)

This is a small but important fix that falls naturally in this spec since we're already
touching the pause and resume paths.

**Problem:** When a delegation pauses (`needs_input`), the Aider Coder used for that turn
stays cached in `executor_cache._CODERS[mcp_session_id]` (the pre-pause state). The resume
turn always uses `mcp_session_id=None` (creates a fresh uncached Coder). The next normal
delegation after resume then picks up the stale pre-pause Coder — a conversation history
gap.

**Fix A — evict Coder on pause:**

In the code path where the Supervisor returns `outcome="needs_input"` (pause), call:

```python
from core.session.executor_cache import drop_coder
if storage.mcp_session_id:
    drop_coder(storage.mcp_session_id)
```

This ensures the next delegation after a resume starts with a fresh Coder rather than
picking up the stale pre-pause one.

**Fix B — pass `mcp_session_id` to `_handle_resume`:**

Update `_handle_resume` signature to accept `mcp_session_id: str | None` and pass it
through to `engine.run()` instead of the hardcoded `None`:

```python
def _handle_resume(
    state: SupervisorState,
    answer: str,
    task: str,
    ctx: Context | None,
    mcp_session_id: str | None = None,   # ← add this
) -> str:
    ...
    def _executor_fn(_turn_index: int, correction_note: str | None) -> ExecutionResult:
        ...
        return engine.run(
            prompt,
            target_files,
            workspace_path=ws,
            mcp_session_id=mcp_session_id,   # ← was hardcoded None
        )
```

Pass `storage.mcp_session_id` when calling `_handle_resume` from `delegate_to_agent`.

This allows the resume turn to benefit from `align_host` Coder warmth (repo map cache)
when the same host session is still active, consistent with normal delegation behaviour.

**Note:** The full Supervisor-owned session lifecycle (Supervisor decides when to reset via
`ExecutorFn` `reset_session` hint) is BL-545, deferred to end of Phase 12 / Phase 13.

---

## What is NOT in scope

- Context pipeline skip (clarity / context_compile / planner) — future optimization; the
  per-delegation pipeline still runs fully for correctness.
- Registry eviction / size limits — not needed; MCP server is per-workspace, small N.
- Thread safety / locking — MCP stdio is single-threaded.
- Full BL-545 `ExecutorFn reset_session` hint — Phase 13.
- CLI changes — `delegate_to_agent` is the only entry point that matters here.

---

## Acceptance checklist

- [ ] `SupervisorAgent.begin_delegation()` resets all per-delegation fields; keeps
  `_project_state` and `_workspace_path` untouched.
- [ ] `_SUPERVISOR_REGISTRY` in `mcp_server.py` is a module-level dict keyed by
  `project_key`.
- [ ] `_get_or_create_supervisor()` returns the same agent object on second call for the
  same `project_key` — no new `SupervisorAgent(…)` constructor called.
- [ ] `begin()` does not reload `project_state` from disk on second delegation when agent
  is warm (verified: `_project_state is not None` guard already in `begin()`; no code
  change needed, just verify via test).
- [ ] `_handle_resume` stores the resumed agent in `_SUPERVISOR_REGISTRY`.
- [ ] `project_state_loaded` trace event fires only once per project_key per process
  lifetime (cold start), not on every delegation.
- [ ] On `needs_input` outcome, `drop_coder(storage.mcp_session_id)` is called so the
  next delegation after a resume doesn't pick up the stale pre-pause Coder.
- [ ] `_handle_resume` accepts `mcp_session_id` param and passes it to `engine.run()`
  instead of the hardcoded `None`.
- [ ] All existing tests still pass (`pytest -q tests/test_supervisor_state_p12_001.py
  tests/test_supervisor_agent_p12_001.py tests/test_project_state_p12_002.py
  tests/test_delegate_tool.py`).

## New tests (add to `tests/test_supervisor_state_p12_001.py`)

Add at least **5 new tests**:

1. `test_get_or_create_supervisor_returns_same_object` — two calls with same project_key
   return the same `SupervisorAgent` instance (identity check `is`).
2. `test_get_or_create_supervisor_different_keys_different_objects` — different project_key
   returns a different instance.
3. `test_begin_delegation_resets_per_delegation_fields` — after one `begin_delegation()` +
   simulated turn, calling `begin_delegation()` again clears `_decisions`, `_cur_turn`,
   `_completed_turn_artifacts`, `_pending_host_clarification`, `_plan`.
4. `test_begin_delegation_preserves_project_state` — after the first `begin_delegation()` +
   `begin()`, manually set `agent._project_state.decisions.append(…)`. Call
   `begin_delegation()` again + `begin()` — `_project_state.decisions` still contains the
   earlier entry.
5. `test_project_state_not_reloaded_on_warm_agent` — mock `ProjectState.load`; call
   `begin_delegation()` + `begin()` twice on the same agent; assert `load` called exactly
   once (first call only).

---

## § Results

**Date completed:** 2026-06-21

**Tests:** `pytest -q tests/test_supervisor_state_p12_001.py tests/test_supervisor_agent_p12_001.py tests/test_project_state_p12_002.py tests/test_delegate_tool.py` — **56 passed, 0 failures** (3.10 s).

**Files changed:**
- `core/engine/supervisor_agent.py` — added `begin_delegation()` instance method (resets all per-delegation fields, preserves `_project_state` and `_workspace_path`).
- `server/mcp_server.py`:
  - Added module-level `_SUPERVISOR_REGISTRY: dict[str, SupervisorAgent]`.
  - Added `_get_or_create_supervisor(project_key, workspace_path, spec_path)` factory (before `_handle_resume`).
  - `delegate_to_agent`: replaced `SupervisorAgent(…)` constructor with `_get_or_create_supervisor(…) + agent.begin_delegation(…)`.
  - `_handle_resume`: added `mcp_session_id: str | None = None` parameter; passes it to `engine.run()` instead of hardcoded `None`; stores resumed agent in `_SUPERVISOR_REGISTRY[_pk]`.
  - On `supervisor_agent_result.outcome == "escalated"`: calls `drop_coder(storage.mcp_session_id)` (BL-545 interim fix).
- `tests/test_supervisor_state_p12_001.py` — added 5 new tests: `test_get_or_create_supervisor_returns_same_object`, `test_get_or_create_supervisor_different_keys_different_objects`, `test_begin_delegation_resets_per_delegation_fields`, `test_begin_delegation_preserves_project_state`, `test_project_state_not_reloaded_on_warm_agent`.

**Notes / blockers:**
- `mcp_session_id` in the `_handle_resume` call site from `delegate_to_agent` is `None` (the default) because `storage` is not yet created at that early-return point in the function. The parameter is in place and fully wired inside `_handle_resume`; a future refactor moving the resume early-return to after `storage` creation would enable passing the real `mcp_session_id`.
- `_project_state_trace_enabled` is reset to `False` in `begin_delegation()` so `begin()` re-enables it when `spec_path is not None`, preserving the existing guard and event-order stability for callers without a spec path.
