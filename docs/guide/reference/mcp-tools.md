# MCP tools reference

**Status:** Living — update when tool signatures or response shapes change.  
**Source:** `server/mcp_server.py` — every `@mcp.tool` decorator.  
**How called:** All tools are invoked by the host (Cursor today) via JSON-RPC over stdio. The host sees the tool schema; Cursor's agent rules (`use-mcp-coder.mdc`) guide *when* to call each one.

---

## Quick index

| Tool | Category | Edits disk? | Returns |
|------|----------|-------------|---------|
| [`delegate_to_agent`](#delegate_to_agent) | **Primary** | Yes (implement mode) | Delegation response |
| [`inspect_context`](#inspect_context) | Dry-run | No | ContextPackage JSON |
| [`list_delegations`](#list_delegations) | History | No | Delegation list |
| [`get_checkpoint_detail`](#get_checkpoint_detail) | History | No | Checkpoint metadata |
| [`get_file_history`](#get_file_history) | History | No | Per-file timeline |
| [`get_delegation_diff`](#get_delegation_diff) | History | No | Unified diffs |
| [`rag_search`](#rag_search) | Search | No | Ranked past delegations |
| [`workspace_search`](#workspace_search) | Search | No | Ranked workspace-file summaries |

---

## `delegate_to_agent`

**The primary tool.** Runs the full delegation pipeline: compiles context, calls the executor (Aider today), audits the result, writes JSONL + spec report.

### Parameters

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `task` | `str` | Yes | What the executor should do — free text, seen by executor |
| `target_files` | `list[str]` | Yes | Repo-relative paths. For `implement`: edit targets (+ read deps if `auto_merge_spec_read` is on). For `review`: **must be `[]`** |
| `context_summary` | `str` | Yes | Decisions from chat the executor can't otherwise see. Never omit — this is the planner's voice |
| `spec_path` | `str` | No | Step task spec path under `.mcp-coder/specs/tasks/` (e.g. `tasks/auth-01-model.md`). Strongly recommended for all implement calls |
| `mode` | `str` | No | `implement` (default) or `review` (questions only, no edits) |
| `backend` | `str` | No | `aider` (only backend today) |

### Modes

**`implement`** — executor edits `target_files` on disk. Full pipeline runs: spec read → validation? → picker → assemble → builder? → executor → gateway → report → verify?

**`review`** — LLM answers questions about the spec / code. `target_files` must be `[]`. Most pipeline stages skipped. Returns answer text in `output`.

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
| `clarification_needed` | `list[str]` | Set when `spec_validation` blocks — questions for the planner |
| `prior_failed_attempts` | `list` | Past failures on the same spec (surface for planner adjustment) |
| `auto_merged_read_paths` | `list[str]` | Read paths auto-added from spec `files_read` |
| `suggested_edit_paths` | `list[str]` | Symbol-scan hits in edit dirs (audit hint, not in contract) |
| `model_roles` | `dict` | Per-role model + token counts — live counts for all 4 roles since Phase 6; `source` field indicates measurement method (`owned_completion` for helpers, `aider_output_parse` for executor) |
| `context_refs` | `list` | RAG retrieval hits (delegation + workspace-file) when `rag_retrieval` ran |
| `usage` | `dict` | Token estimate + preflight info |
| `verify_result` | `dict` | `auto_verify` outcome (command, exit_code, passed) |
| `error_class` / `error_message` | `str` | Structured error info on failure |
| `log_path` | `str` | Path to the session's `delegations.jsonl` file |

### What gets written to disk

- One **lean** record (~12 KB) appended to `~/.mcp-coder/projects/<key>/sessions/<id>/delegations.jsonl` — pointers and hashes, bodies stored separately
- Per-delegation trace events written to `sessions/<id>/traces/<delegation_id>.jsonl` (`llm_call`, `tool_call`, `action`, `compile_event`)
- Spec report appended to `.mcp-coder/specs/reports/<spec-name>-report.md`
- Workspace history row + checkpoint + file diffs in `workspace_history.db`
- Delegation indexed in `delegation_rag.db` (FTS5)
- Changed files incrementally re-indexed in `workspace_rag.db` when `workspace_file_rag` is on

### When spec_validation blocks

If `spec_validation: true` in config and the LLM finds real ambiguity: `success: false`, `outcome: needs_input`, `clarification_needed: [...]` — executor never runs, no files changed. **Pipeline stops before `rag_retrieval`** — `context_refs` stays empty (by design; see BL-364).

---

## `inspect_context`

Dry-run context compiler. Builds the `ContextPackage` that *would* be sent to the executor — without calling any backend or editing any files.

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
| `context_refs` | RAG hits when `rag_retrieval` ran (inspect dry-run mirrors delegate) |
| `contract_warnings` | Spec contract issues |

**Note:** `inspect_context` (MCP) does not run helper LLMs. Use `mcp-coder inspect-context --run-builder-llm` from CLI to opt into helper phases.

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

Cursor's agent reads `use-mcp-coder.mdc` (synced by `mcp-coder setup`) which instructs it when to call each tool. The key rules today:

- `delegate_to_agent` when user asks to build / create / change files — with `spec_path` when a step spec exists.
- `inspect_context` before delegating when scope or read-deps are uncertain.
- History tools (`list_delegations`, `get_file_history`, etc.) when user asks "what changed?", "what did the last step do?", or to inform the next `context_summary`.
- `rag_search` / `workspace_search` when the user asks about prior work, a topic, or "where is X implemented?" — or to sanity-check what the builder will retrieve.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-13 | Phase 6 — `model_roles` tokens now live (not null); lean JSONL note; trace file in disk-writes list |
| 2026-06-13 | Phase 5 — `workspace_search`, `context_refs`; builder RAG wired; validation-block note |
| 2026-06-12 | Initial version — all 7 tools, parameter tables, response fields, Cursor call rules |
