# mcp-coder: code structure

**Purpose:** Read this first. Explains what every directory and module does so you can find your way around the codebase without loading the whole thing into your head.

**Last updated:** 2026-06-23 (Phases 1–13; Supervisor agent, project state, observability/proxy stack, lifecycle envelope).

---

## Top-level layout

```
mcp_coder/
  main.py                 Entry point — CLI subcommands + MCP stdio server startup
  pyproject.toml          Package (name: mcp-coder, entry: main:main, deps below)
  .env                    Your local secrets + model config (never committed)
  .env.example            Template for .env

  server/
    mcp_server.py         MCP tool handlers + delegation entry (~thin orchestration; Supervisor owns lifecycle)

  core/                   All business logic — no Cursor/MCP transport here
    cli/                  CLI subcommands (inspect, delegate, view, trace, replay, logs, …)
    config/               Feature flags, model registry/policy, runtime config
    context/              Context compiler: assemble, picker, helper prompts
    delegation/           Prepare path, artifacts, delegation errors
    engine/               Backends (Aider), SupervisorAgent, helper/reviewer LLMs
    host/                 Host adapter (Cursor paths, transcript, rules sync)
    logging/              Delegation JSONL writer + reader, server log
    observability/        Trace backend, LiteLLM callback, training capture, stats
    pipeline/             Phase recorder (delegation_pipeline audit)
    proxy/                Local LLM HTTP proxy (Phase 9 capture)
    rag/                  Delegation + workspace-file FTS5; builder retrieval
    server/               MCP singleton (process-level server instance)
    session/              Session store, policy, executor cache
    specs/                Spec reading, contract enforcement, outcome labelling
    state/                Project state, Supervisor pause state, agent checkpoint
    storage/              ~/.mcp-coder path layout, project registry, workspace config
    usage/                Token telemetry, cost rates, per-role audit records
    verify/               Auto-verify runner (pytest hook)
    workspace/            Workspace history DB, manifest, diff, gateway, checkpoint

  tools/
    delegation_viewer.html  Static browser UI for delegation/trace inspection

  resources/
    cursor-rules/         Bundled Cursor rules (synced to workspace on MCP startup)
    examples/             config.yaml template, MCP setup guide
    model_rates.yaml      Static cost rates per model (used for cost_est_usd)
    spec-template.md      Copy-only spec template

  scripts/                Operational scripts (not installed; run manually)
  tests/                  pytest suite (~1300 tests at Phase 13)
  docs/                   All documentation
    guide/                THIS FOLDER — onboarding, tutorials, architecture
    notes/                Refined design notes (see system-design-overview.md)
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

CLI subcommands (see `core/cli/` table below for implementations):

| Command | What it does |
|---------|-------------|
| *(no subcommand)* | Starts the MCP stdio server (used by Cursor `mcp.json`); bare TTY prints help |
| `mcp-coder setup` | Workspace info, model resolution, `mcp.json` wiring (`--local` / `--global`) |
| `mcp-coder test-model` | Ping configured model(s); `--all` tests every role |
| `mcp-coder inspect-context` | Dry-run context compiler — builds the prompt without calling any backend; opt-in helper LLM flags; `--include-prompt` |
| `mcp-coder delegate` | Full delegation pipeline (or `--stop-after context` for prepare-only); structured `artifacts` + `caller_response` |
| `mcp-coder replay` | Replay one delegation from disk artifacts (JSONL + trace + context blob) |
| `mcp-coder compare` | Compare `backend_llm_call` vs `proxy_llm_call` for one delegation |
| `mcp-coder trace inspect` | Dump/filter events from a delegation trace |
| `mcp-coder logs tail` | Tail delegation trace events in real time |
| `mcp-coder view delegations` | Delegation viewer UI (`tools/delegation_viewer.html`) |
| `mcp-coder history` | Browse `workspace_history.db` (list, diff, revert) |
| `mcp-coder search` | `delegations` \| `files` keyword search |
| `mcp-coder index-workspace` | Build / refresh `workspace_rag.db` summaries |
| `mcp-coder maintenance stats` | Observability storage stats |
| `mcp-coder ps` / `status` / `kill` | MCP stdio process management (`core/cli/mcp_process.py`) |

### `server/mcp_server.py` — MCP entry hub

Large file where MCP tools connect to `core/`. It:
- Registers MCP tools (`delegate_to_agent`, `inspect_context`, `answer_delegation_question`, `list_delegations`, history/RAG helpers, …)
- Runs pre-executor pipeline stages and hands off to `SupervisorAgent` for lifecycle ownership
- Builds lean delegation records + trace files via observability layer

**Reading tip:** search for `@server.call_tool` handlers. `delegate_to_agent` is the main path; post-planning control flow lives in `core/engine/supervisor_agent.py`.

---

## `core/cli/` — CLI subcommand implementations

| Module | Subcommand | What it does |
|--------|-----------|-------------|
| `setup.py` | `mcp-coder setup` | Workspace info, model resolution, `mcp.json` block; `--init-config` |
| `test_model.py` | `mcp-coder test-model` | Ping model(s) via Aider or LiteLLM |
| `inspect_context.py` | `mcp-coder inspect-context` | Dry-run context compiler |
| `delegate.py` | `mcp-coder delegate` | Full pipeline; `--stop-after context` for prepare-only |
| `replay.py` | `mcp-coder replay` | Replay delegation artifacts from disk |
| `compare.py` | `mcp-coder compare` | Backend vs proxy LLM event comparison |
| `trace_inspect.py` | `mcp-coder trace inspect` | Filter/dump trace events |
| `logs_tail.py` | `mcp-coder logs tail` | Live tail of trace JSONL |
| `history.py` | `mcp-coder history` | `workspace_history.db` browser |
| `view_delegations.py` | `mcp-coder view delegations` | Serve delegation viewer HTML |
| `delegation_view_enrich.py` | *(imported by viewer)* | Raw records → `view_events[]` boundary model |
| `search.py` | `mcp-coder search` | Unified delegation / file search |
| `index_workspace.py` | `mcp-coder index-workspace` | Workspace-file summary indexer |
| `maintenance.py` | `mcp-coder maintenance stats` | Storage/observability maintenance stats |
| `mcp_process.py` | `ps` / `status` / `kill` | MCP stdio process discovery and cleanup |
| `rag.py` | `mcp-coder rag` | Legacy delegation search / index |

---

## `core/` module guide

### `core/config/` — feature flags and model resolution

Everything that reads `.mcp-coder/config.yaml` or environment variables.

| Module | What it resolves |
|--------|-----------------|
| `context_builder.py` | `context_builder_enabled()`, `context_builder_llm_enabled()` |
| `planner_pass.py` | `planner_pass_enabled()` (canonical; legacy `architect_pass` alias) |
| `architect_pass.py` | Legacy shim → prefer `planner_pass.py` |
| `auto_verify.py` | `auto_verify_enabled()`, `resolve_verify_command()` |
| `spec_validation.py` | `spec_validation_enabled()`, `clarity_pass_enabled()` |
| `role_models.py` | Per-role model + budget resolution |
| `model_registry.py` | Layered `model_policy` resolution, registry front door, `policy_applied` |
| `host_model_policy.py` | Parse host `model_policy` MCP arg |
| `models.py` | `resolve_model_name()` — base executor model |
| `aider_runtime.py` | Aider-specific runtime config |
| `observability.py` | Observability backend selection |
| `rag.py` | RAG feature flags (defaults on) |
| `auto_merge.py` | `auto_merge_spec_read` flag |
| `providers.py` | Provider env normalization |

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
| `builder_prompt.py` | Builder LLM prompt assembly |
| `builder_history.py` | `gather_builder_history()` — past delegations on same spec |
| `planner_prompt.py` | Planner-pass prompt assembly |
| `clarity_prompt.py` | Clarity-check prompt assembly |
| `reviewer_prompt.py` | Reviewer-pass prompt assembly |
| `architect_prompt.py` | Legacy planner prompt path (prefer `planner_prompt.py`) |
| `spec_validation_prompt.py` | Spec validation prompt assembly |
| `inspect.py` | `inspect_context_package()` — dry-run path (no Aider) |
| `helper_llm_pipeline.py` | Shared helper pipeline; may inject `project_state` for planner |
| `../delegation/prepare.py` | Delegate-faithful pre-executor compile (`prepare_delegation_context`) |
| `../delegation/artifacts.py` | CLI artifact envelope (`executor_in` / `executor_out` / `post_delegate`) |
| `capability_adjust.py` | Adjusts context based on Aider edit format capabilities |
| `mcp_summary.py` | Handles `context_summary` field from MCP call (Phase 1 fallback mode) |
| `summary.py` | Simple text summary utilities |
| `transcript_policy.py` | Host transcript handling (Mode B — host_transcript: dump) |
| `package_cache.py` | Cache key for ContextPackage (deduplication) |

**Reading tip:** start with `package.py` (the data model), then `assemble.py` (the main function), then `file_picker.py`.

### `core/engine/` — execution backends, Supervisor, helper LLMs

| Module | What it does |
|--------|-------------|
| `supervisor_agent.py` | **`SupervisorAgent`** — owns post-planning lifecycle, pause/resume, multi-turn loop, lifecycle envelope events |
| `supervisor_tool_runner.py` | Tool-calling loop for Supervisor decisions (`get_project_state`, `read_file`, …) |
| `supervisor.py` | `DelegationSupervisor` — confirm-ask interception LLM (approve/deny/abort/escalate) |
| `supervised_io.py` | Routes Aider `confirm_ask` to Supervisor during executor run |
| `aider_engine.py` | Main executor — Aider `Coder` API; `translate_context_package()` |
| `planner_pass_llm.py` | Planner-pass LLM call |
| `clarity_llm.py` | Clarity-check LLM call |
| `reviewer_llm.py` | Reviewer-pass LLM call |
| `context_builder_llm.py` | Builder-brief LLM call |
| `spec_validation_llm.py` | Spec-validation LLM call |
| `spec_review.py` | `mode=review` LLM call |
| `owned_helper_llm.py` | Owned helper LLM path via gateway/observability |
| `observable_model.py` | Aider model wrapper for inner-loop capture (Phase 8) |
| `interception_profile.py` | Backend interception profile config |
| `planner_decision_extractor.py` | Extract durable decisions from planner output → project state |
| `architect_pass_llm.py` | Legacy alias path for planner pass |
| `architect_trigger.py` | Heuristic for when planner pass fires |
| `base.py` | `ExecutionEngine` abstract base |
| `factory.py` | `get_engine()` — backend selection |
| `stdio_isolation.py` | Captures Aider stdout/stderr without breaking MCP stdio |
| `opencode_engine.py` | Stub backend (unused) |

**Note:** Aider API terms (`fnames`, `repo_map`, `yes=True`) belong only in `aider_engine.py` + `aider_runtime.py`.

### `core/state/` — persistent Supervisor state (Phase 12–13)

| Module | What it does |
|--------|-------------|
| `project_state.py` | `ProjectState` — cross-delegation memory at `project_state.json` |
| `agent_checkpoint.py` | `AgentCheckpoint` — steady-state snapshot at `agent_state.json` (process rehydrate) |
| `supervisor_state.py` | `SupervisorState` — expiring pause/resume payload under `supervisor_states/` |
| `project_key.py` | Project key resolution helpers |

### `core/observability/` — traces, capture, stats (Phase 6–9)

| Module | What it does |
|--------|-------------|
| `base.py` | `ObservabilityBackend` protocol |
| `local.py` | `LocalObservability` — writes traces, builds lean delegation records |
| `null.py` | No-op backend for tests |
| `trace.py` | Trace event types (`llm_call`, `compile_event`, lifecycle, supervisor, proxy, …) |
| `litellm_callback.py` | LiteLLM callback shim for helper LLM capture |
| `gateway.py` | Observability-facing LLM gateway wrapper |
| `training_capture.py` | Opt-in training artifact capture |
| `reasoning_buffer.py` | Hot reasoning-token buffer |
| `stats.py` | Maintenance/storage stats |
| `bootstrap.py` | Observability backend initialization |
| `context.py` | Context blob persistence for replay |
| `version_tags.py` | Version metadata on trace events |

### `core/proxy/` — local LLM proxy (Phase 9)

| Module | What it does |
|--------|-------------|
| `local_proxy.py` | `LocalLlmProxy` — HTTP proxy for raw provider capture |
| `routing.py` | Provider routing helpers for proxy mode |

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
| `read_deps_merge.py` | Append spec Read paths to `effective_target_files` (flag `auto_merge_spec_read` — name is historical; see T-03 §5) |

### `core/storage/` — home directory and workspace config

| Module | What it does |
|--------|-------------|
| `paths.py` | `MCP_CODER_HOME`, `project_key(workspace)`, session dirs — `~/.mcp-coder/` layout |
| `project_registry.py` | Register and look up projects by key |
| `session_paths.py` | Session dirs (`delegations.jsonl`, traces, `server.jsonl`) |
| `workspace_config.py` | Read `.mcp-coder/config.yaml` |
| `workspace_session.py` | Link workspace to session |

Project-scoped persistent files (via `core/state/`): `project_state.json`, `agent_state.json`, `supervisor_states/<token>.json`.

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
| `aider_tokens.py` | Extract token counts from Aider `Coder` post-run (executor-internal tokens; per-event token counts on `backend_llm_call` via Phase 9 P9-009/P9-012) |
| `policy.py` | Usage policy helpers |

### `core/rag/` — retrieval (Phase 3 index + Phase 5 builder wiring)

| Module | What it does |
|--------|-------------|
| `db.py` | `delegation_rag.db` SQLite FTS5 schema |
| `index.py` | Index a delegation into FTS5 |
| `search.py` | `rag_search()` — delegation FTS5 search |
| `retrieval.py` | `ContextRef`, `retrieve()`, `context_refs_to_dict()` — shared contract |
| `builder_retrieval.py` | `rag_retrieval` pipeline phase; merged delegation + file hits |
| `workspace_search.py` | `workspace_search()` over `workspace_rag.db` |
| `workspace_index.py` | Per-file LLM summary indexer (`index-workspace`) |
| `fts.py` | Query tokenization (stopwords, term cap, hyphen split) |

**Status:** Delegation index auto-updates each delegate. Workspace-file index: `index-workspace` + incremental on `files_changed`. Builder consumes both by default (`rag_retrieval` phase → `## Relevant prior work` + JSONL `context_refs[]`). Planner tools: `rag_search`, `workspace_search`, CLI `search`.

---

## `scripts/` — operational helpers (not installed)

| Script | Use |
|--------|-----|
| `view_delegations.py` (script) | Backward-compat wrapper → `core.cli.view_delegations` (prefer `mcp-coder view delegations`) |
| `logs_last.py` | Tail recent delegation log entries |
| `server_logs_last.py` | Tail server.jsonl |
| `smoke_delegation.py` | Quick smoke test delegation (not pytest) |
| `mcp-coder` | Shell shim (used during dev before `pip install -e .`) |
| `bootstrap.sh` | Initial environment setup |
| `install.sh` | **One-command global install** — creates `.venv`, writes `/usr/local/bin/mcp-coder` wrapper; run once per machine |
| `lock-deps.sh` | Repin requirements*.txt |

---

## `tests/` — pytest suite

~1300 tests at Phase 13. Tests mirror `core/` modules; LLM calls are mocked in unit tests.

---

## Where to look for specific things

| Question | Where to look |
|----------|--------------|
| How does a delegation start? | `server/mcp_server.py` → `delegate_to_agent`; then `core/engine/supervisor_agent.py` |
| Who owns pause/resume and lifecycle events? | `core/engine/supervisor_agent.py` + `core/state/supervisor_state.py` |
| Where is project memory stored? | `core/state/project_state.py` → `~/.mcp-coder/projects/<key>/project_state.json` |
| Where is cross-process Supervisor state? | `core/state/agent_checkpoint.py` → `agent_state.json` |
| How is the prompt assembled? | `core/context/assemble.py` → `assemble_context()` |
| What does Aider actually receive? | `core/engine/aider_engine.py` → `translate_context_package()` |
| How are sessions persisted? | `core/storage/paths.py`, `core/session/store.py` |
| How is `files_changed` computed? | `core/workspace/snapshot.py` + `diff_util.py` |
| Where do trace events come from? | `core/observability/trace.py`, `core/observability/local.py` |
| How does the viewer map events? | `core/cli/delegation_view_enrich.py` + `tools/delegation_viewer.html` |
| Supervisor tool-calling loop? | `core/engine/supervisor_tool_runner.py` |
| Model policy resolution? | `core/config/model_registry.py` |
| What does a JSONL record look like? | `core/logging/delegation_log.py` + `core/observability/local.py` |
| Where do Cursor rules get written? | `core/host/cursor_rules.py` |

---

## Reading order (suggested)

If you want to understand the full delegation flow from scratch:

1. `pyproject.toml` — dependencies
2. `main.py` — CLI + MCP entry
3. `core/specs/read.py` + `delegation_policies.py` — spec contract
4. `core/context/package.py` + `assemble.py` — context compiler
5. `core/engine/supervisor_agent.py` — lifecycle owner (start here for Phase 12+ behavior)
6. `core/state/project_state.py` + `agent_checkpoint.py` — persistent memory
7. `core/engine/aider_engine.py` — executor adapter
8. `core/observability/local.py` + `trace.py` — audit/trace output
9. `server/mcp_server.py` `delegate_to_agent` — wiring it together
