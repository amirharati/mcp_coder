<!--
  STEWARDSHIP — Phase 14 master session handoff. See docs/VISION_DOCS.md.

  - This is the bootstrap prompt for a NEW master session that will plan Phase 14 work.
  - It is onboarding-first: the session should orient itself before writing any task spec.
  - Specs are built ONE AT A TIME, after discussion with the user to refine details.
  - Workers implement from docs/tasks/P14-*.md; the master session writes those specs.
  - Do NOT edit IDEA.md, PHASES.md, PHASE*_MVP.md (frozen), or VISION_DOCS.md without user ask.
-->

# Phase 14 master session bootstrap

**Created:** 2026-06-23
**Status:** Active — onboarding handoff for a new master session.
**Purpose:** Orient a fresh master session on the mcp-coder project, its current state, the codebase layout, and the master session's own role/rules — so it can then plan Phase 14 work **one task spec at a time**, after discussion with the user.
**PM board:** [PHASE14_MVP.md](../../PHASE14_MVP.md)
**Issues:** [PHASE14_ISSUES.md](../../PHASE14_ISSUES.md)
**Prior handoffs:** [phase11-master-session-bootstrap.md](./phase11-master-session-bootstrap.md) · [phase10-master-session-bootstrap.md](./phase10-master-session-bootstrap.md) · [archive index](./README.md)

---

## How to use this document

This file is the **handoff prompt**. The section below labeled **"FIRST PROMPT — paste into a new master session"** is the verbatim opening message to send to a new master session in a fresh Cursor chat. Everything above and below it is context for the human.

The first prompt is deliberately **onboarding-only**: it tells the new session where things live, what its role is, and what Phase 14 is about — but it does **not** ask the session to start writing specs. Specs are written one at a time, after the user and the session talk through each milestone's details.

---

## FIRST PROMPT — paste into a new master session

> You are the **master session** for the `mcp-coder` project. This is an onboarding message. Read it carefully, orient yourself, and **do not start writing task specs yet**. We will plan each task one at a time after talking through the details.
>
> ### What this project is
>
> `mcp-coder` is a task-level coding-agent orchestration layer that sits between an MCP host (Cursor, Claude Code, etc.) and an executor backend (Aider-first). The core idea: stateless coding agents lose cross-session memory and task-level context — `mcp-coder` adds a persistent **Supervisor Agent** that owns the delegation lifecycle, project state, checkpointing, pause/resume, and sub-agent coordination (planner, clarity, reviewer, builder). It is a Python project (`core/` package + `server/` MCP entry + `main.py` CLI) shipping as an MCP server.
>
> The product vision lives in `docs/IDEA.md` (tier 0 — do not edit). The phase delivery plan lives in `docs/PHASES.md`. We are now in **Phase 14**.
>
> ### Your role as master session
>
> You are **not** a worker. Workers implement from `docs/tasks/P14-*.md` specs and report in § Results. Your job:
>
> 1. **Plan Phase 14** by writing task specs (`docs/tasks/P14-*.md`), **one at a time**, after discussing the details with me for each.
> 2. Keep `docs/PHASE14_MVP.md` (the PM board) and `docs/PHASE14_ISSUES.md` in sync as work progresses.
> 3. Review worker § Results when they return; promote findings to issues or backlog.
> 4. Do **not** edit tier 0–2 vision docs (`IDEA`, `PHASES`, `PHASE*_MVP` frozen ones, `VISION_DOCS`) without my explicit ask.
> 5. When a decision has trade-offs or is ambiguous, **stop and ask me** — do not guess.
>
> ### Where things live (codebase map)
>
> Read these to orient yourself before anything else:
>
> - `docs/VISION_DOCS.md` — the canonical doc map; read this first to understand what's vision vs operational.
> - `docs/PHASE14_MVP.md` — **your PM board.** Four milestones: P14-003, P14-001, P14-002, P14-004. This is the source of truth for Phase 14 scope.
> - `docs/PHASE14_ISSUES.md` — issue log; file P14-ISS-* here as workers find bugs.
> - `docs/notes/supervisor-agent-architecture.md` — active design note for the Supervisor (persistent project agent, state model, pause/resume, project memory).
> - `docs/notes/system-design-overview.md` — refined design map; how the notes fit together.
> - `docs/guide/architecture/overview.md` — guide-level architecture overview (layer map, delegation lifecycle, state files).
> - `docs/guide/env-vars.md` — reference for all `MCP_CODER_*` env vars (will be relevant for P14-003 config audit).
> - `docs/BACKLOG.md` — backlog index; full text in `docs/backlog/deferred.md` + `done.md`.
>
> Code layout (the directories you will touch in Phase 14):
>
> - `core/engine/` — executor + helper LLM engines: `aider_engine.py`, `planner_pass_llm.py`, `reviewer_llm.py`, `clarity_llm.py`, `architect_pass_llm.py`, `context_builder_llm.py`, `observable_model.py`, `owned_helper_llm.py`, `interception_profile.py`, `question_registry.py`, `reviewer_findings_classifier.py`. **P14-003 prompt/config audit lives here.**
> - `core/pipeline/` — `phases.py` (preloop/loop/postloop orchestration). **P14-002 control loop lives here.**
> - `core/state/` — `project_state.py`, `agent_checkpoint.py`, `supervisor_state.py`, `project_key.py`. **P14-001 context block reads from `project_state.py`.**
> - `core/specs/` — `read.py`, `files_contract.py`, `sections.py`, `modes.py`, `outcome.py`. **P14-001 reads the spec contract from here.**
> - `core/observability/` — `trace.py`, `gateway.py`, `litellm_callback.py`, `reasoning_buffer.py`, `bootstrap.py`, `context.py`, `stats.py`, `training_capture.py`. **P14-004 logging audit + reasoning token capture lives here.**
> - `core/proxy/` — `local_proxy.py`, `routing.py`. **P14-003c streaming/thinking-token wiring; P14-004 capture parity.**
> - `core/config/` — `env.py`, `models.py`, `role_models.py`, `model_registry.py`, `providers.py`, `openrouter_models.py`, `aider_runtime.py`, plus role-specific config (`planner_pass.py`, `review_model.py`, `architect_pass.py`, `spec_validation.py`, `context_builder.py`). **P14-003 config audit reads/writes here.**
> - `core/context/` — `assemble.py`, `budget.py`, `helper_llm_pipeline.py`, plus prompt files (`planner_prompt.py`, `reviewer_prompt.py`, `builder_prompt.py`, `clarity_prompt.py`, `architect_prompt.py`). **P14-003 prompt audit reads/writes here.**
> - `core/logging/` — `delegation_log.py`, `read_delegations.py`, `server_log.py`. **P14-004 on-disk log audit.**
> - `core/cli/delegation_view_enrich.py` — the viewer enrichment layer. **P14-004 viewer parity audit lives here.**
> - `core/session/` — `executor_cache.py`, `policy.py`, `store.py`, `activity.py` (Supervisor session state).
> - `server/mcp_server.py` — thin MCP entry; not the orchestration owner.
> - `tests/` — large test suite; P14-004 will add audit fixtures here.
>
> ### Phase 14 in one sentence
>
> Make the Supervisor actually think — give it context to reason over, a control loop that uses that context, clean helper inputs, and a logging stack that captures and shows everything it does. This is a **trust phase**, not a feature phase. Output feeds the Phase 15 MVP usage decision (adopt or pause).
>
> ### Phase 14 milestones (high-level — details in PHASE14_MVP.md)
>
> | Order | Milestone | One-line | Status |
> |-------|-----------|----------|--------|
> | 1 | **P14-003** | Helper LLM + prompt + config audit (incl. streaming/thinking-token wiring) | pending |
> | 2 | **P14-001** | Supervisor context window v1 (spec + plan + decision log + output tail + project_state) | pending |
> | 3 | **P14-002** | Control loop — autonomous interception v1 + reviewer findings injection | pending |
> | 4 | **P14-004** | Logging depth audit + viewer parity (capture completeness, viewer find-and-fix, cleanliness find-and-flag) | pending |
>
> The order is deliberate: P14-003 first (clean inputs + test traffic), then P14-001 (context), then P14-002 (control loop uses context), then P14-004 (audit everything produced). Partial completion is acceptable — the goal is "meaningfully closer to viable MVP," not "100% solved."
>
> ### What I want from you right now (onboarding only)
>
> 1. Read `docs/PHASE14_MVP.md`, `docs/notes/supervisor-agent-architecture.md`, and `docs/guide/architecture/overview.md` to orient on Phase 14 scope and the Supervisor's current shape.
> 2. Skim the code directories above to confirm where each milestone's work would land.
> 3. Give me a short orientation summary in your own words: (a) what the Supervisor currently does vs. what Phase 14 makes it do, (b) where the logging stack currently has gaps that P14-004 would audit, and (c) any questions you have before we start planning.
>
> **Do not write any `docs/tasks/P14-*.md` spec yet.** We will plan P14-003 first, together, after your orientation summary. I want to refine the details of each spec with you before you write it.

---

## Planning protocol (for the human, after onboarding)

Once the new session returns its orientation summary:

1. **Talk through P14-003 first.** The user and the session refine: which prompts to audit, which configs to verify, which provider to use for the thinking-token capture test, what counts as "obvious weakness fixed" vs. "filed as P14-ISS-*."
2. **Session writes `docs/tasks/P14-003.md`** using `docs/TASK_SPEC_TEMPLATE.md` as the base. Self-contained: goal, scope, files policy, acceptance, pointers to design notes.
3. **A worker session picks up P14-003**, implements, fills § Results.
4. **Master session reviews § Results**, updates `PHASE14_MVP.md` status, files any P14-ISS-*.
5. **Repeat for P14-001**, then P14-002, then P14-004 — each preceded by a planning conversation.

One spec at a time. No batch-writing all four specs upfront — the details of later milestones depend on what earlier milestones surface.

---

## Cross-phase context the new session needs

### What Phase 13 shipped (the foundation Phase 14 builds on)

- **Lifecycle envelope** — unified `delegation_lifecycle_start/end` + `phase_start/end` + `supervisor_paused/resumed` trace events.
- **Agent checkpoint** (`agent_state.json`) — non-expiring steady-state snapshot; Supervisor rehydrates across process restarts.
- **Supervisor state** (`supervisor_states/<token>.json`) — expiring in-flight pause payload for intra-delegation resume.
- **Project state** (`project_state.json`) — durable cross-delegation memory: decisions, risks, hot areas, reviewer finding summaries.
- **Pause/resume verified in dogfood** — CLI session `28fbe283`; both clarity-block and escalation paths work. **Note:** the trace file for `28fbe283` is not currently on disk under `.mcp-coder/projects/`; the reference is to the session id from the P13 dogfood, not a reusable baseline. P14-004 workers generate fresh traffic and save their capture-complete run's trace path in § Results as the new baseline.
- **Reviewer/classifier tail-hardened** — false-critical reduction; typed-cause surfacing for unknown-loop failures.
- **Docs consolidated** — guide synced to Phase 12/13; tutorials T-02/T-06 updated; T-07/T-08 stubs created.

### What Phase 13 left partial (Phase 14 picks up)

- **BL-529 (Supervisor context)** — partial; tier-1 base context shipped but `evaluate()` still sees almost nothing per decision. → P14-001.
- **BL-543 (context lifecycle)** — partial; planner pre-injection shipped but turn-2+ continuation brief + reviewer findings injection not done. → P14-002.
- **BL-547 (autonomous interception)** — not started; every `confirm_ask` still escalates. → P14-002.
- **BL-534/536 (logging depth)** — capture substrate is solid but never systematically audited end-to-end; viewer parity unverified after P13-008 fixes. → P14-004.
- **BL-556 (dogfood integration tests)** — deferred from P13-003; not Phase 14 scope but P14-004 audit fixtures may overlap.

### The LLM config concern (from the user, explicit)

One thing Phase 14 must specifically check: **proper LLM configs for both helpers and Aider**, including streaming options. Some LLMs (especially via OpenRouter) have different options — e.g. the `reasoning` param for Anthropic models, `include_usage` for streaming — that may need to be enabled to capture "hidden thinking tokens" or enable certain capabilities. We have done some work in this regard but not fully. P14-003 slice 3b/3c owns this end-to-end.

### Phase 15 (the fork)

Phase 14 is the last dev phase before the **adopt-or-pause fork**:

- If after P14 the Supervisor can intercept easy `confirm_ask` and logs show its reasoning → **adopt MVP usage** on an external project in Phase 15.
- If interception is still mostly escalating and logs are opaque → **pause MVP usage**, keep developing.
- "Pause" means pause MVP usage, not abort the project. Development continues; we use the latest version as we improve.

Phase 15 is validation, not development.

---

## Non-goals for the master session (do not pull these into Phase 14)

- Full autonomous interception policy (BL-547 full vision — Phase 14 ships v1 only)
- Full continuation brief assembly (BL-543 full — Phase 14 ships reviewer injection start only)
- Executor-pull RAG sidecar (BL-354)
- Planner-as-full-agent loop (BL-525)
- Architect/CTO role (BL-526)
- Product UI or spec MCP tools
- Replanning phases or contradicting `IDEA.md`

These stay in backlog. Phase 14 deepens the spine, not the vision surface.
