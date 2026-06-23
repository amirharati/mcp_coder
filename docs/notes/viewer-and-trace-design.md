<!--
  STEWARDSHIP — primary viewer and trace design note. See docs/VISION_DOCS.md.

  - Purpose: current source for delegation viewer mental model, event mapping, and rendering rules.
  - Keep UI guidance tied to trace/event semantics, not one-off visual preferences.
  - Source lineage: viewer-design-principles-v2.md.
-->

# Viewer and trace design

**Status:** Current viewer/trace design note for `tools/delegation_viewer.html` and `core/cli/delegation_view_enrich.py`.  
**Supersedes:** [archive/viewer-design-principles-v2.md](./archive/viewer-design-principles-v2.md) and [archive/viewer-design-principles.md](./archive/viewer-design-principles.md).

---

## Purpose

This note defines how the delegation viewer should represent execution:

- the mental model for events,
- how raw trace/delegation records become view events,
- what belongs in Python enrichment vs browser rendering,
- and which UI rules keep traces readable.

## Core Mental Model

A delegation is a chronological series of **boundary crossings**.

Every event is one of:

- **send** — one system hands something to another,
- **receive** — a response comes back,
- **one-way action** — file write, shell command, state save, etc.,
- **divider/container** — a virtual grouping for child events.

The viewer is a flat chronological table. Reading top-to-bottom should explain the delegation in time order.

## Real vs Virtual Events

| Event kind | Meaning | Detail panel |
|---|---|---|
| **Real boundary** | directly observed send/receive/action | fields for that one event |
| **Virtual boundary** | container whose children happen between start/end | aggregate summary + child list |
| **Divider** | non-boundary grouping row, usually step/phase | compact summary, often non-clickable |

Virtual events help explain the shape of execution without hiding the underlying trace rows.

## Canonical Boundary Hierarchy

```text
host -> mcp                         task enters system
  mcp.phase/helper ->               helper call request
  mcp.phase/helper <-               helper call response
  mcp -> executor                   virtual boundary: executor run begins
    executor.step{N}                divider
    executor -> llm{N.M}            backend/provider request
    llm -> executor{N.M}            backend/provider response
    executor.file_write             one-way action
    executor.shell                  one-way action
  executor -> mcp                   virtual boundary closes
mcp -> host                         result exits system
```

Names may evolve as event schemas evolve, but the shape should remain: boundary crossings first, raw event type second.

## Mapping Raw Logs to View Events

Raw events should be mapped once in Python into a stable viewer model.

| Raw source | Viewer meaning |
|---|---|
| delegation request | `host -> mcp` |
| delegation response | `mcp -> host` |
| lifecycle / phase events | phase start/end or dividers |
| helper `llm_call` / compile events | helper send/receive/detail |
| final executor prompt / adapter input | `mcp -> executor` virtual boundary |
| executor actions | step dividers and one-way actions |
| proxy/backend LLM call pair | executor/provider send/receive |
| unmatched proxy/backend calls | partial provider boundary rows |
| trace header/version rows | metadata, not visible rows |

The mapping should preserve traceability back to raw records through IDs and detail fields.

## Middleware Contract

The canonical event model belongs in Python, not browser JavaScript.

`core/cli/delegation_view_enrich.py` should:

1. consume delegation record + trace lines,
2. group related raw events,
3. merge proxy/backend pairs when possible,
4. synthesize host/MCP boundary rows,
5. assign stable sequence ordering,
6. return structured `ViewEvent` records.

The browser should render the model it receives; it should not reverse-engineer trace semantics.

## ViewEvent Shape

The exact implementation can use dataclasses or typed dicts, but the conceptual shape is:

```text
ViewEvent
  id
  name
  direction
  scope
  is_virtual
  is_boundary
  is_divider
  timestamp
  seq
  summary
  detail
  children
```

### Field Intent

| Field | Meaning |
|---|---|
| `id` | stable row/detail identity |
| `name` | human label for the row |
| `direction` | send/receive/action/divider |
| `scope` | host, mcp, executor, provider, storage, etc. |
| `summary` | one-line explanation |
| `detail` | raw/structured payload for inspection |
| `children` | virtual grouping only |

## Display Rules

The viewer should remain a flat readable table:

- one event per row,
- chronological order,
- compact summary in the left pane,
- detail panel on selection,
- virtual/container rows summarize children,
- large values are scrollable/collapsed,
- raw JSON is available but not the default visual shape.

### Summary Rules

| Event | Good summary |
|---|---|
| host request | task text preview |
| mcp result | outcome/output preview |
| helper send/receive | role, model, pass/block, token/cost summary |
| context compile | bytes/refs/package summary |
| executor/provider call | model, step/call index, token counts |
| file write | path + byte/change summary |
| shell action | command + exit status |
| pause/resume/checkpoint | reason + token/state pointer |

## Color and Visual Semantics

Colors should communicate scope, not decoration:

| Scope | Intent |
|---|---|
| host boundary | user/host interaction |
| mcp phase/helper | internal orchestration |
| executor | implementation backend activity |
| provider/LLM | model request/response |
| storage/checkpoint | persistence/state updates |
| warnings/errors | outcome or risk |

The same event type should use the same visual language across delegations.

## Current Event Coverage

The viewer should be able to render:

- host/MCP request and response,
- lifecycle start/end,
- phase start/end,
- helper LLM calls,
- context compilation milestones,
- executor steps,
- backend/proxy LLM calls,
- file/shell/tool actions where available,
- supervisor pause/resume/abandon/checkpoint events,
- reviewer/classifier events where present.

If an event is valid but lacks a special renderer, it should still appear as a generic trace row rather than disappear.

## What Not To Do

- Do not parse raw trace semantics in JavaScript.
- Do not group by event type instead of time.
- Do not create nested cards inside nested cards.
- Do not render unbounded `<pre>` blocks.
- Do not show trace headers as timeline rows.
- Do not hide unmatched proxy/backend calls.
- Do not make virtual rows imply data exists that was never captured.

## Relationship to Observability

The viewer depends on the observability model:

- logs/traces must preserve stable IDs and enough provenance,
- enrichment should be deterministic and testable,
- missing capture should be shown as missing/partial rather than guessed,
- and display should help diagnose what was intended, sent, received, and persisted.

## Deferred Direction

Future viewer work may include:

- richer phase/lifecycle groupings,
- better diff/file-write previews,
- search/filter over events,
- compare mode across delegations,
- explicit context-ref rendering,
- and replay-oriented views once lean refs and retrieval corpora mature.

These are UI/product improvements, not changes to the underlying mental model.

## Legacy Source Notes

This note replaces the active role of:

- [archive/viewer-design-principles-v2.md](./archive/viewer-design-principles-v2.md)
- [archive/viewer-design-principles.md](./archive/viewer-design-principles.md)

Keep the archived notes for exact source-era event tables and implementation-plan wording.
