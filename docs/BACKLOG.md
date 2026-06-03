# Project backlog

Items deferred from active phases, future ideas, and nice-to-haves. **Not** scheduled for the current worker session unless pulled into [PHASE1_MVP.md](./PHASE1_MVP.md).

Status: `idea` | `deferred` | `blocked` | `done`

---

## Deferred from Phase 1 (by design → later phases)

| ID | Item | Target | Notes |
|----|------|--------|-------|
| BL-001 | Owned context pipeline (summarize, rank, trim) | Phase 2 | Phase 1 is pass-through only |
| BL-002 | RAG / cross-session memory (`rag_search`, SQLite) | Phase 3 | See [IDEA.md](./IDEA.md) data models |
| BL-003 | Router / janitor LLM inside mcp-coder | Phase 2+ | Cheap orchestrator pattern |
| BL-004 | OpenCode adapter (subprocess) | Phase 2 or 1.x spike | Aider first; adapter pattern ready |
| BL-005 | Dual-mode CLI (`mcp-coder run …`) | Phase 2 | Same core as MCP |
| BL-006 | Context janitor, critic, test-writer sub-agents | Phase 4 | Composable one-shots |
| BL-007 | Multi-model ensemble | Phase 4+ | IDEA.md § future |
| BL-008 | Skills injection library | Phase 4+ | Topic → skill file |
| BL-009 | Explicit MCP tools: `continue_session`, `get_session_status` | Phase 3 | Phase 1 uses implicit session only |
| BL-010 | DB-backed session persistence | Phase 3 | Phase 1 = in-process only |

---

## Phase 1 optional (if time remains in MVP)

| ID | Item | Notes |
|----|------|-------|
| BL-101 | Dumb SpecStory tail truncation cap | `MCP_CODER_MAX_SPECSTORY_BYTES`; log `truncated` |
| BL-102 | Fallback `cheap_llm` session classifier | See [PHASES.md](./PHASES.md) § optional classifier |
| BL-103 | `inspect_delegations.py` CLI | Like proxy `inspect_logs.py` |
| BL-104 | Aider dry-run mode in MCP | Safe first tests |
| BL-105 | Default Aider → `context_optimizer_proxy` in setup template | Composes with sibling project |
| BL-106 | MCP progress notifications for long Aider runs | Avoid Cursor timeout perception |

---

## Host & integration

| ID | Item | Notes |
|----|------|-------|
| BL-201 | Claude Desktop as MCP host | Fallback context only unless export exists |
| BL-202 | Windsurf / other IDEs | Host matrix TBD |
| BL-203 | Read Cursor `agent-transcripts/*.jsonl` as context source | Alternative to SpecStory; fragile |
| BL-204 | Proxy intercept: save latest Cursor prompt from `context_optimizer_proxy` | Tight coupling; powerful for personal workflow |
| BL-205 | Cursor rule / skill snippet for routing to `delegate_to_agent` | Improve ~70–90% auto-routing |

---

## Observability & ops

| ID | Item | Notes |
|----|------|-------|
| BL-301 | Delegation log web UI | Proxy has `/ui`; optional later |
| BL-302 | Redaction policy doc for logs (secrets) | Required before sharing logs |
| BL-303 | Metrics export (Prometheus / statsd) | Enterprise-ish; low priority |

---

## Experiments to schedule (outcomes → backlog or phases)

| ID | Experiment | Outcome drives |
|----|------------|----------------|
| BL-401 | `always_new` vs `heuristic` vs `cheap_llm` (fallback) | Default session policy |
| BL-402 | SpecStory freshness window (5 vs 10 min) | Config defaults |
| BL-403 | Prompt size vs failure rate per model | Truncation cap, Phase 2 summarization priority |
| BL-404 | Cursor `target_files` reliability | Schema / inference rules |
| BL-405 | Tool name/description for routing | MCP tool marketing string |

---

## After Phase 1 — adapt our dev workflow to the product

| ID | Item | Notes |
|----|------|-------|
| BL-150 | **Spec-based delegation** — structured task spec instead of / in addition to full chat transcript | See [notes/spec-based-development.md](./notes/spec-based-development.md). May reduce SpecStory dependency. |
| BL-151 | Mirror `delegations.jsonl` + local task spec § Results in product UX | Same closed loop as `docs/tasks/` workflow |

---

## Ideas (unscoped)

| ID | Item |
|----|------|
| BL-501 | Job ID + async delegation (poll / MCP notification) for long Aider runs |
| BL-502 | Git worktree / dry-run diff return to Cursor instead of direct write |
| BL-503 | Grade executor output with cheap model before returning to Cursor |
| BL-504 | Workspace-level `.mcp-coder/config.yml` |
| BL-505 | Support non-Cursor transcript exporters (generic `transcript.md` watch folder) |

---

## Done

_Move items here when completed._

| ID | Item | Completed |
|----|------|-----------|
| — | — | — |
