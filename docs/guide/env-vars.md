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

## Proxy control

| Variable | Default | Effect |
|---|---|---|
| `MCP_CODER_PROXY_ENABLED` | `1` | `0` disables local proxy bootstrap and prevents proxy API-base override. |

When proxy is enabled, the bootstrap path starts a local proxy and points provider API base variables to that proxy endpoint.
When proxy is disabled, requests use provider URLs directly and `proxy_llm_call` events are not emitted.

## Write-vs-display semantics

Phase 9+ observability uses write-always semantics for trace/delegation artifacts.
Verbosity and CLI filters control **display/detail level**, not whether records are written at all.
