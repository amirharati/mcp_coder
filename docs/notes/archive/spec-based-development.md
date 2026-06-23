<!--
  STEWARDSHIP — Tier 3 direction note. See docs/VISION_DOCS.md.

  - Hypothesis for P1-199 / Phase 2; not canonical vision (IDEA.md is).
  - Updated 2026-06-05 after P1-151 ship — experiment is live, not deferred.
-->

# Note: Spec-based development (meta → product)

**Status:** **Shipped experiment** (P1-150/151, 2026-06-05). Consumer workflow validated on expense-splitter E2E. Gatekeeper (BL-151) still deferred.

**Related:** [PHASE1_MVP.md](../PHASE1_MVP.md) P1-150/151 · [spec-review-loop.md](./spec-review-loop.md) · [BACKLOG.md](../BACKLOG.md) BL-150 (done) · [PHASE1_ISSUES.md](../PHASE1_ISSUES.md)

---

## What we do today (building mcp-coder)

1. **Planning chat** agrees scope (high level in `PHASE1_MVP.md`).
2. **Local spec file** `docs/tasks/P1-{…}.md` — concrete handoff for one worker session (gitignored).
3. **Worker** implements from that spec only; reports back.
4. **PM doc** tracks status in git; spec § Results holds run notes locally.

This works well: bounded context, clear done-when, no need to paste entire chat history into the worker session.

---

## What we ship in consumer repos (product experiment)

Mirrors the meta workflow with workspace specs under `.mcp-coder/`:

| Role | Owns |
|------|------|
| **Cursor (planner)** | Epic, step task specs, revision bumps, `pytest` verify, `status: done` |
| **mcp-coder (MCP)** | `delegate_to_agent`, `specs/reports/` audit only |
| **Aider (worker)** | Code edits or review Q&A — never planning |

**Hypothesis confirmed (initial):** Executor does not need full chat if **task spec + small delta** (`task`, `context_summary`) is the contract — same as our `docs/tasks/` worker handoff.

---

## Workspace layout (v2 — P1-151)

```text
<workspace>/.mcp-coder/
  spec-template.md
  spec-epic-template.md
  spec-report-template.md
  config.yaml                    # session_policy, cursor_rules_policy, host_transcript
  specs/
    epics/<epic_id>.md           # planner — north star, steps table
    tasks/<epic>-<step>.md       # planner — one file per delegatable step
    reports/<same-filename>.md   # MCP — Run log, Worker feedback (never edit in Cursor)
```

Templates: `resources/spec-*.md` (bundled; copied on bootstrap).

**Delegate:**

```text
delegate_to_agent(
  spec_path="tasks/my-epic-01-core.md",
  mode="review" | "implement",   # default implement
  target_files=[...],          # review: must be []
  task="...",
  context_summary="...",
)
```

See root [README.md](../../README.md) § Task specs.

---

## Lean context thesis (why this still adds value)

Delegation + specs is not only “use Aider for edits.” It keeps **both sides** of the loop quieter than dumping full chat history.

| Side | Without lean contract | With spec + delegate (today) |
|------|------------------------|------------------------------|
| **Worker (Aider)** | Every call might include full Cursor thread + tool noise | ~800–900 tok/call: task spec slice + `task` + `context_summary` + `target_files` ([E2E ~4.2k tok total](../tasks/P1-1.51-spec-delegate-v2-review.md)) |
| **Planner (Cursor chat)** | Long implement threads, diffs, retries in one composer | Thin planner turns: write/read specs & reports, delegate, `pytest` — implementation detail stays in worker session + `delegations.jsonl` |

**Why we avoid `host_transcript: dump` by default:** it re-introduces noise on the **executor** and scales badly (final E2E chat ~9k tok × N delegates ≈ 44k tok counterfactual). Spec + summary is the intentional substitute for “paste the whole chat.”

**What we are not claiming yet:** cheaper end-to-end vs one long Cursor-only session (no control run). We **are** claiming: bounded executor prompts, auditable steps, less polluted planner chat.

### Phase 2+ — smart injection instead of dump

Progression (aligned with [BACKLOG.md](../BACKLOG.md)):

1. **Today:** `host_transcript: none` + workspace task spec + optional review.
2. **Next (BL-001, BL-154):** MCP-owned **assembly** — pick files, constraints, rolling summary; explicit window budget and logged truncation.
3. **Then (BL-153, BL-002):** **Topic / session slice** — inject only delegations + spec revisions relevant to this step (RAG-like over `~/.mcp-coder` session history), not raw JSONL dump.
4. **Optional:** Let worker **pull** context (read/search tools) like Cursor’s retrieval — instead of pushing entire transcript into every Aider prompt.

Dump remains an **audit / debug** mode (P1-140), not the default product path.

---

## Open questions (P1-199)

| # | Question | Current answer |
|---|----------|----------------|
| Q1 | Mandatory spec for every delegate? | Optional param; **strict cursor rules** encourage for multi-step epics |
| Q2 | Commit task specs to git? | Team choice; E2E keeps under `.mcp-coder/` |
| Q3 | MCP run pytest before `delegated_ok`? | **No** — planner verifies ([P1-ISS-013](../PHASE1_ISSUES.md), BL-310) |
| Q4 | Auto-review on step N+1? | **No** — optional ([BL-312](../BACKLOG.md)) |
| Q5 | Gatekeeper MCP (BL-151)? | Still deferred |

---

## Success criteria (experiment — partial met)

- [x] Multi-step feature completed via epic + step specs + delegates (expense-splitter).
- [x] Review loop improves step-2 spec clarity before implement.
- [x] Structured `outcome` + `delegate_mode` on logs and tool response.
- [x] Smaller executor prompts than full transcript inject (E2E: ~4.2k tok vs ~44k counterfactual dump×5; BL-001 to systematize).
- [ ] No critical nuance loss vs transcript — qualitative; 3–5 more tasks TBD.

---

## Why infra came first (P1-110–P1-140)

Phase 1 validated MCP → Aider → home storage → host adapter → sessions → transcript before spec product features. Spec experiment needed delegation logs, session reuse, and cursor rules sync — all in place before P1-151.

---

## Changelog

| Date | Note |
|------|------|
| 2026-06-05 | **Shipped** P1-150/151; layout v2; review loop; E2E; issues + backlog synced |
| 2026-06-04 | Deferred to P1-199; SpecStory removed from plan |
| 2026-06-03 | Initial note from planning chat |
