# Delegation viewer — design principles v2

**Supersedes:** `viewer-design-principles.md` (v1, pipeline/card era — keep for historical reference)  
**Scope:** `tools/delegation_viewer.html` + `core/cli/delegation_view_enrich.py` Phase 9+  
**Status:** living reference — update when a new pattern is established

---

## Core mental model

A delegation is a series of **boundary crossings** — something sent from one system to another.
Every event is either:

- A **→ send** — one system hands something to another
- A **← receive** — a response comes back
- A **one-way action** — something happens with no response (file write, shell exec)

Boundaries can be **real** (atomic, directly observable) or **virtual** (a container whose → and ← wrap child events that happen in between).

The viewer is a flat, chronological table. Every row is one boundary crossing. Reading top-to-bottom = reading the delegation in time order.

---

## Canonical event model

### Boundary hierarchy

```
host→mcp                        →  real      task enters the system
  mcp.spec_validation →         →  real      MCP sends task to spec_validation LLM
  mcp.spec_validation ←         ←  real      spec_validation LLM responds (pass/block)
  mcp.architect →               →  real      MCP sends context to architect LLM
  mcp.architect ←               ←  real      architect LLM responds (plan)
  mcp.context_builder →         →  real      MCP sends raw context to context_builder LLM
  mcp.context_builder ←         ←  real      context_builder LLM responds (assembled context)
  mcp→executor                  →  virtual   MCP sends compiled prompt to executor (Aider)
    executor.step{N}                divider   step N starts (scope_check / lint_retry / …)
    executor→llm{N.M}           →  real      executor sends prompt to LLM (call M of step N)
    llm→executor{N.M}           ←  real      LLM responds to executor
    executor.file_write         →  real      executor writes file (one-way, no ←)
    executor.shell              →  real      executor runs shell command (one-way, no ←)
  executor→mcp                  ←  virtual   executor done, result returned to MCP
mcp→host                        ←  real      result exits the system
```

### Real vs virtual

| Boundary | Real / Virtual | Why |
|---|---|---|
| `host→mcp` | real | no children — task text is the full event |
| `mcp.spec_validation →/←` | real | LLM call is atomic from MCP's view |
| `mcp.architect →/←` | real | LLM call is atomic from MCP's view |
| `mcp.context_builder →/←` | real | LLM call is atomic from MCP's view |
| `mcp→executor` | virtual | the entire executor run happens between → and ← |
| `executor→mcp` | virtual | closing side of the above |
| `executor.step{N}` | divider | groups llm calls + file writes inside a step |
| `executor→llm{N.M}` | real | one HTTP round-trip |
| `llm→executor{N.M}` | real | the response of the above |
| `executor.file_write` | real | one-way, no response |
| `executor.shell` | real | one-way, no response |
| `mcp→host` | real | no children — output text is the full event |

**Virtual boundary detail panel:** shows a summary of children (aggregated tokens, duration, list of child events).  
**Real boundary detail panel:** shows the full fields of that one event.

### Complete log entry → canonical event mapping

| Raw log entry | Key discriminator | Maps to |
|---|---|---|
| delegation record `mcp_request` | — | `host→mcp` |
| delegation record `response_to_cursor` | — | `mcp→host` |
| `compile_event` stage=`validation_input` | stage | `mcp.spec_validation →` |
| `compile_event` stage=`validation_output` | stage | `mcp.spec_validation ←` |
| `llm_call` role=`spec_validation` | role | folded into `mcp.spec_validation →/←` detail |
| `compile_event` stage=`architect_input` | stage | `mcp.architect →` |
| `compile_event` stage=`architect_output` | stage | `mcp.architect ←` |
| `llm_call` role=`architect` | role | folded into `mcp.architect →/←` detail |
| `compile_event` stage=`builder_input` | stage | `mcp.context_builder →` |
| `compile_event` stage=`builder_output` | stage | `mcp.context_builder ←` |
| `compile_event` stage=`mechanical_brief` | stage | folded into `mcp.context_builder` detail |
| `llm_call` role=`context_builder` | role | folded into `mcp.context_builder →/←` detail |
| `compile_event` stage=`final_executor_prompt` | stage | `mcp→executor` (partial — task string only) |
| `action` kind=any | kind | `executor.step{N}` divider row |
| `llm_call` role=`executor`, `executor_turn=True` | role+flag | folded into `executor.step{N}` detail |
| `proxy_llm_call` + `backend_llm_call` (matched by step+call index) | step_index+call_index | `executor→llm{N.M}` + `llm→executor{N.M}` (one merged row) |
| `proxy_llm_call` unmatched | — | shown as `executor→llm` with partial data |
| `backend_llm_call` unmatched | — | shown as `llm→executor` with partial data |
| `tool_call` tool=`file_write` | tool | `executor.file_write` |
| `tool_call` tool=`shell_exec` | tool | `executor.shell` |
| `trace_header` | — | skip — version metadata only |

### Step kinds (from `action.kind`)

| kind | Meaning |
|---|---|
| `scope_expansion_check` | executor checked if it needs more files before proceeding |
| `lint_retry` | executor hit a lint error and is retrying the step |
| `auto_confirm` | executor auto-confirmed a change |
| `executor_stall` | executor got stuck / needed intervention |

### Note on `mcp→executor` completeness

`compile_event stage=final_executor_prompt` only captures the **task string** (small). The actual full context window Aider received (system prompt, target files, session history, RAG context) is only observable via `executor→llm{1.1}.prompt_body` — the first LLM call's full prompt body. The detail panel for `mcp→executor` should note this and link to `executor.llm{1.1}`.

---

## Middleware architecture (not UI-hardcoded)

The canonical event model must be computed in **Python** (`core/cli/delegation_view_enrich.py`), not in JavaScript. The UI receives a structured list of `ViewEvent` objects and renders them without knowing anything about raw log format.

### `ViewEvent` structure

```python
@dataclass
class ViewEvent:
    id: str              # e.g. "executor.llm.1.1", "mcp.architect.out"
    name: str            # display name: "executor→llm{1.1}", "mcp.architect ←"
    direction: str       # "→" | "←" | "·" (one-way)
    scope: str           # "host", "mcp", "executor"
    is_virtual: bool     # True if has children (detail = summary of children)
    is_boundary: bool    # True if it's a system boundary crossing
    is_divider: bool     # True if it's a step separator row (executor.step{N})
    timestamp: str | None
    seq: int             # sort order (chronological)
    summary: str         # one-line human summary
    detail: dict         # full fields for detail panel
    children: list[ViewEvent]  # non-empty only for virtual events and step dividers
```

### Mapper responsibilities (`_build_view_events`)

1. Consume all raw trace lines once, in order
2. Group proxy+backend pairs by `(step_index, call_index)` → merged into one `executor→llm` + `llm→executor` pair
3. Group actions by `step_index` → `executor.step{N}` dividers
4. Fold `llm_call role=executor` into the corresponding step detail
5. Map `compile_event` stages to named phase boundary events
6. Fold `llm_call` roles (architect, context_builder, spec_validation) into their phase detail
7. Synthesize `host→mcp` and `mcp→host` from delegation record fields
8. Return `list[ViewEvent]` in chronological order

### UI contract

The JS receives `enriched.view_events: ViewEvent[]` and:
- Renders each as one table row (using `name`, `direction`, `summary`, `timestamp`)
- On click: populates detail panel from `detail` (real events) or summarizes `children` (virtual)
- Step dividers render as full-width labeled separators, not clickable rows
- Never parses raw log entry types — all logic is in the mapper

---

## Display rules

### Row anatomy (flat table, left panel)

```
[delg-id]  [seq]  [dir]  [name]       [summary — fills width]   [HH:MM:SS.mmm +offset]
afa64a7    1      →      host→mcp     Phase 9 dogfood: inspect only...     23:22:30.638
afa64a7    ───────── executor.step{1} · scope_expansion_check · 46s ────────────────────
afa64a7    2      →      executor→llm{1.1}  claude-sonnet-4 · 4,445 in    23:22:42.559
afa64a7    3      ←      llm→executor{1.1}  209 out · 4.2s               23:22:46.818
```

Step divider row is full-width, visually distinct (darker bg, left accent bar), non-data.

### Detail panel (right panel on click)

**Real event** → show all fields of that event.  
**Virtual event** → show aggregate summary + list of child events with their summaries.

For `executor→llm{N.M}` + `llm→executor{N.M}` (merged pair — treated as real):
- Proxy fields: HTTP status, wire_latency_ms, raw_request, raw_response
- Backend fields: model, tokens (in/out/thinking), duration_ms, prompt_body, response_body, thinking_body

### One-line summary rules

| Event | Summary |
|---|---|
| `host→mcp` | task text (first 120 chars) |
| `mcp→host` | output_preview (first 120 chars) |
| `mcp.spec_validation →/←` | "pass" / "block: reason" |
| `mcp.architect →/←` | model · tokens |
| `mcp.context_builder →/←` | model · tokens · bytes assembled |
| `mcp→executor` | N bytes · sha256 prefix |
| `executor→llm{N.M}` | model · step N call M · N tokens |
| `llm→executor{N.M}` | N tokens out · Xms · HTTP status |
| `executor.file_write` | path · N bytes |
| `executor.shell` | command · exit_code |
| `executor→mcp` | total: N tokens · Xs |

---

## Color system

| Scope | Color | Applied to |
|---|---|---|
| host boundary | `#a78bfa` violet | `host→mcp`, `mcp→host` |
| mcp phase | `#f59e0b` amber | `mcp.*` rows |
| executor→llm (send) | `#6eb6ff` blue | `executor→llm{N.M}` |
| llm→executor (recv) | `#7ddb8c` green | `llm→executor{N.M}` |
| file / shell | `#e8b84b` gold | `executor.file_write`, `executor.shell` |
| step divider | `#334155` dark slate bg | `executor.step{N}` |
| thinking | `#b48eff` purple | thinking content |
| muted metadata | `var(--muted)` | timestamps, byte counts, seq numbers |

---

## What NOT to do

- ❌ Parse raw log entry types (`proxy_llm_call`, `backend_llm_call`, `compile_event`) in JavaScript — all mapping happens in Python
- ❌ Cards inside cards — max depth: table row → detail panel
- ❌ Grouping events by type — always chronological
- ❌ `JSON.stringify()` in rendered output — use `renderValue()`
- ❌ Unbounded `<pre>` — always `class="scrollable"` with `max-height`
- ❌ Showing `trace_header` as a row — it is version metadata only
- ❌ Showing `llm_call role=executor` as its own row — it is the step aggregate, fold into step detail

---

## Implementation plan

**Phase A — Middleware (`delegation_view_enrich.py`)**
1. Define `ViewEvent` dataclass (or typed dict)
2. Write `_build_view_events(record, trace_lines) → list[ViewEvent]` mapper
3. Add `view_events` key to `enrich_delegation_record` return dict
4. Add tests for mapper with real trace fixtures

**Phase B — UI (`delegation_viewer.html`)**
1. Replace `delegRowsHtml` to consume `view_events` instead of raw trace events
2. Render step divider rows with distinct style
3. Update detail panel to branch on `is_virtual` vs real
4. Update color system to new scope-based scheme
5. Update summary formatter to use new `summary` field from mapper

**Phase C — Cleanup**
1. Remove old `renderPipelineView`, `renderEventTimeline` (already partially done)
2. Remove old `_build_pipeline_stages` from enrich (after Phase B ships)
