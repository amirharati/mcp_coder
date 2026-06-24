# Environment variable reference

Runtime knobs for mcp-coder. Variables can be set in any of these locations (first set wins per variable):

1. Shell environment or `mcp.json` `env` block.
2. `MCP_CODER_ENV_FILE` — explicit path to a `.env` file.
3. `.env` in process `cwd` (Cursor MCP `cwd` is usually the target workspace).
4. `.env` in the mcp-coder repo root (next to `pyproject.toml`).

Most knobs also have a `config.yaml` equivalent (noted in each section). The yaml key always wins over the env var when both are set, unless noted otherwise.

---

## Pipeline feature flags

On/off switches for each pipeline stage. Default `1` (enabled) unless noted.

| Variable | Default | yaml key | Effect |
|---|---|---|---|
| `MCP_CODER_SPEC_VALIDATION` | `1` | `spec_validation` | Pre-flight coherence check; blocks if spec is incoherent or ambiguous |
| `MCP_CODER_CLARITY_PASS` | `1` | `clarity_pass` | Clarity gate; blocks or pauses if task is underspecified |
| `MCP_CODER_PLANNER_PASS` | `1` | `planner_pass` | Planner pass prepended to executor brief; reads project state |
| `MCP_CODER_ARCHITECT_PASS` | *(legacy)* | `architect_pass` | Deprecated alias for `MCP_CODER_PLANNER_PASS`; logs a warning |
| `MCP_CODER_CONTEXT_BUILDER_ENABLED` | `1` | `context_builder` | File picker + context assembly stage |
| `MCP_CODER_CONTEXT_BUILDER_LLM` | `1` | `context_builder_llm` | LLM builder brief inside context assembly (gated by `CONTEXT_BUILDER_ENABLED`) |
| `MCP_CODER_SUPERVISED_EXEC` | `1` | `supervised_execution` | `SupervisedIO` intercepts Aider `confirm_ask`; `0` = Aider runs unsupervised |
| `MCP_CODER_REVIEWER_PASS` | `1` | `reviewer_pass` | Reviewer advisory scan after execution; findings written to project state |
| `MCP_CODER_AUTO_VERIFY` | `0` | `auto_verify` | Run verify command after execution and update outcome |
| `MCP_CODER_RAG_ENABLED` | `1` | `rag_enabled` | Delegation + workspace FTS retrieval; `0` = no RAG context injected |

---

## Supervisor and agent loop

| Variable | Default | yaml key | Effect |
|---|---|---|---|
| `MCP_CODER_SUPERVISOR_MAX_TURNS` | `1` | `supervisor_max_turns` | Maximum executor turns per delegation; `1` = single Aider run (safe default); `2`–`3` = autonomous fix+retry |
| `MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY` | `0` (off) | — | Reset executor session every N turns (drift bound); `0` = only reset on resume or policy trigger |
| `MCP_CODER_RESUME_TOKEN_TTL` | `86400` (24 h) | — | Pause/resume token lifetime in seconds; expired tokens raise `ResumeTokenExpired` |
| `MCP_CODER_HOT_AREAS_MAX` | `50` | — | Max hot-area entries kept in `project_state.json` |
| `MCP_CODER_SINGLETON` | `1` | — | `1` = only one `SupervisorAgent` instance per server process; `0` = allow concurrent (not recommended) |

---

## Per-role model overrides

Each role resolves its model independently. Precedence: env var → `config.yaml` → built-in default.
Executor model is `AIDER_MODEL` / `MCP_CODER_MODEL` (standard Aider env); no separate env for the executor role.

| Variable | Role | yaml key | Built-in default |
|---|---|---|---|
| `MCP_CODER_MODEL` | `executor` | — | Aider's own `AIDER_MODEL` fallback |
| `MCP_CODER_SUPERVISOR_MODEL` | `supervisor` | `supervisor_model` | `MCP_CODER_CONTEXT_BUILDER_DEFAULT_MODEL` or executor model |
| `MCP_CODER_PLANNER_PASS_MODEL` | `planner_pass` | `planner_pass_model` | Executor model |
| `MCP_CODER_REVIEWER_PASS_MODEL` | `reviewer_pass` | `reviewer_pass_model` | Context builder default |
| `MCP_CODER_CONTEXT_BUILDER_MODEL` | `context_builder` | `context_builder_model` | `MCP_CODER_CONTEXT_BUILDER_DEFAULT_MODEL` or executor model |
| `MCP_CODER_CONTEXT_BUILDER_DEFAULT_MODEL` | *(fallback for builder/supervisor/reviewer)* | — | Executor model |
| `MCP_CODER_REVIEW_MODEL` | `review` (mode=review) | `review_model` | Executor model |
| `MCP_CODER_CRITIC_MODEL` | `critic` | `critic_model` | Executor model |

Dogfood recommendation: set `MCP_CODER_CONTEXT_BUILDER_DEFAULT_MODEL=openrouter/google/gemini-2.5-flash` in `.env`.

---

## Per-role token budget caps

Optional hard caps. `None` (unset) = no cap beyond model context. Precedence: env → yaml.

| Variable | Role | yaml key |
|---|---|---|
| `MCP_CODER_EXECUTOR_BUDGET_TOKENS` | `executor` | `executor_budget_tokens` |
| `MCP_CODER_CONTEXT_BUILDER_BUDGET_TOKENS` | `context_builder` | `context_builder_budget_tokens` |
| `MCP_CODER_REVIEW_BUDGET_TOKENS` | `review` | `review_budget_tokens` |
| `MCP_CODER_CRITIC_BUDGET_TOKENS` | `critic` | `critic_budget_tokens` |

---

## Executor (Aider) advanced params

These tune the Aider executor call. Unset = use Aider's own defaults.

| Variable | Default | Effect |
|---|---|---|
| `MCP_CODER_EXECUTOR_SYSTEM_PREFIX` | *(unset)* | Optional system-prompt prefix prepended before every Aider message |
| `MCP_CODER_EXECUTOR_EDIT_FORMAT` | *(unset)* | Aider edit format override (`whole`, `diff`, `udiff`, …) |
| `MCP_CODER_EXECUTOR_MAX_TOKENS` | *(unset)* | Max output tokens for executor call |
| `MCP_CODER_EXECUTOR_TEMPERATURE` | *(unset)* | Temperature override for executor |
| `MCP_CODER_EXECUTOR_REASONING_EFFORT` | *(unset)* | Reasoning effort string (provider-specific; e.g. `high`) |
| `MCP_CODER_EXECUTOR_THINKING_BUDGET` | *(unset)* | Extended thinking budget tokens (Anthropic) |
| `MCP_CODER_EXECUTOR_TOP_P` | *(unset)* | Top-p override |
| `MCP_CODER_EXECUTOR_EXTRA_PARAMS` | *(unset)* | JSON blob of extra params forwarded verbatim to the provider |
| `MCP_CODER_EXECUTOR_WEAK_MODEL` | *(unset)* | Override Aider's weak model choice |
| `MCP_CODER_EXECUTOR_MAX_STEPS` | *(unset)* | Max Aider steps per run |
| `MCP_CODER_EXECUTOR_STEP_TIMEOUT_S` | *(unset)* | Per-step timeout (seconds) |
| `MCP_CODER_EXECUTOR_TOTAL_TIMEOUT_S` | *(unset)* | Total executor run timeout (seconds) |
| `MCP_CODER_DELEGATION_TIMEOUT_S` | *(unset)* | Full delegation wall-clock timeout (seconds; wraps the whole pipeline) |
| `MCP_CODER_STALL_AUTO_RETRY` | `0` | `1` = auto-retry once when Aider stalls requesting files (see below) |
| `MCP_CODER_EXECUTOR_PULL_HINT` | `1` | Inject executor-pull hint into prompt so Aider knows it can fetch context |

### Stall auto-retry (`MCP_CODER_STALL_AUTO_RETRY`)

**Off (default):** if Aider output matches a file-request stall, `delegate_to_agent` returns `needs_input` with `files_requested[]` so the host can add paths and re-call.

**On (`1`):** mcp-coder automatically merges requested paths into `target_files` / read context and runs the executor one more time in the same MCP call. If the retry still stalls, it escalates to `needs_input`. Audited as `auto_retried: true` in the delegation record.

This applies only to the `needs_input_files` stall pattern — not timeouts, test failures, or model errors.

---

## Context and RAG tuning

| Variable | Default | yaml key | Effect |
|---|---|---|---|
| `MCP_CODER_CONTEXT_BUDGET_ENABLED` | `1` | `context_budget_enabled` | Enable token-budget trimming in context assembly |
| `MCP_CODER_CONTEXT_BUDGET_TOKENS` | *(unset)* | `context_budget_tokens` | Hard budget cap for assembled context |
| `MCP_CODER_BUILDER_RAG_K` | *(unset)* | — | Max delegation RAG results fed to builder |
| `MCP_CODER_BUILDER_HISTORY_RAG` | *(unset)* | — | `1` = include delegation history RAG in builder brief |
| `MCP_CODER_BUILDER_HISTORY_PROJECT_LIMIT` | *(unset)* | — | Max project-level history entries in builder brief |
| `MCP_CODER_BUILDER_HISTORY_SPEC_LIMIT` | *(unset)* | — | Max same-spec history entries in builder brief |
| `MCP_CODER_WORKSPACE_FILE_RAG` | *(unset)* | — | `1` = include workspace file corpus RAG in builder brief |
| `MCP_CODER_WORKSPACE_FILE_RAG_K` | *(unset)* | — | Max workspace file RAG results |
| `MCP_CODER_WORKSPACE_INDEX_LIMIT` | *(unset)* | — | Max workspace files indexed per delegation |
| `MCP_CODER_PICKER_MAX_DISCOVERED` | *(unset)* | — | Max files the file picker may consider |
| `MCP_CODER_REPO_MAP_MAX_FILES` | *(unset)* | — | Max files included in repo map section |
| `MCP_CODER_READ_FULL_MAX_BYTES` | *(unset)* | — | Max bytes for a `read-full` tier path |
| `MCP_CODER_FTS_MAX_TERMS` | *(unset)* | — | Max FTS query terms per RAG search |
| `MCP_CODER_DIFF_MAX_CHARS_PER_FILE` | *(unset)* | — | Max diff chars shown per changed file in reviewer/inspect |
| `MCP_CODER_DIFF_MAX_TOTAL_CHARS` | *(unset)* | — | Max total diff chars per delegation |
| `MCP_CODER_AUTO_MERGE_SPEC_READ` | *(unset)* | — | `1` = merge spec read deps into context automatically |
| `MCP_CODER_WORKSPACE_FILE_HINTS` | *(unset)* | — | Extra file hints for context assembly |
| `MCP_CODER_INSPECT_RUN_BUILDER_LLM` | `0` | — | `1` = run builder LLM in `inspect-context` CLI dry run |

---

## Session policy

| Variable | Default | yaml key | Effect |
|---|---|---|---|
| `MCP_CODER_SESSION_POLICY` | `always_new` | `session_policy` | `always_new` = new Aider `Coder` per delegation; `align_host` = try to reuse across delegations within the same Cursor session |
| `MCP_CODER_FALLBACK_SESSION` | *(deprecated)* | — | Legacy alias for `MCP_CODER_SESSION_POLICY`; logs deprecation warning |

---

## Logging and observability

| Variable | Default | yaml key | Effect |
|---|---|---|---|
| `MCP_CODER_LOG_BRIEF` | `1` | — | One-line stderr receive/send trace per MCP call |
| `MCP_CODER_LOG_VERBOSE` | `0` | — | Extra verbose delegation write lines to stderr |
| `MCP_CODER_LOG_FULL_PROMPT` | `0` | — | `1` = log full prompt text to stderr (verbose debugging) |
| `MCP_CODER_LOG_DIR` | *(unset)* | — | Write server log to this directory in addition to default location |
| `MCP_CODER_MIRROR_LOGS_TO_WORKSPACE` | `0` | — | `1` = also write `server.jsonl` into `<workspace>/.mcp-coder/` |
| `MCP_CODER_SERVER_LOG` | `1` | — | Structured `server.jsonl` event logging |
| `MCP_CODER_SERVER_LOG_LEVEL` | `info` | — | Server log filter (`error\|warn\|info\|debug`) |
| `MCP_CODER_SERVER_LOG_SCOPE` | `global` | — | Server log target (`global\|project\|both`) |
| `MCP_CODER_OBS_VERBOSITY` | `standard` | `observability_verbosity` | Trace verbosity tier (`lean\|standard\|full`) |
| `MCP_CODER_OBS_RETENTION` | `session` | `observability_retention` | Retention policy (`session\|forever\|<N>_days`); note: Phase 9+ is write-always — this controls lifecycle, not writing |
| `MCP_CODER_CAPTURE_REASONING` | `1` | `capture_reasoning` | Capture reasoning token payloads in trace events |
| `MCP_CODER_REASONING_BUFFER_SIZE` | `3` | `reasoning_buffer_size` | Session reasoning summary ring buffer size |
| `MCP_CODER_CAPTURE_FOR_TRAINING` | `0` | `capture_for_training` | Write training-capture artifact (`-training.json`) per delegation |
| `MCP_CODER_USAGE_REPORT` | *(unset)* | — | `1` = emit usage summary to stderr after each delegation |
| `MCP_CODER_USAGE_WARN_TOKENS` | *(unset)* | — | Warn when a delegation exceeds this token total |

### Write-vs-display semantics

Phase 9+ uses write-always semantics: trace and delegation artifacts are always written regardless of verbosity. `MCP_CODER_OBS_VERBOSITY` and `MCP_CODER_OBS_RETENTION` control how much detail is written and how long files are kept, not whether they are written.

---

## Proxy control

| Variable | Default | Effect |
|---|---|---|
| `MCP_CODER_PROXY_ENABLED` | `1` | `0` = disable local proxy; requests go directly to provider URLs; `proxy_llm_call` events not emitted |
| `MCP_CODER_OPENROUTER_API_BASE` | *(unset)* | Override OpenRouter API base URL for proxy routing |

---

## Host and Cursor integration

| Variable | Default | Effect |
|---|---|---|
| `MCP_CODER_HOST_TRANSCRIPT` | *(unset)* | Override transcript path (normally resolved from Cursor context) |
| `MCP_CODER_MAX_TRANSCRIPT_BYTES` | *(unset)* | Cap transcript bytes read per delegation |
| `MCP_CODER_CURSOR_ROOT` | `~/.cursor` | Override Cursor data root (for transcript/session discovery) |
| `MCP_CODER_CURSOR_PROJECT_SLUG` | *(unset)* | Override Cursor project slug used for transcript path resolution |
| `MCP_CODER_CURSOR_RULES_POLICY` | *(unset)* | Control when Cursor rules are injected into context |
| `MCP_CODER_SYNC_CURSOR_RULE` | *(unset)* | `1` = sync workspace Cursor rules to the MCP rule file on startup |
| `MCP_CODER_HOST_TIE_WINDOW_SEC` | *(unset)* | Window (seconds) for tying a delegation to a Cursor host session |

---

## Storage and paths

| Variable | Default | Effect |
|---|---|---|
| `MCP_CODER_HOME` | `~/.mcp-coder` | Root of all system-owned storage (history DB, traces, state files) |
| `MCP_CODER_WORKSPACE` | `cwd` | Workspace root; used to derive `project_key` and workspace config path |
| `MCP_CODER_PROJECT_KEY` | *(derived)* | Override the `sha256(workspace_path)` project key (testing / migration) |
| `MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT` | `0` | `1` = skip pre/post manifest snapshots (disables file diffing) |
| `MCP_CODER_SNAPSHOT_MAX_FILE_MB` | *(unset)* | Skip files larger than this in workspace snapshot |
| `MCP_CODER_ERROR_OUTPUT_MAX_CHARS` | *(unset)* | Cap on captured error output appended to delegation result |

---

## Environment file loading

| Variable | Default | Effect |
|---|---|---|
| `MCP_CODER_ENV_FILE` | *(unset)* | Explicit path to a `.env` file loaded before any other candidate |

Load order (first-set-wins per variable): explicit `MCP_CODER_ENV_FILE` → `.env` in process `cwd` → `.env` in mcp-coder repo root. Requires `python-dotenv`; silently skipped if not installed.

---

## Aider-specific pass-through

These are forwarded to Aider and live in `core/config/aider_runtime.py`. Unset = use Aider's own defaults.

| Variable | Default | Effect |
|---|---|---|
| `MCP_CODER_AIDER_AUTO_COMMITS` | *(unset)* | Override Aider `--auto-commits` |
| `MCP_CODER_AIDER_DIRTY_COMMITS` | *(unset)* | Override Aider `--dirty-commits` |
| `MCP_CODER_AIDER_AUTO_LINT` | *(unset)* | Override Aider `--auto-lint` |
| `MCP_CODER_AIDER_STREAM` | *(unset)* | Override Aider `--stream` |
| `MCP_CODER_AIDER_USE_GIT` | *(unset)* | Override Aider `--git` |
| `MCP_CODER_AIDER_SUGGEST_SHELL` | *(unset)* | Override Aider `--suggest-shell-commands` |
| `MCP_CODER_AIDER_DETECT_URLS` | *(unset)* | Override Aider `--detect-urls` |
