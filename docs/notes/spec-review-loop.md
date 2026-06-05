# Spec review loop (Phase 1+)

**Status:** Shipped (P1-151, 2026-06-05) — `delegate_to_agent(mode=review|implement)`.

**E2E:** `mcp_coder_phase1_e2e` expense-splitter — step 2 used review then implement + planner fix delegates. See [PHASE1_MVP.md](../PHASE1_MVP.md) § 1.51 experiment.

---

## Workflow

1. Planner creates `specs/tasks/<epic>-<step>.md` (+ optional `specs/epics/<slug>.md`).
2. **Optional:** `mode=review` — worker returns questions/suggestions; MCP appends **Worker feedback** on `specs/reports/<same-name>.md`.
3. Planner updates **same** task spec (`revision++`, `status: ready`); human input optional.
4. `mode=implement` — worker edits `target_files` (**include files to read** for imports / prior steps).
5. Planner runs `pytest`; sets task `status: done` and epic Steps table — **not** MCP.

## When to use review

| Trigger | Example |
|---------|---------|
| **User asks** | “Review before implement” / brainstorm |
| **Planner judges risk** | Ambiguous scope, cross-step deps, large multi-file step |
| **After bad implement** | “Add files to chat” → use review or fix `target_files` / `context_summary` |

**Not automatic** on every step. Step 1 greenfield often skips review (observed in E2E).

Review answers **spec** questions; it does **not** substitute for putting step N code in implement context ([P1-ISS-015](../PHASE1_ISSUES.md#p1-iss-015-review-mode-does-not-validate-prior-step-api)).

---

## Files

| Path | Owner |
|------|--------|
| `specs/tasks/*.md` | Planner (Goal → Revision log) |
| `specs/reports/*.md` | MCP (Status, Run log, Worker feedback) |
| `specs/epics/*.md` | Planner |

---

## Modes

| `mode` | `target_files` | MCP report | Typical `outcome` |
|--------|----------------|------------|-------------------|
| `review` | must be `[]` | appends Worker feedback; status `reviewed` | `review` |
| `implement` (default) | edit + read deps | Run log; status `delegated_ok` or `blocked` | `success` / `needs_input` / `failed` |

Implement mode treats “please add files to chat” as **failure** (`needs_input`) — use review or expand `target_files` ([P1-ISS-016](../PHASE1_ISSUES.md#p1-iss-016-implement-add-files-to-chat-marked-failure)).

---

## Decisions (revisit at P1-199)

| ID | Decision | Backlog if we change |
|----|----------|----------------------|
| D-SPEC-1 | Review optional | BL-312 auto-review policy |
| D-SPEC-3 | Planner verifies tests; MCP `delegated_ok` ≠ done | BL-310 |
| D-SPEC-4 | Read deps in `target_files` or `context_summary` | BL-311 |

Full table: [PHASE1_MVP.md](../PHASE1_MVP.md) § P1-199.

---

## Changelog

| Date | Note |
|------|------|
| 2026-06-05 | Shipped P1-151; E2E notes; issues P1-ISS-013–016 |
| 2026-06-05 | Initial design doc |
