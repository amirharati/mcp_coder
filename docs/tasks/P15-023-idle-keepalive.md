# P15-023 — Server-level idle keepalive

**Phase:** 15 · **Status:** pending  
**Issue:** [P15-ISS-023](../PHASE15_ISSUES.md)  
**Severity:** high (reliability)

---

## Goal

Keep the MCP stdio connection alive **between tool calls** so Cursor never
sees the server as disconnected during normal session idle time.

P15-016 fixed in-delegation timeouts (the `_DelegationProgressBridge`
heartbeat runs only while `delegate_to_agent` is executing). Epic 4
confirmed the gap: after 4a v1 completed, the server was fully idle, the
pipe went silent, Cursor dropped the connection, and `Not connected`
remained for the rest of the session.

This task adds a **server-level idle keepalive**: a background asyncio
task that periodically sends an MCP `notifications/message` to the client
regardless of whether a delegation is running.

---

## Background: why this is non-trivial

The `ctx: Context` object in each FastMCP tool handler is only valid inside
a request — `ctx.info()` can only be called from within a tool handler.  
The background keepalive task needs to send notifications **outside** of any
handler.

The MCP SDK's `ServerSession.send_log_message()` is the correct primitive
(it sends a `notifications/message` JSON-RPC notification). The session
object is **per-connection** (not per-request), so a reference captured
during any tool handler stays valid between requests for the entire
connection lifetime.

FastMCP 1.x (mcp==1.27.2, installed in `.venv`) supports a `lifespan`
parameter on `FastMCP(...)`:

```python
FastMCP.__init__(..., lifespan: Callable[[FastMCP], AbstractAsyncContextManager] | None = None, ...)
```

This is the standard ASGI lifespan pattern. The lifespan async-context-
manager wraps the entire connection, so we can start a background asyncio
task there. The task runs for the full connection lifetime — idle between
requests, active during requests, until the server exits.

The only missing piece: the lifespan's startup phase runs **before** the
`ServerSession` is created. We need a way to hand the session to the
background task once it's available. The cleanest mechanism is to capture
it by monkey-patching `mcp._mcp_server._handle_message` after `FastMCP` is
instantiated (before `mcp.run()`), since `_handle_message` receives the
`session` on every inbound message.

---

## Scope

**Single file:** `server/mcp_server.py`  
**Support files:** `.env.example`, `docs/guide/env-vars.md` (add env var)  
**New tests:** `tests/test_p15_023_idle_keepalive.py`  
**Must not touch:** other source files, docs, task specs

---

## Implementation

### Step 1 — env helper

Add near the existing `_progress_heartbeat_seconds()` function (line ~176):

```python
def _idle_keepalive_seconds() -> float:
    """Seconds between idle keepalive notifications when server is between tool calls.

    Default 25s (just under a typical 30s idle timeout).
    Set to 0 to disable.
    """
    raw = os.environ.get("MCP_CODER_IDLE_KEEPALIVE_S", "25").strip()
    try:
        v = float(raw)
        return max(0.0, v)
    except ValueError:
        return 25.0
```

### Step 2 — module-level session holder

Add two module-level variables near the top of `mcp_server.py` (after
imports, before `mcp = FastMCP(...)`):

```python
# P15-023: session reference captured by _install_session_tracker().
# Per-connection, valid for entire connection lifetime.
_idle_session: "Any | None" = None          # holds a ServerSession
_idle_last_activity: float = 0.0            # time.monotonic() of last message
```

(`Any` to avoid importing `ServerSession` at the top level; it's private
to the MCP SDK and the type is only used for `send_log_message` calls.)

### Step 3 — lifespan context manager

Add before `mcp = FastMCP(...)`:

```python
@asynccontextmanager
async def _idle_keepalive_lifespan(server: Any) -> AsyncGenerator[None, None]:
    """FastMCP lifespan: background keepalive task for the idle MCP pipe.

    Sends a periodic ``notifications/message`` so Cursor never considers
    the stdio connection idle and closes it. Fires only when the server
    has been silent for ``_idle_keepalive_seconds()`` seconds.
    """
    import anyio

    interval = _idle_keepalive_seconds()

    async def _keepalive() -> None:
        global _idle_last_activity
        if interval <= 0:
            return
        check_every = min(interval / 2, 5.0)  # poll at half-interval, max 5s
        while True:
            await anyio.sleep(check_every)
            session = _idle_session
            if session is None:
                continue
            since = time.monotonic() - _idle_last_activity
            if since < interval:
                continue
            try:
                await session.send_log_message(
                    level="info",
                    data="⏳ mcp-coder idle keepalive",
                )
                _idle_last_activity = time.monotonic()
            except Exception:
                pass  # broken pipe → server will exit on its own

    async with anyio.create_task_group() as tg:
        tg.start_soon(_keepalive)
        yield
        tg.cancel_scope.cancel()
```

Required import additions at the top of `mcp_server.py`:
```python
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any  # Any probably already imported
```

### Step 4 — session tracker installer

Add after `mcp = FastMCP(...)` (not inside the lifespan — we need access to
`mcp._mcp_server`):

```python
def _install_session_tracker() -> None:
    """P15-023: monkey-patch _handle_message to capture the session reference.

    FastMCP's lifespan starts *before* the ServerSession is created, so we
    cannot access the session during lifespan startup. Instead we wrap
    _handle_message (called on every inbound message with the session object)
    to stash a reference in the module-level ``_idle_session`` variable.

    The session is per-connection (not per-request), so storing it once on
    the first message is sufficient for the connection lifetime.

    The existing bound method is preserved and called normally — this wrapper
    only adds the session capture and activity timestamp update.
    """
    global _idle_session, _idle_last_activity

    _orig = mcp._mcp_server._handle_message  # bound method — includes self

    async def _tracking_handle_message(
        message: Any,
        session: Any,
        lifespan_context: Any,
        raise_exceptions: bool = False,
    ) -> None:
        global _idle_session, _idle_last_activity
        _idle_session = session
        _idle_last_activity = time.monotonic()
        await _orig(message, session, lifespan_context, raise_exceptions)

    mcp._mcp_server._handle_message = _tracking_handle_message


_install_session_tracker()
```

### Step 5 — wire lifespan to FastMCP

Change the `mcp = FastMCP(...)` call (around line 727) to pass `lifespan`:

```python
mcp = FastMCP(
    "mcp-coder",
    instructions=(
        "Implementation delegate for this repo. Use delegate_to_agent when the user "
        "wants code written or changed on disk—especially HTML/CSS/JS, multi-file "
        "work, or refactors. Do not use for chat-only answers. Requires context_summary."
    ),
    lifespan=_idle_keepalive_lifespan,
)
```

### Step 6 — document env var

In `.env.example` (near `MCP_CODER_PROGRESS_HEARTBEAT_S`):

```bash
# Seconds between server-level idle keepalive notifications (between tool calls).
# Prevents Cursor from closing the stdio pipe during session idle time.
# Default: 25. Set to 0 to disable.
# MCP_CODER_IDLE_KEEPALIVE_S=25
```

In `docs/guide/env-vars.md` (same section):

```markdown
| `MCP_CODER_IDLE_KEEPALIVE_S` | `25` | Seconds between idle keepalive notifications sent when the server is idle between tool calls. Prevents B011-class disconnects during session idle time. Set to `0` to disable. |
```

---

## What to verify before marking done

- [ ] **D1** — keepalive fires: mock session; advance time past `interval`; assert `send_log_message` called with `level="info"` and data containing `"keepalive"`.
- [ ] **D2** — keepalive silent when active: mock session; call tracking hook (simulating tool call activity) every 20s with `interval=25`; assert `send_log_message` NOT called.
- [ ] **D3** — keepalive disabled: `MCP_CODER_IDLE_KEEPALIVE_S=0`; assert task exits immediately (or never sends).
- [ ] **D4** — session capture: call `_tracking_handle_message` with a mock session; assert `_idle_session` is set and `_idle_last_activity` is updated.
- [ ] **D5** — `_idle_keepalive_seconds()` env reading: valid float, invalid string → 25.0, zero → 0.0.
- [ ] **D6** — no regression: existing `_progress_heartbeat_seconds()` and `_DelegationProgressBridge` unchanged; the two keepalives are orthogonal (idle keepalive = between calls; delegation heartbeat = during `delegate_to_agent`).

Run targeted tests:
```bash
pytest tests/test_p15_023_idle_keepalive.py -v
```

Run full suite:
```bash
pytest tests/ -x -q
```

Expected: new tests pass; no new failures in full suite (pre-existing B009
`legacy_contract` failures are expected).

Check linter:
```bash
ruff check server/mcp_server.py
```

---

## Files policy

| File | Action |
|------|--------|
| `server/mcp_server.py` | **edit** — add lifespan, session tracker, env helper |
| `.env.example` | **edit** — document `MCP_CODER_IDLE_KEEPALIVE_S` |
| `docs/guide/env-vars.md` | **edit** — add env var row |
| `tests/test_p15_023_idle_keepalive.py` | **create** — unit tests D1–D6 |
| Everything else | **do not touch** |

---

## Key invariants (do not break)

1. `_DelegationProgressBridge._drain_worker` (P15-016) is NOT removed or
   modified. The two mechanisms are complementary: idle keepalive fires
   between calls; delegation heartbeat fires during active `delegate_to_agent`.
2. The monkey-patch must call `_orig(message, session, lifespan_context,
   raise_exceptions)` — the original bound method (which includes `self`) — to
   avoid breaking the server's message dispatch.
3. The background task must swallow `Exception` on `send_log_message` — a
   broken pipe here means the server will exit naturally on the next read; the
   keepalive task must not itself crash the server.
4. The lifespan must cancel the task group on exit (`tg.cancel_scope.cancel()`
   inside the `yield`) so the server shuts down cleanly.

---

## § Results

*(Fill in when done)*

- [ ] D1–D6 checkboxes above ticked
- [ ] Full suite: `N passed, M pre-existing failures, 0 new failures`
- [ ] Linter: clean on `server/mcp_server.py`
- [ ] Summary of changes made (any deviations from spec + why)
- [ ] Suggested for master session: (bullets only — do not edit other docs)
