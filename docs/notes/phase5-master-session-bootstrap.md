# Phase 5 master session bootstrap

**Created:** 2026-06-13  
**Purpose:** Frozen summary of Phase 5 planning session decisions. Use as context for future master sessions continuing Phase 5 work.  
**Status:** Frozen — Phase 5 **closed** 2026-06-13 (recommended exit).
**Authoritative PM docs:** [PHASE5_MVP.md](../PHASE5_MVP.md) · [PHASE5_ISSUES.md](../PHASE5_ISSUES.md)  
**Design note:** [rag-gap-analysis.md](./rag-gap-analysis.md)

---

## What was locked in this session

### Phase 5 one-line goal

Move the context builder from *recency + `rg`* toward *relevance retrieval*, starting with delegation RAG (already indexed, not yet wired) and workspace-file summaries (new corpus) — with a proper RAG toolset (CLI + MCP) as the shared interface.

### Milestones locked

| Milestone | One-line | Min exit? |
|-----------|----------|-----------|
| P5-001 | `ContextRef` + `retrieve()` contract; fix BL-335 token null | Plumbing |
| P5-002 | `rag_retrieval` pipeline phase → builder; delegation search CLI | **Yes — minimum** |
| P5-003 | `workspace_rag.db` + per-file summaries; `workspace_search` MCP + CLI | Recommended |
| P5-004 | File corpus hints in picker + builder; `context_refs[]` in JSONL | **Recommended exit** |
| P5-005 | Recall metric; cost delta; lean refs; embeddings go/no-go | Optional capstone |

### Locked design decisions (D-P5-1 through D-P5-8)

| ID | Decision |
|----|----------|
| D-P5-1 | Phase 5 = infra + connect; advanced corpora (Corpus 3/4) → Phase 5+/~8–9 |
| D-P5-2 | FTS + LLM summaries first; embeddings only if P5-005 recall metric shows gap |
| D-P5-3 | `retrieve(query, corpus, k) -> [ContextRef]` — one contract for all corpora |
| D-P5-4 | Separate DBs: `delegation_rag.db` (existing) vs `workspace_rag.db` (new) |
| D-P5-5 | Diffs stay in `workspace_history`; RAG stores digests + path names only |
| D-P5-6 | sha256 change = lazy re-index signal for workspace file summaries |
| D-P5-7 | Retrieval = explicit named pipeline phase (`rag_retrieval`) in `delegation_pipeline` JSONL |
| D-P5-8 | RAG tools exposed as both MCP tools **and** CLI; `--format plain` for executor prompt injection |

### Open questions closed

| Q | Answer |
|---|--------|
| Q1: Primary pain | Within-repo (files + delegation history). Cross-project → ~Phase 8–9. |
| Q2: Builder integration style | Explicit named phase `rag_retrieval` — auditable in `delegation_pipeline`, not implicit |
| Q3–Q10 | Deferred (chat distillation, embeddings, executor-pull, web localization, retention) — all Phase 5+/6+ |

### Phase 5 exit conditions

| Level | Requires |
|-------|----------|
| Minimum | P5-001 + P5-002 + `mcp-coder search delegations` CLI — **code shipped 2026-06-13**; dogfood with `builder_history_rag: true` still TBD |
| Recommended | P5-001…P5-004; dogfood delegation with both corpus hits in `context_refs` |
| Stretch | + P5-005 capstone |

---

## What Phase 4.5 delivered (context for Phase 5 workers)

| Track | Status |
|-------|--------|
| T-01…T-05 tutorials | Done |
| T-06 (delegation pipeline) | Skeleton → BL-362 |
| T-07 (end-to-end trace) | Pending → BL-362 |
| `docs/guide/architecture/overview.md` | Done — D-1…D-8 locked |
| Architecture sub-pages | Pending → BL-363 |
| Gap analysis (formal doc) | Absorbed into `rag-gap-analysis.md` + architecture overview |
| P4.5 fixes (001–005) | Done |
| All P4.5 issues | Frozen → BACKLOG BL-341–363 |

---

## Code already in place (do not re-implement)

| What | Where |
|------|-------|
| `delegation_rag.db` FTS5 — indexed after each delegate | `core/rag/` (db.py, index.py, search.py, models.py) |
| `rag_search` MCP tool | `server/mcp_server.py` |
| `workspace_history.db` — manifest walk, diffs, file deltas | `core/workspace/` |
| Context compiler pipeline (picker → assemble → builder → executor) | `core/context/`, `server/mcp_server.py` |
| Helper LLM pipeline (builder, architect, spec-validation) | `core/engine/context_builder_llm.py`, `architect_pass_llm.py`, `spec_validation_llm.py` |

| `retrieve()` + `ContextRef` contract | `core/rag/retrieval.py` (P5-001) |
| BL-335 token extractor | `core/usage/litellm_tokens.py` (P5-001) |
| `rag_retrieval` pipeline phase + builder injection | `server/mcp_server.py`, `core/rag/builder_retrieval.py` (P5-002) |
| `mcp-coder search delegations` CLI | `core/cli/search.py` (P5-002) |
| `builder_history_rag` config toggle | `core/config/rag.py` (P5-002) |
| `workspace_rag.db` + indexer + search | `core/rag/workspace_*.py` (P5-003) |
| `mcp-coder index-workspace` + `search files` CLI | `core/cli/index_workspace.py`, `core/cli/search.py` (P5-003) |
| `workspace_search` MCP tool | `server/mcp_server.py` (P5-003) |
| `workspace_file_rag` config toggle | `core/config/rag.py` (P5-003) |

**Critical gap (P5-004):** File corpus not wired into picker/builder or merged `rag_retrieval` / `context_refs`.

**Resolved (was P5-003):** `workspace_rag.db`, workspace search MCP + CLI, incremental index.

**Resolved (was P5-001):** BL-335 token extractor shipped; live dogfood verify still TBD (P5-005).

---

## Confusion traps for future sessions

1. **Delegation RAG already exists** — Phase 5 wires it in; it does NOT rebuild FTS from scratch.
2. **RAG ≠ logging.** Helper LLM inputs missing from JSONL = BL-353 observability, not RAG.
3. **RAG ≠ code-intel cache.** Symbol outlines, import graphs = BL-348 (substrate); different from file summaries.
4. **RAG ≠ recency.** Recently touched files = BL-349; different problem.
5. **Specs are not indexed.** Historical specs enter via Delegation Memory corpus (Corpus 2), not a specs-folder grep.
6. **Tracker vs RAG:** `workspace_history` owns diffs; RAG owns searchable digests; sha256 change triggers lazy file re-index.
7. **CLI tools are fundamental.** `--format plain` output is designed for executor prompt injection (pre-shapes BL-354 at toolset level without mid-loop wiring).
8. **Phase 5 is not Phase 6.** Full wire logging, reasoning traces, executor-pull are adjacent but deferred.
9. **BL-002 corpus table** in BACKLOG used to say "Workspace source files | Phase 4 — primary" — this was revised during Phase 4.5 to **Phase 5**. The BACKLOG BL-002 section now reflects this correctly. Do not revert.

---

## Worker rules (enforce when dispatching P5-* workers)

- Single source of truth: attached `docs/tasks/P5-<NNN>-<name>-v1.md` only (gitignored)
- Fill `§ Results` in spec; propose PM changes as bullets under **§ Results → Suggested for master session**
- Do NOT edit IDEA, PHASES, PHASE*_MVP, BACKLOG, PHASE*_ISSUES, VISION_DOCS unless task spec explicitly lists them
- No Aider API terms (`fnames`, `yes=True`, `Coder`) in `core/rag/`, `core/context/`, or `core/specs/` — backend-neutral rule
- Worker specs: `docs/tasks/P5-NNN-name-v1.md`

---

## Phase 5 exit — **done** (2026-06-13)

Recommended exit met. RAG retrieval defaults **on**. Open issues → **BL-335**, **BL-364**. Optional **P5-005** deferred.

## Next planning session

Pick Phase 5+/6 entry: **BL-335** (tokens), **BL-353** (observability), **P5-005** (measure), or **BL-354** (executor-pull).
