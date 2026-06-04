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
| BL-004 | OpenCode adapter (subprocess) | Phase 2 or spike | Aider first; adapter pattern ready |
| BL-005 | Dual-mode CLI (`mcp-coder run …`) | Phase 2 | Same core as MCP |
| BL-006 | Context janitor, critic, test-writer sub-agents | Phase 4 | Composable one-shots |
| BL-007 | Multi-model ensemble | Phase 4+ | IDEA.md § future |
| BL-008 | Skills injection library | Phase 4+ | Topic → skill file |
| BL-009 | Explicit MCP tools: `continue_session`, `get_session_status` | Phase 3 | Phase 1 uses disk registry + policy |
| BL-010 | ~~DB-backed session persistence~~ | Phase 3 | **P1-130:** disk sessions under `~/.mcp-coder` (not DB) |

---

## Removed / demoted from Phase 1 spine

| ID | Item | Notes |
|----|------|-------|
| BL-505 | SpecStory `.specstory/history/*.md` | Replaced by Cursor host transcript (P1-140) |
| BL-402 | SpecStory freshness window | N/A |
| BL-101 | SpecStory tail truncation cap | Use `MCP_CODER_MAX_TRANSCRIPT_BYTES` in P1-140 |

---

## Phase 1 optional (if time remains in MVP)

| ID | Item | Notes |
|----|------|-------|
| BL-102 | Fallback `cheap_llm` session classifier | Was P1-131; after P1-130 baseline |
| BL-103 | `inspect_delegations.py` CLI | Home-path aware |
| BL-104 | Aider dry-run mode in MCP | Safe first tests |
| BL-105 | Default Aider → `context_optimizer_proxy` in setup template | Composes with sibling project |
| BL-106 | MCP progress notifications for long Aider runs | Avoid Cursor timeout perception |
| BL-107 | `MCP_CODER_MIRROR_LOGS_TO_WORKSPACE` default policy | Migration from P1-100 paths |
| BL-108 | Pick “main” mcp session among N per `host_session_id` | Heuristic TBD |
| BL-109 | `continue_session` by explicit `mcp_session_id` | After P1-130 infra |
| BL-125 | **Persistent MCP server log** + verbosity tiers | **P1-125** — see [PHASE1_ISSUES.md](./PHASE1_ISSUES.md) **P1-ISS-004** (location + levels + defaults) |
| BL-305 | Server log scope: global vs per-`project_key` | Sub-issue of P1-ISS-004 / BL-125 |

---

## Host & integration

| ID | Item | Notes |
|----|------|-------|
| BL-201 | Claude Desktop host adapter | Own `core/host/claude_desktop.py` |
| BL-202 | Windsurf / other IDEs | Host matrix TBD |
| BL-203 | ~~Read Cursor agent-transcripts~~ | **In Phase 1** as P1-120 + P1-140 |
| BL-204 | Proxy intercept: save latest Cursor prompt from `context_optimizer_proxy` | Personal workflow |
| BL-205 | Cursor rule / skill snippet for routing to `delegate_to_agent` | Improve auto-routing |

---

## Observability & ops

| ID | Item | Notes |
|----|------|-------|
| BL-301 | Delegation log web UI | Extend viewer for `~/.mcp-coder` |
| BL-302 | Redaction policy doc for logs (secrets) | Required before sharing logs |
| BL-303 | Metrics export (Prometheus / statsd) | Enterprise-ish; low priority |
| BL-304 | Global index `hosts/cursor/<id>/index.json` | Cross-project session lookup — **deferred P1-130**; one Cursor chat delegating to multiple repos (see P1-1.3 § Pre-implementation decisions) |
| BL-305 | Persistent MCP **server** log (process audit) | Same as BL-125; stderr brief today is not persisted |
| BL-306 | Startup **code version / git hash** in MCP stderr | Detect stale process (P1-ISS-009) |
| BL-307 | `MCP_CODER_SINGLETON=all` aggressive global kill | Escape hatch; default stays per-workspace |

---

## Experiments to schedule (outcomes → backlog or phases)

| ID | Experiment | Outcome drives |
|----|------------|----------------|
| BL-401 | `always_new` vs `align_host` | Default `MCP_CODER_SESSION_POLICY` — **partial:** E2E favors `align_host` for test sandbox; keep default `always_new` globally |
| BL-403 | Prompt size vs failure rate per model | Transcript cap, Phase 2 summarization |
| BL-404 | Cursor `target_files` reliability | Schema / inference rules |
| BL-405 | Tool name/description for routing | MCP tool description |

---

## After Phase 1 — adapt our dev workflow to the product

| ID | Item | Notes |
|----|------|-------|
| BL-150 | **Spec-based delegation** | **P1-199 review** — see [notes/spec-based-development.md](./notes/spec-based-development.md) |
| BL-151 | Gatekeeper MCP for protected specs | [OTEHR_RELATED_IDEAS/GATEKEEPING_MCP.md](./OTEHR_RELATED_IDEAS/GATEKEEPING_MCP.md) — out of scope until post-P1 |
| BL-152 | Mirror `delegations.jsonl` + task spec § Results in product UX | Same closed loop as `docs/tasks/` workflow |

---

## Ideas (unscoped)

| ID | Item |
|----|------|
| BL-501 | Job ID + async delegation (poll / MCP notification) for long Aider runs |
| BL-502 | Git worktree / dry-run diff return to Cursor instead of direct write |
| BL-503 | Grade executor output with cheap model before returning to Cursor |
| BL-504 | Global `~/.mcp-coder/config.yaml` defaults | Per-repo `config.yaml` shipped P1-130 |
| BL-506 | Generic `transcript.md` watch folder (non-Cursor hosts) |

---

## Done

_Move items here when completed._

| ID | Item | Completed |
|----|------|-----------|
| — | — | — |
