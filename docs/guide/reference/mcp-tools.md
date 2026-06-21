# MCP tools reference

**Status:** Living — update when tool signatures or response shapes change.  
**Source:** `server/mcp_server.py` — every `@mcp.tool` decorator.  
**How called:** All tools are invoked by the host (Cursor today) via JSON-RPC over stdio. The host sees the tool schema; Cursor's agent rules (`use-mcp-coder.mdc`) guide *when* to call each one.

---

## Quick index

| Tool | Category | Edits disk? | Returns |
|------|----------|-------------|---------|
| [`delegate_to_agent`](#delegate_to_agent) | **Primary** | Yes (implement mode) | Delegation response |
| [`answer_delegation_question`](#answer_delegation_question) | **In-flight** | No | Gate status |
| [`get_server_status`](#get_server_status) | Health | No | PID + freshness info |
| [`inspect_context`](#inspect_context) | Dry-run | No | ContextPackage JSON |
| [`list_delegations`](#list_delegations) | History | No | Delegation list |
| [`get_checkpoint_detail`](#get_checkpoint_detail) | History | No | Checkpoint metadata |
| [`get_file_history`](#get_file_history) | History | No | Per-file timeline |
| [`get_delegation_diff`](#get_delegation_diff) | History | No | Unified diffs |
| [`rag_search`](#rag_search) | Search | No | Ranked past delegations |
| [`workspace_search`](#workspace_search) | Search | No | Ranked workspace-file summaries |

---

## `delegate_to_agent`

**The primary tool.** Runs the full delegation pipeline: spec validation + clarity check → compiles context → supervisor loop (executor + reviewer) → audits the result → writes JSONL + spec report.

### Parameters

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `task` | `str` | Yes | What the executor should do — free text, seen by executor |
| `target_files` | `list[str]` | Yes | Repo-relative paths. For `implement`: edit targets (+ read deps if `auto_merge_spec_read` is on). For `review`: **must be `[]`** |
| `context_summary` | `str` | Yes | Decisions from chat the executor can't otherwise see. Never omit — this is the planner's voice |
| `spec_path` | `str` | No | Step task spec path under `.mcp-coder/specs/tasks/` (e.g. `tasks/auth-01-model.md`). Strongly recommended for all implement calls |
| `mode` | `str` | No | `implement` (default) or `review` (questions only, no edits) |
| `backend` | `str` | No | `aider` (only backend today) |
| `model_policy` | `dict` | No | Per-delegation role overrides. Keys: `executor`, `planner`, `supervisor`, `reviewer`, `context_builder`. Each value: `{model, reasoning_effort, thinking_budget}` |

### Modes

**`implement`** — executor edits `target_files` on disk. Full pipeline runs:
`spec_validation?` → `clarity_check?` → `file_picker` → `assemble` → `planner_pass?` → `builder_llm?` → supervisor loop (`executor` + `reviewer_pass?`) → `post_gateway` → `spec_report` → `verify?`

**`review`** — LLM answers questions about the spec / code. `target_files` must be `[]`. Most pipeline stages skipped. Returns answer text in `output`.

### Pre-execution gates

Two stages can block execution before the executor runs, returning `outcome: needs_input`:

| Stage | Env var | When it blocks |
|-------|---------|----------------|
| `spec_validation` | `MCP_CODER_SPEC_VALIDATION` | Spec text has genuine ambiguity or missing decisions |
| `clarity_check` | `MCP_CODER_CLARITY_PASS` | Task description is underspecified or contradicts the spec |

When blocked: `success: false`, `outcome: needs_input`, `clarification_needed: [...]` — no files changed, no executor tokens spent.

### Response fields (JSON string)

**Always present:**

| Field | Type | Meaning |
|-------|------|---------|
| `success` | `bool` | Whether the executor ran without error |
| `output` | `str` | Executor's output tail (truncated to ~4000 chars) |
| `files_changed` | `list[str]` | Files created/modified/deleted by the executor (from snapshot diff) |
| `files_unexpected` | `list[str]` | Files changed outside the spec Files contract |
| `session_reused` | `bool` | Whether an existing Aider `Coder` instance was reused |
| `session_policy` | `str` | `always_new` or `align_host` |

**Present when a spec was used:**

| Field | Type | Meaning |
|-------|------|---------|
| `outcome` | `str` | `success`, `partial`, `needs_input`, `error` |
| `spec_path` | `str` | Normalized spec path |
| `spec_report_path` | `str` | Path to the updated spec report |
| `delegation_pipeline` | `list` | Per-phase `{phase, status, duration_ms}` |
| `judgment_checklist` | `dict` | Structured checklist for planner post-delegate review |
| `delegation_diff` | `dict` | Summary of what changed (paths + sizes) |
| `scope_violations` | `list[str]` | Paths edited outside `files_edit` when `edit_scope: strict` |
| `contract_warnings` | `list[str]` | Spec contract issues (e.g. edit paths missing from `target_files`) |

**Present when relevant:**

| Field | Type | Meaning |
|-------|------|---------|
| `clarification_needed` | `list[str]` | Set when `spec_validation` or `clarity_check` blocks — questions for the planner |
| `prior_failed_attempts` | `list` | Past failures on the same spec (surface for planner adjustment) |
| `auto_merged_read_paths` | `list[str]` | Read paths auto-added from spec `files_read` |
| `suggested_edit_paths` | `list[str]` | Symbol-scan hits in edit dirs (audit hint, not in contract) |
| `model_roles` | `dict` | Per-role model + token counts. Roles: `executor`, `planner`, `context_builder`, `supervisor`, `reviewer`. `source` field indicates measurement method |
| `context_refs` | `list` | RAG retrieval hits (delegation + workspace-file) when `rag_retrieval` ran |
| `usage` | `dict` | Token estimate + preflight info |
| `verify_result` | `dict` | `auto_verify` outcome (command, exit_code, passed) |
| `error_class` / `error_message` | `str` | Structured error info on failure |
| `log_path` | `str` | Path to the session's `delegations.jsonl` file |

### What gets written to disk

- One **lean** record (~12 KB) appended to `~/.mcp-coder/projects/<key>/sessions/<id>/delegations.jsonl`
- Per-delegation trace events written to `sessions/<id>/traces/<delegation_id>.jsonl` — includes `llm_call`, `compile_event`, `clarity_result`, `supervisor_loop_start/end`, `supervisor_turn_start/end`, `supervisor_decision`, and `backend_llm_call` events for every role
- Spec report appended to `.mcp-coder/specs/reports/<spec-name>-report.md`
- Workspace history row + checkpoint + file diffs in `workspace_history.db`
- Delegation indexed in `delegation_rag.db` (FTS5)
- Changed files incrementally re-indexed in `workspace_rag.db` when `workspace_file_rag` is on

### When a gate blocks

If `spec_validation` or `clarity_check` finds a problem: `success: false`, `outcome: needs_input`, `clarification_needed: [...]` — executor never runs, no files changed. **Pipeline stops before `file_picker`** — `context_refs` stays empty.

---

## `answer_delegation_question`

Unblock a paused delegation by providing a human answer to an escalated supervisor question. Call while `delegate_to_agent` is still running after it emits a `[gate]` notification in the host.

### Parameters

| Param | Type | Notes |
|-------|------|-------|
| `delegation_id` | `str` | The active delegation ID shown in the gate notification |
| `answer` | `str` | `yes` / `no` (or any text — `yes`/`y`/`true`/`1` = approve) |

### Response

```json
{"status": "ok", "delegation_id": "...", "answer": "yes"}
```

`status: not_found` if no gate is waiting for that delegation ID (already timed out or completed).

> **Note:** This requires the MCP client to support concurrent tool calls. If Cursor's implementation does not, the gate will time out and the delegation will abort with `needs_input` — no data is lost.

---

## `get_server_status`

Return MCP server runtime identity and freshness signals. Use to confirm Cursor is talking to the most recent local server code.

### Parameters

| Param | Type | Notes |
|-------|------|-------|
| `workspace_path` | `str` | Optional override |

### Response fields

| Field | Meaning |
|-------|---------|
| `pid` | Server process PID |
| `source_revision` | Git commit hash of running code |
| `started_at` | Process start timestamp |
| `is_stale` | True if local files are newer than the running process |
| `stale_files` | List of files changed since process start |
| `sibling_pids` | Other `mcp-coder` stdio processes (duplicate instances) |

---

## `inspect_context`

Dry-run context compiler. Builds the `ContextPackage` that *would* be sent to the executor — without calling any backend or editing any files. Helper LLM phases are not available via MCP (use `mcp-coder inspect-context --run-all-helpers` from CLI).

### Parameters

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `task` | `str` | Yes | Same as `delegate_to_agent` |
| `target_files` | `list[str]` | Yes | Same |
| `context_summary` | `str` | Yes | Same |
| `spec_path` | `str` | No | Same |
| `include_payloads` | `bool` | No | Include full file text in `entries` (default `false` — can be large) |
| `include_adapter_preview` | `bool` | No | Include `fnames`, `read_paths_in_prompt`, sizes (default `true`) |
| `include_prompt` | `bool` | No | Include full executor prompt text (default `false`) |

### Response fields

| Field | Meaning |
|-------|---------|
| `context_package.entries` | Per-file `{path, tier, bytes, excerpt_path}` |
| `context_package.brief` | The compiled brief text |
| `context_package.metadata` | Budget, truncations, candidate_files, symbol_queries, repo_map_count |
| `adapter_preview.fnames` | Paths Aider would open for editing |
| `adapter_preview.read_paths_in_prompt` | Paths injected as fenced read blocks |
| `adapter_preview.prompt_chars` / `prompt_tokens_est` | Prompt size estimate |
| `adapter_preview.prompt` | Full executor prompt (only if `include_prompt: true`) |
| `auto_merged_read_paths` | Read paths auto-added from spec |
| `context_refs` | RAG hits when `rag_retrieval` ran |
| `contract_warnings` | Spec contract issues |

---

## `list_delegations`

Browse recent checkpoints from `workspace_history.db`. Lighter than parsing `delegations.jsonl` directly.

### Parameters

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `limit` | `int` | 20 | Max rows |
| `spec_path` | `str` | — | Filter to delegations for this spec |
| `file_path` | `str` | — | Filter to delegations that touched this path |
| `workspace_path` | `str` | — | Workspace root (default: `MCP_CODER_WORKSPACE` / cwd) |

### Response

List of checkpoint rows with `delegation_id`, `timestamp`, `outcome`, `spec_path`, `files_changed`, `checkpoint_summary`.

---

## `get_checkpoint_detail`

Return metadata + file delta lists for a single delegation checkpoint. No unified diffs (use `get_delegation_diff` for those).

### Parameters

| Param | Type | Notes |
|-------|------|-------|
| `delegation_id` | `str` | From `delegate_to_agent` response or `list_delegations` |
| `latest` | `bool` | Use the most recent checkpoint if no `delegation_id` |
| `workspace_path` | `str` | Optional override |

---

## `get_file_history`

Per-file timeline: which delegations touched the path, what changed.

### Parameters

| Param | Type | Notes |
|-------|------|-------|
| `file_path` | `str` | Repo-relative path |
| `limit` | `int` | Default 20 |
| `workspace_path` | `str` | Optional |

---

## `get_delegation_diff`

Return unified diffs and file delta summary for a delegation checkpoint.

### Parameters

| Param | Type | Notes |
|-------|------|-------|
| `delegation_id` | `str` | From `delegate_to_agent` or `list_delegations` |
| `latest` | `bool` | Most recent if no id |
| `file_path` | `str` | Filter diffs to one file |
| `workspace_path` | `str` | Optional |

---

## `rag_search`

Keyword search over indexed past delegations (FTS5 over `delegation_rag.db`).

### Parameters

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `query` | `str` | — | Free text — searches summaries, tasks, spec paths |
| `limit` | `int` | 5 | Max hits |
| `spec_path_prefix` | `str` | — | Filter by spec path prefix |
| `outcome` | `str` | — | Filter by outcome (`success`, `partial`, etc.) |
| `workspace_path` | `str` | — | Optional |

### Response

Ranked list with `delegation_id`, `score`, `spec_path`, `outcome`, `checkpoint_summary`. Pair with `get_delegation_diff` for the full diff.

Also available via `mcp-coder search delegations` CLI (`--format plain` for executor snippets).

---

## `workspace_search`

Keyword search over indexed workspace-file summaries (`workspace_rag.db`).

### Parameters

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `query` | `str` | — | Free text — searches file paths + summary text |
| `limit` | `int` | 5 | Max hits |
| `workspace_path` | `str` | — | Optional |

### Response

Ranked list with `path`, `score`, `snippet` (summary excerpt). Requires `mcp-coder index-workspace` (or a prior delegate that indexed changed files). Parity: `mcp-coder search files` CLI.

**Builder integration:** When `workspace_file_hints` is on (default), hits feed the picker and appear in `## Relevant prior work` + `context_refs[]`.

---

## How Cursor calls these tools

Cursor's agent reads `use-mcp-coder.mdc` (synced by `mcp-coder setup`) which instructs it when to call each tool. Key rules:

- `delegate_to_agent` when the user asks to build / create / change files — with `spec_path` when a step spec exists.
- `answer_delegation_question` when a `[gate]` notification arrives mid-delegation (concurrent tool call).
- `get_server_status` to confirm it is talking to the latest local server code before starting work.
- `inspect_context` before delegating when scope or read-deps are uncertain.
- History tools (`list_delegations`, `get_file_history`, etc.) when the user asks "what changed?", "what did the last step do?", or to inform the next `context_summary`.
- `rag_search` / `workspace_search` when the user asks about prior work, a topic, or "where is X implemented?" — or to sanity-check what the builder will retrieve.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-20 | Added `answer_delegation_question` and `get_server_status` tools; added `model_policy` param to `delegate_to_agent`; updated pipeline description with all 7 phases; added pre-execution gates section; updated `model_roles` response to include all 5 roles; updated disk-writes list with supervisor trace events |
| 2026-06-13 | `model_roles` tokens now live (not null); lean JSONL note; trace file in disk-writes list |
| 2026-06-13 | `workspace_search`, `context_refs`; builder RAG wired; validation-block note |
| 2026-06-12 | Initial version — all 7 tools, parameter tables, response fields, Cursor call rules |
