# Environment Variable Matrix

This page summarizes active runtime knobs for logging/observability/proxy behavior.

## Logging and observability controls

| Variable | Default | Effect |
|---|---|---|
| `MCP_CODER_LOG_BRIEF` | `1` | Enables one-line stderr receive/send traces. |
| `MCP_CODER_LOG_VERBOSE` | `0` | Emits extra verbose delegation write lines to stderr. |
| `MCP_CODER_SERVER_LOG` | `1` | Enables structured `server.jsonl` event logging. |
| `MCP_CODER_SERVER_LOG_LEVEL` | `info` | Filters server log events (`error|warn|info|debug`). |
| `MCP_CODER_SERVER_LOG_SCOPE` | `global` | Target log scope (`global|project|both`). |
| `MCP_CODER_OBS_VERBOSITY` | `standard` | Trace verbosity tier (`lean|standard|full`). |
| `MCP_CODER_OBS_RETENTION` | `session` | Retention policy (`session|forever|<N>_days`). |
| `MCP_CODER_CAPTURE_REASONING` | `1` | Enables/disables reasoning payload capture. |
| `MCP_CODER_REASONING_BUFFER_SIZE` | `3` | Session reasoning summary ring size. |
| `MCP_CODER_CAPTURE_FOR_TRAINING` | `0` | Enables training-capture artifact writes. |

## Executor behavior (P10-001 / P10-003)

| Variable | Default | Effect |
|---|---|---|
| `MCP_CODER_EXECUTOR_SYSTEM_PREFIX` | *(unset)* | Optional system-prompt prefix prepended by Aider before every message. |
| `MCP_CODER_EXECUTOR_EDIT_FORMAT` | *(unset)* | Optional Aider edit format override (`whole`, `diff`, `udiff`, …). |
| `MCP_CODER_STALL_AUTO_RETRY` | `0` | `1` enables one-shot auto-retry when Aider stalls asking for files (see below). |

### Stall auto-retry (`MCP_CODER_STALL_AUTO_RETRY`)

When **off** (default): if Aider output matches a file-request stall, `delegate_to_agent` returns `status: needs_input` with `files_requested[]` so the Cursor planner can add paths and call the tool again.

When **on** (`1`): mcp-coder automatically merges the requested paths into `target_files` / read context and runs the executor **one more time** in the same MCP call. If the retry still stalls, it escalates to `needs_input` as usual. Delegation audit records `auto_retried: true` when the retry path runs.

This is **not** a general failure retry (timeouts, test failures, model errors). It only applies to the `needs_input_files` stall pattern.

## Proxy control

| Variable | Default | Effect |
|---|---|---|
| `MCP_CODER_PROXY_ENABLED` | `1` | `0` disables local proxy bootstrap and prevents proxy API-base override. |

When proxy is enabled, the bootstrap path starts a local proxy and points provider API base variables to that proxy endpoint.
When proxy is disabled, requests use provider URLs directly and `proxy_llm_call` events are not emitted.

## Write-vs-display semantics

Phase 9+ observability uses write-always semantics for trace/delegation artifacts.
Verbosity and CLI filters control **display/detail level**, not whether records are written at all.
