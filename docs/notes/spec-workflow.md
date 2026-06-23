<!--
  STEWARDSHIP — primary spec workflow note. See docs/VISION_DOCS.md.

  - Purpose: current workflow contract for planning/master sessions, worker sessions, and review/implement modes.
  - Source lineage: spec-based-development.md + spec-review-loop.md.
-->

# Spec workflow

**Status:** Current workflow note — reflects the shipped spec-driven worker model and `review`/`implement` behavior.  
**Related docs:** [PHASE1_MVP.md](../PHASE1_MVP.md), [TASK_SPEC_TEMPLATE.md](../TASK_SPEC_TEMPLATE.md), [spec-based-development.md](./archive/spec-based-development.md), [spec-review-loop.md](./archive/spec-review-loop.md).

---

## Purpose

This note explains the current spec-driven workflow in one place:

- how planning/master sessions hand work to worker sessions,
- how local task specs are used in this repo,
- how consumer repos use spec-driven delegation,
- and how `mode=review` differs from `mode=implement`.

## Current workflow in this repo

### Master/worker split

| Role | Responsibility |
|---|---|
| **Planning / master session** | Define scope, create or refine task spec, update PM/vision/backlog docs |
| **Worker session** | Implement only what the local task spec defines, then fill `§ Results` |

This separation is one of the most important workflow constraints in the repo.

### Local spec lifecycle

At a high level:

1. planning/master session agrees scope,
2. a task spec is created locally under `docs/tasks/`,
3. a worker implements from that spec only,
4. the worker reports results back into the same spec,
5. planning/master updates PM/backlog/vision docs as needed.

### Why this model exists

The source notes made the motivation explicit:

- bounded context for the worker,
- reproducible handoff across sessions,
- less need to paste whole chat history,
- clearer ownership of implementation vs PM/vision updates.

## Product workflow in consumer repos

The shipped experiment generalizes the same idea:

- an epic/task spec describes bounded work,
- `delegate_to_agent` acts on that spec,
- reports capture outcome,
- and the planner remains responsible for deciding the next step.

The point is not “prompt the worker better.” The point is:

- bounded context,
- explicit contract,
- reproducible handoff,
- and easier post-hoc understanding of what happened.

### Workspace layout

The source notes included a concrete layout that is still useful to preserve conceptually:

```text
<workspace>/.mcp-coder/
  specs/
    epics/<epic_id>.md
    tasks/<epic>-<step>.md
    reports/<same-filename>.md
```

The important ownership split is:

| Artifact | Primary owner |
|---|---|
| epic spec | planner/master layer |
| task spec | planner/master layer |
| report | MCP/audit layer |
| repo code edits | worker/executor path |

## `mode=review` vs `mode=implement`

### `mode=review`

Use when the spec is incomplete, ambiguous, or needs worker feedback before implementation.

Expected behavior:

- worker returns questions/suggestions,
- planner revises the same task spec,
- code implementation does not happen yet.

Additional still-relevant source constraints:

- review is optional, not mandatory on every step,
- review is for spec clarity, not for loading prior code context for implement,
- greenfield/simple steps may skip review.

### `mode=implement`

Use when the spec is ready and the planner wants execution.

Expected behavior:

- worker performs the implementation,
- planner still owns validation/next-step decisions,
- read dependencies must be represented correctly in the spec/target files.

Important source constraints:

- planner verifies tests / completion, not MCP,
- implementation mode should treat missing needed files as a workflow problem, not silently guess,
- implementation outcome is not the same thing as “planner says the step is done.”

### Mode table

| Mode | Typical target files | Typical outcome |
|---|---|---|
| `review` | empty / no implementation file context | questions, suggestions, `review`-style outcome |
| `implement` | edit paths + read deps | success / failed / needs_input / blocked variants |

## Read-deps and file contract

One of the most important operational rules:

> Files needed for understanding prior work or imports must be included intentionally, not guessed implicitly.

That means the workflow should preserve:

- explicit read vs edit intent,
- correct file lists,
- and post-run awareness of unexpected file touches or scope drift.

### Read-deps checklist preserved from the source note

- task specs should distinguish **Edit** vs **Read**
- prior-step APIs should appear in **Read** when later steps depend on them
- review mode does not replace implement-time read context
- unexpected file touches should be interpreted as a signal to refine the contract

## Current shipped workflow guarantees

| Guarantee | Status |
|---|---|
| Spec as bounded contract | shipped |
| Review-before-implement mode | shipped |
| Master/worker separation | shipped workflow convention |
| Local worker-result capture in the spec | current repo workflow |
| Planner-owned verification after delegate | shipped workflow convention |

### Open questions from the earlier source note that still matter

Some older questions were already resolved in practice and are worth carrying forward explicitly:

| Question | Current practical answer |
|---|---|
| Mandatory spec for every delegation? | optional, but strongly encouraged for bounded multi-step work |
| Does MCP decide “done”? | no — planner/master still verifies and marks done |
| Is review automatic every step? | no — optional and situational |
| Is gatekeeper/spec lint fully complete? | no — later/backlog evolution still exists |

## Design constraints that still matter

- specs should be self-contained enough for a worker session,
- workers should not rewrite PM/vision truth unless the spec explicitly allows it,
- review mode is not the same as implementation,
- planner verification remains distinct from worker execution,
- and spec-driven workflow is a product/workflow architecture choice, not just a documentation habit.

## Deferred / future direction

These remain related but are not current workflow truth:

| Theme | Direction |
|---|---|
| Bigger workflow cadence | polish/refactor/document/digest style turns |
| More automated gates | additional pre/post workflow checks |
| Richer product spec flows | further consumer-repo evolution beyond the current experiment |

## Coverage notes

This note intentionally preserves:

- the master/worker split,
- consumer-repo spec workflow shape,
- the `review` vs `implement` distinction,
- read-deps / file-contract discipline,
- and the “planner verifies, worker executes” rule.

The older source notes still contain richer phase-era rationale and examples, so they should remain until we decide this note fully covers the still-relevant material.

## Legacy source notes

This note consolidates the current workflow layer from:

- [spec-based-development.md](./archive/spec-based-development.md)
- [spec-review-loop.md](./archive/spec-review-loop.md)

After comparison, one or both of those may become legacy/supporting notes if this file fully covers their still-relevant content.
