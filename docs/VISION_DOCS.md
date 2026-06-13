<!--
  STEWARDSHIP — meta index for vision / design docs (this file included).

  Do NOT edit this map or demote IDEA.md unless the user explicitly asks.
  Workers: implement per docs/tasks/*.md; report in § Results only.
-->

# Vision & design documents — map

Use this page so **main vision** ([IDEA.md](./IDEA.md)) is not lost when editing phase or backlog docs.

## Canonical stack (read order)

| Tier | Document | Role | Who may edit |
|------|----------|------|----------------|
| **0 — Why** | [IDEA.md](./IDEA.md) | Product vision, architecture, principles, data models. Roots: commit `074753b` (`README.md`) + Grok ideation. | **User only** (explicit ask to change vision) |
| **1 — How we ship** | [PHASES.md](./PHASES.md) | Multi-phase delivery, boundaries, validation. Must stay **consistent with IDEA**. | Planning / master session; not workers |
| **2 — Phase 1 PM** | [PHASE1_MVP.md](./PHASE1_MVP.md) | Tasks, status, acceptance — **closed/frozen P1-199** | Historical only; do not add new rows |
| **2 — Phase 2 PM** | [PHASE2_MVP.md](./PHASE2_MVP.md) | Phase 2 milestones — **closed / frozen P2-499** | Historical; new work → PHASE3_MVP |
| **2 — Phase 3 PM** | [PHASE3_MVP.md](./PHASE3_MVP.md) | Phase 3 milestones — **closed / frozen P3-499** | Historical; new work → PHASE4_MVP |
| **2 — Phase 4 PM** | [PHASE4_MVP.md](./PHASE4_MVP.md) | Phase 4 milestones — **closed / frozen P4 exit** | Historical; new work → Phase 4.5 / BACKLOG |
| **2 — P4 gaps** | [PHASE4_ISSUES.md](./PHASE4_ISSUES.md) | Issues from Phase 4 — **frozen at P4 exit** | Read-only; carried → BACKLOG § Phase 4 exit |
| **2 — Phase 4.5 PM** | [PHASE4.5_MVP.md](./PHASE4.5_MVP.md) | Stack literacy gate — tutorials, inspect, gap analysis | **Planning handoff done (2026-06-13)**; T-06/T-07 → BL-362; arch sub-pages → BL-363 |
| **2 — P4.5 gaps** | [PHASE4.5_ISSUES.md](./PHASE4.5_ISSUES.md) | Issues from Phase 4.5 — **frozen at planning handoff** | Read-only; carried → BACKLOG BL-341–363 |
| **2 — Phase 6 PM** | [PHASE6_MVP.md](./PHASE6_MVP.md) | Phase 6 milestones — observability substrate + reasoning buffer | **Active** — planning locked 2026-06-13 |
| **2 — Phase 5 PM** | [PHASE5_MVP.md](./PHASE5_MVP.md) | Phase 5 milestones — RAG + retrieval integration | **Frozen** — closed 2026-06-13 (recommended exit) |
| **2 — P5 gaps** | [PHASE5_ISSUES.md](./PHASE5_ISSUES.md) | Issues from Phase 5 implementation | **Frozen**; open → BL-335, BL-364 |
| **2 — Deferred** | [BACKLOG.md](./BACKLOG.md) | BL-* items, priorities, post–P1/P2 focus | Add/defer with user; do not delete rows silently |
| **2 — P1 gaps** | [PHASE1_ISSUES.md](./PHASE1_ISSUES.md) | Issues from P1 — **frozen / historical at P1-199** | Read-only; new gaps → BACKLOG |
| **2 — P2 gaps** | [PHASE2_ISSUES.md](./PHASE2_ISSUES.md) | Issues from Phase 2 — **frozen at P2-499** | Read-only; carried → PHASE3_ISSUES |
| **2 — P3 gaps** | [PHASE3_ISSUES.md](./PHASE3_ISSUES.md) | Issues from Phase 3 — **frozen at P3-499** | Read-only; carried → BL-324–328 |
| **3 — Direction notes** | [notes/spec-based-development.md](./notes/spec-based-development.md) | Spec-as-contract — **shipped experiment** (P1-151) | Update when workflow changes |
| **3 — Direction notes** | [notes/spec-review-loop.md](./notes/spec-review-loop.md) | Review vs implement modes | Same |
| **3 — Direction notes** | [notes/phase2-owned-context.md](./notes/phase2-owned-context.md) | Context compiler design — locked P1-199 | Update as Phase 2 decisions land |
| **3 — Direction notes** | [notes/multi-model-roles.md](./notes/multi-model-roles.md) | Per-role models (D-P4-8) + future escalation/critic/swarm | Update as multi-model decisions land |
| **3 — Direction notes** | [notes/rag-gap-analysis.md](./notes/rag-gap-analysis.md) | RAG vs not-RAG gaps, corpora, Phase 5 sequencing — **living** (T-04 / observability pass) | Update as we dogfood and plan Phase 5 |
| **3 — Direction notes** | [notes/workflow-turns.md](./notes/workflow-turns.md) | Special turns (polish, refactor, document, digest) + cadence — **living** | Update as workflow modes are planned |
| **3 — Handoff** | [notes/phase3-master-session-bootstrap.md](./notes/phase3-master-session-bootstrap.md) | Phase 3 master session prompt + summary | Frozen at P3-499 |
| **3 — Handoff** | [notes/phase4-master-session-bootstrap.md](./notes/phase4-master-session-bootstrap.md) | Phase 4 master session prompt + summary | Frozen at P4 exit |
| **3 — Handoff** | [notes/phase6-master-session-bootstrap.md](./notes/phase6-master-session-bootstrap.md) | Phase 6 planning decisions + bootstrap — observability/logging refactor | Active (Phase 6 planning locked) |
| **3 — Handoff** | [notes/phase5-master-session-bootstrap.md](./notes/phase5-master-session-bootstrap.md) | Phase 5 master session decisions + bootstrap | Frozen at Phase 5 planning handoff |
| **3 — Exit** | [notes/phase2-exit-validation.md](./notes/phase2-exit-validation.md) | P2-499 dogfood sign-off | Frozen at exit |
| **3 — Related ideas** | [OTEHR_RELATED_IDEAS/](./OTEHR_RELATED_IDEAS/) | Gatekeeper, experiments — **not** canonical vision | Optional; may inform backlog only |

## Operational (not vision — safe to update when implementing)

| Document | Role |
|----------|------|
| [INSTALL.md](./INSTALL.md) | Install, Python, locks |
| [notes/storage-and-linking.md](./notes/storage-and-linking.md) | `~/.mcp-coder` layout |
| [TASK_SPEC_TEMPLATE.md](./TASK_SPEC_TEMPLATE.md) | Copy-only template |
| `docs/tasks/P1-*.md` | **Gitignored** Phase 1 worker specs |
| `docs/tasks/P2-*.md` | **Gitignored** Phase 2 worker specs |
| `docs/tasks/P3-*.md` | **Gitignored** Phase 3 worker specs |
| `docs/tasks/P4-*.md` | **Gitignored** Phase 4 worker specs |
| [README.md](./README.md) (this folder) | Workflow index |

## Rules for agents

1. **Never** rewrite Tier 0–1 to “match implementation” without the user asking — adapt with **additions** and phase tables, not deletions of original intent.
2. **Workers** implement from `docs/tasks/*.md` only; they do **not** edit IDEA, PHASES, PHASE1_MVP, PHASE2_MVP, or BACKLOG.
3. **Status-only** updates in PHASE2_MVP (mark P2-* done) belong to the **planning / master** session after reviewing worker § Results. PHASE1_MVP is frozen.
4. When unsure whether a change is vision vs execution: **stop** and ask — default to [IDEA.md](./IDEA.md) § Core problem & why this exists.
5. **Root** [README.md](../README.md) is install/quick start; vision lives under `docs/`.

## Quick anchors (do not forget)

- **Problem:** Stateless coding agents → cross-session memory + task-level orchestration ([IDEA.md](./IDEA.md)).
- **Two tiers:** Task-level (`mcp-coder`) + turn-level (`context_optimizer_proxy`) — separate repos.
- **Phase 1:** Delegate + pass-through context + home storage + sessions + opt-in transcript — **no** owned RAG/router yet.
- **Phase 2:** Owned context compiler — **exit complete** [PHASE2_MVP.md](./PHASE2_MVP.md), [phase2-exit-validation.md](./notes/phase2-exit-validation.md).
- **Phase 3 (closed P3-499):** [PHASE3_MVP.md](./PHASE3_MVP.md) — workspace tracker, versioned specs, delegation RAG shipped; issues frozen → [PHASE3_ISSUES.md](./PHASE3_ISSUES.md) / BL-324–328.
- **Phase 4 (closed P4 exit):** Context builder + manager + verify + pipeline — [PHASE4_MVP.md](./PHASE4_MVP.md); gaps → [BACKLOG.md](./BACKLOG.md) § Phase 4 exit (BL-335–339).
- **Phase 4.5 (planning handoff done 2026-06-13):** Stack literacy gate — tutorials, inspect, gap analysis — [PHASE4.5_MVP.md](./PHASE4.5_MVP.md). Phase 5 scope locked. Pending items → BL-362, BL-363.
- **Phase 5 (closed 2026-06-13):** RAG + retrieval integration (BL-002 compile-push) — [PHASE5_MVP.md](./PHASE5_MVP.md). Defaults on. Carried: BL-335, BL-364, P5-005.
- **Phase 6 (active — planning locked 2026-06-13):** Observability substrate + reasoning buffer — `core/observability/` adapter seam; live token fix (BL-335); per-delegation trace files; reasoning hot buffer (BL-333); training opt-in — POC/MVP of AGENTIC_LOOP_LOGGING product. See [PHASE6_MVP.md](./PHASE6_MVP.md) · [notes/phase6-master-session-bootstrap.md](./notes/phase6-master-session-bootstrap.md).
- **Phase 6+:** Supervised loop control / escalation (BL-350), executor-pull tools (BL-354), interactive sessions (BL-160), multi-host, ensemble (BL-007).
- **Executor:** Aider-first; OpenCode/other hosts very low priority.

## Changelog

| Date | Change |
|------|--------|
| 2026-06-13 | Phase 6 planning locked — PHASE6_MVP.md + phase6-master-session-bootstrap.md created; P6-001…P6-005 milestones; `ObservabilityBackend` seam + BL-335 + BL-333 + BL-353 + training opt-in |
| 2026-06-13 | Phase 5 closed — recommended exit; RAG defaults on; PHASE5_ISSUES frozen → BL-335, BL-364 |
| 2026-06-13 | Phase 5 planning locked — PHASE5_MVP.md + PHASE5_ISSUES.md created; PHASE4.5_ISSUES.md frozen; BL-360–363 added to BACKLOG; rag-gap-analysis.md § MVP promoted to locked |
| 2026-06-11 | rag-gap-analysis.md — living RAG gap note (T-04 / observability pass); linked from BL-002 |
| 2026-06-09 | Phase 4.5 created — PHASE4.5_MVP + PHASE4.5_ISSUES; stack literacy gate before Phase 5 |
| 2026-06-09 | Phase 4 closed (P4 exit); PHASE4_MVP + PHASE4_ISSUES frozen; Phase 5 next; REASONING_TRACE_REUSE.md |
| 2026-06-09 | multi-model-roles direction note added (D-P4-8 + future stages) |
| 2026-06-09 | PHASE4_ISSUES added; Wave 1 dogfood gaps tracked |
| 2026-06-09 | Phase 4 docs created (PHASE4_MVP, phase4-master-session-bootstrap); Phase 3 PM + bootstrap marked frozen; doc map updated |
|| 2026-06-09 | Phase 3 closed (P3-499); PHASE3_ISSUES frozen; Phase 4 active; BL-324–328 |
| 2026-06-08 | Phase arc in PHASES (3–5); Phase 2 frozen; PHASE3_MVP + PHASE3_ISSUES; tracker-primary D-P3-2; phase2-exit + phase3-bootstrap |
| 2026-06-06 | PHASE2_MVP + PHASE2_ISSUES created; PHASE1_ISSUES frozen; phase2-owned-context note added; doc map updated |
| 2026-06-05 | Initial vision-doc map + stewardship tiers (with IDEA audit) |
