<!--
  STEWARDSHIP — primary model routing and policy note. See docs/VISION_DOCS.md.

  - Purpose: explain shipped model-policy behavior first, then future routing/escalation direction.
  - Source lineage: model-policy-layer.md + multi-model-roles.md.
-->

# Model routing and policy

**Status:** Current design note for shipped model policy behavior, with future routing/escalation captured separately.  
**Primary shipped anchor:** Phase 9 Stage 1 (`model_policy`, registry front door, `policy_applied` tracing).  
**Related backlog:** BL-511..BL-515, BL-162, BL-321, BL-007.

---

## Purpose

This note answers:

- how model selection and generation parameters work **today**,
- where policy is resolved,
- which layers are already shipped,
- and which multi-model or escalation ideas are still future direction.

## Current shipped reality

### One policy front door

The current system aims for a single answer to:

> For this role and this call, what model and parameters should we use?

That answer is expressed through a resolved policy/parameter shape rather than ad-hoc per-call settings.

### Current shipped pieces

| Area | Status |
|---|---|
| Role-oriented model selection | shipped |
| Central/front-door policy resolution for helper paths | shipped |
| Generation parameter handling | shipped |
| `policy_applied` audit/tracing | shipped |
| Weak-model controls/defaults | shipped |
| Host-set overrides and richer escalation layers | deferred/backlogged |

### Already-centralized inputs vs what the policy layer adds

The source design was explicit about two categories:

| Category | Current state |
|---|---|
| **Already centralized** | role-specific model IDs and role budget tokens |
| **Added by model policy / registry layering** | generation params, weak-model resolution, policy provenance, and a single resolved view of what a call should use |

### Current mental model

There are two practical model surfaces:

| Surface | Meaning |
|---|---|
| **Helper / orchestration calls** | Planner/reviewer/other owned helper paths that can use shared policy resolution cleanly |
| **Executor/backend path** | The implementation backend path, which has extra backend-specific constraints |

The policy layer should unify intent without pretending both surfaces are identical.

### Three call-path realities from the source note

The older design note distinguished:

1. **executor/backend path**
2. **owned helper path**
3. **legacy helper paths that needed cleanup/unification**

That distinction matters because one goal of the policy architecture was to eliminate ad-hoc helper call behavior and move everything toward one consistent front door.

## Resolution model

### What policy resolution should produce

The output of policy resolution is a normalized “call parameters” decision, including at least:

- model identity,
- key generation parameters,
- any meaningful policy adjustments,
- and enough trace metadata to understand what actually happened.

### Layered resolution model

The source architecture used a layered merge model:

| Layer | Role |
|---|---|
| **Registry / metadata layer** | model facts and backend-relevant metadata |
| **Role-model layer** | per-role model identity and role budget defaults |
| **Role policy defaults** | generation-parameter defaults by role |
| **Env/runtime overrides** | explicit higher-precedence overrides |
| **Future runtime policy layers** | host-set, AI-suggested, escalation-driven overrides |

The important design constraint is not the exact file layout, but the idea that resolution is:

- **pure / deterministic**,
- layered by precedence,
- and traceable.

### Resolved output shape

The source note also defined a single resolved “call params” shape that should conceptually include:

- model ID,
- role budget,
- max tokens / temperature / top-p / reasoning-style params where relevant,
- weak-model data,
- backend metadata like edit-format/max-window when needed,
- and provenance (`why did this field get this value?`).

### Why this matters

Without a shared resolution layer:

- behavior drifts by call site,
- audit trails are incomplete,
- weak/cheap model behavior is hard to reason about,
- and future escalation logic becomes scattered instead of composable.

### Audit requirement

One of the most important shipped ideas here is that every meaningful model decision should be visible in traces/logs through a `policy_applied`-style record. The source note treated that as the bridge between:

- “what was actually sent” and
- “why the system thought this was the right policy.”

## Current policy constraints

These constraints still matter:

- policy should be auditable,
- the shipped Stage 1 behavior should stay simple and predictable,
- backend-specific behavior should not leak into cross-role policy semantics,
- and future escalation should extend the model rather than replace it.

Additional constraints preserved from the source note:

- the helper path should converge toward one consistent entry point,
- backend metadata may be borrowed as data but should not define the whole policy architecture,
- and policy should remain backend-neutral at the core layer even when executor backends differ.

## Role-based routing today

The current system already assumes different roles may want different models and budgets. The important distinction is:

- **this is already partially real**, not just theoretical,
- but **full dynamic escalation and committees are not shipped**.

### Stage 1 shipped reality

The older notes split the evolution into stages. The important distinction to preserve is:

- **Stage 1 shipped**: one model/policy view per role, with auditability
- **Stage 2+ deferred**: richer escalation, runtime upgrades, and multi-model behavior

### Per-role thinking that still matters

The source documents consistently treated roles as having different cognitive and cost profiles:

- executor: heavy implementation work,
- review/spec-validation/other helpers: narrower and cheaper,
- context builders/summarizers: smaller or more constrained passes,
- future critic/polish roles: different tradeoffs again.

That conceptual separation is still relevant even if the exact default values evolve.

## Future routing and escalation

These ideas remain valuable, but should stay clearly labeled as future:

| Future layer | Meaning |
|---|---|
| **Host-set policy** | More explicit policy injection from the host/session side |
| **AI-suggested policy** | Helpers suggest parameter/model changes without blindly owning the final decision |
| **Dynamic escalation** | Retry or upgrade behavior based on failure/risk/context |
| **Model tiers/classes** | Normalize model capability buckets instead of one-off model-name logic |
| **Multi-model within a role** | Critic redo, staged escalation, or other multi-call patterns |
| **Committee / ensemble** | Deliberate multi-model voting/swarm behavior |

### Stage model from the source notes

| Stage | Meaning |
|---|---|
| **Stage 1** | one model/policy view per role, fully auditable |
| **Stage 2** | multiple models within a role via escalation, policy gating, critic redo, or failed-attempt awareness |
| **Stage 3** | committee / swarm / ensemble patterns |

### Important future patterns to preserve

The older notes contained specific future ideas that should not silently disappear:

- cheap-first then strong escalation,
- policy-triggered upgrades for risky tasks,
- critic-driven redo,
- failed-attempt-aware stronger retries,
- post-executor polish passes,
- and eventual committee/swarm behavior.

## Shipped vs future summary

| Topic | Current state |
|---|---|
| Per-role model thinking | current foundation |
| Shared policy resolution | shipped core |
| Policy tracing / audit | shipped core |
| Weak-model controls | shipped core |
| Dynamic escalation | future |
| Committee/swarm behavior | future |

## Relationship to older notes

This note is the **primary current source** for model-policy reality, but it is intentionally shorter than the older source notes and therefore should preserve the following coverage classes:

- shipped Stage 1 policy/registry behavior,
- the two-surface split (helper vs executor),
- the layered resolution idea,
- the audit/provenance requirement,
- and the staged future routing/escalation roadmap.

Older/supporting notes still help for context:

- [model-policy-layer.md](./archive/model-policy-layer.md) holds the detailed Phase 9-era architecture and stage framing
- [multi-model-roles.md](./archive/multi-model-roles.md) holds longer-horizon multi-model and committee ideas

Those older notes should only be archived once this note fully captures the still-relevant shipped/future split.
