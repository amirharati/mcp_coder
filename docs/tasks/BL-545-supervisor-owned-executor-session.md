# Worker spec: BL-545 — Supervisor-owned executor session lifecycle (v1)

**Task ID:** BL-545 (v1 slice)  
**Backlog:** [BACKLOG.md](../BACKLOG.md) § BL-545 (v1); deferred adaptation → BL-546  
**PM doc:** [PHASE12_MVP.md](../PHASE12_MVP.md) (Phase 12 close-out work)  
**Depends on:** P12-001..P12-005, P12-ISS-002 (singleton), P12-ISS-003 (resume session-id) — all committed first

> **Worker**: implement only what this spec defines. Report in § Results when done.  
> Do not edit PM docs, BACKLOG, PHASES, IDEA, or sibling task specs.  
> **Backend-neutral rule:** no Aider APIs (`drop_coder`, `get_or_create_coder`, repo map,
> `fnames`, `yes=True`) may appear in `core/engine/supervisor_agent.py`. Those stay in
> `server/mcp_server.py` / `core/session/`.

---

## Files policy

### May edit
- `core/engine/supervisor_agent.py` — extend `ExecutorFn` type; add reset-decision policy; pass hint into `executor_fn`
- `server/mcp_server.py` — update executor closures to accept + honor `reset_session`; evict Coder when hinted
- `tests/` — new file `tests/test_supervisor_session_reset_bl545.py`

### Must not touch
- `core/session/executor_cache.py` — already has `drop_coder()`; do not change its API
- `core/engine/aider_engine.py` — not in scope
- `core/state/*`, `core/context/*`, `core/specs/*` — not in scope
- `core/engine/supervisor_tool_runner.py`, `core/engine/supervisor.py` — not in scope
- `docs/` except `§ Results` in this file
- Any sibling `docs/tasks/*.md`

---

## Goal

**This is an infrastructure-first slice.** The objective is to put the *control* of
executor-session lifecycle where it belongs — in the **Supervisor** — and to wire the
plumbing end to end so it works smoothly. It is **not** to build smart context adaptation.
Keep the runtime behavior minimal and safe; the session/context stays exactly as it is
today except where correctness forces a reset. We improve the *mechanism* (smarter reset
decisions) in a later phase, once the control plane is in place.

Concretely: move the decision of **when to reset the executor (Aider) session** from the
host-driven `session_policy` to the Supervisor by introducing a `reset_session` hint on the
`ExecutorFn` callable. The backend-specific eviction (`drop_coder`) stays inside
`server/mcp_server.py`. The Supervisor computes a boolean intent; the closure honors it.

The v1 reset **policy is deliberately trivial** — do not add cleverness beyond:
1. **First turn after a resume** — the cached pre-pause Coder is stale (it never saw the
   turns that ran between pause and resume, and files on disk have moved on). Reset it.
   *(This one is a correctness requirement, not an optimization.)*
2. **Optional periodic reset every N turns** — env-gated and **default OFF**, so default
   behavior preserves the current session/context exactly. This exists only to prove the
   control plane works and to give an escape hatch; it is not a real adaptation strategy.

Everything smarter — hot-area drift detection, `session_policy`-becomes-a-hint, token-window
signals — is explicitly **deferred** (see § Deferred). Do not build it here.

---

## Background: current state

- `ExecutorFn = Callable[[int, "str | None"], ExecutionResult]` in
  `core/engine/supervisor_agent.py` (the `(turn_index, correction_note)` callable).
- `SupervisorAgent.run()` (the multi-turn loop) calls `self._executor_fn(turn_index, correction)`.
- The only place `run()` actually drives real executor work is `_handle_resume()` in
  `server/mcp_server.py`, whose `_executor_fn` (around line 1486) calls
  `engine.run(prompt, target_files, workspace_path=ws, mcp_session_id=mcp_session_id)`.
  After P12-ISS-003, `mcp_session_id` is the real acquired session id — so a warm cached
  Coder **can** be reused on resume, which is exactly the stale-Coder risk this spec fixes.
- The main `delegate_to_agent` path is single-turn host-driven (`begin_turn()` /
  `complete_turn()` / `finish()`); its `executor_fn` is a placeholder
  `lambda _turn, _correction: result` and does not drive real engine runs.
- `core/session/executor_cache.py` already exposes `drop_coder(mcp_session_id)`.
- On pause (`outcome == "escalated"`), `mcp_server.py` already calls
  `drop_coder(storage.mcp_session_id)` (P12-ISS-002 interim fix). This spec adds the
  *resume-side* reset so the first resumed turn also starts clean.

---

## Scope

### 1. `core/engine/supervisor_agent.py` — extend `ExecutorFn` + reset policy

#### 1a. Widen the `ExecutorFn` type

```python
# Worker: given (turn_index, correction_note, reset_session) produce an ExecutionResult.
ExecutorFn = Callable[[int, "str | None", bool], ExecutionResult]
```

#### 1b. Track resume state

In `__init__`, add:
```python
self._resumed_from_pause: bool = False
```

In the `resume()` classmethod, after restoring state, set:
```python
agent._resumed_from_pause = True
```

#### 1c. Reset-decision policy (backend-neutral — no Aider terms)

Add a method:

```python
def _should_reset_executor_session(self, turn_index: int) -> bool:
    """Decide whether the executor session should be reset before this turn.

    Backend-neutral: returns a boolean intent. The caller's executor_fn decides
    how to honor it (e.g. drop a cached Aider Coder). Reasons:
    - First turn of a resumed delegation: the cached session predates the pause
      and is stale.
    - Every N turns when MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY is set (drift bound).
    """
    if self._resumed_from_pause and turn_index == self._cur_turn + 1:
        # _cur_turn is the resumed-at turn; the next turn is the first new one.
        return True
    every = _resolve_session_reset_every()
    if every > 0 and turn_index > 1 and (turn_index - 1) % every == 0:
        return True
    return False
```

Add the config resolver (mirror `resolve_supervisor_max_turns` style):

```python
def _resolve_session_reset_every() -> int:
    """Reset executor session every N turns. 0/unset = never. Env-only for v1."""
    import os
    raw = os.environ.get("MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY", "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0
```

> Note on the resume condition: capture the resumed-at turn once at the start of `run()`
> (e.g. `resumed_at = self._cur_turn` before the loop) and compare against it, so the
> "first new turn" check is robust as `_cur_turn` advances. Implement whichever form is
> cleanest, but the observable behavior must be: **on a resumed delegation, the first
> executor turn after the pause gets `reset_session=True`; subsequent turns get it only
> from the every-N rule.**

#### 1d. Pass the hint into `executor_fn` in `run()`

At the single call site in `run()`:

```python
reset_session = self._should_reset_executor_session(turn_index)
result = self._executor_fn(turn_index, correction, reset_session)
```

Emit a trace event when a reset is signaled (so it's observable):

```python
if reset_session:
    self._emit({
        "type": "supervisor_session_reset",
        "turn_index": turn_index,
        "reason": "resumed_first_turn" if self._resumed_from_pause and ... else "interval",
    })
```

(Keep the reason string simple; `"resumed_first_turn"` vs `"interval"` is enough.)

After the first new turn runs on a resumed delegation, clear the flag so it does not
re-trigger:
```python
self._resumed_from_pause = False   # after the first post-resume turn is dispatched
```

---

### 2. `server/mcp_server.py` — honor the hint + update closures

#### 2a. Resume executor closure (around line 1486)

Update `_executor_fn` to accept the third arg and evict the cached Coder when hinted:

```python
def _executor_fn(
    _turn_index: int,
    correction_note: str | None,
    reset_session: bool = False,
) -> ExecutionResult:
    if reset_session and mcp_session_id:
        from core.session.executor_cache import drop_coder
        drop_coder(mcp_session_id)
    prompt = base_prompt
    if correction_note:
        prompt = f"{prompt}\n\n{correction_note}"
    with role_context(ROLE_EXECUTOR):
        return engine.run(
            prompt,
            target_files,
            workspace_path=ws,
            mcp_session_id=mcp_session_id,
        )
```

#### 2b. Main-path placeholder executor closure

The single-turn host-driven path uses `executor_fn=lambda _turn, _correction: result`.
Update it to accept the third arg so the widened `ExecutorFn` type is satisfied:

```python
executor_fn=lambda _turn, _correction, _reset=False: result,
```

Search for **every** `executor_fn=` / `def _executor_fn(` in `server/mcp_server.py` and
ensure all accept the 3-arg shape (default `False` for the unused placeholder ones).

#### 2c. Keep the existing pause-side `drop_coder` call

Do **not** remove the existing `drop_coder(storage.mcp_session_id)` on the escalated/pause
path (line ~3104). Pause-side eviction + resume-side reset together guarantee a clean
session across the full pause/resume cycle.

---

## Trace events

### `supervisor_session_reset`
```json
{
  "type": "supervisor_session_reset",
  "turn_index": 2,
  "reason": "resumed_first_turn"
}
```
`reason` is `"resumed_first_turn"` or `"interval"`.

---

## Deferred to a later phase — BL-546 (do NOT implement here)

This v1 only lays the control-plane plumbing. The **actual context adaptation** is a larger,
separate body of work for a later phase:

- Hot-area drift detection (reset when changed files diverge from what the session loaded).
- `session_policy` becoming a Supervisor hint rather than a global host override.
- Workspace-config (yaml) key for the reset interval (env-only in v1).
- Resetting based on token/context-window growth signals.
- Any "rebuild context smarter on reset" logic — v1 just drops the cached Coder and lets
  the existing creation path rebuild as it does today (keep the old context behavior).

Leave a one-line code comment near `_should_reset_executor_session` noting that richer
reset policy / context adaptation is deferred to a later phase, but add no logic.

---

## Acceptance checklist

- [ ] `ExecutorFn` type is `Callable[[int, str | None, bool], ExecutionResult]`.
- [ ] `SupervisorAgent._resumed_from_pause` set True in `resume()`, cleared after the first
  post-resume turn is dispatched.
- [ ] `_should_reset_executor_session()` returns True on the first post-resume turn.
- [ ] `_should_reset_executor_session()` returns True every N turns when
  `MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY=N` (N>0); False when unset/0.
- [ ] `run()` passes the computed `reset_session` bool as the 3rd arg to `executor_fn`.
- [ ] `supervisor_session_reset` trace event emitted when a reset is signaled.
- [ ] Resume `_executor_fn` in `mcp_server.py` calls `drop_coder(mcp_session_id)` only when
  `reset_session and mcp_session_id`.
- [ ] All `executor_fn` definitions/lambdas in `mcp_server.py` accept the 3-arg shape.
- [ ] Existing pause-side `drop_coder` call retained.
- [ ] No Aider APIs introduced into `core/engine/supervisor_agent.py`.
- [ ] All existing tests pass: `pytest -q tests/test_supervisor_state_p12_001.py
  tests/test_supervisor_agent_p12_001.py tests/test_delegate_tool.py
  tests/test_supervisor_tool_runner_p12_003.py`.

## New tests (`tests/test_supervisor_session_reset_bl545.py`)

Add at least **6 tests**:

1. `test_executor_fn_receives_reset_false_on_normal_first_turn` — fresh agent (not resumed),
   `MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY` unset; capture the 3rd arg passed to a spy
   `executor_fn` → False on turn 1.
2. `test_resumed_first_turn_signals_reset_true` — build agent via `resume()`, run the loop
   with a spy executor_fn; assert the first dispatched turn receives `reset_session=True`.
3. `test_resumed_reset_flag_cleared_after_first_turn` — resumed agent with `max_turns`
   allowing 2 turns; assert turn 1 gets True, turn 2 gets False (from resume rule).
4. `test_interval_reset_every_n` — set `MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY=2`,
   `max_turns=4`, non-resumed; assert reset True on turns 3 (and any turn where
   `(turn-1) % 2 == 0`), False otherwise — match the exact rule in the spec.
5. `test_supervisor_session_reset_event_emitted` — capture events via `event_sink`; assert
   a `supervisor_session_reset` event with correct `turn_index` and `reason`.
6. `test_resume_executor_fn_drops_coder_only_when_hinted` — unit-test the `mcp_server`
   resume `_executor_fn` (or a small extracted helper): with `reset_session=True` and a
   non-empty `mcp_session_id`, `drop_coder` is called; with `reset_session=False` it is not.
   (Patch `core.session.executor_cache.drop_coder` and `engine.run`.)

---

## § Results

**Date completed:** 2026-06-21
**Tests:**
- `pytest -q tests/test_supervisor_session_reset_bl545.py`
- `pytest -q tests/test_supervisor_state_p12_001.py tests/test_supervisor_agent_p12_001.py tests/test_delegate_tool.py tests/test_supervisor_tool_runner_p12_003.py`

**Notes / blockers:**
- Implemented BL-545 v1 control-plane only: Supervisor now computes `reset_session` intent (resume-first-turn + optional env-gated interval), emits `supervisor_session_reset`, and passes the bool through `ExecutorFn`.
- Resume executor closure in `server/mcp_server.py` now honors `reset_session` by calling `drop_coder(mcp_session_id)` only when hinted; existing pause-side escalated `drop_coder` remains intact.
- Added `tests/test_supervisor_session_reset_bl545.py` with all 6 acceptance tests; all required regression suites pass.
