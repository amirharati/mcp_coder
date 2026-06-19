<!--
  STEWARDSHIP — Tier 3 direction note. See docs/VISION_DOCS.md.

  - Captures the long-term multi-model vision so we don't lose it while shipping the simple version.
  - NOT a commitment to build all of this in Phase 4. Phase 4 ships D-P4-8 (one model per role).
  - Update as decisions land; cross-link BL-162 / BL-007 / BL-321 / BL-006.
-->

# Multi-model roles — direction note

**Status:** Direction only. **Phase 4 ships the simple version** (D-P4-8: one configurable model per role, fully audited). Everything below "Stage 1" is future — recorded so the simple version is built without closing the door on it.

**Decision anchor:** [PHASE4_MVP.md](../PHASE4_MVP.md) D-P4-8.  
**Backlog:** BL-162 (multi-model routing), BL-321 (tiered escalation), BL-006 (critic/test-writer), BL-007 (ensemble).

---

## Core idea

mcp-coder runs several **roles** around a delegation. Each role is an LLM call with its own model, budget, and audit line. Today roles map 1:1 to a single model. The long-term vision: a role can invoke **multiple models** — by policy, escalation, or committee — while keeping every call tracked and auditable.

| Role | Job | Today |
|------|-----|-------|
| **Executor** | Edit code (inside Aider) | `AIDER_MODEL` |
| **Review** | Spec Q&A before implement | `review_model` (defaults to executor) |
| **Context builder** | Pick files + assemble brief | `context_builder_model` (Gemini Flash default) — P4-001b |
| **Critic** (future) | Grade output before returning | — (BL-006 / BL-503) |
| **Polish** (future) | Post-executor refinement (comments, tests, alignment) | — (**BL-358**) |

**Invariant across all stages:** every model call logs `role`, `model`, `tokens`, `cost_est_usd`, `duration_ms`. Per-role budgets. Resolvers stay backend-neutral in `core/config/`.

---

## Stage 1 — one model per role (Phase 4, D-P4-8)

- `resolve_<role>_model_name(workspace)` for each role; same precedence (executor default → env → config.yaml).
- Each role's usage logged in its own JSONL block (`context_builder`, etc.), distinct from executor `tokens`.
- Per-role budget caps (small for builder — it summarizes, not generates).

This alone delivers: "different model for each task with their own cost/budget, fully trackable and auditable."

---

## Stage 2 — multiple models *within* a role (future)

Same role, more than one model, chosen or combined at runtime:

| Pattern | What | Trigger | Backlog |
|---------|------|---------|---------|
| **Tiered escalation** | Cheap model first; escalate to stronger on failure | `error_class` (timeout, 5xx), pytest fail, `mode=review` blocked, step revision N | BL-321 |
| **Policy-gated upgrade** | Stronger model when spec/task flags it (e.g. risky subsystem, file count) | spec front matter / heuristics | BL-321, BL-162 |
| **Critic redo** | Cheap critic grades executor output; redo with stronger model if rejected | critic verdict | BL-006, BL-503 |
| **Failed-attempt aware** | After N failed attempts for a spec, auto-pick stronger tier | `prior_failed_attempts` (P4-008 data) | BL-321 |
| **Deeper context build** | Escalate builder to a larger/stronger model when first brief is thin or task is cross-cutting | builder self-assessment / topic | BL-162 |
| **Post-executor polish** | After Aider succeeds: cheap/large-context model adds comments, tests, style alignment — **no logic change** | spec `polish:` / config `polish_pass` | **BL-358** (distinct from critic redo BL-006) |

**Note:** `prior_failed_attempts` (shipped P4-008) is exactly the signal Stage 2 escalation would consume — the audit data is already there.

---

## Stage 3 — committee / swarm (further future)

Multiple models do the **same** job; combine results.

| Pattern | What | Backlog |
|---------|------|---------|
| **Ensemble vote** | N models attempt; pick best by critic or agreement | BL-007 |
| **Parallel diff + select** | N executors produce diffs; gateway/critic selects | BL-007, BL-503 |
| **Diverse context briefs** | Multiple builders, merge/dedupe selected files | BL-162 + BL-007 |

Highest cost, lowest priority. Only after Stage 1–2 prove value and we have cost telemetry to justify N× spend.

---

## Why start simple

1. Stage 1 already delivers the user-visible win (per-role cost/audit).
2. Stages 2–3 need the audit + cost telemetry Stage 1 produces to decide *when* escalation/ensemble actually pays off.
3. Each stage is additive — Stage 1's resolver + audit block is the foundation; nothing here requires re-architecting it later.

---

## Guardrails (all stages)

- **Backend-neutral:** role resolvers never reference Aider APIs; live in `core/config/`.
- **Auditable by default:** no silent model swaps — every call logged with role + cost.
- **Budget per role:** a runaway builder/critic must not blow the executor's budget.
- **Opt-in complexity:** escalation/ensemble off by default; enabled by explicit config/policy.

---

## Full role hierarchy (Phase 11+ model)

This section captures the complete conceptual model agreed 2026-06-19. Not all roles are implemented yet.

```
User  (CEO)
  — ultimate authority; sets goals; approves direction
  — outside the system; communicates via Host only

Host  (CEO assistant)
  — bridge: translates user intent into mcp-coder calls
  — manages overall work flow; doc updates; routing decisions
  — cheap/mid model by default ("junior PM")
  — capability hedged by mcp-coder internal layers (BL-527)
  — if host is expensive, internal layers can be lighter; never assumed capable

[mcp-coder boundary]

Architect  (CTO)                                            [Phase 12+, BL-526]
  — epic scope only
  — context: epic goal + milestones delivered + risks — NO diffs, NO file details
  — fires at epic open + epic boundary reviews
  — job: "is this epic evolving correctly?"

Planner  (Senior engineer / manager)                        [Phase 12 full, BL-525]
  — session-bounded (can span multiple delegations)
  — context: spec + RAG (prior similar plans) + session state
  — owns mutable plan artifact; updates it mid-run and post-run
  — may merge with Supervisor after Phase 11 dogfood
  — NOTE: current code `architect_pass` = task-level planner; rename → planner_pass at P11-008

Supervisor  (Tech lead on call)                             [Phase 11 P11-002, BL-351]
  — decision-bounded (per confirm_ask from executor)
  — context: spec + decision log + output tail (~2k tokens, D-ARCH-1)
  — intercepts executor decisions: approve / deny / abort
  — possible merge with Planner in Phase 12 (same context scope)

Executor  (Implementation engineer)                         [Shipped — Aider]
  — delegation-bounded
  — context: full compiled brief (~32k tokens)
  — writes code; surfaces questions via confirm_ask

Reviewer  (QA / code reviewer)                              [Phase 11 P11-005, BL-358]
  — post-execution, per delegation
  — context: diff + acceptance criteria (~8k tokens)
  — surfaces obvious issues; feeds report to Planner / spec report
```

### Host capability hedging (BL-527)

mcp-coder internal layers must work correctly **regardless** of host model tier. The system compensates for a cheap host:

| Host tier | mcp-coder compensation |
|-----------|----------------------|
| Cheap / junior | Clarity pass + Planner do heavier lifting; Architect holds epic integrity |
| Mid (typical) | Balanced — internal layers add judgment; host handles routing + docs |
| Expensive | Internal layers can be lighter / optional; host may handle some planning |

**Consequence:** never design an internal role that assumes a capable host. Every quality gate must be independently effective.

---

## Host layer — the "junior PM" pattern *(BL-523 / BL-524)*

The existing stage model covers roles **within** mcp-coder (executor, builder, architect, supervisor, reviewer). This section captures the complementary pattern at the **host layer**.

**Framing:** The MCP host (Cursor or any client) runs as a **junior PM** by default. Its model tier governs cost for:
- User conversation
- Updating planning docs (status rows, `§ Results`)
- Routing decisions + small judgments

For heavyweight one-shots — spec authoring, epic decomposition, architecture decisions — a junior PM model is insufficient. Two resolution paths:

| Path | How | Owner |
|------|-----|-------|
| **User manual** | User switches host model for the heavy task | Today; works but random |
| **MCP-facilitated** | mcp-coder exposes bounded senior-model tools (`plan_task`, `draft_spec`) the host calls one-shot | Phase 12+ |

The MCP-facilitated path generalises the existing `architect_pass` pattern: a bounded, logged, senior-model call inside mcp-coder, invisible to the host's model tier. The junior PM host stays cheap; expensive intelligence is a one-shot inside the pipeline.

**Host model detection (BL-524):** eventually mcp-coder detects or receives `host_model` and emits advisory suggestions (`ctx.info` / response metadata) when the task warrants an upgrade. No automatic switching — advisory only.

**See:** BL-523 (escalation paths), BL-524 (detection + suggestion), BL-512 (host-set `model_policy` for executor roles).

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-19 | Added § Full role hierarchy — 6-layer model (User/Host/Architect/Planner/Supervisor/Executor/Reviewer); host hedging principle (BL-527); Supervisor+Planner merger decision deferred to Phase 12; P11-008 naming refactor planned. |
| 2026-06-19 | Added § Host layer — "junior PM" framing; BL-523 / BL-524 captured. |
| 2026-06-09 | Created — Wave 2 discussion; D-P4-8 (Stage 1) locked; Stages 2–3 recorded as direction |
