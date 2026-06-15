# Phase 9 master session bootstrap

**Created:** 2026-06-14
**Status:** Active — planning complete; PM doc at [PHASE9_MVP.md](../PHASE9_MVP.md).
**Purpose:** Record all Phase 9 scope decisions, design rationale, and locked choices made in the master planning session. Workers read the PM doc; this note is the *why* behind it.
**Related notes:** [llm-interception-strategies.md](./llm-interception-strategies.md) (proxy architecture detail), [phase8-master-session-bootstrap.md](./phase8-master-session-bootstrap.md) (Phase 8 decisions)

---

## Phase 9 in one sentence

Add a universal internal HTTP proxy between litellm and the real provider — so every LLM byte is captured before any normalization layer can touch it — then complete the storage/replay substrate and prove 100% coverage by cross-checking the proxy against Phase 8's `ObservableModel`.

---

## Why Phase 9 is bigger than originally planned

The original Phase 9 plan (from Phase 8 master session) was:
- Write-always storage (remove verbosity gate)
- Context package blob
- `mcp-coder replay` CLI
- Storage GC first slice

That plan assumed Phase 8's `ObservableModel` was sufficient for "100% captured." The Phase 9 master session expanded the scope based on two insights:

**Insight 1 — The proxy is the right ground truth.** `ObservableModel` is user-space Python instrumentation. It is *very* good but it sits above litellm's normalization. Whatever litellm drops silently (thinking blocks, provider-specific fields) is permanently lost before we see it. The only way to be *certain* nothing is dropped is to capture at the HTTP level, before litellm normalizes the response.

**Insight 2 — One proxy solves everything.** Once we have a local proxy between litellm and the real provider, it works for every caller: LlmGateway, AiderEngine, and any future backend. The same proxy extended in Phase 10+ handles Claude Code, Codex, OpenCode by pointing their base URL at it. This is the universal architecture, and Phase 9 is the right time to build it.

---

## Locked scope

### A — Write-always storage
Remove verbosity from the write gate. `lean`/`standard`/`full` become display/export/RAG-promotion filters only. Trace file written unconditionally for every delegation.

### B — Context package blob
Store the assembled context package per delegation at `sessions/<id>/context_packages/<hash>.json`. Hash-deduped. Combined with trace + JSONL row: any delegation is fully replayable from disk.

### C — Universal internal proxy
A local OpenAI-compatible HTTP proxy started at MCP server bootstrap. **All LLM calls from all in-process callers route through it.** Captures raw HTTP request + response before litellm normalization. See § Proxy architecture below for full design.

### D — Replay CLI (dry)
`mcp-coder replay <delegation_id>` reconstructs the full delegation from disk: context package, prompt, every executor turn and backend call, response bodies. No re-execution. No Cursor required. Now backed by raw proxy-captured bodies.

### E — Storage GC first slice
`mcp-coder maintenance gc [--dry-run]` + TTL configuration. Promote-then-prune policy. First pass only — no archival, no global promotion store.

---

## Proxy architecture (locked decisions)

### D-P9-1: Proxy sits between litellm and the real provider

```
Any caller (LlmGateway / AiderEngine / future)
    ↓
litellm  — request formatting, retry, ModelResponse wrapping (unchanged)
    ↓  api_base = http://localhost:PORT at bootstrap
LocalLlmProxy  ← capture here (raw HTTP, sees everything)
    ↓  model-prefix routing → real upstream + API key
OpenRouter / Anthropic / OpenAI / ...
```

litellm stays in the stack. The proxy is a transparent pass-through that logs and routes.

### D-P9-2: Proxy captures raw bytes before litellm normalization

The raw response body is stored as-is. Any field loss is attributed unambiguously:
- Present in raw response but absent in `ObservableModel` event → litellm dropped it
- Absent from raw response entirely → upstream provider dropped it (e.g. OpenRouter stripping thinking blocks)

This makes "100% captured from our boundary" a provable statement, not a confident guess.

### D-P9-3: Per-session lifecycle

Proxy starts once at MCP server bootstrap (alongside `ensure_observability_bootstrap()`). All delegations in a session share it. No per-delegation startup overhead, no port lifecycle complexity.

### D-P9-4: Model-prefix routing table built from env vars

```python
ROUTING_TABLE = {
    "openrouter/":  ("https://openrouter.ai/api/v1",    env["OPENROUTER_API_KEY"]),
    "anthropic/":   ("https://api.anthropic.com/v1",     env["ANTHROPIC_API_KEY"]),
    "openai/":      ("https://api.openai.com/v1",        env["OPENAI_API_KEY"]),
}
```

The env vars we already use for LLM routing become the proxy's routing table. No separate config. Callers need no API keys.

### D-P9-5: Attribution via active context store

In-process callers: proxy reads `delegation_id_var` and `step_index_var` from the active context store on each request. No header injection needed. Exact attribution, same quality as `ObservableModel`.

Out-of-process backends (Phase 10+): header injection (`X-Mcp-Delegation-Id`) or timing correlation fallback (see [llm-interception-strategies.md](./llm-interception-strategies.md) § Attribution with the HTTP proxy).

### D-P9-6: Dual capture — proxy is ground truth

Both `ObservableModel` (Phase 8) and proxy run simultaneously during Phase 9:
- `ObservableModel` → `backend_llm_call` event (in-process, fast)
- Proxy → `proxy_llm_call` event (HTTP-level, raw, ground truth)

Diff is logged. If they agree: `ObservableModel` is proven complete. If proxy has calls `ObservableModel` missed: proxy captures them; gap is identified. By Phase 9 exit: 100% coverage proven by evidence, not assertion.

### D-P9-7: Phase 9 proxy scope is in-process callers only

Phase 9 proxy handles: LlmGateway helpers + AiderEngine (via litellm api_base override).

Phase 10+ extends the same proxy to out-of-process backends (Claude Code, Codex, OpenCode) by pointing their base URL at it. No new proxy infrastructure — just base URL config per backend.

### D-P9-8: Write-always is the new default

Verbosity levels (`lean`/`standard`/`full`) control display, CLI output, and RAG promotion only. They never gate what is written to disk. Applies uniformly to all observers.

### D-P9-9: Proxy is an observability observer — common writer

The proxy is not a separate writer. It is a third observer, same as `ObservableModel` and `LiteLLMCallback`:

```
Observers (emit events):          Backend (single writer):
  ObservableModel  ─┐
  LiteLLMCallback  ─┤──► ObservabilityBackend.record_*(...)
  LocalLlmProxy    ─┘       └─ LocalObservability  → traces/<id>.jsonl
                               └─ NullObservability → no-op (tests)
```

`LocalLlmProxy` calls `get_observability().record_proxy_llm_call(...)` exactly as `ObservableModel` calls `record_backend_llm_call(...)` (Phase 8 pattern). `ObservabilityBackend` gains one new abstract method; `LocalObservability` and `NullObservability` implement it. Write-always (D-P9-8), verbosity filtering, and `NullObservability` in tests apply automatically. No separate write path, no file locking, no second schema. Comparison between `proxy_llm_call` and `backend_llm_call` is a single JSONL filter on the same file.

### D-P9-10: Attribution across the HTTP boundary — experimental in Phase 9

**The problem:** Python `contextvars` (`delegation_id_var`, `step_index_var`) do not cross the HTTP boundary. When litellm opens a TCP connection to the proxy, the proxy's async handler has no knowledge of the Python context that initiated the call.

**Primary approach — `extra_headers` injection (three levels):**

`ObservableModel` and `LlmGateway` read context vars before calling litellm and inject attribution headers. No litellm modification needed — `extra_headers` is a public litellm parameter. For `ObservableModel`, headers are injected via `self.extra_params['extra_headers']` before calling `super()`:

```python
self._call_index += 1
self.extra_params['extra_headers'] = {
    **old_headers,
    'X-Mcp-Delegation-Id': delegation_id,       # outer: same for all calls in delegation
    'X-Mcp-Step-Index':    str(step_index),      # executor step (context var)
    'X-Mcp-Call-Index':    str(self._call_index), # Aider inner-loop turn counter
}
```

Three attribution levels and why each is needed:

| Header | Level | Source | Why needed |
|--------|-------|--------|------------|
| `X-Mcp-Delegation-Id` | Outer | `delegation_id_var` context var | Ties all calls in a delegation together — easy, no ambiguity |
| `X-Mcp-Step-Index` | Executor step | `step_index_var` context var | Which outer executor step initiated this |
| `X-Mcp-Call-Index` | Aider inner turn | `ObservableModel._call_index` counter | **Critical:** Aider makes N LLM calls per delegation in its own loop; proxy sees them as N separate HTTP requests with no inherent turn label — this counter gives exact turn identity |

The messages array length serves as a natural cross-check for call order (each Aider turn appends to the conversation, so message count monotonically increases).

**Fallback — timing correlation:**

If headers are absent on a given call path, the proxy timestamps the request (`request_received_at`) and response (`response_received_at`). `ObservableModel` timestamps its call start (`T1`) and end (`T4`). Join condition: `proxy.request_received_at` falls within `[backend.T1, backend.T4]` for matching `model`. Sufficient for sequential delegations.

**Timestamps are always recorded on both events** — they enable post-hoc alignment and reveal latency breakdown:
- `proxy`: `request_received_at` (T2) + `response_received_at` (T3) → pure wire latency (T3−T2)
- `backend_llm_call`: `started_at` (T1) + `completed_at` (T4) → total latency including litellm overhead
- Delta `(T4−T1) − (T3−T2)` = litellm formatting + normalization cost, visible for the first time

**Independent capture, analysis-time alignment:**

Both paths capture their own exact boundaries independently at runtime — proxy records wire-level boundaries (T2, T3); `ObservableModel` records Python-level boundaries (T1, T4). Neither path depends on the other at capture time. Alignment — joining the two event streams to compare what each saw and why they differ — is a post-hoc analysis concern, not a capture concern.

**Phase 9 stance — capture first, align later:**

Boundary alignment is experimental. If some paths don't carry headers cleanly (e.g. `warm_cache_worker` background thread, future callers), the proxy still captures the raw data with `delegation_id: null` — nothing is lost, just unattributed. Alignment refinement is a follow-up, not a Phase 9 exit blocker. The proxy proves coverage counts regardless of attribution completeness.

---

## What Phase 9 does NOT own

| Item | Why deferred |
|------|-------------|
| Out-of-process backends (Claude Code, Codex, OpenCode) | Phase 10+ — just a base URL config change once proxy exists |
| Inner loop control / BL-351 supervisor | Phase 10+ — visibility before intervention |
| Full re-execution replay (sandboxed) | Phase 10+ — needs isolation infra |
| Novelty / curation pipeline | After raw corpus exists |
| Training dataset export | Separate product scope |
| Embeddings for RAG (BL-366) | Measure FTS recall first |

---

## Phase 9 acceptance (north star)

After a live `delegate_to_agent` call at any verbosity setting:

1. Full prompt + response bodies written to `traces/<id>.jsonl` — not truncated, not gated on verbosity.
2. Context package blob stored at `sessions/<id>/context_packages/<hash>.json`.
3. `proxy_llm_call` events present in trace alongside `backend_llm_call` events — proxy and `ObservableModel` cross-check confirmed.
4. BL-507 resolved: proxy raw response log reveals whether thinking tokens are present at the HTTP boundary (ruling out litellm as the stripping layer).
5. `mcp-coder replay <delegation_id>` reconstructs the full delegation from disk — no Cursor.
6. `mcp-coder maintenance gc --dry-run` reports what would be pruned.

---

## Milestone order rationale

P9-001 (write-always) first — it's a small flag flip and immediately makes all subsequent data richer.
P9-002 (blob) before P9-004 (replay) — replay needs the blob to be useful.
P9-003 (proxy) can run in parallel with P9-002 since it's infrastructure, not storage format.
P9-004 (replay) last among the capture milestones — it validates everything above works together.
P9-005 (GC) last — only relevant once you have data worth managing.
