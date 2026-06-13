# T-02: Sessions, storage, and logs

**Goal:** Understand where mcp-coder stores everything outside your repo, how sessions are structured, and how to read the audit trail. By the end you can navigate `~/.mcp-coder` confidently and extract any information from a JSONL record.

**Prerequisites:** T-01 complete — at least one delegation has run so there is real data to inspect.

**Estimated time:** 15–20 min (mostly reading and running CLI commands).

---

## 1. The two storage scopes

mcp-coder keeps state in two places:

```
<your-project>/                     ← in the repo (user-visible, committable)
  .mcp-coder/
    config.yaml                     user-owned config (never written by mcp-coder)
    session.json                    pointer to the current session (system-managed)
    spec-template.md                bundled templates (auto-created)
    specs/tasks/*.md                your step specs
    specs/epics/*.md                your epic specs
    specs/reports/*.md              mcp-coder audit reports (one per spec)

~/.mcp-coder/                       ← outside the repo (machine-level)
  projects/<sha256>/                one dir per workspace, keyed by path hash
    project.json                    workspace path + timestamps
    workspace_history.db            SQLite: file snapshots, diffs, checkpoints
    delegation_rag.db               SQLite FTS5: full-text search over delegations
    sessions/<mcp_session_id>/
      delegations.jsonl             one JSONL record per delegation ← the audit trail
```

The split is intentional: specs and config belong in your repo (versioned, shared). History and logs belong outside (large, machine-specific, no git noise).

---

## 2. Find your project directory

Each workspace is identified by the **SHA-256 of its absolute path**. This is stable as long as the path doesn't change.

```bash
# From inside the project
python3 -c "
from core.storage.paths import project_dir
import os
print(project_dir(os.getcwd()))
"
# → /Users/you/.mcp-coder/projects/abc123.../
```

Or look it up via `.mcp-coder/session.json` inside the project:

```bash
cat .mcp-coder/session.json
# {
#   "project_key": "abc123...",
#   "mcp_coder_home": "/Users/you/.mcp-coder",
#   "sessions_root": "/Users/you/.mcp-coder/projects/abc123.../sessions"
# }
```

And `~/.mcp-coder/projects/<key>/project.json` maps the key back to the workspace path:

```bash
cat ~/.mcp-coder/projects/abc123.../project.json
# {
#   "project_key": "abc123...",
#   "workspace_path": "/Users/you/projects/hello-mcp",
#   "created_at": "2026-06-10T...",
#   "last_seen_at": "2026-06-10T..."
# }
```

To see all registered projects (useful when you have many):

```bash
for f in ~/.mcp-coder/projects/*/project.json; do
  python3 -c "import json,sys; d=json.load(open('$f')); print(d.get('workspace_path','?'), '→', '$f')"
done
```

---

## 3. Sessions

Each Cursor chat maps to an **mcp session** — a UUID directory under `projects/<key>/sessions/`. Session policy controls how they're created:

- **`always_new`** — a new session UUID every time the MCP server starts (i.e. every time Cursor launches it for a workspace). Delegations from different chats go into different session dirs.
- **`align_host`** — mcp-coder tries to reuse a session that matches the current Cursor chat session. Consecutive delegations from the same chat share an Aider `Coder` instance (faster — no re-init).

Inside each session dir there is one file:

```
sessions/<mcp_session_id>/
  delegations.jsonl     one JSON line per delegation, appended in order
```

To find all session dirs for a project and see how many delegations each has:

```bash
for d in ~/.mcp-coder/projects/<key>/sessions/*/; do
  count=$(wc -l < "$d/delegations.jsonl" 2>/dev/null || echo 0)
  echo "$(basename $d)  $count delegations"
done
```

---

## 4. The JSONL audit record — field by field

Every `delegate_to_agent` call appends **one JSON line** to `delegations.jsonl`. This is the canonical record — the MCP response payload is a projection of it.

Find the file and read the last record:

```bash
# Quickest way from cwd
find ~/.mcp-coder -name delegations.jsonl | head -5

# Read and pretty-print the last record
tail -1 <path/to/delegations.jsonl> | python3 -m json.tool | head -80
```

### Key top-level fields

| Field | Type | What it is |
|-------|------|-----------|
| `delegation_id` | uuid | Unique id for this delegation |
| `timestamp_start` / `timestamp_end` | ISO-8601 | Wall-clock start/end |
| `duration_ms` | int | Total wall time |
| `workspace_path` | string | Absolute path of the project |
| `project_key` | string | sha256 of `workspace_path` |
| `mcp_session_id` | uuid | Which session this belongs to |
| `session_action` | string | `new`, `reused`, `recreated` |
| `session_policy` | string | `always_new` or `align_host` |
| `backend` | string | `aider` (only backend today) |
| `model` | string | Executor model used |
| `success` | bool | Whether the executor succeeded |
| `outcome` | string | `success`, `partial`, `needs_input`, `error` |
| `files_requested` | list | `target_files` from MCP call |
| `files_changed` | list | Files actually created/modified/deleted (from snapshot diff) |
| `context_refs` | list | RAG retrieval hits when `rag_retrieval` ran (empty if validation blocked) |

### `mcp_request` — what the planner sent

```json
"mcp_request": {
  "task": "...",
  "target_files": ["hello.py"],
  "context_summary": "...",
  "spec_path": "tasks/hello-01-v1.md",
  "mode": "implement"
}
```

### `context` — audit metadata about the prompt (not the full context)

**Important:** `context` is **not** the assembled context package. It records **provenance, sizes, hashes, and pipeline flags** — enough to audit and compare delegations without bloating every JSONL line with full file bodies.

What it typically contains:

| Sub-area | Example fields | What you learn |
|----------|----------------|----------------|
| Final prompt size | `prompt_chars`, `prompt_tokens_est`, `prompt_hash` | How big the executor prompt was; hash lets you compare runs |
| Prompt slice | `prompt_preview` | First ~500 chars of the **final** executor prompt (truncated) |
| Host transcript | `host_transcript_path`, `host_transcript_hash`, `host_transcript_bytes` | Which Cursor chat was injected and how much |
| Context package summary | `context_package.entries` | Path + tier per file (`edit-full`, `read-excerpt`, …) — **no file payloads** |
| Builder / architect flags | `context_builder_enabled`, `builder_brief_applied`, `architect_pass_enabled` | Which pipeline stages ran — config/audit, not the brief text |
| Phase audit | `delegation_pipeline` | Per-phase status + `duration_ms` (implement+spec only; see below) |
| Executor session | `executor_reused`, `executor_recreated` | Whether the Aider instance was reused |

Example (abbreviated):

```json
"context": {
  "prompt_chars": 4820,
  "prompt_tokens_est": 1205,
  "prompt_hash": "a3f2…",
  "prompt_preview": "## Cursor chat history\n\n[user]\n…",
  "host_transcript_path": "/Users/you/.cursor/projects/…/agent-transcripts/…jsonl",
  "host_transcript_hash": "cc6cd8…",
  "host_transcript_bytes": 842,
  "context_builder_enabled": true,
  "builder_brief_applied": true,
  "context_package": {
    "compiler_version": "0.3.0",
    "entries": [
      {"path": "hello.py", "tier": "edit-full", "bytes": 240},
      {"path": "README.md", "tier": "read-excerpt", "bytes": 80}
    ]
  }
}
```

**Where the actual assembled context lives:**

- **`context.prompt_preview`** — quick peek at the start of what the executor saw
- **`context.prompt_full`** — full executor prompt, only if `MCP_CODER_LOG_FULL_PROMPT=1` in `.env` (off by default; can be large)
- **`mcp-coder inspect-context`** — dry-run the compiler and see the full brief + package (T-04)
- **Spec report** — `.mcp-coder/specs/reports/<spec>-report.md` written after each spec-backed delegation

### `model_roles` — per-role model audit

```json
"model_roles": {
  "executor": {
    "role": "executor",
    "model": "openrouter/anthropic/claude-sonnet-4",
    "tokens": {"input": null, "output": null, "total": null, "source": "executor"},
    "duration_ms": 8240
  },
  "context_builder": {
    "role": "context_builder",
    "model": "openrouter/google/gemini-2.5-flash",
    "tokens": {"input": null, "output": null, "total": null, "source": "context_builder_llm"},
    "duration_ms": 680
  }
}
```

> `tokens` are currently `null` for most paths — BL-335, a known gap. The models ran; counting is a pending fix.

### `context.delegation_pipeline` — phase audit (JSONL)

In **JSONL**, the phase list lives under **`context.delegation_pipeline`**, not at the top level. The **MCP response** to Cursor also exposes it as top-level `delegation_pipeline` for convenience.

Present only when the delegation ran the implement+spec pipeline (`mode=implement`, valid spec, Phase 4+). Older or pass-through records may not have this key at all.

```json
"context": {
  "delegation_pipeline": [
  {"phase": "spec_read",    "status": "ok", "duration_ms": 3},
  {"phase": "file_picker",  "status": "ok", "duration_ms": 118},
  {"phase": "context_assemble", "status": "ok", "duration_ms": 45},
  {"phase": "builder_llm",  "status": "ok", "duration_ms": 682},
  {"phase": "executor",     "status": "ok", "duration_ms": 8240},
  {"phase": "post_gateway", "status": "ok", "duration_ms": 12},
  {"phase": "spec_report",  "status": "ok", "duration_ms": 4}
  ]
}
```

Phase statuses: `ok | skipped | error | blocked`. Opt-in stages that are off appear as `skipped`. Full delegation-pipeline tour: **T-06**.

---

## 5. CLI commands for navigating history

All commands default to `cwd` as the workspace. Use `--workspace <path>` if needed.

### Open the delegation browser UI

```bash
mcp-coder view delegations              # merged JSONL for cwd workspace
mcp-coder view delegations --no-open    # serve at http://127.0.0.1:8765/ without opening a tab
```

Good for browsing many delegations without `tail` + `python -m json.tool`. Today the list view is structured; **expanded detail is still mostly raw JSON** — structured pipeline/model-role sections are planned (**P4.5-ISS-006** / **BL-343**). Until then, use `context.delegation_pipeline` and `model_roles` in the JSON block, or ask Cursor via MCP history tools (§7).

### List recent delegations

```bash
mcp-coder history list
# Shows: delegation_id, timestamp, outcome, files_changed, spec_path
# --limit N   (default 20)
# --spec tasks/hello-01-v1.md   (filter by spec)
# --file hello.py               (filter by file touched)
```

### Show the diff from a delegation

```bash
mcp-coder history diff --latest        # most recent
mcp-coder history diff abc123          # by delegation_id prefix
mcp-coder history diff abc123 --path hello.py   # single file
mcp-coder history diff abc123 --json   # full JSON output
```

The diff is computed from **pre/post workspace snapshots** (SHA-256 manifests), not git. It's available even in repos without commits or with dirty state.

### Revert a delegation

```bash
mcp-coder history revert abc123        # undo one delegation's file edits
```

---

## 6. `workspace_history.db` — what's in the SQLite

The DB stores the underlying data that `history` queries. You can inspect it directly:

```bash
sqlite3 ~/.mcp-coder/projects/<key>/workspace_history.db
.tables
# checkpoints   files   file_versions   delegations_meta ...
```

You don't normally need to query it directly — the CLI and MCP tools cover the common cases. But it's good to know it exists and that:
- **Checkpoints** record the pre/post state of each delegation
- **`file_versions`** stores content hashes (not full content) so diffs are possible without re-reading disk
- All of this is per-project, outside the repo, and **never committed to git**

---

## 7. Ask Cursor instead (via MCP tools)

During active work you rarely need the CLI — the planner has direct access:

| What you want | Ask in Cursor chat |
|--------------|-------------------|
| Recent delegations | *"List the last 5 delegations"* |
| What changed in a delegation | *"Show me the diff for delegation abc123"* |
| Which delegations touched a file | *"What delegations changed hello.py?"* |
| Detail on a checkpoint | *"Show checkpoint detail for abc123"* |

These call `list_delegations`, `get_delegation_diff`, `get_file_history`, `get_checkpoint_detail` respectively. The planner sees the data inline — no terminal needed.

---

## 8. What to look for in your first JSONL record

After T-01's delegation, open your record and check:

1. **`outcome`** — is it `success`? If `partial`, check `context.delegation_pipeline` for the failing phase (if present).
2. **`context.delegation_pipeline`** — which phase took the most time? `executor` almost always dominates. Skip this if the key is missing (non-implement or pre–Phase 4 run).
3. **`context.context_package.entries`** — which files and tiers made it into the package? (paths only — not content)
4. **`context.builder_brief_applied`** — did the builder LLM stage run? If `true`, check `model_roles.context_builder` for the model; use `prompt_preview` or T-04's `inspect-context` to see the actual brief text
5. **`files_changed` vs `files_requested`** — do they match? If `files_changed` contains entries not in `files_requested`, the executor edited something outside the spec scope — the gateway should have flagged this.
6. **`session_action`** — `new` or `reused`? New is expected on first run or with `always_new` policy.

---

## Next

- **T-03 (Specs):** understand the spec file contract — `## Files`, `## Goal`, `## Constraints`, `## Done when`, front-matter versioning, how the gateway enforces it
- **T-04 (Context compiler):** run `mcp-coder inspect-context` to see exactly what brief the executor received
