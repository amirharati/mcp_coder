# mcp-coder guide

Onboarding, tutorials, and architecture reference for the mcp-coder stack (Phases 1–4).

This folder is the output of **Phase 4.5** — written from actually running and reading the code, not from specs alone.

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
| [architecture/overview.md](./architecture/overview.md) | Layer map — host / MCP / compiler / engine / storage |
| [architecture/context-pipeline.md](./architecture/context-pipeline.md) | Picker → compiler tiers → builder LLM → Aider |
| [architecture/storage-layout.md](./architecture/storage-layout.md) | `~/.mcp-coder`, `workspace_history.db`, JSONL schema |
| [architecture/per-role-models.md](./architecture/per-role-models.md) | Model registry, role resolution, known gaps |
| [architecture/reality-vs-spec.md](./architecture/reality-vs-spec.md) | Where the real code differs from how things were described |

## Gap analysis

| Document | Topic |
|----------|-------|
| [gap-analysis.md](./gap-analysis.md) | Findings → Phase 5 planning input |
| [../notes/rag-gap-analysis.md](../notes/rag-gap-analysis.md) | **Living** — RAG vs not-RAG, four corpora, observability coupling (T-04 pass) |
