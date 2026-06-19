# mcp-coder guide

Onboarding, tutorials, and architecture reference for the mcp-coder stack (Phases 1–9 shipped; **Phase 10** active — see [PHASE10_MVP.md](../PHASE10_MVP.md)).

This folder is the output of **Phase 4.5** literacy work, updated after **Phase 5** (RAG), **Phase 6** (observability substrate), **Phase 7** (executor loop ownership + compile provenance), **Phase 8** (Aider inner-loop capture, ObservableModel), and **Phase 9** (universal HTTP proxy, write-always storage, replay/compare/inspect CLI, model registry, and the v2 boundary delegation viewer). Written from running and reading the code, not from specs alone.

Guide coverage now includes the shipped Phase 9 viewer architecture (`view_events[]` middleware + boundary table UI). Remaining docs debt is additive (extra walkthrough depth), not foundational accuracy gaps.

## Start here

| Document | What it covers |
|----------|---------------|
| [how-it-works.md](./how-it-works.md) | **The mental model.** Actors, delegation pipeline, context compiling, memory, trust model, invariants — re-read once in a while |
| [terminology.md](./terminology.md) | Glossary of terms used in docs, code, and JSONL logs |
| [code-structure.md](./code-structure.md) | Every directory and module — what it does, where to look for specific things, suggested reading order |

## Tutorials

*(Written as sessions progress — see [PHASE4.5_MVP.md](../PHASE4.5_MVP.md))*

| # | Title | Status |
|---|-------|--------|
| T-01 | [Setup & first delegation](./tutorials/01-setup-first-delegation.md) | done |
| T-02 | [Sessions, storage, and logs](./tutorials/02-sessions-storage-logs.md) | done |
| T-03 | [Specs: contract, paths, versioning](./tutorials/03-specs-contract-versioning.md) | done |
| T-04 | [Context compiler deep-dive](./tutorials/04-context-compiler.md) — `inspect-context`, `delegate --stop-after context`, full CLI round-trip on `$DEMO` | done |
| T-05 | [Workspace history](./tutorials/05-workspace-history.md) — checkpoints vs git, `mcp-coder history` CLI | done |
| T-06 | [The delegation pipeline](./tutorials/06-delegation-pipeline.md) — full `delegate_to_agent` flow, `mcp-coder delegate` CLI, `delegation_pipeline` JSONL (context detail: T-04) | done |
| T-07 | [Inspecting a delegation end-to-end](./tutorials/07-end-to-end-trace.md) | pending |

T-04 = how context is compiled (tiers, picker, builder). T-06 = every step on a real delegate (spec read → executor → post_gateway → report) and which flags turn each on — not a second context tutorial.

## Architecture reference

*(Written as sessions progress)*

| Document | Topic |
|----------|-------|
| [architecture/overview.md](./architecture/overview.md) | Layer map, locked decisions, delegation lifecycle, observability layer, known gaps — **living** (Phase 9 synced 2026-06-17) |
| [architecture/context-pipeline.md](./architecture/context-pipeline.md) | Picker → compiler tiers → builder LLM → Aider |
| [architecture/storage-layout.md](./architecture/storage-layout.md) | `~/.mcp-coder`, `workspace_history.db`, JSONL schema |
| [architecture/per-role-models.md](./architecture/per-role-models.md) | Model registry, role resolution, known gaps |
| [architecture/reality-vs-spec.md](./architecture/reality-vs-spec.md) | Where the real code differs from how things were described |

## Reference

| Document | Topic |
|----------|-------|
| [reference/mcp-tools.md](./reference/mcp-tools.md) | MCP tools — parameters, response fields, Cursor call rules |
| [reference/cli.md](./reference/cli.md) | CLI subcommands — all flags, examples, env vars |
| [env-vars.md](./env-vars.md) | Logging/observability/proxy env matrix and write-vs-display semantics |

## Gap analysis & RAG design

| Document | Topic |
|----------|-------|
| [../notes/rag-gap-analysis.md](../notes/rag-gap-analysis.md) | **Living** — corpora, litmus test, Phase 5 scope (shipped), open items (P5-005, BL-354) |
