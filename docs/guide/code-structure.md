# mcp-coder: code structure

**Purpose:** Read this first. Explains what every directory and module does so you can find your way around the codebase without loading the whole thing into your head.

**Last updated:** 2026-06-10 (reflects Phases 1–4, post Phase 4.5 onboarding)

---

## Top-level layout

```
mcp_coder/
  main.py                 Entry point — CLI subcommands + MCP stdio server startup
  pyproject.toml          Package (name: mcp-coder, entry: main:main, deps below)
  .env                    Your local secrets + model config (never committed)
  .env.example            Template for .env

  server/
    mcp_server.py         The MCP server — all MCP tool handlers live here (~1750 lines)

  core/                   All business logic — no Cursor/MCP transport here
    cli/                  CLI-only entry points (not MCP tools)
    config/               Feature flags, model resolution, runtime config
    context/              Context compiler: assemble + picker + builder LLM
    delegation/           Delegation-level errors
    engine/               Execution backends (Aider) + spec review/validation LLMs
    host/                 Host adapter (Cursor paths, transcript, rules sync)
    logging/              Delegation JSONL writer + reader, server log
    pipeline/             Phase recorder (P4-020: delegation_pipeline audit)
    rag/                  Delegation FTS5 index + search (shipped P3, usage deferred)
    server/               MCP singleton (process-level server instance)
    session/              Session store, policy, executor cache
    specs/                Spec reading, contract enforcement, outcome labelling
    storage/              ~/.mcp-coder path layout, project registry, workspace config
    usage/                Token telemetry, cost rates, per-role audit records
    verify/               Auto-verify runner (pytest hook, P4-010)
    workspace/             Workspace history DB, manifest walk, diff, gateway, checkpoint

  resources/
    cursor-rules/         Bundled Cursor rules (synced to workspace on MCP startup)
    examples/             config.yaml template, MCP setup guide
    model_rates.yaml      Static cost rates per model (used for cost_est_usd)
    spec-template.md      Copy-only spec template

  scripts/                Operational scripts (not installed; run manually)
  tests/                  pytest suite (573 passing at Phase 4 exit)
  docs/                   All documentation
    guide/                THIS FOLDER — onboarding, tutorials, architecture
    notes/                Design decision records (PM/architecture notes)
    OTEHR_RELATED_IDEAS/  Future ideas (not canonical vision)
```

---

## Dependencies (pyproject.toml)

| Package | Why |
|---------|-----|
| `mcp>=1.27` | MCP protocol transport (FastMCP) — handles stdio, tool schema, JSON serialization |
| `aider-chat>=0.82` | Execution backend — Aider `Coder` Python API; brings LiteLLM transitively |
| `pyyaml` | Read `.mcp-coder/config.yaml` and `resources/model_rates.yaml` |
| `pytest` (dev) | Test suite only |

**LiteLLM** is not a direct dep — it comes in via `aider-chat`. All cheap-LLM calls (builder, validation, architect, spec review) use LiteLLM directly because Aider depends on it.

---

## Entry points

### `main.py` — the executable

`mcp-coder` (installed by `pip install -e .`) calls `main:main()`.

Three subcommands:

| Command | What it does |
|---------|-------------|
| *(no subcommand)* | Starts the MCP stdio server (used by Cursor `mcp.json`) |
| `mcp-coder test-model` | Sends a one-line ping to the configured model; useful to check API keys |
| `mcp-coder inspect-context` | Dry-run context compiler — builds the prompt without calling Aider (or other backends) |

### `server/mcp_server.py` — the hub (~1750 lines)

This is the largest file and the place everything connects. It:
- Registers MCP tools (`delegate_to_agent`, `inspect_context`, `list_delegations`, `get_delegation_diff`, `get_checkpoint_detail`, `get_file_history`, `rag_search`)
- Runs the delegation pipeline on each `delegate_to_agent` call
- Calls into `core/` for all the actual work

**Reading tip:** the file is long but structured. Look for `@server.call_tool` decorators to find each tool handler. The `delegate_to_agent` handler is the one that does almost everything.

---

## `core/` module guide

### `core/config/` — feature flags and model resolution

Everything that reads `.mcp-coder/config.yaml` or environment variables.

| Module | What it resolves |
|--------|-----------------|
| `context_builder.py` | `context_builder_enabled()`, `context_builder_llm_enabled()` — on/off flags |
| `architect_pass.py` | `architect_pass_enabled()` |
| `auto_verify.py` | `auto_verify_enabled()`, `resolve_verify_command()` |
| `spec_validation.py` | `spec_validation_enabled()` |
| `role_models.py` | Per-role model resolution: `ROLE_EXECUTOR`, `ROLE_CONTEXT_BUILDER`, etc. Resolves env → yaml → default |
| `models.py` | `resolve_model_name()` — the base executor model |
| `aider_runtime.py` | Aider-specific config (headless URL policy, `infer_run_success`, delegation I/O) |
| `openrouter_models.py` | OpenRouter-specific defaults |
| `env.py` | Shared env-reading helpers |
| `rag.py` | RAG feature flags (unused in pipeline; Phase 5) |

**Pattern:** every flag follows the same precedence: env var → yaml key → hardcoded default.

### `core/context/` — context compiler (Phase 2–4 core)

The heart of the system. Builds the prompt Aider sees.

| Module | What it does |
|--------|-------------|
| `package.py` | `ContextPackage` — the data structure holding all assembled context (files, tiers, budget, brief) |
| `assemble.py` | `assemble_context()` — takes spec + workspace → produces `ContextPackage`; applies tiers |
| `file_picker.py` | `pick_candidate_files()` — rules-based: spec paths + ripgrep symbol scan + repo map → `CandidateFilesResult` |
| `repo_map.py` | `build_repo_map_entries()` — walks workspace, extracts def/class outlines → `TIER_MAP_ONLY` entries |
| `budget.py` | Token budget enforcement — trims entries to fit context window |
| `excerpts.py` | Read-excerpt tier — pulls relevant sections from large files |
| `builder_prompt.py` | Assembles the prompt sent to the builder LLM |
| `builder_history.py` | `gather_builder_history()` — queries workspace history for past delegations on same spec |
| `architect_prompt.py` | Assembles the prompt sent to the architect-pass LLM |
| `spec_validation_prompt.py` | Assembles the spec validation prompt |
| `inspect.py` | `inspect_context_package()` — dry-run path (no Aider); called by `inspect-context` CLI |
| `capability_adjust.py` | Adjusts context based on Aider edit format capabilities |
| `mcp_summary.py` | Handles `context_summary` field from MCP call (Phase 1 fallback mode) |
| `summary.py` | Simple text summary utilities |
| `transcript_policy.py` | Host transcript handling (Mode B — host_transcript: dump) |
| `package_cache.py` | Cache key for ContextPackage (deduplication) |

**Reading tip:** start with `package.py` (the data model), then `assemble.py` (the main function), then `file_picker.py`.

### `core/engine/` — execution backends and LLM calls

| Module | What it does |
|--------|-------------|
| `aider_engine.py` | Main executor — wraps Aider `Coder` Python API; `translate_context_package()` → Aider inputs |
| `base.py` | `ExecutionEngine` abstract base |
| `factory.py` | `get_engine()` — returns the right backend by name |
| `context_builder_llm.py` | `run_context_builder_llm()` — cheap LLM call for the builder brief |
| `architect_pass_llm.py` | `run_architect_pass_llm()` — cheap LLM call for the architect plan |
| `spec_validation_llm.py` | `run_spec_validation_llm()` — cheap LLM call for pre-delegate validation |
| `spec_review.py` | `run_spec_review()` — `mode=review` LLM call |
| `capabilities.py` | Edit-format capability detection per model |
| `git_diff.py` | Git-based diff (fallback when workspace history isn't enough) |
| `stdio_isolation.py` | Captures Aider's stdout/stderr without breaking MCP stdio transport |
| `opencode_engine.py` | OpenCode stub — not used; exists for future backend |

**Note:** `aider_engine.py` is the only place Aider API terms (`fnames`, `repo_map`, `yes=True`) should appear. Everything else is backend-neutral.

### `core/specs/` — spec reading and contract enforcement

| Module | What it does |
|--------|-------------|
| `read.py` | Parse spec YAML front-matter + sections |
| `sections.py` | Extract `## Files`, `## Goal`, `## Constraints` etc. from spec markdown |
| `files_contract.py` | Validate `files_edit` / `files_read` from spec against actual request |
| `delegation_policies.py` | `DelegationPolicies` — the parsed contract (edit scope, create rules, untracked policy) |
| `paths.py` | Validate spec path is under `.mcp-coder/specs/tasks/`; `_spec_path_error()` |
| `modes.py` | `implement` vs `review` mode parsing |
| `outcome.py` | `OutcomeLabel` — `success`, `partial`, `needs_input`, `error`; `apply_verify_outcome()` |
| `bootstrap.py` | Write new spec from template |
| `write.py` | Write spec report |
| `read_deps_merge.py` | Auto-merge spec `Files Read` into `auto_merged_read_paths` |

### `core/storage/` — home directory and workspace config

| Module | What it does |
|--------|-------------|
| `paths.py` | `MCP_CODER_HOME`, `project_key(workspace)`, session dirs — the `~/.mcp-coder/` layout |
| `project_registry.py` | Register and look up projects by key |
| `session_paths.py` | Paths under a session dir (delegations.jsonl, session.json) |
| `workspace_config.py` | Read `.mcp-coder/config.yaml` |
| `workspace_session.py` | Link workspace to session |

### `core/session/` — session lifecycle

| Module | What it does |
|--------|-------------|
| `store.py` | `SessionStore` — create/load/save sessions under `~/.mcp-coder` |
| `policy.py` | `always_new` vs `align_host` policy |
| `executor_cache.py` | In-process Aider `Coder` instance cache per `mcp_session_id` |
| `activity.py` | Session activity timestamp updates |

### `core/workspace/` — workspace truth (Phase 3 core)

| Module | What it does |
|--------|-------------|
| `history_db.py` | `workspace_history.db` — SQLite; stores delegation outcomes, file lists, diffs |
| `history_query.py` | Query helpers over history_db |
| `manifest.py` | Walk workspace files, compute SHA-256 per file → manifest dict |
| `snapshot.py` | Pre/post-delegation snapshots for `files_changed` without git |
| `diff_util.py` | Diff two manifests → created/modified/deleted |
| `gateway.py` | Post-delegation gateway — verify files_changed against spec contract |
| `judgment_checklist.py` | Assemble `judgment_checklist` for MCP response |
| `checkpoint_summary.py` | Summarize a checkpoint for `get_checkpoint_detail` |
| `prior_attempts.py` | Fetch `prior_failed_attempts` for response |
| `revert.py` | Revert workspace to a snapshot (not wired into main flow yet) |
| `walk.py` | Shared workspace walk utility |

### `core/logging/` — audit trail

| Module | What it does |
|--------|-------------|
| `delegation_log.py` | Append one JSONL record per delegation to `delegations.jsonl` |
| `read_delegations.py` | Read and query `delegations.jsonl` |
| `server_log.py` | Persistent `server.jsonl` (lifecycle events, errors) |

### `core/pipeline/` — phase recorder (Phase 4)

| Module | What it does |
|--------|-------------|
| `phases.py` | `PipelineRecorder` — start/end each named phase; emit `delegation_pipeline` list |

### `core/host/` — Cursor adapter

| Module | What it does |
|--------|-------------|
| `cursor.py` | Cursor-specific paths (`agent-transcripts`, slug) |
| `cursor_transcript.py` | Parse Cursor transcript JSONL → text block |
| `cursor_rules.py` | Sync bundled rules to `.cursor/rules/`; `_resolve_includes()` for `@include` directives |
| `cursor_rules_policy.py` | Which rules to sync, per workspace config |
| `base.py` | `HostContextProvider` protocol |
| `factory.py` | `get_host_provider()` |
| `null.py` | No-op host (tests) |
| `scoring.py` | Session scoring heuristic for `align_host` |
| `apply.py` | Apply host context to delegation |

### `core/usage/` — cost and telemetry

| Module | What it does |
|--------|-------------|
| `telemetry.py` | `UsageRecord` — preflight + actual token counts + static cost estimate |
| `rates.py` | Load `model_rates.yaml`; `cost_estimate()` |
| `role_audit.py` | `build_role_usage_record()` — per-role `model_roles` block in JSONL |
| `aider_tokens.py` | Extract token counts from Aider `Coder` post-run (currently returns `None` — BL-335) |
| `policy.py` | Usage policy helpers |

### `core/rag/` — delegation search (Phase 3, usage deferred)

| Module | What it does |
|--------|-------------|
| `db.py` | `delegation_rag.db` SQLite FTS5 schema |
| `index.py` | Index a delegation into FTS5 |
| `search.py` | `rag_search()` — FTS5 full-text search over past delegations |
| `models.py` | Data models |

**Status:** Code ships; `rag_search` MCP tool is registered. The index is populated on each delegation. But the search results are **not fed back into the pipeline** — they're available for the planner to call manually. Active integration is Phase 5.

---

## `scripts/` — operational helpers (not installed)

| Script | Use |
|--------|-----|
| `view_delegations.py` | Print delegations.jsonl records for a project |
| `logs_last.py` | Tail recent delegation log entries |
| `server_logs_last.py` | Tail server.jsonl |
| `smoke_delegation.py` | Quick smoke test delegation (not pytest) |
| `mcp-coder` | Shell shim (used during dev before `pip install -e .`) |
| `bootstrap.sh` | Initial environment setup |
| `lock-deps.sh` | Repin requirements*.txt |

---

## `tests/` — pytest suite

573 tests at Phase 4 exit (2 skipped; `test_cli_test_model.py` skipped without Aider in env).

Test files follow the module they cover: `test_file_picker.py` → `core/context/file_picker.py`. No integration tests that hit a live LLM — all LLM calls are mocked.

---

## Where to look for specific things

| Question | Where to look |
|----------|--------------|
| How does a delegation start? | `server/mcp_server.py` → `delegate_to_agent` handler |
| How is the prompt assembled? | `core/context/assemble.py` → `assemble_context()` |
| What does Aider actually receive? | `core/engine/aider_engine.py` → `translate_context_package()` |
| How are sessions persisted? | `core/storage/paths.py`, `core/session/store.py` |
| How is `files_changed` computed? | `core/workspace/snapshot.py` + `diff_util.py` |
| How does the builder LLM work? | `core/engine/context_builder_llm.py` + `core/context/builder_prompt.py` |
| Where do config flags live? | `core/config/*.py` — one file per feature |
| Why are token counts `None`? | `core/usage/aider_tokens.py` (BL-335 — extraction not working yet) |
| What does a JSONL record look like? | `core/logging/delegation_log.py` + any `delegations.jsonl` file |
| Where do Cursor rules get written? | `core/host/cursor_rules.py` |

---

## Reading order (suggested)

If you want to understand the full delegation flow from scratch:

1. `pyproject.toml` — what depends on what
2. `main.py` — entry points
3. `server/mcp_server.py` lines 1–100 (imports + server init) — orientation
4. `core/specs/read.py` + `delegation_policies.py` — what a spec provides
5. `core/context/package.py` — the ContextPackage data model
6. `core/context/assemble.py` — how context is assembled
7. `core/engine/aider_engine.py` — how it becomes Aider input
8. `core/logging/delegation_log.py` — what gets written to JSONL
9. Back to `server/mcp_server.py` delegate handler — now you can read the full flow
