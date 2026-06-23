<!--
  STEWARDSHIP — Tier 3 direction note. See docs/VISION_DOCS.md.

  - Living doc: update as roles/workflow evolve and phases ship.
  - NOT a phase commitment — this is the eventual target, not the current state.
  - Cross-link BL-525, BL-526, BL-527, BL-523, BL-524, multi-model-roles.md.
-->

# Delegation workflow vision

**Status:** Living direction note — 2026-06-19.  
**Purpose:** Make the eventual mcp-coder workflow explicit: who does what, at which scope, with what model tier. Replaces ad-hoc role naming with a stable vocabulary. Guards the design as phases ship incrementally.  
**Related:** [multi-model-roles.md](./multi-model-roles.md) (model tiers per role), [workflow-turns.md](./workflow-turns.md) (special turn types), [phase11-master-session-bootstrap.md](./archive/phase11-master-session-bootstrap.md) (Phase 12 preview).  
**Backlog:** BL-525 (Planner), BL-526 (Architect), BL-527 (host hedging), BL-523/524 (host escalation/detection).

---

## The full role hierarchy

```
User  (CEO)
  └── Host  (CEO assistant / junior PM)
        └── [mcp-coder boundary]
              ├── Architect  (CTO)               [Phase 12+]
              ├── Planner    (Senior engineer)    [Phase 12 full; partial today as architect_pass]
              │     ├── Supervisor  (Tech lead)   [Phase 11 P11-002]
              │     └── Reviewer    (QA)          [Phase 11 P11-005]
              └── Executor   (Implementation)     [Shipped — Aider]
```

### Role definitions

| Role | Analogy | Scope | Context budget | Status |
|------|---------|-------|----------------|--------|
| **User** | CEO | Unbounded | Full | Always existed |
| **Host** | CEO assistant / junior PM | Session | Full (MCP JSON args) | Always existed; model tier matters |
| **Architect** | CTO | Epic | ~4k — epic goal + milestones only, NO diffs/files | Phase 12+ (BL-526) |
| **Planner** | Senior engineer | Session / task | ~16k — spec + RAG + session history | Phase 12 full; today: one-shot `architect_pass` (being renamed P11-008) |
| **Supervisor** | Tech lead on call | Decision (per confirm_ask) | ~2k — spec + decision log + output tail | Phase 11 P11-002 (BL-351) |
| **Executor** | Implementation engineer | Delegation / turn | ~32k — full compiled brief | Shipped (Aider) |
| **Reviewer** | QA / code reviewer | Post-execution | ~8k — diff + acceptance criteria | Phase 11 P11-005 (BL-358) |

---

## The delegation lifecycle

### Phase A — Before delegation (pre-flight)

```
Host sends delegate_to_agent(task, spec, ...)
  │
  ├─ [clarity_check]    Planner-lite: "is this task clear enough to execute?"
  │    Cheap model, ~3k tokens. Returns clarification_needed or CLEAR.
  │    Shipped: P11-001 (MCP_CODER_CLARITY_PASS=1)
  │
  ├─ [spec_validation]  Planner-lite: "does the spec match the host conversation?"
  │    Cheap model, ~8k tokens. Shipped: P4-009.
  │
  └─ [planner_pass]     Planner: "how should this be implemented?"
       Currently named architect_pass. Sonnet-class, ~8k tokens.
       Produces implementation plan injected into executor prompt.
       Today: one-shot, static. Eventually: mutable, RAG-aware, session-persistent.
       Rename → planner_pass at P11-008.
```

### Phase B — Context compilation (compile)

```
[file_picker]      Picks relevant files (rules + ripgrep + RAG hints)
[builder_llm]      Cheap model compresses mechanical brief + history → executor brief
[rag_retrieval]    Pulls relevant prior delegations + workspace files
→ context_package  Full brief assembled (~32k tokens)
```

### Phase C — Execution (executor loop)

```
Executor (Aider) runs with full context_package
  │
  ├─ [supervisor]   On every confirm_ask:
  │    - Low-risk action → auto-approve (no LLM call)
  │    - High-risk / unknown → Supervisor LLM decides: approve / deny / abort
  │    - Human judgment needed → escalate (P11-004 mid-run gate, experimental)
  │    Pending: P11-002.
  │
  └─ Reports back: files_changed, output, stall reason if any
```

### Phase D — Post-execution (review + close)

```
[reviewer_pass]   Cheap model scans files_changed + acceptance criteria
  │               Returns: LGTM or up-to-3 issues
  │               Appended to spec report under ## Tier-1 Review
  │               Pending: P11-005.
  │
[spec_report]     Writes § Results to spec file
[delegation_log]  Full JSONL record written (always)
[trace]           Trace events written (always, write-always since Phase 9)
```

---

## Planner / Executor separation (core principle)

The planner does **light thinking with good context**; the executor does **heavy work with bounded context**.

| Dimension | Planner | Executor |
|-----------|---------|----------|
| Job | Creates + updates implementation plan | Writes code |
| Model | Sonnet-class (judgment) | Configured — can be expensive |
| Context | Spec + RAG + session history (light, focused) | Full compiled brief (large, compiled) |
| Lifecycle | Session-bounded; survives multiple delegations | Delegation-bounded |
| Updates | Plan patches as executor surfaces new info | Doesn't plan — just executes |
| RAG access | Yes — "what worked for similar tasks?" | No direct RAG access (executor-pull v0: /read hint only) |

The Planner and Supervisor may eventually merge (same scope, same context budget) — decision deferred to Phase 12 after dogfood. For now: Planner = proactive (owns the plan), Supervisor = reactive (intercepts decisions).

---

## Host as junior PM (host hedging principle)

The Host (Cursor or any MCP client) is the **CEO assistant**: it translates user intent into mcp-coder calls, manages doc updates, handles conversation, and routes work. Its model tier is **not controlled by mcp-coder** and defaults to cheap/mid.

**The hedging principle (BL-527):** mcp-coder's internal layers must compensate for host capability gaps. The system must work correctly regardless of host model tier.

```
Cheap host → mcp-coder layers do more (clarity pass, planner, architect all fire)
Mid host   → balanced; mcp-coder adds judgment
Exp host   → internal layers can be lighter/optional; host may pre-plan
```

**Never assume a capable host.** Every quality gate (clarity, planning, supervision, review) must be independently effective.

**Escalation (BL-523):** for specific high-value tasks (spec authoring, epic decomposition, architecture decisions), the host should escalate to a senior model. Two paths:
1. User-triggered (manual model switch today)
2. MCP-facilitated (future `plan_task` / `draft_spec` tools run a bounded senior-model call inside mcp-coder)

---

## Architect role (CTO) — epic scope

The Architect is a **strategic** role that operates at epic boundaries only. It is explicitly NOT involved in per-task implementation.

**What it sees:** epic goal, milestones delivered, outstanding risks — nothing more. No diffs, no file contents, no implementation details.

**What it does:** "Is this epic evolving correctly? Does the next planned step fit the overall direction? Are we accumulating architectural debt that needs addressing?"

**When it fires:**
- Epic open: sets architectural constraints for all tasks in the epic
- Epic boundary review: after N tasks, assess trajectory before continuing
- On escalation from Planner: when a task decision may have epic-level implications

**Phase placement:** Phase 12+ — depends on epic/plan object.

---

## Naming: current code → vision vocabulary

| Current code name | Vision role | Rename target | When |
|---|---|---|---|
| `architect_pass` | Planner (task-level, one-shot) | `planner_pass` | P11-008 |
| `architect_pass_llm.py` | Planner LLM runner | `planner_pass_llm.py` | P11-008 |
| `architect_prompt.py` | Planner prompt builder | `planner_prompt.py` | P11-008 |
| `MCP_CODER_ARCHITECT_PASS` | Planner on/off | `MCP_CODER_PLANNER_PASS` | P11-008 |
| (reserved) | Architect (epic-level CTO) | `architect_*` | Phase 12+ |
| `spec_validation` | Planner-lite (spec coherence) | keep name | — |
| `clarity_check` | Planner-lite (task completeness) | keep name | P11-001 ✅ |
| `supervisor` | Supervisor | keep name | P11-002 |
| `reviewer_pass` | Reviewer | keep name | P11-005 |

---

## How Phase 11 builds toward this vision

| Milestone | What it installs | Role it enables |
|-----------|-----------------|-----------------|
| P11-001 ✅ | Clarity check (pre-flight task completeness) | Planner-lite: verifies task before exec |
| P11-002 | SupervisedIO + DelegationSupervisor | Supervisor: first live judgment role |
| P11-003 | Executor-pull `/read` hint | Executor: reduces blind stalls |
| P11-004 | Mid-run human gate (experimental) | Human escalation path |
| P11-005 | Tier-1 reviewer (cheap model, diff scan) | Reviewer: first post-execution quality gate |
| P11-006 | Smart planner-pass trigger heuristic | Planner: smarter when to invoke (trivial skip) |
| P11-007 | Host `model_policy` arg | Host layer: per-delegation role model control |
| P11-008 | Naming refactor + role constants | Sets stable vocabulary; frees `architect` name |

**After Phase 11:** all five execution roles exist in code (some minimal). Phase 12 upgrades the Planner to session-bounded + mutable plan, introduces the Architect, and wires the full lifecycle.

---

## What Phase 12 adds

- **Mutable plan object** — plan is a first-class artifact, patched mid-run by Supervisor, updated end-of-loop by Planner
- **Session-bounded Planner** — plan state persists across multiple delegations in one MCP session
- **Planner / Supervisor merger decision** — after Phase 11 dogfood: one role or two?
- **Architect role** — epic-boundary, high-level context only, strategic misalignment detection
- **MCP-facilitated host escalation** — `plan_task` / `draft_spec` tools (BL-523)
- **Full executor-pull sidecar** — HTTP server for executor context tools (BL-354 full)

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-19 | Created — full role hierarchy, delegation lifecycle, planner/executor separation, host hedging, naming table, Phase 11 → Phase 12 arc. |
