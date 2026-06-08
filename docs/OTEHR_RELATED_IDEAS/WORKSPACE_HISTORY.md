<!--
  STEWARDSHIP — Tier 3 related idea (not canonical). See docs/VISION_DOCS.md.

  - This design emerged organically from the Phase 2 tail review session (2026-06-07).
  - Informs BL-322 in BACKLOG.md. Does not override IDEA.md.
  - Do not treat as shipped design without a Phase 3 task spec.
-->

# Workspace History — Delegation-Granularity Version Control

**Status:** Design idea — Phase 3 candidate. See [BL-322](../BACKLOG.md#bl-322-workspace-hash-snapshot--post-delegation-gateway).  
**Related:** [GATEKEEPING_MCP.md](./GATEKEEPING_MCP.md) (pre-run gate) · [CONTEXT_AS_GIT.md](./CONTEXT_AS_GIT.md) · [BL-314](../BACKLOG.md) · [P2-ISS-002](../PHASE2_ISSUES.md)

---

## The problem this solves

In a human-in-the-loop AI coding workflow, the planner (Cursor + human) makes decisions between MCP calls:

- Did this delegation do what I intended?
- What files were created — including ones Aider invented beyond the spec?
- Did something change that shouldn't have?
- Tests are failing in task 5 — when did `models.py` break?

Today, mcp-coder reports `files_changed` / `files_unexpected` via git diff. This works when the workspace is a git repo. It fails silently when:

- The workspace has no git
- Aider creates new untracked files
- The workspace is dirty before delegation (pre-existing untracked files, human WIP)
- Multiple MCP calls accumulate changes without any commit checkpoint

Forcing the user to `git commit` between calls, or `git init` their workspace, or keep a clean working tree is not acceptable. Real projects are messy.

---

## The insight (discovered 2026-06-07)

> mcp-coder can own its own lightweight, delegation-scoped version control layer — independent of git, invisible to the user, automatic.

Key properties:

1. **Hash everything** — not just `target_files`, not git-tracked files only. Every text file in the workspace gets SHA-256'd before the delegation runs.
2. **Delta storage** — store unified diffs (not full copies) of what changed. Unchanged files cost nothing. Content-addressable blob store for new files (created by delegation).
3. **Per-delegation checkpoint** — one checkpoint per `delegate_to_agent` call. Granularity matches the human review loop exactly.
4. **Non-invasive** — no git writes, no branches, no stash, no cleanup of user's working tree. Completely invisible to the user's own git workflow.
5. **Persistent history** — checkpoints accumulate across sessions. Time-travel to any past MCP call boundary.

---

## Why this is stronger than git for this purpose

| | User's git | mcp-coder workspace history |
|--|------------|----------------------------|
| Requires `git init` | Yes | No |
| Works with messy/dirty workspace | No (stash/commit required) | Yes |
| Tracks new untracked files | No (until `git add`) | Yes |
| Tracks changes to gitignored files | No | Yes (intentionally — catches policy violations) |
| Granularity | Developer commits (manual) | Per MCP delegation call (automatic) |
| Understands spec contract | No | Yes — can flag which changes were outside `files_edit` |
| Time-travel to AI task boundary | No | Yes |
| Revert individual files to pre-task state | Via `git checkout` (but only tracked files) | Yes, any file, any checkpoint |

The user's git is for **developer intent** (commits). This is for **AI execution checkpoints** — a different, complementary thing.

---

## Storage design: SQLite delta store

Single file per workspace, stored in mcp-coder home:

```text
~/.mcp-coder/projects/<project_key>/workspace_history.db
```

### Schema

```sql
-- One row per delegation
CREATE TABLE snapshots (
    delegation_id  TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL,
    timestamp      TEXT NOT NULL,
    spec_path      TEXT,            -- which task spec triggered this
    workspace_path TEXT NOT NULL
);

-- One row per file that changed in a delegation
-- Only changed/created/deleted files are stored (unchanged = zero cost)
CREATE TABLE file_deltas (
    snapshot_id    TEXT NOT NULL REFERENCES snapshots(delegation_id),
    path           TEXT NOT NULL,   -- workspace-relative path
    change_type    TEXT NOT NULL,   -- 'created' | 'modified' | 'deleted' | 'renamed'
    content_hash   TEXT,            -- SHA-256 of content after this delegation
    prev_hash      TEXT,            -- SHA-256 of content before (NULL if created)
    diff           TEXT,            -- unified diff (NULL if created or deleted)
    is_binary      BOOLEAN DEFAULT 0,
    PRIMARY KEY (snapshot_id, path)
);

-- Content-addressable blob store — deduplication across all snapshots
CREATE TABLE blobs (
    hash     TEXT PRIMARY KEY,
    content  TEXT NOT NULL          -- full file content for 'created' files
);
```

### Why SQLite

- **Stdlib** (`sqlite3`) — zero new dependencies
- **Atomic transactions** — snapshot is committed atomically; partial runs don't corrupt history  
- **WAL mode** — safe for multiple sessions writing to same workspace (MCP is single-threaded but CLI may run alongside)
- **Self-contained** — one file, easy to inspect, copy, delete
- **Efficient** — only changed files stored; blobs deduplicated by content hash

### Delta storage example

```text
Task 2 changed models.py (was 500 lines, added 3 lines):
  file_deltas row: path=src/models.py, change_type=modified,
                   diff="@@ -43,4 +43,7 @@ ..."     ← 50 bytes, not 10KB

Task 2 created utils.py (new file, 80 lines):
  blobs row: hash=abc123, content="..."             ← full content once
  file_deltas row: path=src/utils.py, change_type=created, content_hash=abc123

Task 3 deleted old_helper.py:
  file_deltas row: path=old_helper.py, change_type=deleted, prev_hash=def456
  (content already in blobs from when it was created — no duplicate)

Task 4 models.py unchanged:
  (no file_deltas row — zero storage cost)
```

---

## What to scan (workspace walk)

```python
HARD_SKIP_DIRS = {
    "node_modules", ".venv", "venv", "env",
    "__pycache__", ".git", "dist", "build",
    ".tox", ".mypy_cache", ".pytest_cache",
    ".mcp-coder",   # avoid recursing into our own storage
}

HARD_SKIP_EXTENSIONS = {
    ".pyc", ".so", ".dll", ".exe",
    ".jpg", ".jpeg", ".png", ".gif", ".pdf",
    ".zip", ".tar", ".gz", ".whl",
}

BINARY_HEURISTIC = True   # try UTF-8 decode; if fails, mark is_binary=True, hash only
MAX_FILE_SIZE_MB  = 1     # configurable MCP_CODER_SNAPSHOT_MAX_FILE_MB
```

No `.gitignore` dependency. The exclusion list is **mcp-coder's own judgment** about what changes meaningfully for the project. Binary files are hashed (detect creation/deletion/rename) but not diffed.

---

## Time-travel API

```python
# Reconstruct a file's content at any checkpoint
history.file_at(delegation_id, "src/models.py") -> str

# Walk a file's change history across all delegations
history.file_history("src/models.py") -> list[FileChange]
# → [{delegation_id, timestamp, change_type, spec_path, diff}, ...]

# Full diff for one delegation
history.delegation_diff(delegation_id) -> DelegationDiff
# → {created: [...], modified: [...], deleted: [...], diffs: {path: unified_diff}}

# Revert files to their state before a specific delegation
history.revert_to_before(delegation_id, paths=["src/models.py"])
# → writes pre-delegation content back to disk

# Reconstruct entire workspace as of a delegation (selective restore)
history.workspace_at(delegation_id) -> dict[str, str]
# → {path: content} for all files as they were after that delegation
```

These can be exposed as:
- **MCP tools**: `get_delegation_diff(delegation_id)`, `revert_to_checkpoint(delegation_id, paths)`  
- **CLI**: `mcp-coder history list`, `mcp-coder history diff <id>`, `mcp-coder history revert <id>`

---

## The "find when it broke" workflow

```bash
$ mcp-coder history list --file src/models.py

  del-001  2026-06-07 14:23  task-1-core-split    modified
  del-003  2026-06-07 15:41  task-2-add-loader    modified  ← when did it break?
  del-007  2026-06-07 17:02  task-3-tests         modified

$ mcp-coder history diff del-003 src/models.py

  --- src/models.py (before task-2-add-loader)
  +++ src/models.py (after)
  @@ -12,3 +12,5 @@
       def load(self, path):
  -        return json.load(open(path))
  +        with open(path) as f:           ← looks fine
  +            return json.load(f, strict=True)  ← strict=True broke callers

$ mcp-coder history revert del-002 --files src/models.py
  Reverted src/models.py to state after del-002.
```

---

## Connection to gatekeeping (BL-151 + BL-322c)

The workspace history snapshot is the **prerequisite** for a real post-delegation policy gate:

```text
BEFORE delegation:   take_snapshot(delegation_id)
AIDER RUNS
AFTER delegation:    diff = compute_diff(delegation_id)
                     violations = diff.all_changes - spec.files_edit
                     
                     if edit_scope == "strict" and violations:
                         revert_files(violations, to=before_this_delegation)
                         report_blocked(violations)
                     elif edit_scope == "discover":
                         report_informational(diff.unexpected)
```

Today `strict` mode reports violations but leaves the workspace dirty. With BL-322b (content snapshot), strict mode can **enforce** a clean post-state — only contract-allowed changes remain.

This connects:
- **BL-322a** (hash manifest) → reliable attribution
- **BL-322b** (content snapshot) → revert capability  
- **BL-322c** (post-gate) → enforcement, not just reporting
- **BL-151** (pre-gate) → validate spec before running

Together: full enforcement cycle with evidence trail.

---

## Multi-session / single workspace

Multiple Cursor sessions writing to the same workspace all append to the same `workspace_history.db`. Each delegation has a `session_id` and `delegation_id` — no conflicts.

SQLite WAL mode handles concurrent readers; MCP stdio is single-threaded for writes.

**Scope boundary:** one workspace = one DB. Cross-workspace / monorepo linking is Phase 4+ (BL-304).

---

## Retention policy

Configurable in `.mcp-coder/config.yaml`:

```yaml
snapshot_retention: session   # ephemeral | session | all (default: session)
```

| Mode | Behaviour |
|------|-----------|
| `ephemeral` | Delete snapshot data immediately after diff is computed. No history. Just attribution. |
| `session` | Keep per-session. Auto-clean on `session_policy: always_new` when session expires. |
| `all` | Keep indefinitely. Full project-lifecycle time-travel. |

Default `session` gives useful history within a task without indefinite accumulation.

---

## Phase 3 implementation order

```text
Phase 3a — BL-322a:  Hash manifest scan + delta DB
           Replaces mtime fallback in git_diff.py
           Closes P2-ISS-002
           Gives accurate files_changed + files_unexpected in all workspaces

Phase 3b — BL-322b:  Content snapshot for files_edit + files_read
           Enables revert
           Strict mode with teeth

Phase 3c — BL-322c:  Post-delegation gateway
           Enforce contract, not just report

Phase 3d — BL-322d:  MCP tools + CLI for history / diff / revert
           Planner-facing time-travel
```

---

## Why this is a big deal for AI coding workflows

The core problem with AI coding tools that don't do auto-git: **you can lose track of what the AI did**, especially across multiple calls, failed attempts, and sessions. Forcing the user to commit constantly, or maintain a pristine working tree, is friction that breaks the flow.

This design gives:
1. **Complete, automatic audit** — every AI action recorded at the right granularity
2. **Non-invasive** — user's git workflow, untracked files, WIP all untouched
3. **Reversible** — any file, any checkpoint, without git
4. **Policy-enforceable** — the diff is the input to the gate
5. **Inspectable** — unified diff format, human-readable, standard tooling

It's purpose-built for the delegation lifecycle that mcp-coder already manages. The storage layer (`workspace_history.db`) lives alongside `delegations.jsonl` in the same project directory — same lifecycle, same ownership.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-07 | Initial design — emerged from Phase 2 tail review (chat [Phase 2 tail review](d44a5b15-2ed4-4834-bc91-91f776e5dd02)) |
