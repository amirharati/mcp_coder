# Phase 1 MVP — Product manager doc

**Status:** Spine complete (replanned 2026-06-04; P1-140 done 2026-06-05) — **next:** P1-199 exit review  
**Host:** Cursor first (other hosts via adapter layer later)  
**Technical reference:** [PHASES.md](./PHASES.md) § Phase 1 · [Storage & linking](./notes/storage-and-linking.md)  
**Vision:** [IDEA.md](./IDEA.md)  
**Deferred work:** [BACKLOG.md](./BACKLOG.md)  
**Known gaps / follow-ups:** [PHASE1_ISSUES.md](./PHASE1_ISSUES.md)

---

## Purpose of this doc

- **What:** Track Phase 1 scope, tasks, status, and acceptance criteria.
- **How we build:** Delegate focused work to a **worker session** with a tight local spec (`docs/tasks/P1-….md`), then review logs/artifacts.
- **Not here:** Phase 2+ delivery; unscheduled ideas → [BACKLOG.md](./BACKLOG.md).

---

## Phase 1 summary (replanned)

**Order:** **Infrastructure first**, then **session persistence**, then **full host context**.

1. **Infra (P1-110–P1-120):** User-home store (`~/.mcp-coder`), project registry, session folders, linked JSONL logs, host adapter interface, Cursor-only host implementation. Execution adapter (Aider) unchanged from P1-100.
2. **Sessions (P1-130):** Disk-backed `mcp_session_id`, link to `host_session_id`, policies `always_new` | `align_host`, executor reuse per session.
3. **Full context (P1-140):** Read Cursor `agent-transcripts/*.jsonl` via host adapter; inject into Aider prompt (replace SpecStory plan).
4. **Checkpoint:** Spec-as-contract, gatekeeper, N-session heuristics → **end of Phase 1 review** (not blocking 1.1–1.4).

Phase 1 still **no** owned context pipeline (no summarizer/RAG inside mcp-coder). Pass-through: Cursor summary in tool args; **opt-in** full Cursor transcript (`host_transcript: dump`, default `none`).

---

## Workflow (planning chat ↔ worker session)

| Step | Where | What |
|------|--------|------|
| **1. Plan** | This chat | Pick task; create `docs/tasks/P1-{…}.md` from [TASK_SPEC_TEMPLATE.md](./TASK_SPEC_TEMPLATE.md) (local, gitignored) |
| **2. Implement** | New worker session | Attach spec only — *Implement per attached spec; that scope only.* |
| **3. Report** | Back here | Results in local spec § Results → update task board (git) |
| **4. Next** | This chat | Mark `done`, unblock next |

**Rules:** One milestone per worker session; no scope creep; unknowns → backlog.

**Workers do not edit** `IDEA.md`, `PHASES.md`, `PHASE1_MVP.md`, `BACKLOG.md`, or `PHASE1_ISSUES.md` — only code, README, `.env.example`, and task-listed `docs/notes/*`. Master session updates PM/vision docs from worker § Results. See [TASK_SPEC_TEMPLATE.md](./TASK_SPEC_TEMPLATE.md) § Files policy.

---

## Milestones & task board

| Milestone | Task ID | Status | Local spec | Summary |
|-----------|---------|--------|------------|---------|
| **1.0** Barebones MCP + Aider | P1-100 | `done` | `P1-1.0-barebones-mcp-aider.md` | E2E 2026-06-04; workspace-local JSONL |
| **1.1** Home storage + linking | P1-110 | `done` | `P1-1.1-home-storage.md` | E2E 2026-06-04; `~/.mcp-coder`, per-session jsonl |
| **1.2** Host adapters (Cursor) | P1-120 | `done` | `P1-1.2-host-adapter-cursor.md` | E2E 2026-06-04; host metadata on logs |
| **1.3** Session persistence | P1-130 | `done` | `P1-1.3-session-persistence.md` | Policies, host scoring, Coder cache |
| **1.4** Full context (Cursor) | P1-140 | `done` | `P1-1.4-cursor-transcript-context.md` | E2E 2026-06-05; opt-in `dump`; overflow test |
| **1.x opt** Richer MCP fields | P1-115 | `optional` | — | `explicit_constraints`, snippets — if still needed |
| **1.x opt** Cheap LLM classifier | P1-131 | `optional` | — | Deferred; backlog |
| **1.x opt** Server log + verbosity | P1-125 | `done` | `P1-1.25-server-log.md` | E2E 2026-06-05; `~/.mcp-coder/server.jsonl` |
| **Exit** Phase 1 review | P1-199 | `todo` | — | **Next** — spec strategy, gatekeeper, Phase 2 goals |

**Removed from spine:** P1-120 SpecStory, schema-first P1-110.

Status: `todo` | `in_progress` | `done` | `blocked` | `optional`

---

## Task details

### P1-100 — Milestone 1.0 (done)

Cursor → `delegate_to_agent` → Aider → delegation JSONL under **workspace** `.mcp-coder/logs/`. `always_new`, `context_summary` + `task`.

See local `docs/tasks/P1-1.0-barebones-mcp-aider.md` § Results.

---

### P1-110 — Milestone 1.1: Home storage & linking (done)

**Depends on:** P1-100 `done`

Canonical logs under `MCP_CODER_HOME`; per-session `delegations.jsonl`; workspace pointer; viewer merges session logs.

See local `docs/tasks/P1-1.1-home-storage.md` § Results.

**In scope**

- [x] `core/storage/` — resolve `MCP_CODER_HOME`, `project_key` from `workspace_path`
- [x] Create/update `~/.mcp-coder/projects/<project_key>/project.json`
- [x] Per-delegation: create `sessions/<mcp_session_id>/` + `session.json` + append `delegations.jsonl`
- [x] JSONL fields: `project_key`, `mcp_session_id`, `session_dir`, `log_path`
- [x] Optional `<workspace>/.mcp-coder/project.json` pointer
- [x] Env: `MCP_CODER_HOME`; optional `MCP_CODER_MIRROR_LOGS_TO_WORKSPACE=1`
- [x] Update delegation viewer / `read_delegations` to default to home paths
- [x] README + `.env.example` document home layout

**Done when**

- [x] Delegation writes only under `~/.mcp-coder/...` (mirror optional)
- [x] One JSONL line contains enough IDs to open the correct session folder
- [x] Worker spec § Results has sample paths + one record

---

### P1-120 — Milestone 1.2: Host adapter (Cursor) (done)

**Depends on:** P1-110 `done`

`HostSessionHint` + `CursorHostProvider`; host fields on `session.json` and delegation JSONL. No transcript injection.

See local `docs/tasks/P1-1.2-host-adapter-cursor.md` § Results.

**In scope**

- [x] `core/host/base.py` — `HostContextProvider` protocol, `HostSessionHint` dataclass
- [x] `core/host/cursor.py` — map workspace → `.cursor/projects/<slug>/agent-transcripts/`, active transcript heuristic
- [x] Populate `host_kind`, `host_session_id`, `host_transcript_path` on `session.json` and delegation records
- [x] No prompt injection yet (hints + logging only)

**Done when**

- [x] Delegate from Cursor → log shows `host_session_id` when transcript exists
- [x] No imports of `cursor` paths outside `core/host/cursor.py`

**Known gaps (tracked):** [PHASE1_ISSUES.md](./PHASE1_ISSUES.md) — e.g. **P1-ISS-001** (active chat heuristic, partial).

---

### P1-130 — Milestone 1.3: Session persistence (`done`)

**Depends on:** P1-120 `done`  
**E2E:** 2026-06-04 — `mcp_coder_test_proj`, `align_host`, 5 delegations → one `mcp_session_id` (`e9787d0d…`)

**Goal:** Two policies (`always_new`, `align_host`), host active-session scoring (mtime + delegation log), Coder cache per `mcp_session_id`.

**Worker spec:** `docs/tasks/P1-1.3-session-persistence.md` § Results

**In scope**

- [x] `core/session/` — `SessionStore`, policy env, executor cache
- [x] Host scoring in `core/host/scoring.py` + `core/session/activity.py`
- [x] Unified `session_policy` / `session_reason` (P1-ISS-007)
- [x] Closes P1-ISS-001 (partial), P1-ISS-006 (reuse latest)

**Also shipped (post-spec extras)**

- [x] Workspace `config.yaml` (user) vs `session.json` (system pointer)
- [x] MCP singleton per workspace on startup (`core/server/singleton.py`)
- [x] Makefile: `mcp-smoke`, `mcp-kill`, `logs-last`

**Done when**

- [x] See worker spec § Done when + § Results E2E table

**Known gaps:** [PHASE1_ISSUES.md](./PHASE1_ISSUES.md) — **P1-ISS-009** (MCP restart after code deploy), **P1-ISS-010** (UE zombies), **P1-ISS-011** (global server log interleave — low).

---

### P1-140 — Milestone 1.4: Full context (Cursor transcript) (`done`)

**Depends on:** P1-130 `done`  
**E2E:** 2026-06-05 — default `host_transcript: none`; `dump` on `mcp_coder_test_proj`; overflow ~1.86M bytes → 128k token limit error

**Goal:** Opt-in dump-all of Cursor `agent-transcripts` into Aider prompt; log inject sizes; prove context-limit failures are visible.

**Worker spec:** `docs/tasks/P1-1.4-cursor-transcript-context.md` § Results

**Shipped**

- [x] `core/host/cursor_transcript.py` — JSONL → plain text (`[user]` / `[assistant]` blocks)
- [x] `core/context/transcript_policy.py` — `none` (default) \| `dump`; env + `config.yaml`
- [x] `assemble_prompt` — transcript + summary + task; `context_mode` `fallback` \| `host_transcript`
- [x] Logging: `host_transcript_injected_bytes`, `host_transcript_file_bytes`, hash, policy, truncation fields
- [x] `MCP_CODER_MAX_TRANSCRIPT_BYTES` optional tail cap when `dump`
- [x] Overflow test (`MCP_CODER_OVERFLOW_TEST=1`); 95 pytest (+1 skipped)

**Also shipped (post-spec)**

- [x] `aider_engine.py` — `ThreadPoolExecutor` around Aider run so sync Playwright (`detect_urls`) works under FastMCP asyncio

**Decisions**

- Default inject **`none`** (backward compatible)
- **`host_transcript_bytes`** aliases injected bytes; **`host_transcript_file_bytes`** = stat
- Empty parse under `dump` → `context_mode: fallback`

---

### P1-125 — Server log + verbosity (`done`)

**Depends on:** P1-130 `done`  
**E2E:** 2026-06-05 — live global `server.jsonl` after Cursor MCP restart + delegate; 78 pytest (incl. 8 server-log tests)

**Goal:** Durable MCP process audit trail (`type: server` JSONL) separate from per-session `delegations.jsonl`.

**Worker spec:** `docs/tasks/P1-1.25-server-log.md` § Results

**Shipped**

- [x] `core/logging/server_log.py` — enable/level/scope, env + workspace yaml
- [x] Default **`global`** → `~/.mcp-coder/server.jsonl`; optional `project` / `both`
- [x] Events: `stdio_server_ready`, singleton, host, session, delegation received/completed/failed, `config_deprecated`
- [x] `make server-logs-last`, `scripts/server_logs_last.py`
- [x] README, `.env.example`, `docs/examples/config.yaml`, storage note

**Decisions (from worker)**

- Failed delegations: **`delegation_failed` only** (not also `delegation_completed`)
- No file locking on global log — acceptable for debug; see **P1-ISS-011** / BL-308 if garbled lines appear

---

### P1-115 / P1-131 — Optional

- **P1-115:** `explicit_constraints`, `code_snippets_from_chat` — only if P1-140 still loses nuance.
- **P1-131:** Cheap LLM session classifier — [BACKLOG.md](./BACKLOG.md) BL-102.

---

### P1-199 — End of Phase 1 review

- [ ] Re-read [IDEA.md](./IDEA.md) and Phase 2 in [PHASES.md](./PHASES.md)
- [ ] Decide: spec-as-contract timing, gatekeeper, default session policy, second host priority
- [ ] Capture decisions in experiment notes below

---

## Phase 1 success checklist

- [x] P1-100: Cursor invokes tool; Aider edits files; JSONL exists
- [x] Home storage: all delegations under `~/.mcp-coder` with clear links
- [x] Host adapter: Cursor isolated; `host_session_id` on records
- [x] Session policies: `always_new` and `align_host` logged and testable (E2E 2026-06-04)
- [x] Server audit log: `server.jsonl` with lifecycle + delegation link fields (E2E 2026-06-05)
- [x] Full context: opt-in transcript dump; overflow + size fields documented (E2E 2026-06-05)
- [ ] P1-199 review completed; Phase 2 goals adjusted from logs

---

## Open questions (PM track)

| # | Question | When |
|---|----------|------|
| Q1 | `project_key` = hash of resolved path — include realpath? | P1-110 |
| Q2 | Mirror workspace JSONL by default or opt-in? | P1-110 |
| Q3 | `align_host` reuse latest vs first session? | **Latest** (agreed in planning) |
| Q4 | Transcript tail cap default on or off? | **Resolved P1-140:** inject default **`none`**; byte cap **off** (`0`); enable `dump` + optional `MCP_CODER_MAX_TRANSCRIPT_BYTES` per repo |
| Q5 | Spec mandatory when? | P1-199 only |
| Q6 | Cursor `target_files` reliability? | Ongoing |
| Q7 | Server log: global vs per-`project_key`? Verbosity tiers? Default on? | **Resolved P1-125:** default `global`, level `info`, log on; yaml can set `server_log_scope: project` |

---

## Experiment results

### 1.2 — Host adapter (Cursor)

| Field | Value |
|-------|-------|
| Date | 2026-06-04 |
| host_session_id | `90fcb3f8-…` (test_proj, live resolve) |
| Notes | `core/host/` shipped; metadata on session + JSONL |

---

### 1.25 — Server log

| Field | Value |
|-------|-------|
| Date | 2026-06-05 |
| Path | `~/.mcp-coder/server.jsonl` (default scope `global`) |
| Notes | Live E2E: `stdio_server_ready` → `delegation_received` → `delegation_failed` (Aider error path); disambiguate via `pid`, `project_key`; see P1-1.25 § Results |

---

### 1.1 — Home storage

| Field | Value |
|-------|-------|
| Date | 2026-06-04 |
| project_key | `38edc83881edda61d3bae81485e3213dfb54d9364c12e6d550395551845fd373` (mcp_coder repo) |
| Notes | Per-session jsonl under home; viewer merges; see P1-1.1 spec § Results |

---

### 1.0 — First delegation

| Field | Value |
|-------|-------|
| Date | 2026-06-04 |
| delegation_id | `9f0e23a1-c352-4463-91b2-5413c51e6545` |
| Notes | Workspace-local log; see P1-1.0 spec § Results |

### 1.3 — Session policy

| Policy | Notes |
|--------|-------|
| `always_new` | Default; one new `mcp_session_id` per call |
| `align_host` | E2E 2026-06-04 — 5 delegations → one session (`e9787d0d…`); see P1-1.3 § Results |

### 1.4 — Transcript context

| Field | Value |
|-------|-------|
| Date | 2026-06-05 |
| Default policy | `host_transcript: none` |
| Overflow test | ~1,860,512 injected bytes → `128,000 token limit` (gpt-4o-mini via OpenRouter) |
| Live dump E2E | `03ee1bd0` — 824 B injected, URL scrape OK after Playwright thread fix |
| Notes | See P1-1.4 § Results; reload MCP after deploy |

---

## Next action

1. **P1-199** — Phase 1 exit review (spec-as-contract, gatekeeper, Phase 2 goals).
2. Operator: reload Cursor MCP after deploy (`make mcp-kill` or Reload Window) — [P1-ISS-009](./PHASE1_ISSUES.md#p1-iss-009-mcp-process-stale-after-code-deploy).

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-04 | Milestone 1.3 done; config.yaml, MCP singleton, Makefile; issues 009/010 opened |
| 2026-06-03 | Initial PM doc |
| 2026-06-04 | P1-100 done |
| 2026-06-04 | P1-110 done — home storage, per-session jsonl, viewer merge |
| 2026-06-04 | P1-120 done — Cursor host adapter, host metadata on logs |
| 2026-06-04 | P1-130 done — session policies, host scoring, executor cache; E2E align_host |
| 2026-06-04 | **Gap logged:** persistent MCP server log → BL-125/305, optional P1-125 |
| 2026-06-04 | **Replanned:** infra → host adapter → sessions → full context; `~/.mcp-coder`; SpecStory removed; spec deferred to P1-199 |
| 2026-06-05 | **P1-125 done** — `server.jsonl`, P1-ISS-004 closed; P1-ISS-011 opened (global log interleave, wontfix-p1) |
| 2026-06-05 | **P1-140 done** — opt-in transcript dump; overflow E2E; Aider Playwright thread isolation |
