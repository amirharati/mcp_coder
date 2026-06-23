# Delegation viewer — visual design principles

**Scope:** applies to `tools/delegation_viewer.html` and any future viewer extensions across Phase 9+.  
**Status:** living reference — update when a new pattern is established, not when one is merely proposed.

---

## Core philosophy

> The viewer is a **read-only narrative** of what happened. The reader should be able to skim the top level and understand the outcome in 5 seconds, then drill in only as deep as needed.

Three rules that override everything else:

1. **No raw JSON blobs.** `JSON.stringify(val, null, 2)` is never an acceptable final rendering. Every object renders as a `kv-table`; every array of strings renders as chips; long strings render in a capped, scrollable `<pre>`.
2. **All data present, most data hidden.** Every field should be reachable by clicking, but only primary fields should be visible without any interaction.
3. **Clear boundaries.** Every distinct logical unit (stage, call, capture, field group) has a visible border or background separation. The reader should never have to guess where one thing ends and the next begins.

---

## Visual hierarchy (three tiers)

### Tier 1 — always visible (no click required)
- Stage header: name, direction arrow, status badge, timing chip, token chip
- Delegation card header: id, model, duration, task preview, success/fail badge

### Tier 2 — visible when unit is open (one click)
- Content summaries: brief text, file lists as chips, model identity
- Token counts, duration breakdown
- Short previews (first ~200 chars) of sent/received content

### Tier 3 — visible when explicitly expanded (second click / nested details)
- Full prompt body (scrollable `<pre>`, max-height 200px)
- Full response body
- Raw HTTP captures (proxy JSON, backend JSON)
- Full `kv-table` for objects with many keys

**Rule:** a user debugging a delegation should only need Tier 2 for most investigations. Tier 3 exists for deep audits.

---

## Color system

| Purpose | CSS variable / color | Usage |
|---|---|---|
| → Sent direction | `#6eb6ff` (blue) | `pl-msg-label.sent`, request-side labels |
| ← Received direction | `#7ddb8c` (green) | `pl-msg-label.received`, response-side labels |
| Executor stage accent | `var(--accent)` | Aider step stage borders, call headers |
| Helper stage | `var(--muted)` | Spec/architect/context builder headers |
| Metadata / secondary | `var(--muted)` | Timestamps, byte counts, call index |
| Success | existing `.ok` badge | |
| Failure / error | existing `.fail` badge | |
| Pair: dual capture | `#7ddb8c` (green) | ev-pair-badge.dual |
| Pair: one capture only | `#e8b84b` (amber) | ev-pair-badge.proxy_only / .backend_only |
| Pair: no capture | `#e05c5c` (red) | ev-pair-badge.none |
| Tool call chips | `rgba(255,200,100,0.08)` bg + amber text | `.pl-tool` |
| Helper LLM chips | neutral bg | context_builder, architect, etc. |

---

## Layout patterns

### Cards
Every distinct unit is a card: `border: 1px solid var(--border); border-radius: 6px; overflow: hidden`.  
Cards may nest (stage card → call sub-card → capture detail). Max nesting depth: 3.

### Stage headers
Always flex row: `[arrow] [label] [flex-spacer] [chips] [toggle ▾]`.  
Clicking anywhere on the header toggles the body.  
Default state: **open** for executor stages (Aider steps), **closed** for pipeline-setup stages (spec validation, context builder, etc.).

### Key-value tables (`.kv-table`)
```
key   │ value
──────┼────────────────
task  │ Build a CLI tool for…
model │ claude-sonnet-4
```
- Key column: monospace, muted color, `min-width: 120px`, `white-space: nowrap`
- Value column: normal weight, word-break allowed
- For nested objects: recurse into a nested `kv-table` (max depth 2; beyond that show `{N keys}` chip)
- For arrays of strings: render as inline chips, not bullet list

### Direction rows (sent / received)
```
▸ → Sent          [collapsible — default closed]
  [scrollable pre, max-height 160px]

▸ ← Received      [collapsible — default closed]
  [scrollable pre, max-height 160px]
```
Direction label color follows the color system above.  
Thinking blocks (if present) appear as a third row: `◈ Thinking`, color `#b48eff` (purple).

### Scrollable pre
```css
pre.scrollable { max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
```
All `<pre>` in the viewer should apply this — never let a pre grow unbounded.

### Chips
Short scalar values (file names, models, roles, tool names) render as `<code class="chip">`. Chips wrap naturally.  
File chips include a "copy path" secondary button (already in card template).

### Token chips
Inline in stage headers and call headers:
```
[12.4k in] [1.2k out] [340 thinking]
```
Show only non-zero values. If total > 10k, use `k` suffix. Color: muted by default; accent if thinking > 0.

### Timing chips
```
[1.8s]
```
Single chip in stage header showing `timing_ms / 1000` rounded to 1 decimal. Omit if < 50ms or not available.

---

## Spacing

| Context | Value |
|---|---|
| Gap between stages in pipeline | `0.35rem` |
| Padding inside stage body | `0.6rem 0.8rem` |
| Gap between call sub-cards | `0.4rem` |
| Padding inside call header | `0.35rem 0.6rem` |
| Padding inside sent/received rows | `0.25rem 0.6rem` |

---

## What NOT to do

- ❌ `JSON.stringify(val, null, 2)` anywhere in final rendered output
- ❌ Unbounded `<pre>` (no max-height)
- ❌ Flat list of events grouped only by type label (e.g., "all proxy events", "all backend events") — group by logical step instead
- ❌ Filter chips that split two views of the same event (e.g., proxy-only vs backend-only filter hides paired context)
- ❌ Showing all fields at tier 1 — large fields (prompt bodies, raw HTTP) must be tier 3
- ❌ Monospace font for non-code content (task descriptions, response text should use body font)
- ❌ Hard-coded pixel widths for responsive content

---

## Reference implementations in codebase

| Pattern | Where it's implemented |
|---|---|
| `kv-table` | `tools/delegation_viewer.html`, `renderValue()` function |
| Scrollable `<pre>` | `delegation_viewer.html` CSS: `pre { max-height: 200px }` |
| Token bar | `renderTokenBar()` in delegation_viewer.html |
| Pair badge (dual/proxy_only/backend_only) | `.ev-pair-badge` CSS + `renderEventSummary()` |
| Chip with copy button | `.chip` CSS + `[data-copy]` listener |
| Field hide/show | `hiddenFields` Set + `[data-hide-field]` buttons |
| Session grouping | `renderList()` + `groupBySessions` toggle |
