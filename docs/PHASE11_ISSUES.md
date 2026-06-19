# Phase 11 issues

**Status:** **Active** — Phase 11 opened 2026-06-18.
**Open:** none yet
**Promoted from backlog:** BL-351 (full), BL-521 (new), BL-354 (v0), BL-358 (v0), BL-512 (Stage 2), BL-522 (new) — see [PHASE11_MVP.md](./PHASE11_MVP.md)
**Related PM board:** [PHASE11_MVP.md](./PHASE11_MVP.md)

---

## Promoted from backlog → Phase 11 milestones

*(Planning session 2026-06-18. Full vision for BL-351 / BL-354 / BL-358 remains in [BACKLOG.md](./BACKLOG.md); only the scoped slices below are Phase 11 work.)*

| Backlog | Milestone | Scope in Phase 11 | Full vision deferred |
|---------|-----------|-------------------|----------------------|
| **BL-521** | **P11-001** ✅ | Clarity pass: cheap LLM pre-delegation Q&A, `clarification_needed` early return | Cross-session intent history → Phase 12 |
| **BL-351** | **P11-002** | Supervised IO: `SupervisedIO` + `DelegationSupervisor` + in-memory decision log + abort-on-escalate | Mid-run async resume, cheap-LLM step planner, outer-loop resume → Phase 12 |
| **BL-354** | **P11-003** | Executor-pull v0: system prefix `/read` hint only | Full sidecar HTTP tool server → Phase 12 |
| **BL-522** | **P11-004** | Mid-run human gate: `answer_delegation_question` tool + Event bridge (experimental) | Protocol-level async mid-run gate → Phase 12 |
| **BL-358** | **P11-005** | Tier-1 reviewer: cheap model scan on `files_changed`, appended to spec report | Tier-2 epic-boundary review, critic/redo → Phase 12 |
| — | **P11-006** | Smart architect trigger: heuristic skip for trivial tasks, spec front-matter override | — |
| **BL-512** | **P11-007** | Host model policy: `model_policy` arg on `delegate_to_agent`, precedence over env | BL-513 AI-suggested, BL-514 dynamic escalation → Phase 12 |

---

## Shipped milestones

| Milestone | Date | Notes |
|-----------|------|-------|
| P11-001 | 2026-06-19 | `clarity_check` phase; 16 tests; code uncommitted pending review |

---

## Open implementation issues

*None yet — issues opened here during worker sessions (P11-ISS-NNN format).*
