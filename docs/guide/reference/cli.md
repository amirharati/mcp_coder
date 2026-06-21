# CLI reference

**Status:** Living — update when commands or flags change.  
**Binary:** `mcp-coder` (installed via `pip install -e .` / `pyproject.toml` entry point → `main:main`).

---

## Quick index

| Command | What it does |
|---------|--------------|
| *(bare)* | Start the MCP stdio server (Cursor mode) |
| [`setup`](#setup) | Configure Cursor mcp.json + workspace |
| [`test-model`](#test-model) | Ping configured models to verify connectivity |
| [`delegate`](#delegate) | Run the full delegation pipeline from the CLI |
| [`inspect-context`](#inspect-context) | Dry-run context compiler, no backend |
| [`view delegations`](#view-delegations) | Browser UI for `delegations.jsonl` |
| [`history`](#history) | Browse / diff / revert from `workspace_history.db` |
| [`rag`](#rag) | Search / index delegation FTS5 (`delegation_rag.db`) |
| [`search`](#search) | Unified search: `delegations` \| `files` (Phase 5 toolset) |
| [`index-workspace`](#index-workspace) | Build / refresh `workspace_rag.db` file summaries |
| [`maintenance`](#maintenance) | Storage stats — JSONL records, trace files, DB row counts |
| [`ps`](#ps) | List running `mcp-coder` stdio server processes |
| [`status`](#status) | Freshness + duplicate-instance health check |
| [`kill`](#kill) | Kill `mcp-coder` stdio server process(es) |

> **Bare invocation at a terminal** prints help; it does **not** start the MCP server. The stdio server starts only when Cursor launches the process (stdin is not a TTY), or when you explicitly pass `--mcp`.

---

## `setup`

Prints workspace / environment status and writes the `mcp-coder` block to Cursor's `mcp.json`.

```
mcp-coder setup [--global | --local] [--init-config]
```

| Flag | Meaning |
|------|---------|
| *(no flag)* | Print status + the JSON block to paste — no file written |
| `--global` | Merge block into `~/.cursor/mcp.json` (system-wide) |
| `--local` | Merge block into `.cursor/mcp.json` in the current directory |
| `--init-config` | Create `.mcp-coder/config.yaml` from the bundled template if absent. Never overwrites. |

**What it checks:**

- `mcp-coder` binary path
- `MCP_CODER_WORKSPACE` / cwd resolution
- `AIDER_MODEL` and provider API key presence
- Spec layout (`specs/tasks/`, `specs/epics/`, `specs/reports/`)
- mcp.json final JSON block

**Typical first-time flow:**

```bash
cd my-project
mcp-coder setup --local --init-config
# Paste printed JSON into .cursor/mcp.json (or the --local flag does it)
# Restart Cursor
```

---

## `test-model`

Sends a minimal ping to configured models using the same Aider/litellm stack that delegations use.

```
mcp-coder test-model [--model MODEL] [--all] [--prompt TEXT]
                     [--max-tokens N] [--via aider|litellm|both]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--model MODEL` | `AIDER_MODEL` | Test a specific model id |
| `--all` | — | Test all configured roles (executor, context_builder, review) sequentially |
| `--prompt TEXT` | `"Reply with exactly: ok"` | Message to send |
| `--max-tokens N` | `16` | litellm path only |
| `--via` | `aider` | `aider` = `Model.send_completion`; `litellm` = raw completion; `both` = compare |

Exit code 0 on success, 1 on failure. Use before first delegation or after changing API keys.

---

## `delegate`

Runs the same pipeline as the `delegate_to_agent` MCP tool — from the terminal. Useful for scripting, CI pipelines, and playground experiments without opening Cursor.

```
mcp-coder delegate --task TEXT --target-files PATH [PATH …]
                   [--context-summary TEXT] [--spec PATH]
                   [--backend aider] [--mode implement|review]
                   [--stop-after context]
                   [--include-payloads] [--pretty]
                   [--workspace PATH]
```

| Flag | Required | Notes |
|------|----------|-------|
| `--task TEXT` | Yes | Task description — seen by executor |
| `--target-files PATH` | Yes (implement) | Repo-relative; repeatable or comma-separated |
| `--context-summary TEXT` | — | Planner decisions (same as MCP) |
| `--spec PATH` | — | Step task spec under `.mcp-coder/specs/tasks/` |
| `--backend` | — | `aider` only today |
| `--mode` | — | `implement` (default) or `review` |
| `--stop-after context` | — | Compile context and print artifacts; do **not** call Aider. No JSONL side effects beyond prepare. |
| `--include-payloads` | — | Include file text in `context_package.entries` |
| `--pretty` | — | Pretty-print JSON output |
| `--workspace PATH` | — | Override repo root |

**Full run** emits the same response JSON as the MCP tool (see `delegate_to_agent` response fields in [mcp-tools.md](mcp-tools.md)).

**`--stop-after context`** is the "prepare-only" mode — equivalent to `inspect-context` but goes through the full `prepare_delegation_context` path. Good for debugging context assembly and verifying what would be sent to Aider without touching files or spending tokens on the executor.

**Example — inspect what context would look like:**

```bash
mcp-coder delegate \
  --workspace . \
  --task "Add retry logic to the HTTP client" \
  --target-files src/http_client.py \
  --context-summary "Using tenacity; max 3 retries with exponential backoff" \
  --spec tasks/auth-02-retry.md \
  --stop-after context \
  --pretty
```

---

## `inspect-context`

Dry-run context compiler with optional helper LLM phases. No executor call, no file edits. CLI-only flags (`--run-builder-llm`, `--run-architect`, `--run-spec-validation`) allow opting into helper phases — these are **not available in the MCP version** which always skips helpers.

```
mcp-coder inspect-context --task TEXT --target-files PATH [PATH …]
                          [--context-summary TEXT] [--spec PATH]
                          [--include-payloads] [--no-adapter-preview]
                          [--include-prompt]
                          [--run-builder-llm] [--run-architect]
                          [--run-spec-validation] [--run-all-helpers]
                          [--host-transcript-file PATH]
                          [--force-helpers]
                          [--fail-on-validation-block]
                          [--pretty] [--workspace PATH]
```

| Flag | Notes |
|------|-------|
| `--task`, `--target-files`, `--context-summary`, `--spec`, `--workspace` | Same as `delegate` |
| `--include-payloads` | Add full file text to `context_package.entries` |
| `--no-adapter-preview` | Omit `adapter_preview` (fnames, prompt stats) |
| `--include-prompt` | Add full executor prompt text in `adapter_preview.prompt` |
| `--run-builder-llm` | Run the context-builder LLM brief pass (API cost) |
| `--run-architect` | Run the architect pass LLM (API cost) |
| `--run-spec-validation` | Run pre-delegate spec validation LLM (API cost) |
| `--run-all-helpers` | Shorthand for all three above |
| `--host-transcript-file PATH` | Inject host transcript for validation / architect |
| `--force-helpers` | Run helpers even when disabled in `config.yaml` |
| `--fail-on-validation-block` | Exit 2 if spec validation would block a real delegate |
| `--pretty` | Pretty-print JSON |

**Output:** JSON with `context_package`, `adapter_preview`, and `helper_phases` if any were run.

**Useful workflow — verify read deps before delegating:**

```bash
mcp-coder inspect-context \
  --task "Add retry logic" \
  --target-files src/http_client.py \
  --spec tasks/auth-02-retry.md \
  --pretty \
  | jq '.adapter_preview | {fnames, read_paths_in_prompt, prompt_tokens_est}'
```

---

## `view delegations`

Opens a browser UI for browsing `delegations.jsonl` logs interactively.

```
mcp-coder view delegations [LOG_FILE] [--workspace PATH] [--port PORT] [--no-open]
```

| Arg / Flag | Default | Meaning |
|------------|---------|---------|
| `LOG_FILE` | — | Path to `delegations.jsonl` (merged logs for cwd workspace if omitted) |
| `--workspace PATH` | cwd | Project root (alternative to explicit LOG_FILE) |
| `--port PORT` | `8765` | Local HTTP port |
| `--no-open` | — | Don't open browser automatically |

`LOG_FILE` and `--workspace` are mutually exclusive.

Viewer behavior (Phase 9):
- Chronological, multi-delegation browser with collapsible delegation blocks
- Boundary-oriented event timeline (`host→mcp`, `mcp.*`, `executor→llm`, `llm→executor`, `executor→mcp`, `mcp→host`)
- Detail panel per row (context, request params, policy, prompt/response fields, tool activity)
- Enrichment loaded lazily from trace + RAG/context sources on card expand

---

## `history`

Browse `workspace_history.db` checkpoints. Provides list, diff, per-file timeline, and revert.

### Subcommands

#### `history list`

```
mcp-coder history list [--workspace PATH] [--limit N] [--spec SPEC_PATH] [--file PATH] [--json]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--limit N` | 20 | Max rows |
| `--spec SPEC_PATH` | — | Filter to a specific spec path |
| `--file PATH` | — | Filter to delegations that touched this path |
| `--json` | — | JSON lines output |

Human output: `<timestamp>  <id8>…  +N ~M -P  <spec>  <summary>`

#### `history show <delegation_id>`

```
mcp-coder history show [DELEGATION_ID] [--latest] [--workspace PATH] [--json]
```

Metadata + created/modified/deleted lists, no diff bodies.

#### `history latest`

```
mcp-coder history latest [--workspace PATH] [--json]
```

Shorthand for `history show --latest`.

#### `history diff <delegation_id>`

```
mcp-coder history diff [DELEGATION_ID] [--latest] [--path PATH] [--workspace PATH] [--json]
```

| Flag | Meaning |
|------|---------|
| `--path PATH` | Filter diff to one file |
| `--json` | Full `delegation_diff` JSON |

Without `--json`: prints unified diff text to stdout (patchable).

#### `history file <file_path>`

```
mcp-coder history file FILE_PATH [--workspace PATH] [--limit N] [--json]
```

Per-file change timeline: which delegations touched the path, change type, summary, and (if stored) inline unified diff.

#### `history revert <delegation_id>`

```
mcp-coder history revert DELEGATION_ID [--paths PATH …] [--workspace PATH]
```

Restores files to their pre-delegation state using stored snapshots.

| Flag | Meaning |
|------|---------|
| `--paths PATH …` | Paths to revert (default: all changed in delegation) |

Prints reverted and skipped paths. Exit 1 if nothing was reverted.

> **Note:** Revert uses snapshot content stored in `workspace_history.db`. If the snapshot is missing (e.g. very old delegation), the revert will skip the path.

---

## `rag`

Inspect and manage the delegation RAG index (`delegation_rag.db` — SQLite FTS5 over `workspace_history.db`).

### Subcommands

#### `rag search <query>`

```
mcp-coder rag search QUERY [--workspace PATH] [--limit N]
                            [--spec-prefix PREFIX] [--outcome OUTCOME] [--json]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `QUERY` | — | Free text; min 2 chars |
| `--limit N` | 5 | Max hits |
| `--spec-prefix PREFIX` | — | Filter spec_path prefix |
| `--outcome OUTCOME` | — | Filter by outcome (`success`, `partial`, `needs_input`, `error`) |
| `--json` | — | Structured JSON output (same schema as `rag_search` MCP tool) |

Human output: `<score>  <timestamp>  <id8>…  <spec>  <summary>`

#### `rag index`

```
mcp-coder rag index [--workspace PATH] [--json]
```

Backfill `delegation_rag.db` from `workspace_history.db`. Run when you've imported an existing history DB or after migrations. New delegations are indexed automatically during `delegate_to_agent`.

#### `rag stats`

```
mcp-coder rag stats [--workspace PATH] [--json]
```

Prints `row_count`, `last_indexed` timestamp, `db_path`.

> **Note:** `mcp-coder rag` is the legacy delegation-only interface. Prefer **`mcp-coder search delegations`** for the same backend plus `--format plain` (executor-injectable snippets). Both remain supported.

---

## `search`

Unified keyword search over indexed corpora (same backends as `rag_search` and `workspace_search` MCP tools).

### Subcommands

#### `search delegations <query>`

```
mcp-coder search delegations QUERY [--workspace PATH] [--limit N]
                                [--spec-prefix PREFIX] [--outcome OUTCOME]
                                [--format table|plain] [--json]
```

Same hits as `mcp-coder rag search` / `rag_search` MCP. `--format plain` emits copy-paste blocks for executor prompts.

#### `search files <query>`

```
mcp-coder search files QUERY [--workspace PATH] [--limit N]
                             [--format table|plain] [--json]
```

Requires `workspace_rag.db` (run `index-workspace` first). Same backend as `workspace_search` MCP.

---

## `index-workspace`

Index workspace source files into `workspace_rag.db` (per-file LLM summary + FTS5).

```
mcp-coder index-workspace [--workspace PATH] [--changed-only] [--limit N] [--json]
```

| Flag | Meaning |
|------|---------|
| `--changed-only` | Re-index only new/changed files (sha256 staleness) |
| `--limit N` | Cap files processed (useful for dry runs) |
| `--json` | Summary JSON (`indexed`, `skipped`, `errors`, …) |

**When to run:** Once per repo before first file RAG use; thereafter delegations incrementally re-index `files_changed`. Controlled by `workspace_file_rag` (default on).

---

## Environment variables

| Var | Used by | Meaning |
|-----|---------|---------|
| `MCP_CODER_WORKSPACE` | all commands | Override workspace root (default: cwd) |
| `AIDER_MODEL` | `test-model`, server | Executor model |
| `MCP_CODER_LOG_FULL_PROMPT` | server | `1` = include full prompt in `delegations.jsonl` (off by default) |
| `MCP_CODER_HOST` | server | Host provider override (`auto`, `cursor`, `none`) |
| `MCP_CODER_SINGLETON` | server | `0` = allow multiple stdio servers (default `1`) |
| `MCP_CODER_RAG_ENABLED` | server | Master RAG index toggle (default on) |
| `MCP_CODER_BUILDER_HISTORY_RAG` | server | Builder delegation RAG (default on) |
| `MCP_CODER_WORKSPACE_FILE_RAG` | server | Workspace-file corpus (default on) |
| `MCP_CODER_WORKSPACE_FILE_HINTS` | server | File hints in picker/builder (default on) |
| `MCP_CODER_BUILDER_RAG_K` | server | Max delegation hits in builder (default 5) |
| `MCP_CODER_WORKSPACE_FILE_RAG_K` | server | Max file hits in builder (default 5) |
| `MCP_CODER_SESSION_POLICY` | server | `always_new` or `align_host` |

| `MCP_CODER_OBSERVABILITY_VERBOSITY` | server | `lean` \| `standard` \| `full` — trace file content depth (default `standard`) |
| `MCP_CODER_CAPTURE_FOR_TRAINING` | server | `1` = write `traces/<id>-training.json` opt-in tuples (off by default) |

`.env` files at workspace root and mcp-coder repo root are loaded automatically on server start.

---

## `maintenance`

Storage health and stats for the current workspace.

```
mcp-coder maintenance stats [--workspace PATH]
```

Prints a summary of all storage artifacts for the workspace:

```
JSONL records:          23       (across all sessions)
Trace files:             2       9743 B
delegation_rag.db:      23 rows
workspace_rag.db:        8 rows
workspace_history.db:   23 snapshots
capture_for_training:   false
```

Use after a delegation to confirm trace files are being written and DB row counts are incrementing. Useful for validating observability config (`observability_verbosity`, `capture_for_training`).

> **Note:** Trace files are written under `sessions/<id>/traces/` for delegations across verbosity tiers. `lean` writes minimal hash/size style records; `standard` adds previews; `full` adds bodies.

---

## `ps`

Lists active `mcp-coder` stdio server processes (PID, start time, workspace cwd, full command).

```bash
mcp-coder ps
```

Use this to quickly confirm whether one or multiple MCP servers are running.

---

## `status`

Checks stdio server health/freshness for current local code:

```bash
mcp-coder status
```

Reports:
- `NO_STDIO_SERVER` / `ONE_STDIO_SERVER` / `MULTIPLE_STDIO_SERVERS`
- per-process start time, workspace cwd, command
- freshness relative to latest local dirty-file change

Exit codes:
- `0`: healthy
- `1`: no server
- `2`: stale or multiple servers

---

## `kill`

Kill running stdio server process(es):

```bash
mcp-coder kill
mcp-coder kill --workspace /path/to/workspace
mcp-coder kill --workspace /path/to/workspace --min-age-seconds 5
mcp-coder kill --all
```

- default: kills only the process whose cwd matches current workspace
- `--workspace`: explicit workspace-scoped kill
- `--min-age-seconds`: skip killing very new processes (useful to avoid reconnect race)
- `--all`: kill every `mcp-coder` stdio process across workspaces

---

## Storage paths (quick ref)

| Path | Contents |
|------|----------|
| `~/.mcp-coder/projects/<key>/sessions/<id>/delegations.jsonl` | Audit log — one lean record per delegation |
| `~/.mcp-coder/projects/<key>/sessions/<id>/traces/<id>.jsonl` | Per-delegation trace events (`llm_call`, `tool_call`, `action`, `compile_event`) |
| `~/.mcp-coder/projects/<key>/workspace_history.db` | SQLite — snapshots + checkpoints + file deltas |
| `~/.mcp-coder/projects/<key>/delegation_rag.db` | SQLite FTS5 — delegation summaries |
| `~/.mcp-coder/projects/<key>/workspace_rag.db` | SQLite FTS5 — workspace-file summaries |
| `.mcp-coder/specs/tasks/<slug>.md` | Step task specs |
| `.mcp-coder/specs/epics/<slug>.md` | Epic specs |
| `.mcp-coder/specs/reports/<slug>-report.md` | Appended delegation reports |
| `.mcp-coder/config.yaml` | Workspace configuration |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-13 | Phase 7 sync — trace path note updated (all tiers), event-type description updated, maintenance stats sample now includes executor turns |
| 2026-06-13 | Phase 6 — `maintenance stats` added; observability env vars; trace file storage path; lean JSONL note |
| 2026-06-13 | Phase 5 — `search`, `index-workspace`; RAG defaults on; env vars for corpus toggles |
| 2026-06-12 | Initial version — all commands with full flag tables, examples, env vars, storage paths |
