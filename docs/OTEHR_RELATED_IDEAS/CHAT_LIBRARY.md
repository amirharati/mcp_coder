<!--
  STEWARDSHIP — Tier 3 related idea (not canonical). See docs/VISION_DOCS.md.

  - May inform BL-* (e.g. BL-152 viewer); does not override docs/IDEA.md.
  - Do not treat as shipped product design without user + backlog entry.
  - Related: CONTEXT_AS_GIT.md, GATEKEEPING_MCP.md, BACKLOG.md § BL-002
-->

# Chat Library — Unified Archive of Past Conversations

**Status:** Idea — brainstorm 2026-06-09; **not scheduled**; product vs module vs skip TBD after cheap validation  
**Related:** [CONTEXT_AS_GIT.md](./CONTEXT_AS_GIT.md) · [GATEKEEPING_MCP.md](./GATEKEEPING_MCP.md) · [BACKLOG.md](../BACKLOG.md) § BL-002, BL-152

---

## The idea

A **local-first library** of past AI conversations across tools — not one chat product, but a **single place to browse, search, filter, and visualize** how ideas evolved.

**Pluggable sources** — user registers folders or paths where chats live:

| Source | Typical location |
|--------|------------------|
| Cursor | `~/.cursor/projects/.../agent-transcripts/` |
| mcp-coder | `~/.mcp-coder/projects/.../delegations.jsonl`, spec reports, `server.jsonl` |
| Grok / ChatGPT / Claude | export folder or dump path the user provides |
| Generic | any directory of `.jsonl`, `.md`, or export files |

**Web UI (aspirational):** timeline, full-text search, filters (project, source, date, topic), word clouds, “how did this idea evolve?” views, links from a thread to related spec / `delegation_id`.

**Primary user:** **human** — research your own thinking, find “what did we decide about X?”, connect a Grok brainstorm to a Cursor session to an mcp-coder report. Not a second coding agent.

---

## Why it might be useful

Coding work spreads across many chats with no cross-links:

- Same topic revisited in Grok, then Cursor, then mcp-coder — hard to see the arc
- “Which chat had the RAG ROI discussion?” requires manual grep or memory
- Failed ideas and accepted decisions sit in the same transcript — but **humans** can tell them apart when browsing

**Different from agent RAG:** BL-002 explicitly **skips raw chat transcripts** for automatic retrieval (noise, topic drift, rejected ideas). A chat library is **human browse + optional promote** → structured artifacts (decision log, spec note, checkpoint). See [CONTEXT_AS_GIT.md](./CONTEXT_AS_GIT.md) § stored vs runtime.

---

## Relevance to mcp-coder

| Layer | mcp-coder core | Chat library |
|-------|----------------|--------------|
| Job | Delegate, checkpoint work, build context for executor | Archive and lens on past *talk* |
| Canonical memory | Specs, reports, `workspace_history.db`, delegation RAG | Optional cross-index; not a replacement |
| Phase priority | Phase 4–5 (builder, file/delegation RAG) | Later / companion — do not block core |

**Natural integration points** (if built):

- Link `host_session_id` / transcript path ↔ `delegation_id` / `spec_path`
- Shared `project_key` / workspace identity
- Adjacent to **BL-152** (product UX viewer for delegations + reports)

**Not the same product:** mcp-coder owns **work checkpoints**; the library owns **conversation archaeology**. Merging too early blurs “what is delegation context?” and expands MCP surface area.

**Possible packaging (TBD):**

1. **Separate product** — own repo, reads `~/.cursor` + `~/.mcp-coder` + user folders  
2. **Companion module** — e.g. `mcp-coder library` subcommand + local web UI, same install  
3. **Skip** — if FTS over transcripts + spec reports is enough after Phase 5  

---

## MCP callable? (narrow cases only)

Default: **UI + human**. Optional MCP tools **only** for structured, bounded retrieval — not auto-inject full threads into every delegate.

| When it helps | Example tool | Returns |
|---------------|--------------|---------|
| Planner asks “what did we decide about X?” | `library_search(query, sources?, limit=5)` | Titles, dates, short excerpts, paths — not full dumps |
| Audit / linking | `library_link_thread(thread_id, delegation_id)` | Metadata only |
| Distillation | `library_promote(thread_id, range → decision_note)` | Writes structured artifact human or agent can cite |
| Pre-delegate hint | `library_related(project, topic)` | Pointers (title + date), not transcripts |

**Do not:** auto-search all chats into `delegate_to_agent` context; replace `list_delegations` / spec reports; run open-ended “explore my Grok history” inside agent loops. Fully agentic use of raw chat history tends to confuse (same lesson as Cursor long sessions — see [CONTEXT_AS_GIT.md](./CONTEXT_AS_GIT.md)).

---

## Decision framework (before committing)

Answer after a **cheap prototype** (SQLite FTS5 over Cursor + mcp-coder paths, CLI search only):

1. How often do you search old chats vs read a spec report?
2. What’s missing — search, timeline, cross-source links, or visualization?
3. Who promotes slices to structured memory — always human, or agent only on explicit ask?
4. Is local-first on one machine enough?
5. Would Phase 5 RAG on delegations/files make **agent-side** library search unnecessary? (Library may still help **humans**.)

| Outcome | Action |
|---------|--------|
| Prototype unused | Drop or park indefinitely |
| CLI search used weekly | Stage 1 web UI; decide product vs module |
| Strong need for multi-source + evolution UI | Companion product or BL-152 expansion |
| Agent needs pointers only | Add narrow MCP tools; keep corpus out of default delegate path |

---

## Staging (if pursued)

| Stage | Deliverable | Decides |
|-------|-------------|---------|
| **0** | Index + CLI search (`~/.cursor` transcripts + `~/.mcp-coder`) | Useful at all? |
| **1** | Local web UI: list, filter, search, open thread | Worth a product surface? |
| **2** | Multi-source adapters + link to spec/delegation | Separate product vs mcp-coder module? |
| **3** | Optional MCP: `library_search` + `library_promote` only | Agent-callable or UI-only? |

Stop at whichever stage stops paying off.

---

## Potential issues

| Issue | Mitigation |
|-------|------------|
| Privacy | Localhost-only by default; no cloud unless user opts in |
| Format churn | Per-source adapters; normalize to common message schema |
| Word-cloud noise | Stopwords; summarize per thread before viz |
| Scope creep | Library + lens only — not a second planner agent |
| Duplicates BL-002 | Agent path stays structured memory; library is human-first |

---

## One-line framing

**Chat library = Dewey Decimal for your past conversations; mcp-coder turns what you pick into specs and checkpoints — it does not read the whole shelf every turn.**
