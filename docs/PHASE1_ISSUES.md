# Phase 1 issue tracker

**Purpose:** Known gaps, limitations, and follow-ups discovered during Phase 1 — so we do not lose them in chat or worker § Results.  
**Not** the full product backlog ([BACKLOG.md](./BACKLOG.md)); items here are **Phase 1–relevant** (fix before/ at P1-199 or explicitly carry to Phase 2).

**Milestone board:** [PHASE1_MVP.md](./PHASE1_MVP.md)

Status: `open` | `scheduled` | `done` | `wontfix-p1` (defer with reason)

| When to fix | Milestone |
|-------------|-----------|
| Before Phase 1 exit | P1-140, or P1-199 decision |
| Phase 2+ | Mark `wontfix-p1` + link BL-* |

---

## Issues

| ID | Status | Priority | Title | Target | Notes |
|----|--------|----------|-------|--------|-------|
| [P1-ISS-001](#p1-iss-001-active-cursor-chat--newest-mtime) | `done` | high | Active Cursor chat ≠ newest transcript mtime | **P1-130** | score + tie-break |
| [P1-ISS-002](#p1-iss-002-cursor-slug-heuristic-failures) | `open` | medium | Cursor project slug heuristic can fail | P1-120+ doc / env | Override exists |
| [P1-ISS-003](#p1-iss-003-legacy-delegations-without-host-fields) | `open` | low | Legacy delegations lack `host_*` | doc only | Expected |
| [P1-ISS-004](#p1-iss-004-persistent-mcp-server-log) | `done` | high | Persistent MCP **server** log + verbosity | **P1-125** | Shipped 2026-06-05 |
| [P1-ISS-011](#p1-iss-011-global-server-log-interleave) | `wontfix-p1` | low | Global `server.jsonl` interleave / rare garbled line | Phase 2+ / BL-308 | Use `server_log_scope: project` |
| [P1-ISS-005](#p1-iss-005-repo-move-orphans-home-data) | `open` | low | Moving repo orphans `project_key` data | P1-199 / Phase 2 | By design for now |
| [P1-ISS-006](#p1-iss-006-many-mcp-sessions-per-host-chat) | `done` | medium | Many mcp sessions per Cursor chat — no “main” picker | **P1-130** | `align_host` reuses latest; UI picker BL-108 |
| [P1-ISS-007](#p1-iss-007-session_policy-field-naming) | `done` | low | `session_policy` naming inconsistent | **P1-130** | `always_new` \| `align_host` |
| [P1-ISS-008](#p1-iss-008-cross-project-host-index) | `open` | low | No cross-project index by `host_session_id` | BL-304 | Optional |
| [P1-ISS-009](#p1-iss-009-mcp-process-stale-after-code-deploy) | `open` | high | MCP child keeps old Python code until process exits | doc + ops | Reload Window after deploy |
| [P1-ISS-010](#p1-iss-010-ue-zombie-mcp-processes) | `open` | low | Stuck `UE` `main.py --mcp` on macOS | doc | Quit Cursor; `make mcp-kill` |

---

## Issue details

### P1-ISS-001: Active Cursor chat ≠ newest mtime

**Status:** `done` (partial) — closed 2026-06-04 at P1-130. Multi-chat same-repo edge cases remain; see P1-140 / BL-109.

**Found:** P1-120 review (2026-06-04).

**Problem:** `CursorHostProvider` picks the **most recently modified** `agent-transcripts/**/*.jsonl` under the project slug. That may not be the Composer chat the user is in when they call `delegate_to_agent` (several chats → wrong `host_session_id` on metadata).

**Impact:** Metadata/linking. Wrong link still allows delegation; `align_host` may attach to wrong session folder if scoring picks wrong chat.

**Mitigation shipped (P1-130):** score = max(transcript mtime, last delegation per host id); 10s tie window; `host_resolve_method` in logs.

**Remaining directions (P1-140 / P1-199):**

- Prefer transcript whose mtime is within last N minutes only.
- Match transcript uuid to something Cursor exposes later (MCP / env).
- Optional MCP arg `host_session_id` from planner when known.
- Scan transcript tail for workspace path / recent user message (expensive).

**Acceptance (when closed):** **P1-130** — score = max(transcript mtime, last delegation per host id); tie window + `host_resolve_method` in logs. **Closed 2026-06-04** with caveat: multi-chat same repo still ambiguous; E2E used `score_global` successfully.

---

### P1-ISS-002: Cursor slug heuristic failures

**Found:** P1-120 (live `mcp_coder_test_proj`).

**Problem:** Slug is derived from resolved path (`/` → `-`, optional `_` → `-`). Cursor’s folder name may not match (e.g. `personal_tools` vs `personal-tools`).

**Mitigation today:** `MCP_CODER_CURSOR_PROJECT_SLUG` env override.

**Follow-up:** README troubleshooting; optional scan fallback (backlog). Consider caching slug in workspace `.mcp-coder/project.json` after first successful resolve.

---

### P1-ISS-003: Legacy delegations without host fields

**Found:** P1-120.

**Problem:** Delegations before P1-120 have `host_kind` / `host_session_id` null.

**Action:** Document in README / viewer. No migration required unless we want a one-off backfill script (not planned).

---

### P1-ISS-004: Persistent MCP server log

**Status:** `done` — closed 2026-06-05 at **P1-125**.

**Found:** P1-120 worker § Results; planning gap vs delegation JSONL.

**Shipped:** `core/logging/server_log.py`; default `~/.mcp-coder/server.jsonl` (`MCP_CODER_SERVER_LOG_SCOPE=global`); levels + workspace yaml overrides; events through delegation lifecycle; `make server-logs-last`. See `docs/tasks/P1-1.25-server-log.md` § Results.

**Not shipped (deferred):** rotation (`MCP_CODER_SERVER_LOG_MAX_MB`), global `~/.mcp-coder/config.yaml`, optional `debug` events, file locking — see **P1-ISS-011** / BL-308.

**Backlog (closed):** BL-125, BL-305.

---

### P1-ISS-011: Global server log interleave

**Status:** `wontfix-p1` — accepted limitation at P1-125; revisit only if garbled lines show up in daily use.

**Found:** P1-125 worker § Results (multi-workspace / concurrency).

**Problem:** With default `server_log_scope: global`, every MCP stdio process appends to one file. Lines interleave but are tagged with `pid`, `workspace_path`, `project_key`. No file locking; under heavy parallel writes a rare **corrupted JSON line** is possible (POSIX `O_APPEND` is usually fine for small lines).

**Mitigation (no code):** Set `server_log_scope: project` (or `both`) in workspace `config.yaml` for repos you run in parallel.

**If we fix later:** file locking, per-pid subfiles, or default scope change — [BACKLOG.md](./BACKLOG.md) BL-308.

---

### P1-ISS-005: Repo move orphans home data

**Found:** P1-110.

**Problem:** `project_key` = SHA-256(resolved workspace path). Clone/move repo → new key; old `~/.mcp-coder/projects/<old_key>/` orphaned.

**Action:** Document. Phase 2: alias table or import tool if needed.

---

### P1-ISS-006: Many mcp sessions per host chat

**Status:** `done` (reuse path) — 2026-06-04. UI “main” picker still BL-108.

**Found:** Planning + P1-110 (`always_new`).

**Problem:** Each delegation creates a new `mcp_session_id`. Same `host_session_id` may map to many folders. No heuristic for “main” worker session.

**Impact:** P1-130 `align_host` reuses **latest** only — older folders remain for audit.

**Follow-up:** BL-108; optional UI in viewer to group by `host_session_id`.

---

### P1-ISS-007: session_policy field naming

**Status:** `done` — 2026-06-04. New records use `always_new` \| `align_host` only.

**Found:** P1-110 / P1-100.

**Problem:** `session.json` uses `"always_new"`; delegation JSONL uses `"fallback:always_new"`.

**Resolution:** Unified in P1-130 (`session_policy` enum + `session_reason`). Old JSONL rows unchanged.

---

### P1-ISS-008: Cross-project host index

**Found:** [storage-and-linking.md](./notes/storage-and-linking.md).

**Problem:** Finding all mcp sessions for a Cursor chat across repos requires scanning all `projects/*/sessions/*/session.json`.

**Follow-up:** `~/.mcp-coder/hosts/cursor/<host_session_id>/index.json` — BL-304. Optional; not blocking P1-130.

---

### P1-ISS-009: MCP process stale after code deploy

**Found:** P1-130 E2E review (2026-06-04).

**Problem:** Cursor spawns a long-lived `python main.py --mcp` child. Python imports modules once at startup. Editing mcp-coder on disk does **not** update the running process. User saw `fallback:always_new` in logs while on-disk code had P1-130 — toggling MCP in Settings was insufficient; process from 2:49 PM survived until Reload Window.

**Impact:** False-negative E2E; appears as “restart didn’t work.”

**Mitigations shipped:** `core/server/singleton.py` (kill stale per workspace on next start); Makefile `mcp-smoke` / `mcp-kill`; startup log includes `pid=`.

**Action:** Document ops workflow: **Reload Window** after code changes; do not run manual `make mcp` alongside Cursor MCP. Optional: startup `code_version` / git hash in stderr (BL-306).

---

### P1-ISS-010: UE zombie MCP processes (macOS)

**Found:** P1-130 E2E review (2026-06-04).

**Problem:** `ps` shows `main.py --mcp` in state `UE` (uninterruptible). `pkill -9` may not remove them. Harmless but confusing in `make mcp-ps`.

**Action:** Quit Cursor fully; document in README/Makefile. Not blocking.

---

## Scheduled / done

| ID | Status | Resolution |
|----|--------|------------|
| — | — | *(move rows here when closed)* |

---

## How to add an issue

1. Append row to **Open issues** table with next `P1-ISS-NNN`.
2. Add ### section with problem, impact, target milestone, acceptance.
3. If long-term only → also add row to [BACKLOG.md](./BACKLOG.md).
4. Reference ID in worker spec § Results (“see P1-ISS-00x”).

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-05 | P1-125 done; P1-ISS-004 closed; P1-ISS-011 opened (wontfix-p1) |
| 2026-06-04 | P1-130 done; P1-ISS-009/010 opened; config.yaml + singleton extras |
| 2026-06-04 | Initial tracker after P1-120 review; P1-ISS-004 server log design sketched |
