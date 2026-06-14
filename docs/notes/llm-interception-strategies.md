# LLM call interception strategies

**Created:** 2026-06-13
**Purpose:** Architectural reference for how to intercept LLM calls made by third-party backends (Aider, future CLI coders). Used in Phase 8 planning; applies to any future phase that extends capture depth or adds control.
**Status:** Living design note — update as approaches are validated or discarded.
**Related backlog:** BL-371 (backend interception matrix), BL-350 (executor loop ownership), BL-351 (supervisor / control)
**Current phase context:** Phase 8 will pick one of these approaches for P8-001 (Aider inner-loop capture).

---

## The problem

mcp-coder runs third-party backends (currently Aider) that make their own LLM calls internally. Those calls are opaque unless we actively intercept them. The goals at different phases:

| Phase | Goal |
|-------|------|
| Phase 7 (done) | Capture outer executor events; see every step from mcp-coder's loop |
| **Phase 8** | Capture every Aider LLM sub-call including thinking tokens; define backend interception contract |
| **Phase 9** | Write-always storage + blobs + replay — "100% log" now honest for primary backend |
| **Phase 10+** | HTTP proxy for Claude Code / Codex / OpenCode; inner loop control (BL-351) |

The four approaches below differ in **where** you tap into the call chain, which determines what you can see and what you can do.

---

## Approach 1 — Harden the existing LiteLLM callback

**Tap point:** LiteLLM's `success_callback` — already registered in `core/observability/litellm_callback.py`. Fires after every `litellm.completion` call anywhere in the process.

**What you get:** Post-call notification with response payload. Attribution requires injecting `metadata` into each litellm call upstream.

**How thinking tokens arrive:** Depends on litellm callback contract for the specific version and provider. Not guaranteed to include full thinking blocks.

**Pros:**
- Already in production; minimal new code
- Works for any backend that uses litellm internally (Aider does)
- No Aider internals touched

**Cons:**
- Attribution is heuristic (inferred from metadata or timing), not structural
- Thinking token preservation varies by litellm version / provider — cannot be guaranteed
- Fire-and-forget: observe only, no intercept/modify path (Phase 9 control impossible)
- Aider can bypass litellm in edge cases (streaming quirks, direct HTTP fallback)

**Best for:** Quick incremental improvement; not a durable Phase 9 foundation.

---

## Approach 2 — Proper wrapper / derived class (preferred over monkey-patching)

**Tap point:** Intercept at the seam the backend already exposes — a class you can subclass or wrap — rather than mutating module-level state at runtime.

Three sub-variants depending on what the backend exposes:

### 2a — Subclass Aider's `Model.send_completion()` *(verified, recommended for Phase 8)*

**Aider audit result (aider-chat 0.82–0.86, checked 2026-06-13):**

**litellm is Aider's universal provider adapter — all LLM calls go through it, always.** Provider-specific logic in Aider (OpenRouter, Anthropic, Gemini, Bedrock, GitHub Copilot, DeepSeek) is config-only: it sets the right model name prefix and `extra_params` (e.g. `openrouter/model-name`, `thinking: {budget_tokens: N}`). The actual API call is always `litellm.completion(**kwargs)`.

`litellm.completion()` is called in exactly **two places** in Aider:

| Location | Method | Purpose | Coverage |
|----------|--------|---------|----------|
| `aider/models.py:1021` | `Model.send_completion()` | Every real LLM turn — the hot path | ✓ Subclass |
| `aider/coders/base_coder.py:1373` | `warm_cache_worker()` inline | Background cache-warming pings (`max_tokens=1`) | ✓ Route A callback |

**Primary seam — `ObservableModel` subclass (recommended):**

```python
class ObservableModel(aider.models.Model):
    def send_completion(self, messages, functions, stream, temperature=None):
        hash_obj, result = super().send_completion(
            messages, functions, stream, temperature
        )
        # Full ModelResponse in hand — thinking blocks preserved before Aider processes them
        get_observability().record_event("backend_llm_call", {
            "call_type": "executor_turn",
            "model": self.name,
            "delegation_id": get_current_delegation_id(),
            "step_index": get_current_step_index(),
            "thinking_tokens": extract_thinking(result),
            "usage": result.usage,
        })
        return hash_obj, result
```

Pass to Aider at construction: `Coder.create(main_model=ObservableModel(...), ...)`.

**Secondary coverage — `warm_cache_worker` via Route A callback:**

`warm_cache_worker` calls `litellm.completion()` directly in a background thread, bypassing `send_completion`. Route A `success_callback` already fires for it. Extend the callback to detect and tag it cheaply:

```python
# In litellm_callback.py — detect cache-warming probes
if kwargs.get("max_tokens") == 1 and get_current_delegation_id():
    obs.record_event("backend_llm_call", {
        "call_type": "cache_warm",
        "model": kwargs.get("model"),
        "delegation_id": get_current_delegation_id(),
    })
```

No content to capture (`max_tokens=1`), but the event closes the coverage gap in the trace.

**Complete Aider coverage after Phase 8:**

| Call site | Capture via | Attribution | Content value |
|-----------|-------------|-------------|---------------|
| `send_completion()` — all real turns | `ObservableModel` subclass | ✓ Exact | ✓ Full (thinking, usage, messages) |
| `warm_cache_worker` — cache pings | Route A callback tag | Inferred | None (`max_tokens=1`) |

**Event routing:** emit `backend_llm_call` events through the existing `Observability` seam into the same `traces/<delegation_id>.jsonl` file — consistent with `llm_call` events for helpers. `call_type` field distinguishes `executor_turn` vs `cache_warm`.

**Pros:**
- ~20 lines of Python — one class, one method override, one `super()` call
- Zero new infrastructure — no proxy, no package management, no import order discipline
- Full `ModelResponse` in hand — thinking blocks captured before Aider processes them
- Typed, testable, normal Python OOP — `TypeError` if Aider changes signature (immediately visible)
- All providers (OpenRouter, Anthropic, Gemini, Bedrock) covered by the same seam
- `warm_cache_worker` gap covered by existing Route A callback at near-zero additional cost

**Cons:**
- Aider-specific — each new backend needs its own equivalent audit (hence P8-002 backend contract)
- Must track when Aider refactors `send_completion` (rare; signature stable across versions)

**Best for:** Phase 8 Aider capture. Highest ROI — minimal effort, near-zero maintenance, 100% coverage of real LLM turns.

### 2b — Module-level wrapper via `sys.modules` (cleaner than function patch)

Rather than patching individual functions, replace the entire `litellm` module entry with a wrapper object before any import:

```python
import sys
import litellm as _real_litellm

class LiteLLMWrapper:
    def completion(self, *args, **kwargs):
        result = _real_litellm.completion(*args, **kwargs)
        emit_gateway_event(args, kwargs, result)
        return result

    def __getattr__(self, name):
        return getattr(_real_litellm, name)  # pass-through everything else

sys.modules['litellm'] = LiteLLMWrapper()
```

**Pros:**
- Single seam for the entire `litellm` API, not per-function patches
- Still works when Aider adds new litellm call variants (pass-through catches them)
- Cleaner than function-level patching: one object, one place

**Cons:**
- `isinstance(x, types.ModuleType)` checks in downstream code will break
- `from litellm import completion` at the top of any already-loaded module holds a direct reference and bypasses the wrapper — import order still matters
- Not standard Python; can surprise future maintainers

### 2c — `LlmGateway` as the owned LLM interface (recommended long-term anchor)

`LlmGateway` already exists in `core/observability/gateway.py` as the owned boundary for all mcp-coder-authored LLM calls (Phase 7: helpers, test-model). The natural extension: every backend adapter also receives an `LlmGateway` instance as a dependency and routes all LLM calls through it, rather than calling `litellm.completion()` directly.

```python
# backend adapter receives gateway at construction
class AiderEngine:
    def __init__(self, ..., gateway: LlmGateway):
        self._gateway = gateway

# Aider model subclass (2a) delegates to the gateway instead of litellm
class ObservableAiderModel(aider.models.Model):
    def __init__(self, *args, gateway: LlmGateway, **kwargs):
        super().__init__(*args, **kwargs)
        self._gateway = gateway

    def send(self, messages, **kwargs):
        return self._gateway.completion(self.name, messages, **kwargs)
```

For backends that support native dependency injection, 2a is not even needed — just pass the gateway directly as the LLM caller. For backends that don't (like current Aider), 2a + 2c compose: 2a provides the injection mechanism, 2c provides the interface.

**Why 2c scales to other backends and LLM libraries:**

The gateway becomes a contract. Different LLM libraries get their own gateway implementation; the backend adapter always receives the same interface:

| Backend | LLM library | Gateway implementation |
|---------|-------------|----------------------|
| Aider | litellm | `LlmGateway` (wraps litellm) — already exists |
| Future tool using litellm | litellm | same `LlmGateway`, no new code |
| OpenCode | openai SDK directly | `OpenAiSdkGateway(LlmGatewayInterface)` |
| Any anthropic-native tool | anthropic SDK | `AnthropicGateway(LlmGatewayInterface)` |

The full call chain after Phase 8:

```
Phase 7: owned helpers → LlmGateway → litellm → provider
Phase 8: backend adapters also receive LlmGateway; Aider routed through it
Phase 9+: swap LlmGateway implementation for OtherLibraryGateway — pattern identical
```

**Pros:**
- Architecturally cleanest — `LlmGateway` is already our abstraction; this is its natural graduation
- Backend-neutral: any backend that accepts a configurable LLM caller uses the same gateway interface
- Works for other litellm-based backends with zero new code
- Extensible to non-litellm backends via new gateway implementations (not new interception strategies)
- Fully testable: inject a `NullGateway` or mock in tests
- Phase 9 control is just new logic inside `LlmGateway.completion()` — one place, all backends benefit

**Cons:**
- Requires backends to accept a configurable LLM provider — Aider may not support this natively (needs `ObservableAiderModel` bridge via 2a)
- `LlmGateway` interface needs to be stable enough to commit to as a public contract
- If a backend bypasses the injected model entirely (internal litellm calls outside `Model.send()`), holes remain — needs verification

**Key investigation needed for P8-001:** Does Aider's `Coder.create(model=...)` route *all* LLM calls through the injected `Model.send()` method, or does it call `litellm.completion()` directly in some paths? This determines whether 2a+2c covers 100% of Aider or needs 2b as a backstop.

---

**What you get (all 2x variants):** Full request + response object before it is consumed by the caller. Thinking blocks present because we own the response.

**How thinking tokens arrive:** Complete — we receive the raw litellm `ModelResponse` including `thinking` content blocks before the backend processes them.

**Best for:** Phase 8 primary approach. Prefer 2a (subclass) if Aider supports injection; fall back to 2b/2c if not. All three are preferable to function-level monkey-patching.

---

## Approach 3 — Own the backend's inner loop

**Tap point:** Drive the backend's execution step-by-step from mcp-coder code, rather than calling `backend.run()` as a black box.

For Aider specifically: call `aider.coder.send_message()` or equivalent directly and intercept each model round-trip in our own loop.

**What you get:** Exact attribution (we control the loop — we know which step each call belongs to), full request/response, thinking tokens, and natural injection points for Phase 9 control.

**How thinking tokens arrive:** Complete — we construct the litellm call ourselves or intercept it directly.

**Pros:**
- Exact attribution — no inference needed
- Full control + full visibility in one architecture (Phase 8 + Phase 9 simultaneously)
- Natural path to BL-351: supervisor can answer Aider prompts, inject context, pause mid-turn
- Cleanest long-term design

**Cons:**
- Deep backend internals dependency — `Coder`, `Model`, `InputOutput` internals for Aider
- High maintenance burden; breaks on Aider refactors
- Significant upfront work; risk of subtle behavioral differences
- Backend-specific: must redo for every new backend

**Best for:** Phase 9+ when control (BL-351) justifies the engineering investment.

---

## Approach 4 — Local HTTP proxy (process boundary)

**Tap point:** Spin up a local OpenAI-compatible HTTP proxy. Set `OPENAI_API_BASE` (or equivalent env var) so the backend routes all LLM calls through it. Proxy captures every request/response and forwards to the real provider.

```
Backend → http://localhost:PORT/v1/chat/completions
         → [capture full request + response]
         → real provider (OpenAI / Anthropic / Gemini)
```

**What you get:** Full HTTP request and response body — thinking blocks included, for any backend, in any language, regardless of whether it uses litellm.

**How thinking tokens arrive:** Complete — captured at the HTTP layer before any SDK processing.

**Pros:**
- Completely backend-agnostic: works for Aider, OpenCode, any future CLI tool in any language
- Thinking tokens guaranteed at the HTTP body level
- Zero backend internals — configure via env var only
- Future: proxy becomes a control plane (Phase 9 — modify requests, inject system prompt, pause)
- Clean architecture; mcp-coder owns the proxy; backends are truly black boxes

**Cons:**
- Non-trivial infrastructure: TLS for non-OpenAI providers; Anthropic/Gemini use different auth schemes (not OpenAI-compatible out of the box)
- Port lifecycle and async server management
- Streaming requires SSE passthrough (complex to tee correctly)
- Attribution still requires request metadata (delegation_id in headers or request body)
- Harder to unit-test without running the proxy
- Subprocess mode required when Python API benefits are lost

**Best for:** Long-term multi-backend architecture; likely the right Phase 9+ foundation once the control story justifies the infrastructure.

## The pretender pattern — install-time substitution (preferred)

The cleanest framing: install *our* package as `litellm` in the environment where Aider runs. Python resolves imports from installed packages, so every import form works with no runtime injection and no import order discipline:

| Import form | Works? |
|-------------|--------|
| `import litellm` | ✓ |
| `from litellm import completion` | ✓ |
| `import litellm.main` | ✓ |
| `from litellm.main import Y` | ✓ |
| Any submodule path | ✓ if mirrored |

### Package structure

In the environment mcp-coder controls (the venv where Aider runs):

```
litellm-upstream   ← real litellm, installed under a private name
litellm            ← our wrapper, installed as the canonical "litellm"
```

Our `litellm` package re-exports everything from `litellm-upstream` and overrides the LLM call methods to route through `LlmGateway`:

```python
# litellm/__init__.py  (our wrapper package)
from litellm_upstream import *                   # re-export full API surface
from litellm_upstream import completion as _real_completion
from litellm_upstream import acompletion as _real_acompletion

def completion(model, messages, **kwargs):
    return LlmGateway.get().completion(model, messages, **kwargs)

def acompletion(model, messages, **kwargs):
    return LlmGateway.get().acompletion(model, messages, **kwargs)
```

Submodules mirror the real structure — either by re-exporting or lazy delegation. Any call Aider makes, in any import form, hits our package.

### Why this is better than runtime injection

| Property | Runtime `sys.modules` injection | Install-time substitution |
|----------|---------------------------------|--------------------------|
| All import forms | ✗ submodule paths escape | ✓ all forms covered |
| Import order sensitivity | ✓ must inject first | ✓ irrelevant |
| Ongoing maintenance | ✗ fragile to litellm internals | ✓ `from upstream import *` handles most changes |
| Standard Python | ✗ runtime magic | ✓ normal packaging |
| Testability | Low | ✓ High (swap gateway) |

### Cons and constraints

- **litellm API surface is large** — `from litellm_upstream import *` + selective overrides handles most of it; only the LLM call functions need explicit override
- **Submodule mirroring** — any submodule Aider imports directly needs to be present in our package (finite, auditable list; most can be thin re-exports)
- **Environment ownership required** — only works because mcp-coder controls the environment Aider runs in; would shadow a user's global litellm install if applied system-wide (wrong)
- **litellm version pinning** — `litellm-upstream` version must be compatible with Aider's litellm dependency; need to track when Aider bumps its litellm requirement

### Open question

Does mcp-coder already run Aider in an isolated venv it controls? If yes, package substitution is straightforward. If Aider runs in the user's system/global environment, a different strategy is needed (fall back to 2a subclass backstop).



## Per-backend audit (2026-06-13)

### Aider (Python, litellm)

**Architecture:** litellm is Aider's universal LLM adapter. All providers — OpenRouter, Anthropic, Gemini, Bedrock, GitHub Copilot — go through litellm. No provider SDK is called directly.

**LLM call seam:** `Model.send_completion()` in `aider/models.py:970` — single method, verified. Two `litellm.completion()` call sites total: this one (all real turns) and a background cache-warming probe (`max_tokens=1`, acceptable gap).

**Extension hooks:** None for LLM calls. Aider has no plugin/hook system.

**Best interception:** Subclass `Model.send_completion()` — pure Python OOP, verified, zero infra.

---

### Claude Code (TypeScript, Anthropic SDK)

**Architecture:** TypeScript monolith. `getAnthropicClient()` factory creates the LLM client at startup; `callModel()` inside `query.ts` (1730-line async generator) is the single LLM call path. Supports Direct API, Bedrock, Vertex, Azure — all via Anthropic SDK wrapper classes presenting the same interface.

**Extension hooks:** Rich 27-event hook system (`PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`, etc.) — but these are for **tool execution interception**, not LLM call capture. No `PreModelCall`/`PostModelCall` hook equivalent.

**Base URL override:** `ANTHROPIC_BASE_URL` env var routes all LLM calls through a custom endpoint. This is the **universal capture path**.

**Best interception (Phase 9):** Set `ANTHROPIC_BASE_URL` → local HTTP proxy. Proxy captures full request + response including thinking blocks. Works for all providers since they all go through `callModel()` → Anthropic SDK.

---

### Codex CLI (Rust)

**Architecture:** Rust binary. `ModelClient`/`ModelClientSession` in `codex-rs/core`. Uses OpenAI `/v1/responses` API exclusively (Responses API, not Chat Completions — newer format). Custom providers configurable in `config.toml` with arbitrary `base_url`, `env_key`, custom headers, retry config.

**Extension hooks:** Has a "Claude-style hooks engine for pre/post-tool execution" (`codex-rs/core/src/session/mod.rs`) — same caveat as Claude Code: tool execution hooks, not LLM call hooks.

**Built-in proxy:** Has a `codex-responses-api-proxy` crate in its own workspace — **OpenAI themselves built the proxy extension point**. Strong signal that this is the intended capture path.

**Base URL override:** `base_url` in `config.toml` — direct configuration.

**Best interception (Phase 9):** `base_url` → local HTTP proxy implementing the Responses API (`/v1/responses`). Note: this is different from the Chat Completions format — proxy must implement the Responses API wire format.

---

### OpenCode (TypeScript/Bun, Vercel AI SDK)

**Architecture:** TypeScript application bundled with Bun. Uses Vercel AI SDK + direct provider SDKs (OpenAI, Anthropic, Google) for 75+ providers. Plugin system loaded from `.opencode/plugins/` or npm.

**Extension hooks:** Rich TypeScript plugin API with hooks:
- `chat.params` — modify LLM call parameters (temperature, topP, custom options) before the call
- `chat.message` — fires on chat messages
- `tool.execute.before/after` — tool execution
- `session.*` events — lifecycle events
- **No `chat.response` hook** — no direct LLM response capture in plugin API

**Base URL override:** Supports custom providers with configurable base URLs (OpenAI-compatible). Can define a provider pointing to a local proxy.

**Best interception (Phase 9):** Register a custom provider in `opencode.json` pointing to a local HTTP proxy. Proxy captures request + response.

---

### Universal pattern across all three (Phase 9)

All three non-Aider backends support **base URL configuration**:

| Backend | Config mechanism | Notes |
|---------|-----------------|-------|
| Claude Code | `ANTHROPIC_BASE_URL` env var | All providers route through this |
| Codex | `base_url` in `config.toml` | Has its own `codex-responses-api-proxy` crate |
| OpenCode | Custom provider in `opencode.json` | OpenAI-compatible base URL |

The hooks systems across all three are for **tool execution** (equivalent to `tool_call` events we already capture in Phase 7 outer loop). They do not expose LLM request/response bodies.

**Phase 9 architecture therefore:** One local HTTP proxy implementing the provider APIs needed (Anthropic Messages API + OpenAI Chat Completions + OpenAI Responses API). Each backend is configured to route to it. Proxy captures full request + response, emits gateway events, forwards to real provider.

```
Phase 8:  Aider → subclass Model.send_completion()      Python, no infra
Phase 9:  Claude Code + Codex + OpenCode                HTTP proxy via base_url config
          (one proxy, three backends, zero backend-internals knowledge)
```

---


|---|---|---|---|---|---|---|---|
| **Thinking tokens** | Fragile | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Attribution accuracy** | Inferred | ✓ Exact | Needs propagation | ✓ Exact | Needs propagation | ✓ Exact | Needs propagation |
| **Any litellm backend** | ✓ | ✗ | ✓ | ✓ | ✓ | ✗ | ✓ |
| **Non-litellm backends** | ✗ | ✗ | ✗ | Interface only | New pretender impl | ✗ | ✓ Any |
| **Backend internals needed** | None | Aider Model API | None | None | None | Deep | None |
| **Phase 9 control path** | ✗ | ✓ | Possible | ✓ | ✓ | ✓ | ✓ |
| **Module side effects** | None | None | Yes | None | Yes (startup only) | None | None |
| **Testability** | Medium | ✓ High | Low | ✓ High | ✓ High (mock gateway) | Medium | Low |
| **Implementation effort** | Low | Medium | Medium | Medium | Medium | High | High |
| **Fragility** | Medium | Low | Medium | Low | Low-medium | High | Low |

---

## Recommended sequencing

```
Phase 7  (done): LlmGateway owned paths + executor outer loop + compile events
Phase 8  (next): Aider full interception via Model.send_completion() subclass + thinking tokens
Phase 9        : Write-always storage + blobs + replay — "100% log" claim now honest
Phase 10+      : HTTP proxy (Claude Code / Codex / OpenCode) + inner loop control (BL-351)
```

| Phase | Backend | Approach | Rationale |
|-------|---------|----------|-----------|
| **Phase 8** | Aider | **2a** — subclass `Model.send_completion()` | Python, verified, zero infra; closes primary backend gap so Phase 9 "100%" claim is honest |
| **Phase 9** | — | Write-always storage, blobs, replay | Storage substrate; no new capture infra needed if Phase 8 done right |
| **Phase 10+** | Claude Code | `ANTHROPIC_BASE_URL` → HTTP proxy | TypeScript; Python subclass not applicable |
| **Phase 10+** | Codex | `base_url` in `config.toml` → HTTP proxy | Rust binary; OpenAI's own `codex-responses-api-proxy` crate confirms this pattern |
| **Phase 10+** | OpenCode | Custom provider base URL → HTTP proxy | Bun/TS binary; no other option |
| **Phase 10+** | All | Inner loop control (BL-351) | Requires proxy in place + Phase 9 storage substrate |

**Phase 8 pre-work (already done):**
- ✓ `Model.send_completion()` confirmed as single seam for all Aider LLM calls
- ✓ Cache-warming bypass (`warm_cache_worker`) identified as acceptable gap
- ✓ All providers (OpenRouter, Anthropic, Gemini, Bedrock) route through this method
- ✓ Thinking blocks in the `result` returned by `super().send_completion()`

Approach 1 (Route A litellm callback) stays in place as a **cross-check and fallback** for any path that slips through.

---

## Attribution with the HTTP proxy (Phase 9)

When using the subclass approach (Aider, Phase 8), attribution is exact — we own the call, we know `delegation_id` and `step_index`. With the proxy, the HTTP request arrives without that context. Three strategies to recover it, from cleanest to fallback:

### Option A — Header injection (exact attribution, all backends)

mcp-coder controls the execution environment. Before each executor step, set env vars:

```bash
MCP_DELEGATION_ID=xxx
MCP_STEP_INDEX=2
```

Configure each backend to pass these as custom request headers:

| Backend | How to inject | Config mechanism |
|---------|--------------|-----------------|
| Claude Code | `--add-header "X-Mcp-Step: $MCP_STEP_INDEX"` CLI flag | Or via hooks `shell.env` |
| Codex | `headers: { "X-Mcp-Step": "${env:MCP_STEP_INDEX}" }` | `config.toml` custom headers |
| OpenCode | Plugin `shell.env` hook injects env vars → passed as provider headers | `.opencode/plugins/` |

Proxy reads `X-Mcp-Step` + `X-Mcp-Delegation-Id`, strips them before forwarding, attributes the call. **Exact attribution — same quality as the subclass approach.**

Note: header injection is also required for Phase 9+ control (BL-351) — the proxy needs to know which step it is in to decide whether to pause/inject. Attribution is solved as part of the control story, not extra work.

### Option B — Timing correlation (no backend config, works for sequential steps)

mcp-coder's outer loop (P7-002) already emits `executor_turn` events with timestamps. The proxy timestamps every call. Match by time window:

```
Step 2 started:  T=10:00:05.001
Proxy call 1:    T=10:00:05.040  → step 2
Proxy call 2:    T=10:00:07.210  → step 2
Step 2 ended:    T=10:00:08.330
```

Works well for all current backends (sequential steps within a delegation). Gets ambiguous only for concurrent sub-delegations — not a current concern.

### Option C — Message-count heuristics (inference from content, last resort)

The `messages` array in the request body grows with each turn. Message count delta between calls allows step-number inference. Not exact but sufficient for forensic replay when A and B are unavailable.

### Summary

| | Subclass (Phase 8) | Proxy + header injection | Proxy + timing only |
|---|---|---|---|
| Thinking tokens | ✓ | ✓ | ✓ |
| Full request/response | ✓ | ✓ | ✓ |
| Attribution: delegation_id | ✓ exact | ✓ exact | Inferred |
| Attribution: step_index | ✓ exact | ✓ exact | Inferred |
| Backend config needed | Python subclass | Small per-backend config | None |
| Phase 9 control path | Extend subclass | ✓ natural | Possible |

---

## Open questions

### Phase 8 (Aider subclass)

1. **Streaming:** Aider uses streaming by default. `send_completion()` returns `(hash_obj, result)` where `result` is a streaming response iterator. Capturing it requires either (a) buffering the full stream before returning — adds latency — or (b) tee-ing the iterator so Aider and our capture both consume it. Or: check if non-streaming mode (`--no-stream`) is viable for mcp-coder delegations.

2. **Thinking block normalization:** litellm normalizes thinking differently per provider — Anthropic returns a `thinking` content block; OpenAI o-series returns `reasoning_content`. Does the trace schema use a normalized `thinking_tokens: int` + `thinking_text: str | null`, or store the provider-native structure? Normalized is safer for cross-provider replay.

3. **Dogfood bar:** Does P8-001 acceptance require a live delegation proving Aider sub-calls appear in the trace, or is a mocked-Aider unit test sufficient? Recommended: live dogfood — same pattern as Phase 7 dogfood IDs.

4. **Route A retirement:** Once `send_completion()` subclass is in place, does the LiteLLM `success_callback` (Route A) become redundant for Aider? Recommendation: keep as cross-check/fallback, but deprioritize it.

5. **Backend contract format (P8-002):** What does the per-adapter interception matrix look like? Options: (a) runtime-checked assertion in adapter base class, (b) documented JSON matrix per adapter, (c) Python `@dataclass InterceptionProfile` attached to each adapter.

### Phase 9 (HTTP proxy)

6. **Wire format coverage:** Proxy needs to implement at least two formats: Anthropic Messages API (Claude Code + OpenCode-Anthropic path) and OpenAI Responses API (`/v1/responses` for Codex). OpenChat Completions (`/v1/chat/completions`) for OpenCode-OpenAI path. Scope: implement all three, or prioritize and defer?

7. **Proxy lifecycle:** How does the proxy server start/stop relative to delegations? Options: (a) long-lived process started with mcp-coder server, (b) per-delegation ephemeral process. Long-lived is simpler; ephemeral avoids port conflicts.

8. **Streaming passthrough:** Proxy must tee streaming SSE responses — capture while forwarding to the backend in real time. Non-trivial but well-understood pattern.

9. **Attribution timing race:** In Option B (timing correlation), if mcp-coder outer loop and proxy are in separate processes, clock skew could misattribute calls. Mitigate with: NTP sync check at startup, or prefer Option A (header injection) once backends support it.

10. **Proxy for owned helpers:** After Phase 9, do owned helper calls (currently routed through `LlmGateway` directly) also route through the proxy for uniformity? Or keep them on the in-process gateway path (lower latency, already tested)?
