<!--
  STEWARDSHIP — Phase 15 master session handoff. See docs/VISION_DOCS.md.

  - This is the bootstrap prompt for a NEW master session that will plan Phase 15 work.
  - It is onboarding-first: the session should orient itself before writing any task spec.
  - Specs are built ONE AT A TIME, after discussion with the user to refine details.
  - Workers implement from docs/tasks/P15-*.md; the master session writes those specs.
  - Do NOT edit IDEA.md, PHASES.md, PHASE*_MVP.md (frozen), or VISION_DOCS.md without user ask.
-->

# Phase 15 master session bootstrap

**Created:** 2026-06-26
**Status:** Active — onboarding handoff for a new master session.
**Purpose:** Orient a fresh master session on the mcp-coder project, its current state, the codebase layout, and the master session's own role/rules — so it can then plan Phase 15 work **one task spec at a time**, after discussion with the user. Also instruct the master session on how to help the user create worker prompts (planner→executor pattern).
**PM board:** [PHASE15_MVP.md](../../PHASE15_MVP.md)
**Issues:** [PHASE15_ISSUES.md](../../PHASE15_ISSUES.md)
**Prior handoffs:** [phase14-master-session-bootstrap.md](./phase14-master-session-bootstrap.md) · [phase11-master-session-bootstrap.md](./phase11-master-session-bootstrap.md) · [archive index](./README.md)

---

## How to use this document

This file is the **handoff prompt**. The section below labeled **"FIRST PROMPT — paste into a new master session"** is the verbatim opening message to send to a new master session in a fresh Cursor chat. Everything above and below it is context for the human.

The first prompt is deliberately **onboarding-only**: it tells the new session where things live, what its role is, and what Phase 15 is about — but it does **not** ask the session to start writing specs. Specs are written one at a time, after the user and the session talk through each milestone's details.

---

## FIRST PROMPT — paste into a new master session

> You are the **master session** for the `mcp-coder` project. This is an onboarding message. Read it carefully, orient yourself, and **do not start writing task specs yet**. We will plan each task one at a time after talking through the details.
>
> ### What this project is
>
> `mcp-coder` is a task-level coding-agent orchestration layer that sits between an MCP host (Cursor, Claude Code, etc.) and an executor backend (Aider-first). The core idea: stateless coding agents lose cross-session memory and task-level context — `mcp-coder` adds a persistent **Supervisor Agent** that owns the delegation lifecycle, project state, checkpointing, pause/resume, and sub-agent coordination (planner, clarity, reviewer, builder). It is a Python project (`core/` package + `server/` MCP entry + `main.py` CLI) shipping as an MCP server.
>
> The product vision lives in `docs/IDEA.md` (tier 0 — do not edit). The phase delivery plan lives in `docs/PHASES.md`. We are now in **Phase 15**.
>
> ### Your role as master session
>
> You are **not** a worker. Workers implement from `docs/tasks/P15-*.md` specs and report in § Results. Your job:
>
> 1. **Plan Phase 15** by writing task specs (`docs/tasks/P15-*.md`), **one at a time**, after discussing the details with me for each.
> 2. Keep `docs/PHASE15_MVP.md` (the PM board) and `docs/PHASE15_ISSUES.md` in sync as work progresses.
> 3. Review worker § Results when they return; promote findings to issues or backlog.
> 4. Do **not** edit tier 0–2 vision docs (`IDEA`, `PHASES`, `PHASE*_MVP` frozen ones, `VISION_DOCS`) without my explicit ask.
> 5. When a decision has trade-offs or is ambiguous, **stop and ask me** — do not guess.
>
> ### How to help me create worker prompts (planner → executor pattern)
>
> When we agree on a milestone's scope and you write the task spec (`docs/tasks/P15-*.md`), the spec itself is what a worker session reads. But workers are often run in **separate Cursor chats** (fresh context), so I will paste a **worker prompt** into those chats. Your job is to help me craft that prompt. The pattern:
>
> 1. **Spec-first:** the `docs/tasks/P15-*.md` spec is the single source of truth. The worker prompt is a *pointer* to the spec + any session-specific instructions (model to use, test conventions, what to report in § Results). The worker prompt should **not** duplicate the spec's content — it should say "read `docs/tasks/P15-XXX.md` and implement it."
> 2. **Plan→implement split (optional):** for larger milestones, we may split into a planner worker (reads the spec, produces a detailed implementation plan in § Results) and an executor worker (reads the spec + the planner's § Results, implements). When we do this, you write **two** worker prompts — one for the planner, one for the executor. The planner prompt asks for a plan only; the executor prompt references both the spec and the planner's plan.
> 3. **Single-go (optional):** for smaller milestones or when we're confident the scope is clear, we skip the split and write one worker prompt that does plan + implement in one session. The prompt still points to the spec.
> 4. **Worker prompt structure:** each worker prompt you help me write should include: (a) "read `docs/tasks/P15-XXX.md`", (b) the model to use if specific, (c) any conventions (test naming, where to report results), (d) "fill § Results in the spec file when done", (e) any guardrails ("do not edit files outside the spec's files policy", "do not build new tools — see infra-first table").
> 5. **Ask before generating:** when I say "write the worker prompt for P15-XXX," confirm with me whether it's plan→implement split or single-go, and which model, before you generate the prompt text.
>
> ### Where things live (codebase map)
>
> Read these to orient yourself before anything else:
>
> - `docs/VISION_DOCS.md` — the canonical doc map; read this first to understand what's vision vs operational.
> - `docs/PHASE15_MVP.md` — **your PM board.** Three milestones: P15-000, P15-001, P15-002. This is the source of truth for Phase 15 scope. Read the **infra-first principle** table carefully — it lists every existing capability workers must reuse.
> - `docs/PHASE15_ISSUES.md` — issue log; file P15-ISS-* here as workers find bugs.
> - `docs/notes/supervisor-agent-architecture.md` — active design note for the Supervisor (persistent project agent, state model, pause/resume, project memory, tool-calling helper loop).
> - `docs/notes/system-design-overview.md` — refined design map; how the notes fit together.
> - `docs/guide/architecture/overview.md` — guide-level architecture overview.
> - `docs/guide/env-vars.md` — reference for all `MCP_CODER_*` env vars.
> - `docs/BACKLOG.md` — backlog index; full text in `docs/backlog/deferred.md` + `done.md`.
>
> Code layout (the directories you will touch in Phase 15):
>
> - `core/context/` — prompt assembly: `planner_prompt.py`, `reviewer_prompt.py`, `builder_prompt.py`, `clarity_prompt.py`, `spec_validation_prompt.py`, `architect_prompt.py`, `summary.py` (executor prompt assembly), `package.py` (ContextPackage). **P15-000 Slices A + B live here.** New file: `core/context/role_rules.py`.
> - `core/engine/` — helper LLM engines: `aider_engine.py` (executor + `EXECUTOR_PULL_HINT_BLOCK`), `planner_pass_llm.py`, `reviewer_llm.py`, `clarity_llm.py`, `spec_validation_llm.py`, `context_builder_llm.py`, `owned_helper_llm.py` (one-shot helper call — needs `system_prompt` param), `supervisor.py` (confirm_ask LLM), `supervisor_agent.py` (inter-turn decision), `supervisor_tool_runner.py` (tool-calling loop — already has `read_file`, `get_project_state`, `get_delegation_history`, `get_reviewer_findings` registered). **P15-000 Slice C + P15-001 + P15-002 live here.**
> - `core/observability/` — `trace.py`, `gateway.py` (LlmGateway — the actual litellm call), `litellm_callback.py`. P15-000 Slice B touches the gateway's `messages` handling.
> - `core/workspace/` — `history_query.py` (`build_delegation_diff`, `list_delegations`). **P15-001 Slice B reuses `build_delegation_diff`.**
> - `core/state/` — `project_state.py` (`ProjectState.to_summary()` — already exists from P14-001). **P15-000 Slice C reuses this.**
> - `server/mcp_server.py` — thin MCP entry; wires `context_package.brief` to the executor. **P15-001 Slice C needs the server to pass the builder brief to the supervisor decision.**
> - `tests/` — large test suite; each milestone adds tests here.
>
> ### Phase 15 in one sentence
>
> Make the supervisor reason (not pattern-match), make the planner investigate (not one-shot), and build a prompt management layer where every LLM call follows consistent rules — all by wiring existing infrastructure, not building new tools.
>
> ### Phase 15 milestones (high-level — details in PHASE15_MVP.md)
>
> | Order | Milestone | One-line | Status |
> |-------|-----------|----------|--------|
> | 1 | **P15-000** | Prompt management layer + executor prompt enrichment (`role_rules.py` + split helper preambles into system+user + enrich executor prompt) | pending |
> | 2 | **P15-001** | Supervisor intelligence v1 (make `_llm_decide` default + inject diff + builder brief into decision prompt) | pending |
> | 3 | **P15-002** | Planner agentic loop v1 (reuse `SupervisorToolRunner` with existing tools; bounded to 3 iterations) | pending |
>
> The order is deliberate: P15-000 first (prompt foundation + lowest-hanging fruit — every LLM call benefits), then P15-001 (supervisor reasoning), then P15-002 (planner loop — biggest structural change). **Phase gate:** P15-000 + P15-001 is the minimum for MVP dogfood. P15-002 is desirable but not blocking.
>
> ### The infra-first principle (critical — read before planning)
>
> Phase 15 is **infra-first**. Workers must reuse existing infrastructure, not build new tools. The table in `docs/PHASE15_MVP.md` lists every existing capability:
>
> | Capability | Already exists? | Where |
> |------------|-----------------|-------|
> | `read_file` tool | **Yes** | `supervisor_tool_runner.py` |
> | `get_project_state` tool | **Yes** | `supervisor_tool_runner.py` |
> | `get_delegation_history` tool | **Yes** | `supervisor_tool_runner.py` |
> | `get_reviewer_findings` tool | **Yes** | `supervisor_tool_runner.py` |
> | `build_delegation_diff` | **Yes** | `core/workspace/history_query.py` |
> | `SupervisorToolRunner` (tool-calling loop) | **Yes** | `core/engine/supervisor_tool_runner.py` |
> | `run_owned_helper_completion` (one-shot) | **Yes** | `core/engine/owned_helper_llm.py` |
>
> **If a worker finds itself writing a new tool function, it must stop and file a P15-ISS-* rather than building it inline.** When you write task specs, include the infra-first table and this instruction.
>
> ### The prompt management abstraction (P15-000 core concept)
>
> Every LLM call is an assembly of prompt fragments:
>
> ```
> system message = role_definition + shared_rules + role_rules + [future: skills]
> user message   = task_context
> ```
>
> Today, all fragments are mixed into a single user message per helper (preamble + context concatenated). P15-000 separates them:
> - `core/context/role_rules.py` — `build_role_rules(role)` returns shared base rules + role-specific rules. Single source of truth.
> - Helpers send rules as a **system message** and task context as a **user message** (not one concatenated blob).
> - `build_role_rules(role)` is the **seam** for future dynamic skills (topic-based, project-state-driven, RAG-retrieved) — call sites don't change when skills arrive later.
> - For the executor (Aider), the same assembly happens at `model.system_prompt_prefix` (Aider prepends to its `main_system`); Aider's own system prompt stays intact.
>
> ### What Phase 14 shipped (the foundation Phase 15 builds on)
>
> - **Supervisor context window v1** (P14-001) — `evaluate()` now receives spec contract + plan + decision log + output tail + compact `project_state` summary + structured `target_files`.
> - **Control loop + autonomous interception v1** (P14-002) — file-in-spec `confirm_ask` auto-approved/denied; reviewer findings injected into turn 2+ decision prompt.
> - **Helper LLM + config audit** (P14-003 3b+3c) — reasoning token capture verified; helper `max_tokens` bumped; `MCP_CODER_CAPTURE_REASONING` gate confirmed.
> - **Logging depth + viewer parity** (P14-004) — all 24 event types render in the viewer; 11 ISS items closed; swallow sites made visible.
> - **BL-557 executor reasoning overlay** — executor `llm_call` now carries `reasoning_tokens` from the litellm callback accumulator.
>
> ### What Phase 14 left partial (Phase 15 picks up)
>
> - **BL-525 (Planner as agent)** — planner is still one-shot (`run_owned_helper_completion`). → P15-002.
> - **BL-529 (Supervisor context)** — supervisor has context but `_policy_decide` (pattern-match) is still the default when `max_turns==1`. → P15-001.
> - **BL-543 (Context lifecycle)** — executor prompt doesn't carry the plan or project state explicitly. → P15-000.
> - **Helper prompts** — preambles are mixed into user messages; shared rules duplicated across 6 files. → P15-000.
>
> ### What I want from you right now (onboarding only)
>
> 1. Read `docs/PHASE15_MVP.md` (especially the infra-first table and P15-000 scope), `docs/notes/supervisor-agent-architecture.md`, and skim `core/engine/supervisor_tool_runner.py` + `core/context/planner_prompt.py` + `core/engine/aider_engine.py` (the `EXECUTOR_PULL_HINT_BLOCK`).
> 2. Give me a short orientation summary in your own words: (a) what the prompt management layer is and why `build_role_rules(role)` is the seam for future skills, (b) what "make `_llm_decide` the default" means and why it's low-risk, (c) how the planner reuses `SupervisorToolRunner` instead of getting a new loop, and (d) any questions you have before we start planning.
>
> **Do not write any `docs/tasks/P15-*.md` spec yet.** We will plan P15-000 first, together, after your orientation summary. I want to refine the details of each spec with you before you write it.

---

## Planning protocol (for the human, after onboarding)

Once the new session returns its orientation summary:

1. **Talk through P15-000 first.** The user and the session refine: which helper prompts to enrich and how, what the shared base rules should say, how to wire `run_owned_helper_completion` to accept `system_prompt`, what the executor `system_prompt_prefix` should contain, where `## Planner plan` goes in the executor user prompt.
2. **Session writes `docs/tasks/P15-000.md`** using `docs/TASK_SPEC_TEMPLATE.md` as the base. Self-contained: goal, scope, files policy, acceptance, pointers to design notes, infra-first table.
3. **Session helps craft the worker prompt** (see "How to help me create worker prompts" above). Confirm: plan→implement split or single-go? Which model? Then generate the prompt text.
4. **A worker session picks up P15-000**, implements, fills § Results.
5. **Master session reviews § Results**, updates `PHASE15_MVP.md` status, files any P15-ISS-*.
6. **Repeat for P15-001**, then P15-002 — each preceded by a planning conversation.

One spec at a time. No batch-writing all three specs upfront — the details of later milestones depend on what earlier milestones surface.

---

## Cross-phase context the new session needs

### The prompt audit findings (from Phase 14 + this planning session)

A full prompt audit was performed during Phase 15 planning. Key findings that inform P15-000:

| Role | File | One-shot or loop? | Key gap |
|------|------|-------------------|---------|
| Planner | `core/context/planner_prompt.py` | One-shot | No tools — can't read files to verify plan feasibility |
| Builder | `core/context/builder_prompt.py` | One-shot | Most sophisticated prompt; budget-aware; but still one-shot |
| Reviewer | `core/context/reviewer_prompt.py` | One-shot | "Junior code reviewer" framing — can't check spec compliance |
| Clarity | `core/context/clarity_prompt.py` | One-shot (retry preamble) | Good design — has retry preamble; could surface project state |
| Spec validation | `core/context/spec_validation_prompt.py` | One-shot | Advisory only |
| Supervisor (confirm_ask) | `core/engine/supervisor.py` | Tool-calling loop | Gets spec + plan but NOT the diff or current file contents |
| Supervisor (inter-turn) | `core/engine/supervisor_agent.py` | Tool-calling loop (only when `max_turns>1`) | **Blind to the diff** — gets file names + stdout tail but can't see what changed |
| Executor (Aider) | `assemble_prompt()` + `EXECUTOR_PULL_HINT_BLOCK` | Aider's own loop | System prompt is minimal (pull hint only); no plan section, no project state |

All helper preambles put rules in the **user message** (concatenated with context). P15-000 moves rules to the **system message**.

### The "dumb supervisor" problem (P15-001 core motivation)

`SupervisorAgent._decide()` defaults to `_policy_decide` when `max_turns==1` (almost always):

```python
def _decide(self, ctx: SupervisorTurnContext) -> SupervisorTurnDecision:
    if self._decision_fn is not None:
        return self._decision_fn(ctx)
    if self._max_turns == 1:
        return self._policy_decide(ctx)   # ← pattern-match shortcut
    return self._llm_decide(ctx)           # ← LLM path, only when max_turns>1
```

`_policy_decide` is pure pattern-matching: `success→done`, `reviewer issues→rerun`, `else→done`. The LLM path (`_llm_decide`) exists, is tested, and falls back to `_policy_decide` on any failure — so making it the default is low-risk.

### The planner one-shot problem (P15-002 core motivation)

`planner_pass_llm.py` calls `run_owned_helper_completion(messages, model=resolved)` — a single LLM call. No tool calls, no file reads, no iteration. But `SupervisorToolRunner` (already built, already tested) is a tool-calling loop with `read_file` + `get_project_state` + `get_delegation_history` registered. The planner can reuse it instead of getting a new loop.

### Phase 16 (post-MVP dogfood)

Phase 15 is the last dev phase before **external MVP dogfood** on a real project:

- If the supervisor reasons and the planner investigates → **adopt MVP usage** on an external project.
- If the supervisor still pattern-matches and the planner is still one-shot → **pause MVP usage**, keep developing.
- The dogfood pain log feeds back into Phase 16-style improvements.

---

## Non-goals for the master session (do not pull these into Phase 15)

- Dynamic skill injection (topic-based, project-state-driven, RAG-retrieved) — seam in place via `build_role_rules(role)`, but skills not populated. Post-Phase-15.
- RAG-fed supervisor context (BL-557 cross-model reasoning sharing layer)
- Full autonomous interception policy (BL-547 full vision — P14-002 shipped v1)
- CTO/Architect role (BL-526)
- Executor session adaptation (BL-546)
- Full mutable planning behavior (BL-525 full — P15-002 ships v1 only)
- RAG-aware planner (`rag_search` as a planner tool — defer)
- Product UI or spec MCP tools
- Replanning phases or contradicting `IDEA.md`

These stay in backlog. Phase 15 wires the intelligence spine, not the vision surface.
