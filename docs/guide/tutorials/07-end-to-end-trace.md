# T-07: Inspecting a delegation end-to-end

**Status:** Planned — content not yet written.

**Goal:** Walk one real `delegation_id` through every artifact it produces — JSONL audit record, workspace history checkpoint, spec report, trace file, and `inspect-context` reconstruction — so you can answer any question about what happened in a past delegation without needing a second run.

**Why this matters:** All previous tutorials cover one artifact at a time. T-07 ties them together in a single narrative: start from `delegations.jsonl`, follow the pointers to `traces/`, `workspace_history.db`, and `specs/reports/`, and use CLI + MCP tools to answer questions a reviewer or debugger would actually ask.

**Prerequisites:** T-01 through T-06 (all completed).

**Estimated time:** 25–30 min (mostly running CLI commands against real data).

---

## Planned content

### 1. Find a real delegation to inspect

- Use `mcp-coder ps` or `mcp-coder list-delegations` to pick a recent `delegation_id`.
- Open the lean audit row in `delegations.jsonl`.
- Key fields to orient: `delegation_id`, `outcome`, `spec_path`, `session_id`, `trace_ref`.

### 2. Read the JSONL record top-to-bottom

- Walk every top-level field from T-02 §4 against a real record.
- Identify `context.delegation_pipeline` timing — which phase was slowest?
- Check `context.context_package.entries` — which tiers made it in?
- Check `model_roles` — what model ran for each role and how many tokens?

### 3. Follow to the trace file

- Resolve `trace_ref` → `traces/<id>.jsonl`.
- Scan for `delegation_lifecycle_start/end`, `phase_start/end`, `supervisor_turn_*`, `supervisor_decision`.
- Find the `llm_call` events for each helper role.
- Understand the difference between `llm_call` (gateway), `proxy_llm_call` (proxy), `backend_llm_call` (Aider).

### 4. Read the workspace history checkpoint

- `mcp-coder history show <delegation_id>` — checkpoint metadata, outcome, model, duration.
- `mcp-coder history diff <delegation_id>` — unified diff of every file changed.
- Cross-check `files_changed` from JSONL with the diff.

### 5. Read the spec report

- `cat .mcp-coder/specs/reports/<spec>-report.md` — run log entry.
- Verify reviewer findings, outcome label, `files_changed` match.

### 6. Reconstruct the context brief

- `mcp-coder inspect-context --spec ... --task ...` — re-run phases 1–7 dry without an API call.
- Compare mechanical brief tiers to what `context_package.entries` shows in JSONL.

### 7. Answer a real debugging question

End-to-end exercise: *"Aider edited a file I didn't expect. How do I trace what happened?"*

- Find the delegation in JSONL → `files_unexpected`.
- Check the scope violation in `delegation_pipeline.post_gateway`.
- Look at `files_edit` from the spec vs what Aider reported.
- Check the trace for `supervisor_decision` — did the Supervisor approve or was it outside the interception path?

---

*This stub will be expanded into a full tutorial with try-it CLI blocks in a future session.*
