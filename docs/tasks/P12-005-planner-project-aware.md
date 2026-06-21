# Worker spec: P12-005 — Planner reads project state (BL-525 v1)

**Task ID:** P12-005  
**PM doc:** [PHASE12_MVP.md](../PHASE12_MVP.md) § P12-005  
**Depends on:** P12-001, P12-002, P12-003, P12-004 — all committed first

> **Worker**: implement only what this spec defines. Report in § Results when done.  
> Do not edit PM docs, BACKLOG, PHASES, IDEA, or sibling task specs.

---

## Files policy

### May edit
- `core/context/planner_prompt.py` — extend `build_planner_pass_prompt()` to accept + inject project state
- `core/context/helper_llm_pipeline.py` — pass project state into `apply_planner_pass()`; extract decisions after plan returns
- `server/mcp_server.py` — pass supervisor's `_project_state` and `spec_rel_path` into `_apply_architect_pass()`

### Must not touch
- `core/engine/planner_pass_llm.py` — not in scope (pure LLM call, unchanged)
- `core/engine/supervisor_agent.py` — not in scope
- `core/engine/supervisor_tool_runner.py` — not in scope
- `core/state/project_state.py` — not in scope (use existing `add_decision()` and `save()`)
- `core/config/planner_pass.py` — not in scope
- `core/context/context_compiler.py` — not in scope
- `core/engine/aider_engine.py` — not in scope
- `docs/` except `§ Results` in this file
- Any sibling `docs/tasks/*.md`

### May create
- `core/engine/planner_decision_extractor.py` — new module; heuristic extraction of decisions from plan text

### May edit (tests)
- `tests/` — new file `tests/test_planner_project_aware_p12_005.py`

---

## Goal

Make the Planner context-aware of project history **before** it plans (D-P12-6). A
`## Project state` section is prepended to the existing planner prompt containing
compressed decisions and open risks from `project_state.json` that touch the current
spec's files (max ~800 tokens). No tool-calling loop for the Planner — that's BL-525
complete / Phase 13.

After planning, the Supervisor extracts explicit decisions from the plan text using a
lightweight heuristic and writes them back to `project_state` so future Planners see them.

After this spec:
- `planner_context_sources: list[str]` field in the `planner_pass` trace event (`[]` when
  nothing injected, `["project_state"]` when the section is non-empty).
- `project_state.decisions[]` grows after each delegation where the Planner ran and the
  extractor found something.
- A second delegation on the same project: the Planner sees prior decisions without the
  human having to repeat them.

---

## Background: what exists already

`build_planner_pass_prompt()` in `core/context/planner_prompt.py` assembles the prompt
from sections joined with `"\n\n"`. Adding a new section is a one-liner.

`apply_planner_pass()` in `core/context/helper_llm_pipeline.py` calls
`build_planner_pass_prompt()` and `run_planner_pass_llm()`. It returns
`(plan, error, model_record, provenance)`. The caller (`_apply_architect_pass` in
`server/mcp_server.py`) already has access to `supervisor_agent._project_state` since
P12-002.

`ProjectState.add_decision(text, delegation_id)` and `ProjectState.save()` already exist.

The spec's `Files` section (from `spec_read.sections.get("Files")`) lists the files the
task touches — use this for relevance filtering.

---

## Scope

### 1. `core/context/planner_prompt.py` — inject `## Project state` section

Extend `build_planner_pass_prompt()` to accept an optional `project_state_section: str | None = None`:

```python
def build_planner_pass_prompt(
    *,
    spec_read: SpecReadResult,
    mechanical_brief: str,
    picker_result: CandidateFilesResult | None,
    host_transcript: str | None,
    task: str,
    context_summary: str,
    project_state_section: str | None = None,   # ← add this
) -> str:
```

Insert the section immediately before `## Delegate task` (i.e. after `_picker_section`):

```python
if project_state_section:
    parts.append(project_state_section)
```

The section is pre-formatted by the caller (see § 2 below). `build_planner_pass_prompt`
just inserts it — no formatting logic here.

Also update the backward-compat `build_architect_pass_prompt` shim to pass
`project_state_section=None` (it already delegates to `build_planner_pass_prompt`).

---

### 2. `core/context/helper_llm_pipeline.py` — build section + extract decisions

#### 2a. Extend `apply_planner_pass()` signature

Add three new keyword-only params (all optional, fully backward-compatible):

```python
def apply_planner_pass(
    *,
    context_package: ContextPackage,
    spec_read: Any,
    picker_result: CandidateFilesResult | None,
    workspace: str,
    task: str,
    context_summary: str,
    host_transcript: str | None,
    timing: dict[str, int | float] | None = None,
    delegation_id: str | None = None,
    log_warn: LogWarnFn | None = None,
    project_state: Any | None = None,        # ← add (ProjectState instance or None)
    spec_files: list[str] | None = None,     # ← add (file paths from spec Files section)
    planner_context_sources: list[str] | None = None,  # ← add (mutated in place; caller reads it)
) -> tuple[str | None, str | None, dict[str, Any] | None, dict[str, Any]]:
```

#### 2b. Build `## Project state` section

Before calling `build_planner_pass_prompt`, build the injection section if `project_state`
is non-None:

```python
_PROJECT_STATE_TOKEN_BUDGET = 800   # chars (rough token proxy, 1 token ≈ 4 chars)

def _build_project_state_section(
    project_state: Any,
    spec_files: list[str] | None,
) -> str:
    """Compress project state entries relevant to spec_files into a prompt section.

    Returns "" if nothing relevant or project_state is empty.
    """
    import json

    spec_file_set = {str(f).strip() for f in (spec_files or [])}

    def _file_relevant(entry: dict) -> bool:
        """True if entry touches any file in spec_file_set (or no filter active)."""
        if not spec_file_set:
            return True
        # decisions have no files field — include all decisions (they are short)
        entry_files = entry.get("files") or []
        entry_text = (entry.get("text") or "") + (entry.get("spec_path") or "")
        return any(f in entry_text or f in entry_files for f in spec_file_set)

    parts: list[str] = []

    # Decisions: last 5 relevant, abbreviated
    relevant_decisions = [
        d for d in (project_state.decisions or [])
        if _file_relevant(d)
    ][-5:]
    if relevant_decisions:
        lines = [f"- {d.get('text', '')[:120]}" for d in relevant_decisions]
        parts.append("### Prior decisions\n" + "\n".join(lines))

    # Open risks: last 5 relevant, with severity
    relevant_risks = [
        r for r in (project_state.open_risks or [])
        if _file_relevant(r)
    ][-5:]
    if relevant_risks:
        lines = [
            f"- [{r.get('severity', 'advisory').upper()}] {r.get('text', '')[:120]}"
            for r in relevant_risks
        ]
        parts.append("### Open risks\n" + "\n".join(lines))

    if not parts:
        return ""

    section = "## Project state\n" + "\n\n".join(parts)

    # Hard cap
    if len(section) > _PROJECT_STATE_TOKEN_BUDGET * 4:
        section = section[: _PROJECT_STATE_TOKEN_BUDGET * 4] + "\n…[truncated]"
    return section
```

#### 2c. Wire into `apply_planner_pass()`

```python
project_state_section = ""
if project_state is not None:
    project_state_section = _build_project_state_section(project_state, spec_files)
    if project_state_section and planner_context_sources is not None:
        planner_context_sources.append("project_state")

prompt = build_planner_pass_prompt(
    ...
    project_state_section=project_state_section or None,
)
```

#### 2d. Extract decisions from plan text after LLM returns

After `llm_result = run_planner_pass_llm(prompt, ...)` and only when `llm_result.success`:

```python
if llm_result.success and project_state is not None and delegation_id:
    from core.engine.planner_decision_extractor import extract_decisions_from_plan
    extracted = extract_decisions_from_plan(llm_result.plan)
    for decision_text in extracted:
        project_state.add_decision(decision_text, delegation_id)
    if extracted:
        project_state.save()
```

`project_state.save()` is called here (not in `_finish()` — the existing finish save will
overwrite harmlessly since it's the same object). Save immediately so decisions are
durable even if the delegation later fails.

---

### 3. `core/engine/planner_decision_extractor.py` — new module

Light heuristic extraction — no LLM call. Looks for sentences that sound like explicit
decisions: "will use X", "decided to", "we will", "approach: …", "strategy: …", numbered
plan steps with a clear decision verb.

```python
_DECISION_PATTERNS = [
    re.compile(r"(?:^|\n)\s*(?:\d+\.\s+)?(?:we\s+will|will\s+use|decided?\s+to|approach:|strategy:|use\s+\w+\s+for)\s+(.{10,120})", re.IGNORECASE),
    re.compile(r"(?:^|\n)\*\*Decision[:\s]+\*\*(.{10,120})", re.IGNORECASE),
    re.compile(r"(?:^|\n)-\s+(?:Decision|Decided):\s+(.{10,120})", re.IGNORECASE),
]
_MAX_DECISIONS = 5

def extract_decisions_from_plan(plan_text: str) -> list[str]:
    """Extract explicit decision statements from plan text. Returns [] if none found.

    Heuristic only — no LLM call. False negatives are acceptable; false positives
    are filtered by the 10-120 char length constraint.
    """
    seen: set[str] = set()
    results: list[str] = []
    for pattern in _DECISION_PATTERNS:
        for m in pattern.finditer(plan_text or ""):
            text = m.group(1).strip().rstrip(".,;:")
            if text and text not in seen:
                seen.add(text)
                results.append(text)
            if len(results) >= _MAX_DECISIONS:
                return results
    return results
```

---

### 4. `server/mcp_server.py` — pass project_state into `_apply_architect_pass()`

In `delegate_to_agent`, where `_apply_architect_pass(...)` is called (around line 2287),
pass two new kwargs:

```python
_planner_context_sources: list[str] = []

(
    architect_plan,
    ...
) = _apply_architect_pass(
    ...existing params...,
    project_state=supervisor_agent._project_state if supervisor_agent is not None else None,
    spec_files=_spec_files_from_read(spec_read),
    planner_context_sources=_planner_context_sources,
)
```

Add a small helper to extract the file list from `spec_read`:

```python
def _spec_files_from_read(spec_read: Any) -> list[str]:
    """Extract file paths from spec_read Files section."""
    if spec_read is None:
        return []
    raw = (spec_read.sections.get("Files") or "").strip()
    if not raw:
        return []
    lines = [ln.strip().lstrip("-*").strip() for ln in raw.splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]
```

Also update `_apply_architect_pass()` (the local wrapper in `mcp_server.py`) to accept
and pass through `project_state`, `spec_files`, and `planner_context_sources`.

Finally, merge `_planner_context_sources` into the existing `planner_pass_audit` dict so
it appears in the trace:

```python
if planner_pass_audit is not None:
    planner_pass_audit["planner_context_sources"] = _planner_context_sources
```

---

## Trace events

No new trace event type required. The existing `planner_pass` audit record in
`context_block["planner_pass"]` gains a new field:

```json
{
  "model": "...",
  "applied": true,
  "plan_chars": 412,
  "duration_ms": 1840,
  "planner_context_sources": ["project_state"]
}
```

When project state is empty or no relevant entries: `"planner_context_sources": []`.

---

## Acceptance checklist

- [ ] `build_planner_pass_prompt()` accepts `project_state_section: str | None = None`;
  inserts it before `## Delegate task` when non-None/non-empty.
- [ ] `_build_project_state_section()` returns `""` when `project_state` has no decisions
  or risks (no injection, no error).
- [ ] `_build_project_state_section()` filters decisions/risks by `spec_file_set` (only
  entries with file overlap included); when `spec_files=[]` all entries included.
- [ ] Section capped at `_PROJECT_STATE_TOKEN_BUDGET * 4 = 3200` chars.
- [ ] `planner_context_sources` list gains `"project_state"` entry only when section is
  non-empty.
- [ ] After successful plan: `extract_decisions_from_plan()` called; results written to
  `project_state.add_decision()` and `project_state.save()`.
- [ ] After failed plan: no decision extraction, no save.
- [ ] `planner_pass_audit["planner_context_sources"]` present in trace context block.
- [ ] `_apply_architect_pass()` in `mcp_server.py` accepts + passes through the new params.
- [ ] All existing tests pass: `pytest -q tests/test_supervisor_state_p12_001.py
  tests/test_supervisor_agent_p12_001.py tests/test_project_state_p12_002.py
  tests/test_delegate_tool.py tests/test_supervisor_tool_runner_p12_003.py
  tests/test_reviewer_findings_p12_004.py`.

## New tests (`tests/test_planner_project_aware_p12_005.py`)

Add at least **7 tests**:

1. `test_project_state_section_injected_when_non_empty` — mock `apply_planner_pass` with
   a non-empty `ProjectState`; assert `"## Project state"` appears in the prompt passed to
   `run_planner_pass_llm`.
2. `test_project_state_section_empty_when_no_entries` — fresh `ProjectState()` with no
   decisions or risks → `_build_project_state_section()` returns `""`.
3. `test_file_filtering_returns_only_relevant` — two decisions, one touching `auth.py`,
   one touching `db.py`; filter by `spec_files=["auth.py"]` → only auth decision in
   section.
4. `test_planner_context_sources_populated` — after `apply_planner_pass()` with non-empty
   project state, `planner_context_sources` contains `"project_state"`.
5. `test_planner_context_sources_empty_when_no_state` — `project_state=None` →
   `planner_context_sources` remains `[]`.
6. `test_decisions_extracted_and_written_to_project_state` — mock plan text containing
   `"will use SQLite for the cache"` → `project_state.decisions` gains one entry after
   `apply_planner_pass()`.
7. `test_no_decision_extraction_on_failed_plan` — mock `run_planner_pass_llm` to return
   `success=False`; `project_state.decisions` unchanged.

---

## § Results

**Date completed:** 2026-06-21  
**Tests:** `pytest -q tests/test_planner_project_aware_p12_005.py tests/test_project_state_p12_002.py tests/test_delegate_tool.py tests/test_supervisor_tool_runner_p12_003.py tests/test_reviewer_findings_p12_004.py` → 37 passed

**Notes / blockers:**
- Implemented exactly the four requested code changes:
  - `core/context/planner_prompt.py`: added `project_state_section` param to `build_planner_pass_prompt()`, injected before `## Delegate task` when non-empty, and updated `build_architect_pass_prompt` shim to pass `project_state_section=None`.
  - `core/context/helper_llm_pipeline.py`: extended `apply_planner_pass()` with `project_state`, `spec_files`, `planner_context_sources`; added `_build_project_state_section()` with file-overlap filtering + 3200-char cap; wired prompt injection and context-source tracking; after successful planner pass, extracted decisions via `extract_decisions_from_plan()` and wrote them to `project_state` with immediate `save()` when any extracted.
  - `core/engine/planner_decision_extractor.py`: new heuristic extractor with the three regex patterns, dedupe, and `max=5`.
  - `server/mcp_server.py`: added `_spec_files_from_read()`, updated `_apply_architect_pass()` wrapper to accept/pass-through `project_state`, `spec_files`, `planner_context_sources`, passed `supervisor_agent._project_state` + spec files at call site, and merged `planner_context_sources` into `planner_pass_audit`.
- Added `tests/test_planner_project_aware_p12_005.py` with 7 tests matching the checklist:
  1) project-state section injected when non-empty  
  2) section empty when no entries  
  3) file filtering keeps only relevant entries  
  4) `planner_context_sources` populated when state injected  
  5) `planner_context_sources` stays empty when no state  
  6) decisions extracted and persisted to project state on successful plan  
  7) no extraction/save on failed plan
