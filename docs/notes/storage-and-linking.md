# Storage & linking (`~/.mcp-coder`)

**Status:** Agreed for Phase 1 replan (2026-06).  
**Related:** [PHASES.md](../PHASES.md) § Phase 1, [PHASE1_MVP.md](../PHASE1_MVP.md)

---

## Canonical rule

**All delegation logs and session metadata live under the user home store**, not inside the git repo (except an optional pointer file).

Default root: `MCP_CODER_HOME` → `~/.mcp-coder` (or `$XDG_DATA_HOME/mcp-coder` if we adopt XDG later).

---

## Directory layout

```text
~/.mcp-coder/
  server.jsonl                        # global MCP server audit log (startup, host, delegations)
  config.yaml                         # optional global defaults (future; per-repo config lives in workspace)
  projects/
    <project_key>/
      project.json                    # workspace_path, timestamps
      server.jsonl                    # optional per-project server log (scope=project|both)
      sessions/
        <mcp_session_id>/
          session.json                # policy, host link, backend
          delegations.jsonl           # append-only log for this session
  hosts/
    cursor/
      <host_session_id>/
        index.json                    # optional cross-project index (P1-130+)
```

**Server audit log:** `server.jsonl` is separate from per-session `delegations.jsonl`. It records MCP process events (startup, singleton, host resolve, session acquire, delegation received/completed) as one JSON object per line (`type: server`). Default path is `~/.mcp-coder/server.jsonl`; with `MCP_CODER_SERVER_LOG_SCOPE=project` or `both`, also append under `projects/<project_key>/server.jsonl`. Controlled by `MCP_CODER_SERVER_LOG*` env or workspace `config.yaml` keys `server_log`, `server_log_level`, `server_log_scope`.

**Workspace pointer (system-managed, overwritten on delegate):**

```text
<workspace>/.mcp-coder/session.json
```

```json
{
  "project_key": "a1b2c3...",
  "mcp_coder_home": "/Users/you/.mcp-coder",
  "sessions_root": "/Users/you/.mcp-coder/projects/a1b2c3.../sessions"
}
```

**User config (never written by mcp-coder):**

```text
<workspace>/.mcp-coder/config.yaml
```

```yaml
# always_new | align_host
session_policy: align_host
```

Legacy: `config.json` still read if yaml is missing. Example template: `docs/examples/config.yaml`.

Legacy: `<workspace>/.mcp-coder/project.json` is still read as pointer fallback if `session.json` is missing.

---

## IDs (foreign keys)

| ID | Meaning |
|----|---------|
| `workspace_path` | Absolute path MCP used as project root |
| `project_key` | Stable id derived from `workspace_path` (hash/normalize) |
| `mcp_session_id` | UUID — one executor conversation bucket |
| `host_kind` | e.g. `"cursor"` — set only by host adapter |
| `host_session_id` | Host chat id (e.g. Cursor transcript file stem) |
| `host_transcript_path` | Optional full path to host transcript file |
| `delegation_id` | UUID — one MCP `delegate_to_agent` call |

**Link chain:**

```text
workspace_path → project_key → mcp_session_id → delegation_id
                      ↓
               host_session_id  (Cursor chat; may map to N mcp sessions)
```

**Cursor (read-only, not our store):**

```text
~/.cursor/projects/<cursor_slug>/agent-transcripts/<host_session_id>/<host_session_id>.jsonl
```

Join: `session.json.host_session_id` equals transcript basename (uuid stem).

---

## `session.json` (minimal)

```json
{
  "mcp_session_id": "uuid",
  "project_key": "a1b2c3",
  "workspace_path": "/path/to/repo",
  "session_policy": "always_new",
  "host_kind": "cursor",
  "host_session_id": "c58d7ae6-e74e-4c46-98fd-40fbfa7b2610",
  "host_transcript_path": "/Users/.../agent-transcripts/c58d7ae6-.../c58d7ae6-....jsonl",
  "created_at": "ISO-8601",
  "last_delegation_at": "ISO-8601"
}
```

Many `mcp_session_id` folders may share one `host_session_id` (N worker sessions per Cursor chat). Picking a “main” session is **out of scope** for early Phase 1 — record association only.

---

## Delegation record (required link fields)

Every JSONL line includes (in addition to existing P1-100 fields):

| Field | Purpose |
|-------|---------|
| `project_key` | Locate project under home |
| `mcp_session_id` | Session folder |
| `session_dir` | Absolute path to `.../sessions/<mcp_session_id>/` |
| `log_path` | Absolute path to this session’s `delegations.jsonl` |
| `host_kind` | null if host adapter unavailable |
| `host_session_id` | null if unknown |

---

## Session policies (Phase 1)

| Policy | Behavior |
|--------|----------|
| `always_new` | New `mcp_session_id` folder every delegation (default) |
| `align_host` | Reuse latest session with same `(project_key, host_session_id)`; new Aider process after MCP restart |

Set via `MCP_CODER_SESSION_POLICY` or `<workspace>/.mcp-coder/config.yaml` (`session_policy:`). **config.yaml wins** over env when both set — see README.

---

## Migration from workspace-local logs

Legacy path: `<workspace>/.mcp-coder/logs/delegations.jsonl`.

Canonical write is under `~/.mcp-coder/projects/.../sessions/.../delegations.jsonl`. Optional mirror via `MCP_CODER_MIRROR_LOGS_TO_WORKSPACE=1`.

**MCP process:** Restart Cursor (or `make mcp-kill`) after pulling code changes — the stdio server loads Python once ([PHASE1_ISSUES.md](../PHASE1_ISSUES.md) P1-ISS-009).

---

## Navigation

| Start from | Go to |
|------------|--------|
| Repo | `<workspace>/.mcp-coder/session.json` (pointer) + `config.yaml` (settings) |
| Cursor chat | `host_session_id` → sessions with matching field or `hosts/cursor/<id>/index.json` |
| Delegation line | `log_path` / `session_dir` on the record |

---

## Changelog

| Date | Note |
|------|------|
| 2026-06-04 | P1-125: `server.jsonl` global/per-project MCP audit log |
| 2026-06-04 | `session.json` pointer, `config.yaml`, session policies, nested Cursor transcript paths |
