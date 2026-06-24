# mcp-coder guide

Onboarding, tutorials, and architecture reference for the mcp-coder stack (Phases 1–13 shipped; see [PHASES.md](../PHASES.md)).

This folder covers Phases 1–13. It was last substantially updated after **Phase 12/13** (persistent Supervisor agent, project state, agent checkpoint, pause/resume lifecycle, lifecycle envelope events). Written from running and reading the code, not from specs alone.

## Start here

| Document | What it covers |
|----------|---------------|
| [how-it-works.md](../how-it-works.md) | **The mental model.** Actors, pipeline, memory, Supervisor — re-read after a break |
| [terminology.md](./terminology.md) | Glossary — includes Supervisor, project state, lifecycle envelope terms |
| [code-structure.md](./code-structure.md) | Every directory and module — what it does, where to look (Phases 1–13) |

## Tutorials

*(Written as sessions progress — see [PHASE4.5_MVP.md](../PHASE4.5_MVP.md))*

| # | Title | Status |
|---|-------|--------|
| T-01 | [Setup & first delegation](./tutorials/01-setup-first-delegation.md) | done |
| T-02 | [Sessions, storage, and logs](./tutorials/02-sessions-storage-logs.md) — storage layout, JSONL records, project state files | done |
| T-03 | [Specs: contract, paths, versioning](./tutorials/03-specs-contract-versioning.md) | done |
| T-04 | [Context compiler deep-dive](./tutorials/04-context-compiler.md) — `inspect-context`, `delegate --stop-after context`, full CLI round-trip on `$DEMO` | done |
| T-05 | [Workspace history](./tutorials/05-workspace-history.md) — checkpoints vs git, `mcp-coder history` CLI | done |
| T-06 | [The delegation pipeline](./tutorials/06-delegation-pipeline.md) — full `delegate_to_agent` flow, supervisor loop, lifecycle envelope, pause/resume | done |
| T-07 | [Inspecting a delegation end-to-end](./tutorials/07-end-to-end-trace.md) — JSONL → trace → history → spec report in one narrative | stub |
| T-08 | [Supervisor: pause, resume, and project memory](./tutorials/08-supervisor-pause-resume.md) — `project_state`, `agent_state`, escalation, resume_token | stub |

T-04 = how context is compiled (tiers, picker, builder). T-06 = every step on a real delegate (spec read → executor → post_gateway → report) and which flags turn each on. T-07/T-08 are planned stubs — content to be filled in a future session.

## Architecture reference

*(Written as sessions progress)*

| Document | Topic |
|----------|-------|
| [architecture/overview.md](./architecture/overview.md) | Layer map, locked decisions, delegation lifecycle (lifecycle envelope), Supervisor persistent state, known gaps — **living** (Phase 12/13 synced 2026-06-23) |
| [architecture/context-pipeline.md](./architecture/context-pipeline.md) | Picker → compiler tiers → builder LLM → Aider |
| [architecture/storage-layout.md](./architecture/storage-layout.md) | `~/.mcp-coder`, `workspace_history.db`, JSONL schema |
| [architecture/per-role-models.md](./architecture/per-role-models.md) | Model registry, role resolution, known gaps |
| [architecture/reality-vs-spec.md](./architecture/reality-vs-spec.md) | Where the real code differs from how things were described |

## Reference

| Document | Topic |
|----------|-------|
| [reference/mcp-tools.md](./reference/mcp-tools.md) | MCP tools — `delegate_to_agent`, pause/resume, history, search |
| [reference/cli.md](./reference/cli.md) | CLI — delegate, inspect, replay, trace, view, history, search, `ps`/`kill` |
| [env-vars.md](./env-vars.md) | Logging/observability/proxy env matrix |

## Gap analysis & RAG design

| Document | Topic |
|----------|-------|
| [../notes/retrieval-and-rag-strategy.md](../notes/retrieval-and-rag-strategy.md) | **Living** — corpora, litmus test, Phase 5 scope (shipped), open items (P5-005, BL-354) |
