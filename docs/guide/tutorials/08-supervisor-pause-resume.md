# T-08: Supervisor agent — pause, resume, and project memory

**Status:** Planned — content not yet written.

**Goal:** Understand the persistent SupervisorAgent — how it maintains project memory across delegations, what happens when a delegation is paused, and how to resume it correctly. After this tutorial you will know how to handle `needs_input` responses, how the Supervisor remembers past work, and how to read the state files.

**Why this matters:** Phase 12/13 changed mcp-coder from a one-shot pipeline into a persistent project workflow agent. Understanding pause/resume and project state is necessary to diagnose unexpected `needs_input` responses and to get the most out of multi-delegation workflows.

**Prerequisites:** T-02 (storage layout), T-06 (delegation pipeline), familiarity with `how-it-works.md`.

**Estimated time:** 20–25 min.

**Design reference:** [supervisor-agent-architecture.md](../../notes/supervisor-agent-architecture.md)

---

## Planned content

### 1. The persistent Supervisor — what changed from Phase 9

- Old model: each `delegate_to_agent` was fully stateless end-to-end.
- New model: `SupervisorAgent` accumulates state across delegations and survives process restarts.
- Two state objects: `project_state.json` (cross-delegation memory) and `agent_state.json` (checkpoint).

### 2. Project state — what the Supervisor remembers

- Location: `~/.mcp-coder/projects/<key>/project_state.json`.
- What it holds: decisions made, risks flagged, hot areas, reviewer finding summaries, delegation summary.
- How the planner can read it: `inspect_context` MCP tool includes a `project_state` section; or `mcp-coder status`.
- How to reset it: delete the file or use the `--start-fresh` path.

### 3. Agent checkpoint — survival across restarts

- Location: `~/.mcp-coder/projects/<key>/agent_state.json`.
- Written at every `finish()`.
- If the MCP server restarts mid-workflow, the Supervisor rehydrates from this file.
- CLI (`mcp-coder delegate`) and the server use the same checkpoint — they are equivalent.

### 4. Lifecycle envelope events

- `delegation_lifecycle_start/end` wrap every delegation.
- `phase_start/end` wrap each logical phase (preloop, loop, postloop).
- `supervisor_turn_start/end` and `supervisor_decision` are inside the loop phase.
- `supervisor_paused` and `supervisor_resumed` appear on pause and resume.
- Walk a real `traces/<id>.jsonl` file and find each event type.

### 5. When a delegation pauses

Two pause semantics:

| Type | Trigger | What you see |
|------|---------|--------------|
| **Clarity block** | `clarity_check` gate fires — unanswered questions in the spec | `status: blocked`, `clarification_needed: [...]`; spec Q&A path |
| **Escalation** | Supervisor decides `escalate_host` inside the loop | `status: needs_input`, `resume_token: "..."`, `question: "..."` |

For escalation: the delegation is paused and a `supervisor_states/<token>.json` file is written. The token expires after 24 h (`MCP_CODER_RESUME_TOKEN_TTL`).

### 6. Resuming a paused delegation

Two ways:

```python
# Option A: pass answer on the next delegate call
delegate_to_agent(task=..., answer="yes, use approach X", ...)
# The resume_token is inferred from the most recent pause for this workspace.

# Option B: explicit answer with resume token
answer_delegation_question(resume_token="abc123", answer="yes, use approach X")
```

What happens on resume: Supervisor rehydrates from `supervisor_states/<token>.json`, injects the answer, and continues the loop from where it paused. Completed preloop stages and earlier executor turns are **not** replayed.

`start_fresh=true` abandons the pause and starts a new delegation from scratch.

### 7. Try-it exercise

1. Trigger a pause by delegating a deliberately underspecified task.
2. Find the `resume_token` in the response.
3. Inspect `supervisor_states/<token>.json` directly.
4. Resume with an answer.
5. Verify the trace shows `supervisor_paused` followed by `supervisor_resumed`.

### 8. Supervisor context — what it sees per decision

- Tier 1 (slow baseline): spec contract + plan + decision log + output tail.
- Tier 2 (on-demand): `SupervisorToolRunner` pulls additional context (RAG search, file reads) when needed.
- This is separate from the executor's context package.

---

*This stub will be expanded into a full tutorial with try-it CLI blocks in a future session.*
