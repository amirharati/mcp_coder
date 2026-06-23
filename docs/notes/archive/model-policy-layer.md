<!--
  STEWARDSHIP — Tier 3 direction note. See docs/VISION_DOCS.md.

  - Records the model registry architecture settled in the Phase 9 master session (2026-06-16).
  - Phase 9 ships Stage 1 (env-controlled generation params + call-path wiring + policy_applied logging).
  - Stages 2–4 and the prompt policy layer are future — recorded so Stage 1 is built without closing the door.
  - Update as decisions land; cross-link BL-511..BL-514 and any new P10-* when they exist.
-->

# Model registry — direction note

**Created:** 2026-06-16  
**Status:** Stage 1 **shipped in Phase 9** — **P9-011** (unify helper path + registry front door) and **P9-012** (generation params + weak model + `policy_applied` logging) both **done** (2026-06-16; full suite `924 passed, 2 skipped`). `policy_applied` landed as a **top-level trace field** carried via the `model_policy_var` contextvar. Stages 2–4 and prompt policy layer remain backlogged.  
**Related notes:** [multi-model-roles.md](./multi-model-roles.md) (per-role model vision), [phase9-master-session-bootstrap.md](./archive/phase9-master-session-bootstrap.md) (proxy + auditable log)  
**Backlog:** BL-511 (Stage 1, Phase 9), BL-512 (Stage 2 — host-set), BL-513 (Stage 3 — AI-suggested), BL-514 (Stage 4 — escalation), BL-515 (model tiers/classes); BL-162 (multi-model routing), BL-321 (tiered escalation)

---

## The problem in one paragraph

mcp-coder today has no single place that answers *"for role X with model Y, what are all the parameters we use?"* Model IDs come from `.env`, but request-level params (thinking budget, max tokens, temperature) are hardcoded ad-hoc in each call site. There is no shared policy, no auditable record of what config was active for a delegation, and no way to enable extended thinking without touching multiple files. Phase 9 dogfooding confirmed this: `proxy_llm_call.raw_request` carries no `thinking` field on any path.

---

## Current state (ground truth, 2026-06-16)

Verified against the code so the registry extends reality rather than an imagined system.

**Already centralized — keep, do not rewrite:**
- `core/config/models.py` — `resolve_model_name()` (`AIDER_MODEL → MCP_CODER_MODEL → DEFAULT`)
- `core/config/role_models.py` — `resolve_role_model_name(role, workspace)` and `resolve_role_budget_tokens(role, workspace)`: per-role **model ID** + **budget tokens** with default → env → workspace-YAML precedence. Roles: executor, review, context_builder, critic.

**Missing entirely — what the registry adds:** generation params (reasoning_effort / thinking_budget / temperature / top_p / extra_params) and a resolved weak model. Nobody sets these today on any path.

**Three call paths — two of them clean, one legacy:**

| Path | Entry | Mechanism | Trace event | Param hook |
|------|-------|-----------|-------------|-----------|
| Executor | `AiderEngine` → `ObservableModel` | Aider `Coder` | `backend_llm_call` | `model.extra_params` |
| Owned helper | `run_owned_helper_completion` → `LlmGateway.complete(role=)` | `litellm.completion` | `llm_call` | direct kwargs |
| **Legacy helper** | `workspace_summarizer_llm`, `spec_review` | `Model().simple_send_with_retries()` | **none (proxy only)** | none |

The legacy path bypasses the gateway and produces no `llm_call` event — a logging hole. **Decision: remove it.** Migrate both onto `LlmGateway` so there is exactly one helper path with uniform params + logging.

## Two engine surfaces (target)

```
ExecutionEngine  (pluggable — user-facing, multiple backends possible)
│
├── AiderEngine       ← today: uses Aider for execution AND as metadata source
├── OpenCodeEngine    ← future: different execution, same registry
└── ClaudeCodeEngine  ← future: different execution, same registry
        ↑ resolve(role="executor") → CallParams → model.extra_params

Helper path  (locked-in — ONE path, internally managed)
│
├── Execution:  always LlmGateway → litellm.completion   (no direct Model() calls)
├── Metadata:   Aider model registry (token limits, quirks)
└── Config:     resolve(role) → CallParams → litellm kwargs
```

Not a `HelperEngine` *class* (helpers stay as functions over `LlmGateway`) — "engine" here is conceptual. The contract is: **every helper LLM call goes through `LlmGateway.complete(role=...)`.**

**Key principle:** Aider is the permanent metadata foundation for ALL roles. It is the most comprehensive model registry in the ecosystem (token limits, edit formats, thinking support, weak models for 200+ models). We read it as a data source; we do not couple our code to its classes. When a future `OpenCodeEngine` ships it calls the same `resolve("executor")`; only the engine implementation changes.

## Module shape — single front door

`core/config/model_registry.py` is **the** entry point: `resolve(role, workspace) → CallParams`, where `CallParams` carries *everything* about a model for a role (id, budget, generation params, weak model, edit-format metadata). It internally reuses `role_models.py` for the proven model-ID + budget resolution and adds the generation-param + weak-model + Aider-metadata layers on top. All call sites import `resolve()` from `model_registry`. `role_models.py` stays as an internal implementation detail (folded in fully by a later cleanup BL). One function to call in code; one resolved object (`policy_applied`) to read in logs.

---

## Architecture: layered resolution (pure function, not a class tree)

```
Aider metadata           ← Layer 0: read from aider.models.Model at resolve-time (lazy import)
    │                       max_tokens, edit_format, weak_model — Aider is a data source
    ↓
role_models.py           ← Layer 1: existing per-role model ID + budget tokens (reused, not rewritten)
    │
    ↓
role defaults (dicts)    ← Layer 2: mcp-coder per-role generation-param defaults (e.g. temperature)
    │
    ↓
env overrides            ← Layer 3 (P9-012): MCP_CODER_<ROLE>_* generation-param env vars
    │
    ↓
runtime overrides        ← Layer 4+ (future): host-set, AI-suggested, escalation
```

**Resolved config = merge down the chain, higher layer wins.** The resolver is a **pure function** — `resolve(role, workspace, overrides) → CallParams` — not a class hierarchy. Per-role defaults are plain data (dicts keyed by role), which keeps the system flat and trivial to read in both code and tests. Each resolved field carries provenance so `policy_applied` can show *where* a value came from.

---

## `CallParams` — the resolved output

```python
@dataclass
class CallParams:
    # Identity + budget (from role_models.py — already implemented today)
    model: Optional[str] = None
    budget_tokens: Optional[int] = None      # per-role cap (resolve_role_budget_tokens)

    # Generation params (P9-012)
    reasoning_effort: Optional[str] = None   # "none"|"low"|"medium"|"high" — litellm portable
    thinking_budget: Optional[int] = None    # Anthropic-only escape hatch (budget_tokens)
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    extra_params: dict = field(default_factory=dict)  # raw passthrough for provider-specific kwargs
    drop_params: bool = True                 # always True — silently drops unsupported params
    weak_model: Optional[str] = None         # resolved weak model (commit msgs + summarization)

    # Prompt settings (future)
    system_prompt_prefix: Optional[str] = None   # prepended to Aider's system prompt (executor)
    system_prompt_override: Optional[str] = None # full replacement (non-Aider models only)
    edit_format: Optional[str] = None            # overrides Aider registry default

    # Metadata (read-only, populated from Aider registry)
    model_max_tokens: Optional[int] = None       # Aider's known context window

    # Audit provenance — per-field source for policy_applied
    sources: dict = field(default_factory=dict)  # {"reasoning_effort": "env", "weak_model": "registry_default", ...}
```

`CallParams` is the **one resolved object** both paths consume. `model` + `budget_tokens` come from the existing `role_models.py` layer; generation params + weak model are the new layers. Prompt settings and `model_max_tokens` are defined now so the shape is final, but wired later.

**Milestone split:**
- **P9-011** — unify the helper path onto `LlmGateway`, create `model_registry.resolve()` returning `CallParams` (wrapping `role_models` for id/budget), no generation-param behaviour yet. Pure refactor + skeleton.
- **P9-012** — generation-param env vars, weak-model resolution, wire `extra_params`/litellm kwargs on both paths, attach `policy_applied` to trace events. This is what unlocks thinking-token verification.

---

## litellm's abstraction layer (what we rely on)

litellm v1.81+ handles the translation from our unified params to provider-specific wire format. Our registry sits entirely on top of it — we never write provider-specific code.

**`reasoning_effort` → translated by litellm automatically:**

| Provider | Wire format |
|----------|------------|
| Anthropic Claude 3.7+ | `thinking: {type: "enabled", budget_tokens: ~N}` |
| Anthropic Opus 4.6 | `thinking: {type: "adaptive"}` |
| Gemini 2.0+ | `thinkingConfig: {thinking_level: "high"}` |
| OpenAI o-series | `reasoning_effort` (native passthrough) |
| Deepseek R1 | `reasoning_effort` |
| Ollama / open-source | not supported → `drop_params=True` drops it gracefully |

**`extra_params` — raw passthrough for provider-specific kwargs:**  
`top_k` (Anthropic/Ollama), `repetition_penalty` (vLLM/HuggingFace), `num_ctx` (Ollama context window), `mirostat` (Ollama sampling), etc. Set via `MCP_CODER_<ROLE>_EXTRA_PARAMS='{"top_k": 40}'`.

**`drop_params=True` is always applied** — same `CallParams` works across Claude, Gemini, Llama, and a custom model on Render without crashing when a param is unsupported.

---

## Logging: `policy_applied` on every trace event

A key output of the registry is **auditability**. After resolving `CallParams`, we attach a `policy_applied` sub-object to each `backend_llm_call` and `llm_call` trace event:

```json
{
  "event_type": "backend_llm_call",
  "model": "anthropic/claude-sonnet-4-5",
  "policy_applied": {
    "role": "executor",
    "reasoning_effort": "high",
    "max_tokens": 64000,
    "source": "env_override"
  },
  ...
}
```

This closes the audit loop: the proxy shows *what was sent* (`proxy_llm_call.raw_request`); the trace shows *why* (`policy_applied`, including per-field `sources`). Phase 9's capture infrastructure is only fully useful once this field exists — which is why P9-012 belongs in Phase 9.

---

## Per-role defaults (generation params)

Model ID env vars are the existing `role_models.py` ones (`AIDER_MODEL`, `MCP_CODER_CONTEXT_BUILDER_MODEL`, `MCP_CODER_REVIEW_MODEL`, `MCP_CODER_CRITIC_MODEL`). The registry adds generation-param defaults on top:

| Role | Model ID source | Generation-param default |
|------|-----------------|--------------------------|
| `executor` | `AIDER_MODEL` | edit_format from Aider registry; thinking off |
| `context_builder` | `MCP_CODER_CONTEXT_BUILDER_MODEL` → executor | temperature 0.2 |
| `architect` | `AIDER_MODEL` | same as executor |
| `spec_validation` | `AIDER_MODEL` | temperature 0.1 |
| `spec_review` | `MCP_CODER_REVIEW_MODEL` → executor | temperature 0.0 |
| `workspace_summarizer` | `MCP_CODER_CONTEXT_BUILDER_MODEL` → executor | smaller max_tokens |

---

## Aider as data source: borrow vs inherit

**Borrow (correct):**
```python
def _aider_defaults(model_id: str) -> dict:
    from aider.models import Model   # ← lazy import, isolated
    m = Model(model_id)
    return {"max_tokens": m.max_tokens, "edit_format": m.edit_format}
```

**Inherit (wrong — creates tight coupling):**
```python
class ExecutorConfig(aider.models.Model):  # ← never do this
    ...
```

`model_registry.py` has **zero Aider imports at module level**. Aider is only touched inside `_aider_defaults()`. Swapping the execution engine never requires touching the registry. Role defaults are plain dicts, not subclasses — no class hierarchy to maintain.

---

## Prompt policy layer (future — not P9-011/012)

A separate future concern: controlling *what we say* to the model, not just *how we configure the call*.

**Executor prompt settings:**
- `model.system_prompt_prefix` → prepend mcp-coder context to Aider's system prompt
- `Coder.create(edit_format=...)` → override edit format for non-registry models
- `coder.gpt_prompts` swap → full replacement (only for completely custom models)

**Helper prompt settings:**
- Helpers own their prompts entirely — no Aider coupling needed
- Can optionally import Aider prompt strings as *inspiration* but not as inheritance
  - e.g. `from aider.coders.ask_prompts import AskPrompts; base = AskPrompts().main_system`

**When this matters:** switching executor to a model not in Aider's registry, or adding global mcp-coder-specific instructions to every delegation. Neither applies today.

---

## Environment variable map (existing kept, new added)

| Var | Role | Handled by | Milestone |
|-----|------|-----------|-----------|
| `AIDER_MODEL` / `MCP_CODER_MODEL` | executor + fallback for all | `role_models.py` → `models.py` | shipped |
| `MCP_CODER_CONTEXT_BUILDER_MODEL` | context_builder | `role_models.py` | shipped |
| `MCP_CODER_REVIEW_MODEL` | review | `role_models.py` | shipped |
| `MCP_CODER_CRITIC_MODEL` | critic | `role_models.py` | shipped |
| `MCP_CODER_<ROLE>_BUDGET_TOKENS` | any | `role_models.py` | shipped |
| `MCP_CODER_<ROLE>_REASONING_EFFORT` | any | `model_registry.py` | **P9-012** |
| `MCP_CODER_<ROLE>_THINKING_BUDGET` | any | `model_registry.py` | **P9-012** |
| `MCP_CODER_<ROLE>_TEMPERATURE` / `_TOP_P` / `_MAX_TOKENS` | any | `model_registry.py` | **P9-012** |
| `MCP_CODER_<ROLE>_EXTRA_PARAMS` (JSON) | any | `model_registry.py` | **P9-012** |
| `MCP_CODER_<ROLE>_WEAK_MODEL` | any | `model_registry.py` | **P9-012** |

`model_registry.resolve()` calls the existing `role_models` functions for `model` + `budget_tokens`; new vars layer on top. The registry is an additive front door, not a replacement.

---

## Weak model — what it is and how to control it

**What Aider uses it for:** Exactly two internal tasks, both cost-optimized:
1. **Commit message generation** — `main_model.commit_message_models()` returns `[weak_model, main_model]`
2. **Chat history summarization** — `ChatSummary([main_model.weak_model, main_model])` compresses `done_messages` when context window fills

**How Aider selects it:** The `weak_model_name` field in Aider's model registry. If `None`, the model falls back to **itself** (same model handles cheap tasks — can be expensive):

| Model | Aider default weak_model |
|-------|-------------------------|
| `anthropic/claude-sonnet-4-5` | *self* (`weak_model_name = None`) — Sonnet for commit msgs! |
| `openai/gpt-4o` | `gpt-4o-mini` |
| `openai/gpt-4o-mini` | *self* |

**Key issue:** Claude Sonnet with `weak_model_name = None` means Sonnet handles every commit message and context window summarization internally. This is correct but expensive. We may want to override with a cheaper model.

**How to override:** Pass `weak_model=<name>` to `Model()` constructor:

```python
from aider.models import Model
m = Model("anthropic/claude-sonnet-4-5", weak_model="anthropic/claude-3-5-haiku-latest")
m.weak_model.name   # → "anthropic/claude-3-5-haiku-latest"
```

### Registry value: filling the gap with defaults

This is a **canonical example of why the registry exists**. Aider leaves many strong models with `weak_model_name = None` → they use *themselves* for cheap tasks (commit messages, summarization). That is wasteful. The registry fills this gap with a sensible default, so the user gets good behaviour out of the box **without configuring anything**.

**Resolution chain for weak model:**

```
MCP_CODER_<ROLE>_WEAK_MODEL env var          ← explicit user override (highest)
  └── registry default weak-model map         ← NEW: fills Aider's gaps
        └── Aider's weak_model_name            ← used when it is NOT self
              └── self (last resort)           ← only if registry has no mapping
```

**Default weak-model map (provider-family heuristic):**

| Strong model family | Registry default weak model |
|---------------------|----------------------------|
| `*claude-sonnet*`, `*claude-opus*` | `anthropic/claude-3-5-haiku-latest` |
| `*gpt-4o*`, `*gpt-4.5*`, `*gpt-5*` | `openai/gpt-4o-mini` |
| `*gemini*-pro*`, `*gemini-2.5*` | `gemini/gemini-2.0-flash-lite` |
| `openrouter/anthropic/*` | `openrouter/anthropic/claude-3.5-haiku` |
| `openrouter/openai/*` | `openrouter/openai/gpt-4o-mini` |
| `openrouter/google/*` | `openrouter/google/gemini-2.0-flash-lite-001` |
| anything else | leave Aider's choice (self) |

The map is intentionally small and provider-keyed. When Aider already has a non-self weak model (e.g. `gpt-4o → gpt-4o-mini`), we keep it. When in doubt, we leave Aider's choice — never *worse* than today.

**Important distinction:** Weak model is *within-delegation* cost optimization (commit + summarize). It has nothing to do with escalation (switching to a *smarter* model on retry). These are orthogonal concerns.

---

## Model tiers and classes — future (BL-515)

This is a separate concern from generation params. The idea: assign every model a tier so the outer loop can escalate automatically.

```
Tier 0: nano      ← gpt-4o-mini, haiku, flash-lite, gemini-flash-8b
Tier 1: balanced  ← claude-sonnet, gpt-4o, gemini-flash, deepseek-chat
Tier 2: powerful  ← claude-opus, gpt-4.5, gemini-pro
Tier 3: thinking  ← claude-opus thinking, o3, gemini-2.5-pro
```

**Use cases:**
- **Escalation (BL-514):** executor starts at configured tier; on repeated failure → escalate one tier
- **Cost budgeting:** host sets `max_tier: 1` → never use Tier 2+ for this delegation
- **Weak model selection:** automatically pick Tier 0 as weak model for Tier 1+ models when not in Aider registry
- **Helper sizing:** spec_validation at Tier 1, workspace_summarizer at Tier 0, etc.

**What needs building (BL-515):**
- `ModelTier` enum + tier assignment dict (covers all models in `openrouter_models.py` + common direct models)
- `get_tier(model_id) → ModelTier`
- `best_model_for_tier(tier, preferred_provider=None) → model_id` — for runtime escalation
- Integration with `resolve()` — `CallParams.tier` field + escalation-aware resolver

**Why deferred:** Tier assignments require research and ongoing maintenance as models release. Phase 9 proxy already captures `model` in every trace event — we can derive tier post-hoc for now. Phase 10 outer-loop work (BL-321) is the right time to build this properly.

---

## Evolution stages (BL-511..BL-514)

### Stage 1 — Env-controlled generation params (Phase 9, BL-511) ✦ THIS PHASE

Split into two milestones:
- **P9-011** — remove the legacy direct-`Model()` helper path (route `workspace_summarizer` + `spec_review` through `LlmGateway`); create `core/config/model_registry.py` with `CallParams` + `resolve(role, workspace)` wrapping `role_models` for id/budget. Refactor + skeleton, behaviour-neutral apart from the new uniform `llm_call` logging for migrated helpers.
- **P9-012** — per-role generation-param env vars, weak-model resolution (incl. default-fill map), wire `model.extra_params` (executor) + litellm kwargs (gateway), attach `policy_applied` (with per-field `sources`) to `backend_llm_call` and `llm_call`.

### Stage 2 — Host-set policy (BL-512, future)

`delegate_to_agent` call includes a `model_policy` block. Overrides env layer for that delegation.

### Stage 3 — AI-suggested parameters (BL-513, future)

Pre-delegation analysis suggests params based on task complexity. Logged as `policy_suggestion` trace event.

### Stage 4 — Dynamic escalation (BL-514, future)

Outer-loop controller mutates active policy mid-delegation (retry exhausted → larger model, critic reject → more thinking, cost cap → downgrade).

---

## Precedence summary (all stages)

```
runtime call kwarg (Stage 4 escalation)
  └── host-set policy block (Stage 2)
        └── AI-suggested policy (Stage 3)
              └── MCP_CODER_<ROLE>_* env vars (Stage 1)
                    └── RoleConfig defaults (mcp-coder layer)
                          └── AiderModelInfo defaults (Aider registry)
```

---

## Open questions (Phase 9 master session — settled)

- ✅ `reasoning_effort` is the portable primary knob; `thinking_budget` is Anthropic escape hatch
- ✅ `drop_params=True` always — safe cross-model default
- ✅ Aider = permanent metadata foundation for all roles; not a coupling risk
- ✅ `extra_params` JSON env var for provider-specific passthrough
- ✅ `policy_applied` attached to trace events — closes the audit loop
- ✅ `policy_applied` is a **top-level** trace field on `backend_llm_call` + `llm_call` (decided + shipped in P9-012; carried via `model_policy_var` contextvar to avoid `record_*` signature churn).
- ⬜ Do we keep `AIDER_MODEL` as fallback for all unspecified roles or create explicit per-role vars? (Recommendation: keep shared fallback for now)
