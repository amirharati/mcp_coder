<!--
  STEWARDSHIP — primary roles and lifecycle note. See docs/VISION_DOCS.md.

  - Purpose: stable vocabulary for roles and the delegation lifecycle.
  - Distinguish shipped behavior from future workflow ideas.
  - Source lineage: delegation-workflow-vision.md + spec-review-loop.md + workflow-turns.md.
-->

# Delegation roles and lifecycle

**Status:** Current vocabulary/lifecycle note — grounded in shipped workflow and current planning language as of 2026-06-23.  
**Related backlog:** BL-525, BL-526, BL-527, BL-523, BL-524, BL-358, BL-359.  
**Primary architecture:** [supervisor-agent-architecture.md](./supervisor-agent-architecture.md).

---

## Purpose

This note defines:

- the main roles around a delegation,
- the lifecycle phases of a delegation,
- the difference between **current shipped modes** and **future workflow turns**,
- and the naming/vocabulary we should keep stable across docs.

## Role model

```text
User
  -> Host
    -> mcp-coder boundary
      -> SupervisorAgent (persistent project workflow agent)
        -> Planner
        -> Reviewer
        -> Executor
        -> Clarity / validators / tools
        -> Architect / CTO / other specialists (future / deferred)
```

### Role definitions

| Role | Analogy | Scope | Context budget (source-era target) | Current status | Main job |
|---|---|---|---|---|---|
| **User** | CEO | Product/task intent | Full | always external | Sets goals and accepts tradeoffs |
| **Host** | CEO assistant / junior PM | User conversation/session boundary | Full MCP/request context | current | Presents requests, handles user-facing conversation, chooses when to delegate, returns results/questions to the user |
| **SupervisorAgent** | Project tech lead / persistent workflow agent | Project workflow across delegations | bounded but project-memory-backed | current foundation, still evolving | Owns orchestration, continuation, escalation, stateful control, project memory, and subagent/tool context |
| **Architect** | CTO | Epic / multi-step strategic layer | small/high-level only | deferred / boundary undecided | Possible high-level design direction at epic/project boundaries |
| **Planner** | Senior engineer | Task/session planning | medium / broader than a narrow confirm decision | partially shipped / evolving | Turns intent/project memory into an actionable delegation plan |
| **Reviewer** | QA / code reviewer | Post-execution quality pass | medium | current in shipped slices | Reviews output and feeds findings back to Supervisor/project memory |
| **Executor** | Implementation engineer | Implementation | largest execution context | current | Performs the actual code/edit execution |

### Role boundary summary

The current vocabulary should reflect one architectural choice:

> The Supervisor is the persistent mcp-coder project agent; Planner, Reviewer, Executor, Clarity, validators, and future specialists are scoped subagents/workers it coordinates.

The Host is outside the mcp-coder boundary. It can be strong or weak, but mcp-coder should not depend on the Host to remember project details or manage executor lifecycle.

## Lifecycle phases

### Current lifecycle

| Phase | What happens | Primary owner |
|---|---|---|
| **Request shaping** | Host/user intent is framed into a delegation goal | Host + planning path |
| **Planning / context setup** | Spec/plan/context are assembled | Supervisor coordinates Planner/helper/context paths |
| **Execution** | Code changes or implementation work happens | Executor |
| **Review / outcome shaping** | Findings and result interpretation are produced | Reviewer + Supervisor |
| **Decision / continuation** | Continue, pause, resume, escalate, or finish | Supervisor |

### More detailed phase view

The source notes broke this into a more explicit lifecycle that is still worth preserving:

| Lifecycle slice | Typical mechanisms |
|---|---|
| **Pre-flight** | clarity-style checks, spec validation, planner/planner-lite work |
| **Compile** | file/context selection, context assembly, retrieval, prompt packaging |
| **Execute** | executor loop, confirm/ask, possible supervision/interception |
| **Close / post-exec** | reviewer pass, reports, logs, traces, continuation decision |

### Core principle

> The lifecycle is not just “call executor and hope.”  
> It is a controlled sequence where planning, execution, review, and continuation all have distinct roles.

## Current shipped modes

These are part of current behavior and should be described as such:

| Mode / behavior | Status | Notes |
|---|---|---|
| `mode=implement` | shipped | Main implementation path |
| `mode=review` | shipped | Spec/questions review loop before implement |
| Reviewer pass | shipped in current slices | Post-execution review path |
| Pause/resume | shipped | Supervisor-owned lifecycle behavior |
| Clarity/spec-validation style pre-execution checks | shipped | Part of the broader lifecycle, distinct from `mode=review` |

### Spec/workflow modes vs orchestration roles

The source notes were mixing two different dimensions, so this distinction should stay explicit:

| Dimension | Examples |
|---|---|
| **Workflow/tool modes** | `mode=review`, `mode=implement`, verify-style follow-up |
| **Lifecycle roles** | Planner, Supervisor, Reviewer, Executor |

`mode=review` is not a role. Reviewer is not the same thing as `mode=review`.

### `mode=review` vs orchestration review

These are related but not the same thing:

- **`mode=review`** is the spec/workflow tool mode for pre-implement feedback.
- **Reviewer/Supervisor review paths** are orchestration-layer behaviors around execution outcome and continuation.

Keeping those separate avoids mixing workflow contracts with orchestration architecture.

## Future workflow turns

These are useful ideas, but they are **not current product truth** yet:

| Future turn | Purpose |
|---|---|
| **polish** | comments/tests/alignment cleanup after implementation |
| **digest** | summarize what changed and what the next step should be |
| **document** | generate/update supporting docs |
| **refactor** | structure cleanup separate from feature implementation |

These concepts remain helpful for future planning, but should stay clearly labeled as deferred.

### Future-turn cadence from the source note

The source material added more nuance than the short list above:

- **implement** should stay the default step-level turn,
- **digest** is an epic-boundary or pause-point comprehension turn,
- **polish** is a non-logic cleanup turn,
- **refactor** is a wider structure-preserving turn,
- **document** is a docs-oriented turn that may or may not use the executor.

That distinction is worth preserving even if none of these turns are fully shipped yet.

## Host boundary

The host is not the same thing as the Planner or Supervisor. It acts as a lightweight boundary that:

- relays user intent,
- chooses when to invoke mcp-coder,
- receives pauses/questions/results from mcp-coder,
- and may eventually participate in model-aware or escalation-aware behavior.

This is still an area where vocabulary matters more than shipped implementation detail. The “host as junior PM” idea is directionally useful, but the concrete product truth is still evolving.

### Host/Supervisor interaction

The Host and Supervisor communicate through delegations:

```text
Host -> delegate_to_agent(...) -> SupervisorAgent
Host <- result / needs_input / resume_token <- SupervisorAgent
```

The long-horizon design is many such delegations over one project. The Host stays user-facing; the Supervisor stays project-memory-facing.

### Host capability hedging

One of the important source ideas was that the system should not assume a strong host model. That still matters.

| Host tier | Desired system behavior |
|---|---|
| cheap / junior | mcp-coder layers compensate with stronger internal structure and checks |
| mid / typical | balanced host + mcp-coder responsibilities |
| expensive | host may do more planning, but internal quality gates should still remain valid |

This is why host capability should influence strategy, but not correctness.

## Naming map

Use this terminology consistently:

| Preferred term | Meaning |
|---|---|
| **Planner** | Task-level planning role |
| **Architect** | Epic-boundary/high-level future role; boundary with Host/Planner/Supervisor remains undecided |
| **SupervisorAgent** / **Supervisor** | Persistent project workflow agent and stateful orchestration/lifecycle owner |
| **Reviewer** | Post-execution review role |
| **Executor** | Implementation backend/engine role |
| **Subagent** / **worker** | Scoped component called by the Supervisor with bounded context |

Avoid reusing older names in a way that blurs role boundaries.

### Older naming quirks worth remembering

The older notes also captured a naming migration that is still useful context:

- older planner-related code used `architect_pass` naming for a task-level planner slice,
- `architect` should remain reserved for the future epic/CTO-style role,
- `planner` is the preferred current term for task-level planning behavior.

## Current vs deferred boundaries

### Current

- role vocabulary around Planner/Supervisor/Reviewer/Executor,
- shipped `review` and `implement` workflow distinctions,
- Supervisor-owned lifecycle and continuation model,
- host boundary as a distinct concept from internal orchestration roles,
- Supervisor as the persistent mcp-coder-side project agent.

### Deferred

- fully realized Architect role,
- full workflow-turn cadence system,
- richer host-side PM/escalation automation,
- more autonomous post-execution turn scheduling,
- exact boundaries for future CTO/Architect-level agents.

## Coverage notes

This note intentionally preserves:

- role glossary and analogies,
- lifecycle phase structure,
- workflow mode vs orchestration role distinction,
- host hedging and naming guidance,
- Supervisor-as-persistent-agent boundary,
- and the key “shipped now vs future turn” split.

The detailed phase-era rollout and older milestone table still live in the legacy source notes until we explicitly decide they are no longer needed.

## Legacy source notes

This note consolidates role and lifecycle framing from:

- [delegation-workflow-vision.md](./archive/delegation-workflow-vision.md)
- [spec-review-loop.md](./archive/spec-review-loop.md)
- [workflow-turns.md](./archive/workflow-turns.md)

Archive or retire those only after checking that any unique glossary, cadence rule, or workflow distinction is preserved here or intentionally dropped.
