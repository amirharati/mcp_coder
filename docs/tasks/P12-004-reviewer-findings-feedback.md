# Worker spec: P12-004 — Reviewer findings feedback loop

**Task ID:** P12-004  
**PM doc:** [PHASE12_MVP.md](../PHASE12_MVP.md) § P12-004  
**Depends on:** P12-001, P12-002, P12-003 (P12-ISS-001, P12-ISS-002) — all committed first

> **Worker**: implement only what this spec defines. Report in § Results when done.  
> Do not edit PM docs, BACKLOG, PHASES, IDEA, or sibling task specs.

---

## Files policy

### May edit
- `core/state/project_state.py` — add `add_reviewer_finding()` method
- `server/mcp_server.py` — after reviewer_pass: classify findings + promote to project state
- `core/engine/supervisor_tool_runner.py` — register `get_reviewer_findings` tool in `build_phase12_tool_runner()`

### Must not touch
- `core/engine/supervisor_agent.py` — not in scope
- `core/engine/supervisor.py` — not in scope
- `core/observability/gateway.py` — not in scope
- `core/context/`, `core/specs/`, `core/engine/aider_engine.py` — not in scope
- `docs/` except `§ Results` in this file
- Any sibling `docs/tasks/*.md`

### May create
- `core/engine/reviewer_findings_classifier.py` — new module; cheap LLM classification call

### May edit (tests)
- `tests/` — new file `tests/test_reviewer_findings_p12_004.py`

---

## Goal

Close the Reviewer → Planner feedback loop. When `reviewer_pass` runs and returns
`outcome="issues"`, the findings in `reviewer_pass_note` are classified by severity and
promoted to `project_state`. Future delegations on the same project can retrieve these via
the `get_reviewer_findings` tool (already registered in P12-003's
`SupervisorToolRunner`).

After this spec:
- Critical and notable findings land in `project_state.open_risks` (durable, cross-delegation).
- All findings (including advisory) land in `project_state.reviewer_findings_summary`
  (full log, bounded to last 50 per project).
- The `get_reviewer_findings(files)` tool is registered in `build_phase12_tool_runner()`
  so the Supervisor can query findings by file.
- Two trace events emitted: `reviewer_findings_classified`, `project_state_risks_updated`.

---

## Background: what exists already

`project_state.py` already has:
- `open_risks: list[dict]` — with `add_risk(text, severity, source_delegation_id)` method
- `reviewer_findings_summary: list[dict]` — field exists, not yet written to
- `_RISK_SEVERITIES = {"advisory", "notable", "critical"}`

In `server/mcp_server.py`, after the reviewer_pass block (around line 2854+):
- `reviewer_pass_outcome` — `"lgtm"` | `"issues"` | `None`
- `reviewer_pass_note` — free-text summary of issues found (or `None`)
- `reviewer_pass_ran` — bool
- `supervisor_agent` — the singleton `SupervisorAgent` (holds `_project_state`)
- `delegation_id` — current delegation UUID
- `spec_rel_path` — current spec path (for file matching)

The supervisor agent's `_project_state` is the in-memory `ProjectState` for this project.
It is saved to disk at the end of the delegation in `supervisor_agent.finish()` —
**no additional save call needed here** (just mutate the in-memory object).

---

## Scope

### 1. `core/engine/reviewer_findings_classifier.py` — new module

Classify a reviewer findings note into per-finding `(text, severity)` pairs using a cheap
LLM call (or regex fallback when no LLM is available).

```python
from __future__ import annotations

_SEVERITIES = ("critical", "notable", "advisory")
_PROMOTE_THRESHOLD = "notable"   # notable + critical → open_risks

@dataclass
class ClassifiedFinding:
    text: str
    severity: str   # "advisory" | "notable" | "critical"

def classify_reviewer_findings(
    note: str,
    *,
    spec_contract: str | None = None,
    workspace_path: str,
    delegation_id: str,
) -> list[ClassifiedFinding]:
    """Split and classify reviewer findings note into (text, severity) pairs.

    Uses a cheap LLM call (ROLE_SUPERVISOR model, no tool-calling loop).
    Falls back to all-advisory if the LLM call fails or model is misconfigured.
    Returns [] if note is empty.
    """
```

**Prompt to LLM** (keep under 800 tokens):
```
You are reviewing a code-reviewer's findings note. Split it into individual findings
and classify each as: critical (broken interface, data loss risk, security hole),
notable (missing error handling, test gap, unclear contract), advisory (style, minor
refactor suggestion, non-blocking).

Respond ONLY with a JSON array, no prose:
[{"text": "...", "severity": "critical|notable|advisory"}, ...]

Reviewer note:
{note[:1500]}

{f"Spec contract (for calibration):\n{spec_contract[:400]}" if spec_contract else ""}
```

**Parse response:** extract JSON array from completion text (use regex to find `[...]`
block; fall back to `[{"text": note, "severity": "advisory"}]` on any parse failure).

**LLM call:** use `run_owned_helper_completion` with `ROLE_SUPERVISOR` model. If
`completion.error` or empty result — return `[ClassifiedFinding(text=note, severity="advisory")]`
(safe fallback, never raises).

**Cap:** return at most 10 findings (slice list if LLM returns more).

---

### 2. `core/state/project_state.py` — add `add_reviewer_finding()`

Add a method for recording a finding to `reviewer_findings_summary`, bounded to the last
50 entries:

```python
_FINDINGS_SUMMARY_MAX = 50

def add_reviewer_finding(
    self,
    text: str,
    severity: str,
    delegation_id: str,
    spec_path: str | None = None,
    files: list[str] | None = None,
) -> None:
    """Append to reviewer_findings_summary (bounded to _FINDINGS_SUMMARY_MAX)."""
    entry = {
        "text": text,
        "severity": severity,
        "delegation_id": delegation_id,
        "spec_path": spec_path or "",
        "files": list(files or [])[:10],
        "timestamp": _utc_now_iso(),
    }
    self.reviewer_findings_summary.append(entry)
    if len(self.reviewer_findings_summary) > _FINDINGS_SUMMARY_MAX:
        self.reviewer_findings_summary = self.reviewer_findings_summary[-_FINDINGS_SUMMARY_MAX:]
```

---

### 3. `server/mcp_server.py` — classify + promote after reviewer_pass

Find the block in `delegate_to_agent` where `reviewer_pass_audit` is recorded into
`context_block` (around line 2854). **Immediately after** that block, add:

```python
# P12-004: promote reviewer findings to project state
if (
    supervisor_agent is not None
    and reviewer_pass_ran
    and reviewer_pass_outcome == "issues"
    and reviewer_pass_note
    and supervisor_agent._project_state is not None
):
    from core.engine.reviewer_findings_classifier import classify_reviewer_findings

    findings = classify_reviewer_findings(
        reviewer_pass_note,
        spec_contract=str(spec_read.sections.get("Contract", ""))[:400]
            if spec_read else None,
        workspace_path=ws,
        delegation_id=delegation_id,
    )

    promoted_count = 0
    for finding in findings:
        supervisor_agent._project_state.add_reviewer_finding(
            text=finding.text,
            severity=finding.severity,
            delegation_id=delegation_id,
            spec_path=spec_rel_path,
            files=list(files_changed or [])[:10],
        )
        if finding.severity in ("notable", "critical"):
            supervisor_agent._project_state.add_risk(
                text=finding.text,
                severity=finding.severity,
                source_delegation_id=delegation_id,
            )
            promoted_count += 1

    _supervisor_event_sink({
        "type": "reviewer_findings_classified",
        "finding_count": len(findings),
        "promoted_to_risks": promoted_count,
        "severities": [f.severity for f in findings],
        "delegation_id": delegation_id,
    })
    if promoted_count > 0:
        _supervisor_event_sink({
            "type": "project_state_risks_updated",
            "new_risks": promoted_count,
            "total_open_risks": len(supervisor_agent._project_state.open_risks),
            "delegation_id": delegation_id,
        })
```

**Important notes:**
- Do NOT call `supervisor_agent._project_state.save()` here — the existing `supervisor_agent.finish()` call later in the function saves it.
- `_supervisor_event_sink` is already defined in this scope.
- Guard with `supervisor_agent._project_state is not None` to be safe; the singleton warm-start guarantees it is set, but defensive guard is correct.

---

### 4. `core/engine/supervisor_tool_runner.py` — register `get_reviewer_findings`

In `build_phase12_tool_runner()`, add a fourth tool after `read_file`:

```python
def _get_reviewer_findings_fn(project_state, files_arg: str | None = None) -> str:
    """Return reviewer findings touching the given files (or all if files not specified)."""
    import json
    findings = project_state.reviewer_findings_summary
    if files_arg:
        target_files = {f.strip() for f in files_arg.split(",") if f.strip()}
        findings = [
            f for f in findings
            if any(tf in (f.get("files") or []) for tf in target_files)
               or any(tf in (f.get("spec_path") or "") for tf in target_files)
        ]
    # Return last 10 findings, most recent first
    results = list(reversed(findings[-10:]))
    return json.dumps(results, ensure_ascii=False)[:_TOOL_RESULT_BUDGET]

runner.register_tool(
    name="get_reviewer_findings",
    description=(
        "Get reviewer findings from past delegations on this project. "
        "Optionally filter by comma-separated file paths. "
        "Use when deciding whether to rerun or escalate after a reviewer flagged issues."
    ),
    schema={
        "type": "object",
        "properties": {
            "files": {
                "type": "string",
                "description": "Comma-separated file paths to filter by (optional)",
            }
        },
        "required": [],
    },
    fn=lambda files=None: _get_reviewer_findings_fn(project_state, files),
)
```

---

## Trace events

### `reviewer_findings_classified`
```json
{
    "type": "reviewer_findings_classified",
    "finding_count": 3,
    "promoted_to_risks": 2,
    "severities": ["critical", "notable", "advisory"],
    "delegation_id": "abc123"
}
```

### `project_state_risks_updated`
```json
{
    "type": "project_state_risks_updated",
    "new_risks": 2,
    "total_open_risks": 5,
    "delegation_id": "abc123"
}
```

---

## Acceptance checklist

- [ ] `ClassifiedFinding` dataclass in `core/engine/reviewer_findings_classifier.py`.
- [ ] `classify_reviewer_findings()` calls LLM; falls back to `advisory` on any error.
- [ ] JSON parse failure in classifier → fallback, never raises.
- [ ] `project_state.add_reviewer_finding()` appends to `reviewer_findings_summary`;
  caps at 50 entries.
- [ ] `notable` and `critical` findings also call `add_risk()` → land in `open_risks`.
- [ ] `advisory` findings do NOT land in `open_risks`.
- [ ] `reviewer_findings_classified` trace event emitted when `reviewer_pass_outcome == "issues"`.
- [ ] `project_state_risks_updated` trace event emitted only when `promoted_count > 0`.
- [ ] Nothing happens when `reviewer_pass_outcome == "lgtm"` or reviewer did not run.
- [ ] `get_reviewer_findings` tool registered in `build_phase12_tool_runner()`.
- [ ] `get_reviewer_findings` with no `files` param returns last 10 findings.
- [ ] `get_reviewer_findings` with `files` filters by file path membership.
- [ ] All existing tests pass: `pytest -q tests/test_supervisor_state_p12_001.py
  tests/test_supervisor_agent_p12_001.py tests/test_project_state_p12_002.py
  tests/test_delegate_tool.py tests/test_supervisor_tool_runner_p12_003.py`.

## New tests (`tests/test_reviewer_findings_p12_004.py`)

Add at least **7 tests**:

1. `test_classify_findings_critical_promoted_to_risks` — mock LLM to return one critical
   finding; assert `open_risks` gains one entry and `reviewer_findings_summary` gains one.
2. `test_classify_findings_advisory_not_promoted` — mock LLM to return advisory only;
   assert `open_risks` unchanged, `reviewer_findings_summary` gains one.
3. `test_classify_findings_llm_failure_falls_back` — mock LLM to return error;
   `classify_reviewer_findings()` returns one advisory finding without raising.
4. `test_classify_findings_json_parse_failure_falls_back` — mock LLM to return non-JSON
   text; fallback fires, result is one advisory entry.
5. `test_add_reviewer_finding_caps_at_50` — add 55 findings; assert
   `len(reviewer_findings_summary) == 50` and oldest are dropped.
6. `test_get_reviewer_findings_tool_filters_by_file` — populate findings with two entries
   (different files); call tool with one file; assert only matching finding returned.
7. `test_no_promotion_when_reviewer_lgtm` — simulate `reviewer_pass_outcome == "lgtm"`;
   assert neither `open_risks` nor `reviewer_findings_summary` is updated.

---

## § Results

*(Worker fills this in when done.)*

**Date completed:**  
**Tests:**  
**Notes / blockers:**
