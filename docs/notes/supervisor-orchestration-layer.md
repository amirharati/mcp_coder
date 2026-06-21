<!--
  STEWARDSHIP — Cross-phase architecture direction note. See docs/VISION_DOCS.md.

  - Captures the long-term vision for the Supervisor as the main intelligence layer.
  - NOT a Phase 12 PM board (see PHASE12_MVP.md for that).
  - Update as decisions land; cross-link BL-540..BL-544, BL-525, BL-529/530.
  - Workers: read this before touching SupervisorAgent, project state, or context lifecycle.
-->

# Supervisor as intelligent orchestration layer — architecture direction note

**Status:** Direction note — **Phase 12 is the first delivery milestone**. Phase 11 shipped the structural foundation (SupervisorAgent as a class, canonical event set, model_policy layer). Phase 12 builds the intelligence.
**Created:** 2026-06-20
**PM board:** [PHASE12_MVP.md](../PHASE12_MVP.md) (once written)
**Related notes:** [phase11-master-session-bootstrap.md](./phase11-master-session-bootstrap.md), [multi-model-roles.md](./multi-model-roles.md), [model-policy-layer.md](./model-policy-layer.md)
**Backlog:** BL-540 (persistent project state), BL-541 (reviewer feedback loop), BL-542 (context router), BL-543 (supervisor context lifecycle), BL-544 (pause/resume), BL-525 (planner as real agent), BL-529/530 (supervisor context window + HelperToolRunner)

---

## The shift in one sentence

Phase 11 gave us a Supervisor that can **run a loop**. Phase 12 makes it a Supervisor that can **think across loops** — one that knows the project's history, can answer most questions autonomously, routes work to stateless specialists with exactly the right context, and can pause and resume across host round-trips without restarting.

---

## mcp-coder as a partner, not a tool

The deeper framing behind this architecture shift:

**Before Phase 12:** the host (Cursor AI) calls `delegate_to_agent` like a function. mcp-coder runs, returns a result, forgets everything. The relationship is one-directional: host gives an order, mcp-coder executes it.

```
Host:  "implement this" → mcp-coder runs → result
Host:  "implement that" → mcp-coder runs → result  (no memory of the first)
```

**After Phase 12:** mcp-coder maintains its own knowledge of the project. It can push back with reasoned questions. It can answer its own questions from project history. It can pause mid-task and resume without starting over. The relationship becomes **bidirectional**:

```
Host:      "implement this"
mcp-coder: runs, discovers an ambiguity
mcp-coder: "I need to know X before I continue (here's why)" → pauses, returns resume_token
Host:      answers X
mcp-coder: resumes with full context intact, no cold restart

Next delegation:
mcp-coder: has memory of prior decisions, reviewer findings, hot areas
mcp-coder: answers most sub-questions itself from that memory
mcp-coder: escalates only what genuinely needs the host
```

The host provides **strategic direction** (what to build, what matters). mcp-coder provides **tactical execution AND institutional memory** (how it was built, what was decided, what went wrong, what's risky). Neither can do the job well without the other — which is the original vision: a coding *partner*, not a coding *subprocess*.

This is what the multi-model Supervisor is built for: it has the project's memory, it routes tools intelligently, it knows when to ask and when to proceed. The stateless helpers (Planner, Reviewer, Clarity) are its hands. The Supervisor is the mind that coordinates them across the full lifecycle of a real project.

---

## Why this shift is necessary for real production use

After Phase 11, mcp-coder's delegation model looks like this:

```
host → delegate_to_agent → [pipeline] → SupervisorAgent loop → result
```

Each call is self-contained. The Supervisor wakes up fresh, runs, and forgets. This is fine for toy tasks. It breaks for real projects:

1. **Every escalation is a cold restart.** When the Supervisor needs human input mid-loop and aborts, the next `delegate_to_agent` re-runs clarity, context compilation, planner, and executor turn 1 — even though all of that work was already done. The second call has no memory of the first.

2. **Every sub-helper question goes to the host.** When Clarity asks "what's the auth strategy?" or the executor's `confirm_ask` fires "should I modify the test file?", the question escalates immediately to the human. But the answer is almost certainly already in the project's history — the Supervisor just doesn't know it.

3. **Context is assembled fresh each time, ignoring prior work.** The Planner sees the spec but not the last three delegations' outcomes. The Reviewer's findings go nowhere. Past decisions don't influence future plans.

4. **The Supervisor picks the same model weight for every decision.** A yes/no routing decision costs the same as a complex plan revision judgment.

These are not edge cases — they're the normal rhythm of a real multi-step engineering project. Fixing them is what moves mcp-coder from "useful for isolated tasks" to "trusted for real dogfooding."

---

## The architecture

### Layer model

```
┌──────────────────────────────────────────────────────────────────┐
│  SupervisorAgent  (the only stateful layer)                      │
│                                                                  │
│  SESSION STATE (in-flight, per-delegation)                       │
│    turn_index, plan, decision_log, completed_turn_artifacts      │
│    pause/resume state: resume_token + serialized session         │
│                                                                  │
│  PROJECT STATE (durable, cross-delegation) ← BL-540             │
│    project_state.json: decisions, hot areas, prior reviews,      │
│    open questions, Reviewer findings summary                     │
│                                                                  │
│  INTERCEPTION LAYER ← BL-543 / BL-544                           │
│    answers sub-helper questions from knowledge before escalating │
│    assembles continuation briefs for multi-turn executor         │
│    enriches confirm_ask responses with injected context          │
│                                                                  │
│  ROUTING LAYER ← BL-542                                          │
│    decides what to call (Planner, Reviewer, specialists)         │
│    decides what context slice each call receives                 │
│    decides model weight for each internal decision               │
│                                                                  │
│  calls stateless workers:                                        │
│  ┌─────────────┐ ┌─────────────┐ ┌───────────────────────────┐  │
│  │   Planner   │ │   Reviewer  │ │  Clarity / Validator /    │  │
│  │  (one-shot) │ │  (one-shot) │ │  Context compiler / ...   │  │
│  └─────────────┘ └─────────────┘ └───────────────────────────┘  │
│  ┌─────────────┐ ┌─────────────────────────────────────────────┐ │
│  │   Executor  │ │  Future specialists (CTO, API designer, ...) │ │
│  │   (Aider)   │ │  — all stateless, all receive context slice  │ │
│  └─────────────┘ └─────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### The single statefulness principle

**Only the Supervisor is stateful.** Every other component is a pure worker: receives context on each invocation, does its job, returns results, has no memory of previous calls. The Supervisor provides what each worker needs to know. New specialists can be added without touching the state model.

This works because the Supervisor's knowledge is sufficient to contextualize any worker call:
- Before calling the Planner: inject project state + prior reviewer findings
- Before calling the Executor: inject the continuation brief (what was done, what remains, host answers)
- Before calling Clarity: inject task history so it doesn't ask questions already answered
- At `confirm_ask`: check plan + decision log before routing to human

### Why the Planner doesn't need its own session state

The Planner reads `project_state.json` before reasoning. That file contains decisions from every prior delegation. The Planner is "stateful" only in the sense that it reads persistent data — but that data is managed by the Supervisor, not the Planner. Called fresh each time; fully informed each time. This is the right separation: the Supervisor owns state, workers consume it.

### Two-tier state model

```
Session state:   in-flight, serialized to disk on pause
                 lives in:  supervisor_states/<resume_token>.json
                 TTL:       configurable (default 24h)
                 purpose:   pause/resume across host round-trips

Project state:   durable, cross-delegation, append-only
                 lives in:  .mcp-coder/projects/<key>/project_state.json
                 TTL:       permanent (until project is removed)
                 purpose:   cross-delegation memory — decisions, findings, hot areas
```

---

## Cross-phase architectural decisions

These decisions apply to Phase 12 and all future phases. Workers must not violate them.

### D-ARCH-7: Supervisor is the sole owner of session and project state

No helper writes to `project_state.json` directly. Reviewer returns findings → Supervisor decides what to persist. Planner returns a plan → Supervisor extracts durable decisions and writes them. This keeps state writes auditable and consistent.

### D-ARCH-8: Interception before escalation

When a sub-helper generates a question (Clarity, `confirm_ask`, spec validation), the Supervisor intercepts first. It checks project state + session state. If the answer is determinable from known context, it answers autonomously. Only questions it genuinely cannot resolve from its knowledge escalate to the host. The goal: minimize human interruptions without hiding important decisions.

### D-ARCH-9: Pause/resume preserves pipeline work

When the Supervisor pauses (needs host input), it serializes session state with a `resume_token`. On resume, the following stages are **not re-run**: clarity_check, spec_validation, context_compile, planner_pass, completed executor turns. The host's answer is injected into the continuation brief for the next turn. The Planner may revise the remaining plan if the answer changes scope.

```
Fresh delegate_to_agent:  all stages run
Resume delegate_to_agent: skip completed stages → Supervisor resumes at turn N
```

### D-ARCH-10: Multi-model Supervisor by decision weight

The Supervisor's internal LLM calls have very different cognitive demands. A yes/no routing decision does not warrant the same model as a plan revision judgment. The Supervisor selects model weight based on the type of decision:

| Decision type | Model tier |
|---|---|
| confirm_ask yes/no (in-scope per plan) | weak (fast, cheap) |
| context routing (what to inject) | weak/medium |
| continuation brief assembly | medium |
| answering sub-helper question from project state | medium |
| plan revision after host answer | strong |
| deciding whether to escalate vs. resolve autonomously | medium/strong |

Configured via an extension of `model_policy` (already shipped in P11). The Supervisor selects its own internal model per decision type; the host can override the whole policy per delegation.

### D-ARCH-11: Two-tier Supervisor context model (replaces single-compile approach)

The Supervisor's context is divided into two tiers with different refresh cadences:

**Tier 1 — Slow context (refreshed at turn boundaries)**
Compiled once per turn (or once per delegation on resume). Changes rarely within a turn.

| Source | What | When refreshed |
|---|---|---|
| Spec text | Full spec (or compressed summary) | Delegation start / resume |
| Project state summary | Decisions + active risks (compressed, ~500 tokens) | Turn start |
| Current plan | From planner_pass | Delegation start |
| Decision log | All confirm_ask decisions so far | Each new decision appended |

**Tier 2 — Action-specific context (pulled on demand via tool calls)**
The Supervisor calls tools based on its own reasoning, mid-loop, when it needs more
information for a specific decision. Only pulled when the LLM reasons it is relevant.

| Tool | Returns | Example trigger |
|---|---|---|
| `get_delegation_history(spec_path, n)` | Last N delegation summaries + files changed | "I should check what was changed last time on this spec" |
| `get_reviewer_findings(files)` | Classified findings for specific files | "This file had reviewer issues before" |
| `read_file(path)` | File content | "I need to see the actual interface before approving this change" |
| `get_diff(delegation_id)` | File diffs from a past run | "What exactly did that delegation change?" |
| `get_project_state()` | Full project_state.json | "What decisions have been made about this?" |
| `search_past_decisions(query)` | Decisions matching a query | Phase 13+, requires RAG |

**Why this is better than a single pre-assembled context block:**
- The LLM pulls only what it actually needs for each decision — no wasted tokens
- Context is always fresh (tool calls execute at decision time, not at delegation start)
- Extending the Supervisor's knowledge is adding a new tool, not changing a monolithic assembler
- The Supervisor's reasoning about *why* it called a tool is traceable (`supervisor_tool_call` events)

**Phase 12 tools available:** `get_delegation_history`, `get_project_state`, `read_file`, `get_diff` (all derivable from existing `.mcp-coder/` storage). `get_reviewer_findings` available after P12-004 ships.

**Phase 13+:** `search_past_decisions` (RAG over decision history), inter-project queries, sidecar HTTP tool server for executor (BL-354 full, BL-530).

**Context frugality still applies (D-ARCH-1):** Tool results are truncated/summarized before injection. The Supervisor cannot load arbitrarily large files in one call — results are bounded by per-tool token limits. The total context window per Supervisor LLM call stays within budget even with tool results included.

**Future direction — smarter context management (Phase 13+, keep in mind):** Turn boundaries are the Phase 12 heuristic for when to refresh tier-1 context. Future iterations can be more intelligent:

- **Topic-based relevance**: before including a project state entry in tier-1, score its relevance to the current task (keyword match or embedding similarity). Include only entries above threshold — avoids bloating tier-1 with unrelated history as the project grows.
- **Recency + importance weighting**: blend `inserted_at` and `severity` (critical risk > advisory finding) to rank what makes it into the tier-1 summary when the total exceeds budget.
- **Context dropping policy**: as `project_state.json` grows, tier-1 cannot include everything. Candidates for dropping: resolved risks, superseded decisions, findings for files outside current spec scope. A cheap classifier decides what's still live vs. historical noise.
- **Event-driven refresh**: refresh tier-1 not just at turn boundaries but on specific events — when a `confirm_ask` touches a new file, when a plan revision changes scope, when the host answer introduces a new constraint.
- **LLM-rated relevance pre-pass**: for complex cases, a cheap pre-call ("given this spec and task, which of these past decisions are relevant?") before assembling tier-1. Expensive but precise.

These become important once project history is large enough that naively including it all would blow the context budget or add noise. Phase 12 dogfood will reveal when that threshold is reached. The two-tier model is designed to accommodate these improvements incrementally — the tier-1 assembly is one function; making it smarter doesn't require changing the tool-calling loop.

---

## Supervisor tool-calling loop (`SupervisorToolRunner`)

The Supervisor's LLM calls go through a multi-turn tool loop rather than a single call with a pre-assembled prompt. This applies to both inter-turn decisions and confirm_ask interceptions.

```
Turn boundary decision:
  1. Supervisor gets: tier-1 context (spec, plan, decision log tail) + question/context
  2. LLM reasons: optionally issues tool calls to pull tier-2 context
  3. Tool results appended to conversation
  4. LLM iterates until it emits a final action (no more tool calls)
  5. Final action extracted: RERUN_AIDER | DONE | ESCALATE_HOST (inter-turn)
                           or: APPROVE | DENY | ABORT | ESCALATE (confirm_ask)
```

`SupervisorToolRunner` (Phase 12, P12-003):
- Wraps the LLM call loop for both decision types
- Registers available tools as function-spec definitions
- Executes tool calls and appends results
- Terminates on: final decision emitted OR max_tool_rounds exceeded (default 3)
- Emits `supervisor_tool_call` trace event per tool call: `{tool, args, result_tokens, duration_ms}`
- Falls back to single-call behavior if model doesn't support function calling

This is a backend-neutral design — `SupervisorToolRunner` is in `core/engine/`, not in `server/`. Tools are Python callables registered at construction time, same pattern as `executor_fn` / `reviewer_fn` in `SupervisorAgent`.

---

## Pause/resume protocol (BL-544)

### Pause

```python
# When Supervisor decides it needs host input:
state = SupervisorState(
    resume_token=uuid4(),
    spec_path=...,
    turn_index=completed_turns,
    plan=current_plan,
    decision_log=decisions,
    completed_turns=[{files_changed, output_tail, reviewer_findings}, ...],
    pause_reason="needs_input",
    questions=[...],
    context_ref=delegation_id,   # pointer to context package on disk
    expires_at=now + TTL,
)
state.save()  # ~/.mcp-coder/projects/<key>/supervisor_states/<token>.json
return DelegationResult(outcome="needs_input", resume_token=state.resume_token, questions=state.questions)
```

### Resume

```python
# delegate_to_agent(resume_token="sv_abc123", answer="yes, also add rate limiting")
state = SupervisorState.load(resume_token)
# skip: clarity, spec_validation, context_compile, planner
# inject: host answer into continuation brief
supervisor = SupervisorAgent.resume(state, host_answer=answer)
supervisor.run()  # continues from state.turn_index
```

### What stages skip on resume

| Stage | Fresh | Resume |
|---|---|---|
| clarity_check | runs | skipped |
| spec_validation | runs | skipped |
| context_compile | runs | skipped — loaded from context_ref |
| planner_pass | runs | skipped (may re-plan if host answer changes scope) |
| completed executor turns | n/a | skipped — already on disk |
| next executor turn | runs | runs |

---

## Interception layer — how Supervisor answers sub-helper questions

The Supervisor intercepts any blocking gate before routing to the host. Resolution order:

```
1. Check decision_log:   "have I already decided this in this delegation?"
2. Check project_state:  "is there a durable decision covering this?"
3. Check plan:           "does the plan explicitly include/exclude this?"
4. Check RAG history:    "have we seen a similar question in prior delegations?"
5. → escalate to host    (only if all above are inconclusive)
```

This applies to: Clarity questions, `confirm_ask` decisions, spec validation blocks, and (future) any other blocking gate a helper generates.

The interception result is logged as `supervisor_intercept` in the delegation trace with: question, resolution_source, answer, reasoning. This creates an audit trail and training signal.

---

## Reviewer findings feedback loop (BL-541)

Reviewer findings currently go into the spec report and are not read by future delegations. The Supervisor closes this loop:

```
turn N runs → Reviewer produces findings
  → Supervisor classifies: advisory | notable | critical
  → critical/notable findings → written to project_state.json
    (e.g., "2026-06-20: auth module has no test coverage — delegation auth-03")
  → next delegation on same project: Planner reads findings before planning
  → Planner can choose to address them or note them as known
```

This creates a durable institutional memory for the project that accumulates across delegations.

---

## Future: host chat access for intent inference

Not in initial Phase 12 scope. Recorded here to not close the door.

The host (Cursor) has a conversation history between the user and the AI. The Supervisor could read a window of that history to infer the user's current intent — useful when a sub-helper question is ambiguous and the project state doesn't resolve it. For example: the user just said "I want to keep this lean" in the chat — the Supervisor can use that as context for a confirm_ask about whether to add a new abstraction layer.

This is a complement to project state (explicit, durable decisions) with live user intent (implicit, ephemeral). First iteration: project state is sufficient. Second iteration: host chat window as optional context for escalation judgment.

---

## What this is NOT

| Item | Reason |
|---|---|
| Multi-agent parallelism | Phase 12 is sequential. Parallel workers (e.g., two reviewers) would need a coordination layer not yet designed. |
| Aider replacement | The Supervisor orchestrates Aider; Aider remains the executor. Nothing in this note changes the executor backend. |
| Autonomous goal decomposition | The Supervisor executes a plan provided by the Planner. It does not decompose high-level goals into specs — that's still the host/user's job. |
| Real-time streaming state | Pause/resume is at turn boundaries. Mid-turn state is not serializable (Aider thread is running). |
| Stateful Clarity or Reviewer | Helpers remain stateless. Their outputs are persisted by the Supervisor, not by themselves. |

---

## Delivery sequence (Phase 12 ordering — updated)

Dependencies under the revised tool-calling model:

```
BL-544 (pause/resume)              ★ structural foundation — ship first
BL-540 (project_state.json)        ← creates the data tools will expose
  │
  ├── BL-530/542 (SupervisorToolRunner + tool registry)
  │     ← the tool-calling loop + tier-1/tier-2 context model
  │     ← tools available: get_delegation_history, get_project_state,
  │                         read_file, get_diff
  │
  ├── BL-541 (reviewer findings → project state)
  │     ← unlocks get_reviewer_findings tool
  │
  └── BL-525 v1 (Planner reads project state via same tool pattern)
```

Revised Phase 12 milestones (as of 2026-06-20):
1. **P12-001**: BL-544 + session state — `SupervisorState`, pause/resume, `resume_token`
2. **P12-002**: BL-540 — persistent `project_state.json`, Supervisor reads/writes per delegation
3. **P12-003**: BL-530/542 — `SupervisorToolRunner`: tool-calling loop, tier-1 base context + tier-2 on-demand tools, `supervisor_tool_call` trace events
4. **P12-004**: BL-541 — reviewer findings → project state; `get_reviewer_findings` tool available
5. **P12-005**: BL-525 v1 — Planner reads project state (via same tool pattern); decisions written back

---

## How Phase 11 laid the foundation

Phase 11 shipped the structural pieces this architecture builds on:

- `SupervisorAgent` class with canonical event set and begin/resume API
- `model_policy` for per-role, per-delegation model overrides
- Decision log (in-memory, per-delegation)
- `answer_delegation_question` — the first human-gate primitive
- `confirm_ask` intercept infrastructure (SupervisedIO)
- Reviewer (tier-1) producing structured findings

Phase 12 does not redesign any of these. It builds on top of them: adds persistence (BL-540), adds intelligence (BL-543, interception), and adds the cross-call continuity that makes the Supervisor a real agent (BL-544).
