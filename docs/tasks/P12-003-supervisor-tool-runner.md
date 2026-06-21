# Worker spec: P12-003 — SupervisorToolRunner (two-tier context + tool-calling loop)

**Task ID:** P12-003  
**Issue:** [PHASE12_ISSUES.md](../PHASE12_ISSUES.md)  
**PM doc:** [PHASE12_MVP.md](../PHASE12_MVP.md) § P12-003  
**Depends on:** P12-001, P12-002, P12-ISS-001, P12-ISS-002 — all must be committed first

> **Worker**: implement only what this spec defines. Report in § Results when done.  
> Do not edit PM docs, BACKLOG, PHASES, IDEA, or sibling task specs.

---

## Files policy

### May edit
- `core/observability/gateway.py` — add `tools` param to `LlmGateway.complete()` and `tool_calls` field to `GatewayCompletion`
- `core/engine/supervisor_agent.py` — wire `SupervisorToolRunner` into `_llm_decide()` and the tier-1 context assembly
- `core/engine/supervisor.py` — wire `SupervisorToolRunner` into `DelegationSupervisor.evaluate()`

### Must create
- `core/engine/supervisor_tool_runner.py` — new module; `SupervisorToolRunner` class + Phase 12 built-in tools

### May edit (tests)
- `tests/` — new test file `tests/test_supervisor_tool_runner_p12_003.py`

### Must not touch
- `core/engine/aider_engine.py` — no Aider API changes
- `core/context/` — context compiler untouched
- `core/specs/` — not in scope
- `core/engine/owned_helper_llm.py` — not changed (SupervisorToolRunner calls gw.complete() directly, per D-P12-8)
- `server/mcp_server.py` — no changes needed; tool-calling is fully internal to supervisor
- `docs/` except `§ Results` in this file

---

## Goal

Replace the Supervisor's single-call LLM model with a **tool-calling loop**: the Supervisor
LLM is given a compact base context (tier 1) and a set of tools (tier 2) it can call on
demand before issuing its final decision. This makes the Supervisor aware of the project's
full history without loading everything upfront — it queries only what it needs, when it
needs it.

This applies to two decision paths:
1. **`SupervisorAgent._llm_decide()`** — inter-turn decisions (done/rerun/escalate)
2. **`DelegationSupervisor.evaluate()`** — `confirm_ask` intercept decisions

Both currently call `run_owned_helper_completion()` with a single flat prompt. After this
spec they both use `SupervisorToolRunner.run()`, which handles the tool-calling loop and
falls back to a single LLM call when tool-calling is unsupported by the model.

Design authority: [supervisor-orchestration-layer.md § D-ARCH-11](../notes/supervisor-orchestration-layer.md)
+ `PHASE12_MVP.md` § D-P12-7, D-P12-8.

---

## Background: what changes

### Current flow (both decision paths)
```
build prompt (flat, all context inline)
    ↓
run_owned_helper_completion([{user: prompt}])
    ↓
parse text response → decision
```

### Target flow
```
build tier-1 prompt (compact: turn summary, plan tail, decision log tail)
    ↓
SupervisorToolRunner.run(system=tier1_prompt, messages=[...])
    ↓
  loop (max 3 rounds):
    gw.complete(messages, tools=registered_tools)
    if response has tool_calls:
        execute tool(s) → append result as "tool" message
        emit supervisor_tool_call trace event
    else:
        return final text → parse decision
```

---

## Scope

### 1. `core/observability/gateway.py` — add `tools` param (D-P12-8)

Extend `LlmGateway.complete()` and `NullLlmGateway.complete()` to accept an optional
`tools` param. Pass it through to `litellm.completion` when non-None. `drop_params=True`
already handles models that don't support function-calling — they simply ignore it.

Extract tool call responses alongside the text response.

```python
@dataclass
class GatewayCompletion:
    text: str
    model: str
    tokens: dict[str, Any]
    duration_ms: int
    reasoning_text: str | None = None
    error: str | None = None
    tool_calls: list[dict] | None = None   # ← add this field
```

Updated `complete()` signature (only the new param shown):

```python
def complete(
    self,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 4096,
    role: str,
    tools: list[dict] | None = None,       # ← add this param
) -> GatewayCompletion:
```

Implementation notes:
- When `tools` is not None, add `"tools": tools` to `completion_kwargs`.
- After `litellm.completion`, extract `tool_calls` from the first choice's `message`:
  ```python
  raw_tool_calls = getattr(message, "tool_calls", None) or []
  tool_calls_out = [
      {
          "id": tc.id,
          "name": tc.function.name,
          "arguments": tc.function.arguments,  # JSON string
      }
      for tc in raw_tool_calls
      if hasattr(tc, "function")
  ] or None
  ```
- Populate `GatewayCompletion.tool_calls = tool_calls_out`.
- `NullLlmGateway.complete()`: same signature, `tool_calls=None` in the returned
  `GatewayCompletion`.
- All existing callers pass `tools=None` (default) — fully backward compatible.

---

### 2. `core/engine/supervisor_tool_runner.py` — new module

#### 2a. `SupervisorToolRunner` class

```python
class SupervisorToolRunner:
    """Tool-calling loop for Supervisor LLM decisions.

    Wraps gw.complete() with a tool registry. On each iteration:
    - If the model returns tool_calls: execute tools, append results, loop.
    - If no tool_calls: return the text response as the final answer.
    - After max_tool_rounds with no final text: return the last non-empty text.

    SupervisorToolRunner calls gw.complete() directly (not run_owned_helper_completion).
    """

    def __init__(
        self,
        *,
        model: str,
        workspace_path: str,
        event_sink: Callable[[dict], None] | None = None,
        max_tool_rounds: int = 3,
    ) -> None: ...

    def register_tool(
        self,
        name: str,
        description: str,
        schema: dict,            # JSON Schema for the parameters
        fn: Callable[..., str],  # called with parsed kwargs; returns str result
    ) -> None: ...

    def run(
        self,
        system_prompt: str,
        messages: list[dict],    # existing conversation messages (user/assistant)
    ) -> str:
        """Run the tool-calling loop. Returns the Supervisor's final text response."""
```

#### 2b. Tool-calling loop implementation

```python
def run(self, system_prompt: str, messages: list[dict]) -> str:
    gw = get_llm_gateway()
    all_messages = [{"role": "system", "content": system_prompt}] + list(messages)
    tools_spec = self._build_tools_spec()   # OpenAI function-call format

    for _round in range(self._max_tool_rounds):
        completion = gw.complete(
            model=self._model,
            messages=all_messages,
            role=ROLE_SUPERVISOR,
            tools=tools_spec if tools_spec else None,
        )
        if completion.error:
            return ""

        if not completion.tool_calls:
            # Final answer — no tool calls requested
            return completion.text

        # Execute each requested tool and append result
        for tc in completion.tool_calls:
            result_text = self._execute_tool(tc)
            self._emit_tool_call_event(tc, result_text, completion)
            all_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_text,
            })
        # Append the assistant's tool-call message before the next round
        all_messages.append({
            "role": "assistant",
            "content": completion.text or "",
            "tool_calls": completion.tool_calls,
        })

    # max_tool_rounds reached — do one final call without tools
    completion = gw.complete(
        model=self._model,
        messages=all_messages,
        role=ROLE_SUPERVISOR,
        tools=None,
    )
    return completion.text
```

#### 2c. Tool execution

```python
def _execute_tool(self, tc: dict) -> str:
    """Parse tool call, execute fn, return result string (truncated to budget)."""
    name = tc.get("name", "")
    entry = self._tools.get(name)
    if entry is None:
        return f"[tool_error] unknown tool: {name}"
    try:
        import json
        kwargs = json.loads(tc.get("arguments") or "{}")
        result = entry["fn"](**kwargs)
        return str(result)[:_TOOL_RESULT_BUDGET]
    except Exception as exc:
        return f"[tool_error] {name}: {exc}"
```

`_TOOL_RESULT_BUDGET = 2000` — per-tool token budget (chars). Configurable via module
constant, not env var, for Phase 12.

#### 2d. Trace event

```python
def _emit_tool_call_event(self, tc: dict, result: str, completion: GatewayCompletion) -> None:
    if self._event_sink is None:
        return
    self._event_sink({
        "type": "supervisor_tool_call",
        "tool": tc.get("name"),
        "args_summary": str(tc.get("arguments") or "")[:200],
        "result_chars": len(result),
        "result_preview": result[:120],
        "model": completion.model,
        "duration_ms": completion.duration_ms,
    })
```

#### 2e. Single-call fallback

When `tools_spec` is empty (no tools registered) or the model doesn't support tool-calling
(`completion.tool_calls is None` after round 0 with tools passed), the loop naturally
returns on the first iteration — `tool_calls` is None → return `completion.text`. No
special fallback branch needed.

---

### 3. Phase 12 built-in tools (register in `supervisor_tool_runner.py`)

Register these three tools via a module-level factory function
`build_phase12_tool_runner(workspace_path, project_key, project_state, event_sink, model)`:

#### Tool 1: `get_project_state`

```
description: "Get the current project state: decisions, open risks, hot areas, 
              last delegation. Use when deciding if this task conflicts with a prior 
              decision or touches a risky area."
parameters: {}   (no params)
```

Implementation: serialize `project_state` (the `ProjectState` already loaded by the
`SupervisorAgent` singleton) to compact JSON, truncated to `_TOOL_RESULT_BUDGET` chars.

```python
def _get_project_state_fn(project_state) -> str:
    import json
    d = {
        "decisions": project_state.decisions[-10:],   # last 10
        "open_risks": project_state.open_risks[-10:],
        "hot_areas": project_state.hot_areas[:20],
        "last_delegation": project_state.last_delegation,
    }
    return json.dumps(d, ensure_ascii=False)[:_TOOL_RESULT_BUDGET]
```

#### Tool 2: `get_delegation_history`

```
description: "Get a summary of recent delegations for this project. Use when you 
              need to know what was implemented in previous tasks, what failed, or 
              what files were changed recently."
parameters:
  limit: {type: integer, description: "Max delegations to return (1-10)", default: 5}
```

Implementation: call `list_delegations(workspace, limit=limit, spec_path=None)` filtered
to the current `project_key` prefix (first two path segments). Return a compact summary
per delegation: `{id, spec_path, outcome, files_changed[:5], task_preview}`.

```python
from core.workspace.history_query import list_delegations

def _get_delegation_history_fn(workspace_path, project_key, limit=5) -> str:
    import json
    limit = max(1, min(10, int(limit)))
    rows = list_delegations(workspace_path, limit=limit * 3)   # over-fetch, filter
    # filter to same project_key prefix
    prefix = project_key.split("/")[0] if project_key else ""
    filtered = [
        r for r in rows
        if not prefix or (r.get("spec_path") or "").startswith(prefix)
    ][:limit]
    summaries = []
    for r in filtered:
        summaries.append({
            "id": str(r.get("delegation_id") or "")[:8],
            "spec_path": r.get("spec_path"),
            "outcome": r.get("outcome"),
            "files_changed": (r.get("files_changed") or [])[:5],
            "task": str(r.get("task") or "")[:120],
        })
    return json.dumps(summaries, ensure_ascii=False)[:_TOOL_RESULT_BUDGET]
```

#### Tool 3: `read_file`

```
description: "Read the contents of a file in the workspace. Use when you need to 
              understand what a specific file currently contains before deciding 
              whether to rerun or escalate."
parameters:
  path: {type: string, description: "Relative path within workspace"}
```

Implementation: read `workspace_path / path`, return first `_TOOL_RESULT_BUDGET` chars.
Reject `..` traversal (return `[tool_error] path traversal not allowed`). Return
`[tool_error] file not found` if missing.

---

### 4. Wire into `SupervisorAgent._llm_decide()`

Replace the `run_owned_helper_completion` call with `SupervisorToolRunner.run()`.

```python
def _llm_decide(self, ctx: SupervisorTurnContext) -> SupervisorTurnDecision:
    from core.engine.supervisor_tool_runner import build_phase12_tool_runner
    ...
    runner = build_phase12_tool_runner(
        workspace_path=self._workspace_path,
        project_key=ProjectKeyResolver.from_spec_path(self._spec_path),
        project_state=self._project_state,
        event_sink=self._event_sink,
        model=model,
    )
    prompt = self._build_decision_prompt(ctx)   # existing method — unchanged
    text = runner.run(
        system_prompt=_DECISION_PREAMBLE,       # existing constant — unchanged
        messages=[{"role": "user", "content": prompt}],
    )
    ...
    # parse action + reason from text — same as before
```

No changes to `_build_decision_prompt()` or `_DECISION_PREAMBLE`. The tier-1 context
is exactly what the existing prompt already assembles (turn summary, plan tail, decision
log tail, files, checks). The tool-calling loop provides tier-2 on demand.

---

### 5. Wire into `DelegationSupervisor.evaluate()`

Same pattern: replace `run_owned_helper_completion` with `SupervisorToolRunner.run()`.

```python
def evaluate(self, *, question: str, risk_tier: str) -> SupervisorDecision:
    from core.engine.supervisor_tool_runner import build_phase12_tool_runner
    ...
    runner = build_phase12_tool_runner(
        workspace_path=self._workspace_path,
        project_key=...,        # derive from spec_contract path if available, else "default"
        project_state=...,      # load ProjectState lazily on first evaluate() call
        event_sink=None,        # DelegationSupervisor has no event sink yet
        model=model,
    )
    prompt = build_supervisor_prompt(...)   # existing — unchanged
    text = runner.run(
        system_prompt="",
        messages=[{"role": "user", "content": prompt}],
    )
    ...
```

`DelegationSupervisor` does not have `_project_state` today. For Phase 12, load it lazily
in `evaluate()` using the `spec_contract` path to derive the project key (or `"default"` if
`spec_contract` is None). Cache it on `self._project_state` (add this field to `__init__`).

---

## Config env vars

No new env vars required for Phase 12. `_TOOL_RESULT_BUDGET` and `max_tool_rounds=3` are
module-level constants. Phase 13 can make them configurable.

---

## Trace events

### `supervisor_tool_call`
Emitted by `SupervisorToolRunner._emit_tool_call_event()` for each tool invocation:

```json
{
    "type": "supervisor_tool_call",
    "tool": "get_project_state",
    "args_summary": "{}",
    "result_chars": 312,
    "result_preview": "{\"decisions\": [...",
    "model": "claude-3-7-sonnet-20250219",
    "duration_ms": 1240
}
```

---

## Acceptance checklist

- [ ] `GatewayCompletion.tool_calls: list[dict] | None = None` field added.
- [ ] `LlmGateway.complete()` accepts `tools: list | None = None`; passes to litellm when
  not None; populates `tool_calls` in the response.
- [ ] `NullLlmGateway.complete()` updated with same signature; returns `tool_calls=None`.
- [ ] `SupervisorToolRunner` created in `core/engine/supervisor_tool_runner.py`.
- [ ] `register_tool()` registers name + description + schema + callable.
- [ ] `run()` executes tool-calling loop (max 3 rounds); final round without tools.
- [ ] `_TOOL_RESULT_BUDGET = 2000` cap applied per tool result.
- [ ] `supervisor_tool_call` trace event emitted for each tool execution.
- [ ] Three Phase 12 tools registered via `build_phase12_tool_runner()`:
  `get_project_state`, `get_delegation_history`, `read_file`.
- [ ] `read_file` rejects `..` path traversal.
- [ ] `get_delegation_history` filters by project_key prefix; `limit` clamped to 1-10.
- [ ] `SupervisorAgent._llm_decide()` uses `SupervisorToolRunner`; existing fallback to
  `_policy_decide()` on error preserved.
- [ ] `DelegationSupervisor.evaluate()` uses `SupervisorToolRunner`; loads `_project_state`
  lazily; existing fallback on error preserved.
- [ ] All existing tests pass: `pytest -q tests/test_supervisor_state_p12_001.py
  tests/test_supervisor_agent_p12_001.py tests/test_project_state_p12_002.py
  tests/test_delegate_tool.py`.

## New tests (`tests/test_supervisor_tool_runner_p12_003.py`)

Add at least **8 tests**:

1. `test_runner_no_tools_returns_text` — runner with no registered tools, model returns
   plain text → `run()` returns that text.
2. `test_runner_tool_called_and_appended` — mock `gw.complete()` to return a tool call on
   round 0, then plain text on round 1 → tool fn called, result appended, final text
   returned.
3. `test_runner_max_rounds_fallback` — mock `gw.complete()` to always return a tool call;
   after `max_tool_rounds`, final call without tools returns text.
4. `test_tool_result_truncated_to_budget` — tool fn returns a very long string;
   `_execute_tool` truncates to `_TOOL_RESULT_BUDGET`.
5. `test_unknown_tool_returns_error` — model requests a tool not in registry; result
   contains `[tool_error] unknown tool`.
6. `test_read_file_traversal_rejected` — `read_file` tool with `path="../secret"` returns
   `[tool_error] path traversal`.
7. `test_get_project_state_returns_compact_json` — `get_project_state` called with a
   `ProjectState` that has 3 decisions; result is valid JSON with `decisions` key.
8. `test_supervisor_tool_call_event_emitted` — verify `supervisor_tool_call` event is
   passed to `event_sink` on each tool execution.

---

## § Results

**Date completed:** 2026-06-21

**What was implemented:**

1. **`core/observability/gateway.py`**
   - Added `tool_calls: list[dict] | None = None` field to `GatewayCompletion`.
   - Added `tools: list[dict] | None = None` param to both `LlmGateway.complete()` and
     `NullLlmGateway.complete()`. When non-None, `"tools"` is added to `completion_kwargs`
     (after `params.extra_params.update`, so `drop_params=True` still handles models that
     don't support function-calling).
   - Added module-level `_extract_tool_calls()` helper that pulls `id`/`name`/`arguments`
     from the first choice's `message.tool_calls` (handles both attr- and dict-style
     messages); result populated into `GatewayCompletion.tool_calls`. `NullLlmGateway`
     returns `tool_calls=None`. All existing callers default to `tools=None` → fully
     backward compatible.

2. **`core/engine/supervisor_tool_runner.py`** (new)
   - `SupervisorToolRunner` with `register_tool()`, `run()` (max 3 rounds, appends the
     assistant tool-call message then each `tool` result message; on the final round does
     one no-tools `gw.complete()` call), `_execute_tool()` (`_TOOL_RESULT_BUDGET=2000` char
     cap, `[tool_error]` on unknown tool / exceptions), `_build_tools_spec()`
     (OpenAI function-call format), and `_emit_tool_call_event()` emitting
     `supervisor_tool_call`. Returns `""` on `completion.error`. No-tools / unsupported-model
     cases return on round 0 naturally (no special fallback branch).
   - `build_phase12_tool_runner(...)` factory registering `get_project_state` (compact JSON
     of last decisions/risks/hot areas/last_delegation), `get_delegation_history`
     (`list_delegations` over-fetched and filtered by `project_key` prefix, `limit` clamped
     1–10), and `read_file` (rejects `..` traversal, `[tool_error] file not found` if
     missing, truncated to budget).

3. **`core/engine/supervisor_agent.py`** — `_llm_decide()` now builds a Phase 12 runner via
   `build_phase12_tool_runner(...)` (project_key via `ProjectKeyResolver.from_spec_path`,
   passing the already-loaded `self._project_state` and `self._event_sink`) and calls
   `.run(system_prompt=_DECISION_PREAMBLE, messages=[{user: prompt}])`. `_build_decision_prompt`
   and `_DECISION_PREAMBLE` unchanged. Existing `_policy_decide()` fallback preserved on any
   exception, on unparseable action, and on provider config hint.

4. **`core/engine/supervisor.py`** — `DelegationSupervisor` gained `self._project_state`
   (lazy, cached on first `evaluate()`). `evaluate()` derives `project_key` from
   `spec_contract` (else `"default"`), loads `ProjectState` once, builds the runner
   (`event_sink=None`), and calls `.run(system_prompt="", messages=[{user: prompt}])`.
   Errors raised during runner construction/run are caught and routed through the existing
   `_fallback_abort` path; empty/garbled text still flows through `parse_supervisor_output`
   → `_fallback_abort`. Removed now-unused `run_owned_helper_completion` import.

**Tests:**
- New `tests/test_supervisor_tool_runner_p12_003.py` — 8 tests (all checklist items),
  using a `_ScriptedGateway` stub registered via `set_llm_gateway`.
- Updated one pre-existing test (`tests/test_supervised_io_p11_002.py::
  test_supervisor_parse_and_fallback_abort`) to patch
  `core.engine.supervisor_tool_runner.build_phase12_tool_runner` instead of the removed
  `run_owned_helper_completion`.
- Required suite green: `pytest -q tests/test_supervisor_state_p12_001.py
  tests/test_supervisor_agent_p12_001.py tests/test_project_state_p12_002.py
  tests/test_delegate_tool.py tests/test_supervisor_tool_runner_p12_003.py` → **64 passed**.
- Broader sweep (`-k "supervisor or gateway or owned_helper or project_state or delegate"`)
  → **200 passed**.

**Notes / blockers:**
- `DelegationSupervisor` token accounting: `runner.run()` returns text only, so per-call
  token totals are no longer accumulated there (`SupervisorDecision.tokens={}`). This matches
  the spec's target flow; `_accumulate_tokens()` remains defined but unused.
- `read_file` traversal guard checks for a `..` path segment (not substring), so filenames
  containing `..` are not falsely rejected.

**Suggested for master session:**
- Phase 13 could thread tool-result token usage back through `SupervisorToolRunner` so
  `DelegationSupervisor.usage_record` regains accuracy under the tool-calling loop.
