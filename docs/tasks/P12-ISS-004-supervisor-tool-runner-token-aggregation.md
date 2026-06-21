# Worker spec: P12-ISS-004 — Aggregate SupervisorToolRunner token usage into decision records

**Task ID:** P12-ISS-004  
**Issue:** [PHASE12_ISSUES.md](../PHASE12_ISSUES.md) § P12-ISS-004  
**PM doc:** [PHASE12_MVP.md](../PHASE12_MVP.md)  
**Depends on:** P12-003 (SupervisorToolRunner), P12-004, P12-005 — all committed first

> **Worker**: implement only what this spec defines. Report in § Results when done.  
> Do not edit PM docs, BACKLOG, PHASES, IDEA, or sibling task specs.

---

## Files policy

### May edit
- `core/engine/supervisor_tool_runner.py`
- `core/engine/supervisor_agent.py`
- `core/engine/supervisor.py`
- `tests/test_supervisor_tool_runner_p12_003.py`

### May create
- `tests/test_supervisor_token_accounting_p12_iss_004.py`

### Must not touch
- `core/observability/gateway.py`
- `server/mcp_server.py`
- `core/state/*`
- `docs/` except `§ Results` in this file
- Any sibling `docs/tasks/*.md`

---

## Goal

`SupervisorToolRunner` can make multiple `gw.complete()` calls per decision (tool rounds +
final response), but callers currently store `tokens={}` in:
- `SupervisorTurnDecision` (`core/engine/supervisor_agent.py`)
- `SupervisorDecision` (`core/engine/supervisor.py`)

This causes supervisor decision records and `DelegationSupervisor.usage_record` to
under-report token usage.

After this fix:
- `SupervisorToolRunner` returns aggregated tokens + LLM duration for the entire loop.
- `_llm_decide()` and `evaluate()` write those tokens into decision records.
- `DelegationSupervisor._accumulate_tokens()` receives real values again.
- Existing behavior and fallbacks stay unchanged.

---

## Scope

### 1) `core/engine/supervisor_tool_runner.py` — add structured run result

Add a result dataclass:

```python
@dataclass
class SupervisorToolRunnerResult:
    text: str
    tokens: dict[str, Any]
    llm_duration_ms: int
    llm_calls: int
```

Add method:

```python
def run_with_metrics(self, system_prompt: str, messages: list[dict]) -> SupervisorToolRunnerResult:
    ...
```

Behavior:
- Execute the same loop as current `run()`.
- Aggregate token fields (`input`, `output`, `total`) across every `gw.complete()` call in
  this loop (tool rounds + final no-tools call when used).
- Aggregate `llm_duration_ms` as the sum of each completion's `duration_ms`.
- Count `llm_calls`.
- Preserve error behavior: if a completion errors, return `text=""` with aggregated metrics
  up to failure point (callers already fallback on empty/unparseable text).

Token merge helper:

```python
def _merge_tokens(acc: dict[str, Any], cur: dict[str, Any]) -> dict[str, Any]:
    # Sum numeric input/output/total; keep source="supervisor_tool_runner".
```

Keep backward compatibility:
- Keep existing `run(...) -> str`.
- Implement it as:
  ```python
  return self.run_with_metrics(system_prompt, messages).text
  ```

No changes to tool semantics, tool registry, or event payload shape.

---

### 2) `core/engine/supervisor_agent.py` — consume structured result

In `_llm_decide()`:
- Replace `text = runner.run(...)` with `tool_result = runner.run_with_metrics(...)`.
- Use `text = tool_result.text`.
- Set `tokens=tool_result.tokens` in returned `SupervisorTurnDecision` instead of `{}`.
- Keep existing `duration_ms` wall-clock measurement logic unchanged.

No changes to fallback paths.

---

### 3) `core/engine/supervisor.py` — consume structured result and restore usage totals

In `DelegationSupervisor.evaluate()`:
- Replace `text = runner.run(...)` with `tool_result = runner.run_with_metrics(...)`.
- Set `tokens=tool_result.tokens` in `SupervisorDecision`.
- Call `self._accumulate_tokens(tool_result.tokens)` after successful runner invocation
  and before returning parsed decision.

Keep existing `duration_ms` wall-clock timing and error fallback behavior unchanged.

---

## Tests

### Update `tests/test_supervisor_tool_runner_p12_003.py`

Add/adjust tests to cover metrics result without breaking existing tests:

1. `test_run_with_metrics_aggregates_tokens_across_rounds`
   - Mock `gw.complete()` for 2 calls:
     - call1: tool_call + tokens `{input:10, output:5, total:15}`
     - call2: final text + tokens `{input:4, output:6, total:10}`
   - Assert `run_with_metrics(...).tokens == {input:14, output:11, total:25, source:"supervisor_tool_runner"}`.
   - Assert `llm_calls == 2`.

2. `test_run_backcompat_returns_text_only`
   - Ensure `run(...)` still returns string and equals `run_with_metrics(...).text`.

### New file `tests/test_supervisor_token_accounting_p12_iss_004.py`

Add at least 3 tests:

1. `test_supervisor_agent_llm_decide_writes_runner_tokens`
   - Patch runner to return known tokens.
   - Assert `SupervisorTurnDecision.tokens` is non-empty and matches expected totals.

2. `test_delegation_supervisor_evaluate_writes_tokens`
   - Patch runner result.
   - Assert returned `SupervisorDecision.tokens` contains expected numeric totals.

3. `test_delegation_supervisor_usage_record_accumulates_runner_tokens`
   - Run `evaluate()` twice with known token bundles.
   - Assert `usage_record.input_tokens/output_tokens/total_tokens` are summed.

Run:

```bash
pytest -q tests/test_supervisor_tool_runner_p12_003.py tests/test_supervisor_token_accounting_p12_iss_004.py
```

---

## Acceptance checklist

- [ ] `SupervisorToolRunnerResult` dataclass added.
- [ ] `run_with_metrics()` implemented with token aggregation across loop calls.
- [ ] Existing `run()` preserved as backward-compatible text-only wrapper.
- [ ] `SupervisorTurnDecision.tokens` populated from runner metrics (not `{}`) in `_llm_decide()`.
- [ ] `SupervisorDecision.tokens` populated from runner metrics in `evaluate()`.
- [ ] `DelegationSupervisor._accumulate_tokens()` receives aggregated runner tokens.
- [ ] Existing behavior and fallback semantics unchanged.
- [ ] Target tests pass.

---

## § Results

**Date completed:** 2026-06-21

**Tests:** 13 passed — `tests/test_supervisor_tool_runner_p12_003.py` (10 tests, +2 new for P12-ISS-004) + `tests/test_supervisor_token_accounting_p12_iss_004.py` (3 new tests).

**Notes / blockers:**

- Added `SupervisorToolRunnerResult` dataclass and `_merge_tokens()` helper to `core/engine/supervisor_tool_runner.py`.
- Added `run_with_metrics()` that aggregates `input`/`output`/`total` tokens and `llm_duration_ms` across every `gw.complete()` call in the tool loop (including the final no-tools fallback call). `run()` preserved as a backward-compatible text-only wrapper (`return self.run_with_metrics(...).text`).
- `_llm_decide()` in `supervisor_agent.py` now uses `run_with_metrics()` and sets `SupervisorTurnDecision.tokens` from the runner result instead of `{}`.
- `evaluate()` in `supervisor.py` now uses `run_with_metrics()`, sets `SupervisorDecision.tokens`, and calls `self._accumulate_tokens(runner_tokens)` so `usage_record` correctly sums across multiple `evaluate()` calls.
- Patch targets in new tests: `core.config.providers.apply_provider_env` (not `supervisor_agent.*`) and `core.engine.supervisor_tool_runner.build_phase12_tool_runner` (source module), because those symbols are locally imported inside the function bodies.
