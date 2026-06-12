# T-04: Context compiler deep-dive

**Goal:** Understand exactly what the executor (Aider) sees and why. By the end you can run `mcp-coder inspect-context` and `mcp-coder delegate`, read every field (including the full prompt and post-delegate artifacts), and confidently adjust specs or config when the executor misses context or costs too much.

**Why this matters:** the executor cannot see your Cursor chat. What it gets is a compiled `ContextPackage` — a tiered, budgeted, optionally LLM-enriched prompt. Understanding how it's built is the difference between "why did the executor change the wrong file?" and "I know exactly what I need to fix in the spec."

**Prerequisites:** T-01 (one delegation ran) and T-03 (spec structure).

**Estimated time:** 25–35 min read; +20 min if you run the hands-on demos.

**How to use this tutorial:** it's one of the big ones. First pass: read §1–§3 + the diagrams, skim the rest. Second pass: run **Try it** demos §0–§7 (dry-run). Third pass: **§8** (helper LLMs) + **§9** (full Aider prompt + optional round trip). §9 Step 4 / §0 Bonus need provider credentials (T-01).

---

## 0. Scratch playground (for all "Try it" demos)

Every demo below uses the same throwaway workspace at `/tmp/ctx-demo`. Copy-paste the setup block once (safe to re-run — overwrites demo files, does **not** delete the folder). When finished, remove from a directory **outside** `$DEMO`: `rm -rf /tmp/ctx-demo` (do not run `rm -rf` while your shell is `cd`'d into the demo).

```bash
export DEMO=/tmp/ctx-demo
mkdir -p "$DEMO/src" "$DEMO/.mcp-coder/specs/tasks"
cd "$DEMO"
git init -q 2>/dev/null || true

# Small read dependency (well under the 8 KB excerpt threshold)
cat > src/api.py <<'EOF'
def get_user(user_id: int) -> dict:
    """Fetch a user record."""
    return {"id": user_id, "name": "demo"}
EOF

# Big file (> 8 KB) — will trigger the excerpt engine
python3 - <<'EOF'
lines = [f'def helper_{i}(x):\n    """Helper {i}."""\n    return x + {i}\n' for i in range(200)]
open("src/big_utils.py", "w").write("\n".join(lines))
EOF

# File the symbol scan should discover (mentions get_user, not in spec)
cat > src/consumer.py <<'EOF'
from src.api import get_user

def show(user_id):
    print(get_user(user_id))
EOF

# Edit target (empty for now) + a minimal spec (front matter = delegation contract)
touch src/cli.py
cat > .mcp-coder/specs/tasks/demo-01-cli.md <<'EOF'
---
spec_id: demo-01-cli
files_edit:
  - src/cli.py
files_read:
  - src/api.py
  - src/big_utils.py
edit_scope: discover
---

# Demo: add CLI

## Goal
Add an argparse CLI entry point that calls `get_user`.

## Constraints
- argparse only, no extra deps

## Files

### Edit
- src/cli.py

### Read
- src/api.py
- src/big_utils.py
EOF
```

**Playground pitfalls (read once):**

| Issue | Fix |
|-------|-----|
| `head: /.mcp-coder/...` or empty paths | Run `export DEMO=/tmp/ctx-demo` (or `export DEMO="$PWD"` after `cd` into the demo). Every Try it assumes `$DEMO` is set. |
| `zsh: no matches found: discover?` | Do **not** paste shell **comment** lines from the doc into zsh — especially lines with `?`. Paste only the `mcp-coder …` / `jq …` lines. |
| `zsh: unknown file attribute` on `jq` | Keep the **whole** `jq '…'` program in **single quotes** so zsh does not glob `[…]`. |
| `rg: command not found` | Use `grep -nE` instead (examples below use `grep`; `rg` is optional). |
| `.cursor/mcp.json` in `map-only` entries | Do **not** run `mcp-coder setup --local` inside `$DEMO`. Wire MCP from your real project. If already created: `rm -rf "$DEMO/.cursor"`. |
| `.aider.tags.cache.*` in `files_changed` | Aider repo-map cache under the demo tree — ignore for this tutorial; `src/cli.py` is what matters. |

### Three CLI levels (same `$DEMO`, increasing fidelity)

| Level | Command | API cost | Edits disk? |
|-------|---------|----------|-------------|
| **1 — inspect** | `mcp-coder inspect-context` | None by default (helpers opt-in) | No |
| **2 — prepare** | `mcp-coder delegate --stop-after context` | Helpers per `config.yaml` (builder on by default) | No |
| **3 — full** | `mcp-coder delegate` | Executor + helpers | Yes |

No MCP server required for any of these. Bare `mcp-coder` with no subcommand prints a hint and exits (not an error).

**Level 1 — dry-run inspect** (repeat in later sections):

```bash
mcp-coder inspect-context --workspace "$DEMO" \
  --task 'Add CLI calling `get_user` per spec' \
  --context-summary 'Demo playground; argparse CLI for get_user' \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md --pretty
```

**Level 2 — delegate-faithful prepare** (full Aider prompt, config-driven helpers, no executor):

```bash
mcp-coder delegate --workspace "$DEMO" \
  --task 'Add CLI calling `get_user` per spec' \
  --context-summary 'Demo playground; argparse CLI for get_user' \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  --stop-after context --pretty \
  | jq -r '.artifacts.executor_in.prompt' | head -40
```

**Level 1 with full prompt text** (opt-in on inspect):

```bash
mcp-coder inspect-context --workspace "$DEMO" \
  --task 'Add CLI calling `get_user` per spec' \
  --context-summary 'Demo playground; argparse CLI for get_user' \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  --include-prompt --pretty \
  | jq -r '.adapter_preview.prompt' | head -40
```

### Bonus — full delegate (Aider in + post steps out)

Requires a working executor model (same as T-01: `mcp-coder test-model`). Uses the **same** `$DEMO` workspace — you will edit `src/cli.py` on disk and get JSONL + spec report under `$DEMO/.mcp-coder/`.

Run from anywhere (credentials from your repo `.env` — T-01). Run `mcp-coder test-model` first; exit 0 required.

```bash
mcp-coder test-model
```

```bash
cd "$DEMO"
mcp-coder delegate \
  --task 'Add CLI calling `get_user` per spec' \
  --context-summary 'Demo playground; argparse CLI for get_user' \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  --pretty > /tmp/ctx-demo-delegate.json
```

What we sent to Aider:

```bash
jq -r '.artifacts.executor_in.prompt' /tmp/ctx-demo-delegate.json | head -20
```

What Aider returned:

```bash
jq '.artifacts.executor_out' /tmp/ctx-demo-delegate.json
```

MCP-shaped response + post steps:

```bash
jq '.caller_response | {success, outcome, files_changed, files_unexpected, spec_report_path}' \
  /tmp/ctx-demo-delegate.json
jq '.artifacts.post_delegate | {delegation_pipeline, scope_violations}' \
  /tmp/ctx-demo-delegate.json
cat "$DEMO/src/cli.py"
```

If `success` is false, read `artifacts.executor_out.output` and `caller_response.error_message` — the post steps (`post_gateway`, `spec_report`) still run on most failures (T-06 §2).

---

## 1. The fundamental distinction: prompt ≠ chat history

### Roles (general) vs today's stack (Cursor + Aider)

mcp-coder sits between two **roles**:

| Role | Job today | Implementation today |
|------|-----------|----------------------|
| **Host / planner** | User chat, writes specs, calls `delegate_to_agent` | **Cursor** (via `.cursor/rules/` + MCP) |
| **Executor / backend** | Edits files from a compiled prompt | **Aider** + an LLM provider |

Cursor is **not** the executor. Aider is **not** the planner. The context compiler's job is to turn planner inputs (spec, `task`, `context_summary`, optional host transcript) into what the **executor** sees — regardless of which host/backend you plug in later.

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 8, 'rankSpacing': 24}}}%%
flowchart TB
    P[Cursor planner] -->|task, spec, summary| C[mcp-coder]
    P -.->|dump: chat JSONL on disk| C
    C -->|compiled prompt + fnames| E[Aider executor]
    E -->|spec report| P
```

**There is no Cursor → Aider shortcut.** Cursor only talks to mcp-coder (MCP). With `host_transcript: dump`, mcp-coder **reads** the active Cursor chat JSONL from disk (`core/host/cursor_transcript.py`) and **attaches** it — into helper LLM prompts (builder, architect, spec validation) and, if enabled, prepended on the executor prompt in the Aider adapter. Default policy is `none`: no chat load, no attach.

The dashed line is the whole point: the executor never sees your chat unless mcp-coder loads and forwards it. Everything else arrives through the compiled `ContextPackage`.

### What the executor does and does not see

**Each `delegate_to_agent` call builds a new prompt from scratch** — picker, assemble, budget, optional builder/architect, then `coder.run(prompt)`. The executor does not “continue” mcp-coder’s memory by itself; it only sees what this compile produced (plus one exception below).

| Source | In executor prompt? | Notes |
|--------|---------------------|--------|
| **This call’s spec + `task` + `context_summary`** | Yes | Mechanical brief (always) |
| **Compiled file payloads + repo map** | Yes | Tiers from this compile |
| **Builder / architect narrative** | If enabled | Only their **output** text in `package.brief` — not their input prompts |
| **Prior delegation summaries** | Often | `builder_history` from `workspace_history.db` (last N same-spec + project rows) — **summaries only**, not full diffs or Aider transcripts |
| **Full Cursor host chat** | Only if `host_transcript: dump` | mcp-coder **reads** chat JSONL and **attaches** it — never a direct Cursor → Aider path |
| **Prior delegate’s full output / unified diffs** | No | Use `history diff` / JSONL yourself; not auto-injected |
| **Helper-LLM wire traffic** | No | Separate cheap-model calls; executor sees merged brief, not builder/architect prompts |
| **Aider in-process LLM chat** | Maybe | If the **same** `Coder` object is reused (uncommon — see below) |

**Delegate 1 → delegate 2 (same MCP session):** Call 2 still gets a **fully recompiled** package. Cross-delegate context you control is mainly **`builder_history`** (+ planner `context_summary`, optional `rag_search`). Step 1 → step 2 usually creates a **new** `Coder` because edit paths or the compiled package hash changed (`core/session/executor_cache.py`). When `executor_reused: true` in JSONL, Aider may also retain **its own** internal multi-turn chat from the previous `coder.run()` — that is a performance-cache side effect, **not** an intentional memory feature, and mcp-coder does not serialize it today.

What it **always** gets (with a spec + `context_builder` on) is a compiled `ContextPackage`:

```
package.brief          ←  layered brief (see below)
file payloads          ←  full text or excerpts, injected as fenced read context blocks
repo map               ←  def/class outlines for files not otherwise included
```

**Brief layers** (bottom → top as they appear in `package.brief`):

```
## Task / ## Context / ## Goal / ## Constraints / ## Paths   ←  mechanical brief (always)
---
## Builder brief                                            ←  helper LLM narrative (default on; disable with context_builder_llm: false)
---
## Architect plan                                           ←  helper LLM plan (opt-in; default off; architect_pass: true)
```

**Important:** `architect_pass` runs as a pipeline phase *before* `builder_llm`, but the architect plan is **merged last** — prepended above the builder + mechanical stack (`server/mcp_server.py`).

**Host transcript** (separate from the brief stack):

- Policy default: `host_transcript: none` — executor gets **no** chat dump.
- With `host_transcript: dump`: mcp-coder loads the active **Cursor** chat JSONL (`core/host/cursor.py` → `load_cursor_transcript`) and:
  1. Passes it into **helper LLM** prompts (builder, architect, spec validation) as context.
  2. Prepends it to the **executor** prompt in the Aider adapter (`translate_context_package(..., host_transcript=...)`), *above* `package.brief`.

So with dump enabled, Aider's final prompt order is:

```
[Cursor chat transcript]     ←  only when host_transcript: dump
---
package.brief                ←  architect? + builder? + mechanical
+ read context blocks
+ repo map block
```

The `context_summary` argument on every `delegate_to_agent` call is **always** included in the mechanical brief — it is the planner's guaranteed voice even when `host_transcript: none`.

---

## 2. Pipeline: picker → assemble → architect* → builder* → budget → executor

For `mode=implement` with a valid spec and `context_builder` enabled (default on), phases run in this order:

```
file_picker       rules-based: spec contract + planner hints + symbol scan → ranked candidates
context_assemble  materialize candidates → PathEntry list with tiered payloads + mechanical brief
architect_pass*   helper LLM produces ## Architect plan (stored; merged after builder)
builder_llm*      helper LLM prepends ## Builder brief above mechanical brief
[merge architect plan on top of package.brief if architect succeeded]
budget            trim read-tier payloads until estimated tokens ≤ model budget
executor          Aider adapter: optional Cursor transcript + package.brief + read/map blocks
```

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 8, 'rankSpacing': 20}}}%%
flowchart TB
    IN[delegate] --> PK[picker]
    PK --> AS[assemble]
    AS --> AR{architect?}
    AR -->|off| BL{builder?}
    AR -->|on| ARP[architect LLM] --> BL
    BL -->|off| MG[merge brief]
    BL -->|on| BLP[builder LLM] --> MG
    MG --> BU[budget]
    BU --> EX[executor]

    style PK fill:#e8f4e8
    style AS fill:#e8f4e8
    style BU fill:#e8f4e8
    style ARP fill:#fdf0e0
    style BLP fill:#fdf0e0
```

Green = mechanical/deterministic (no LLM). Orange = optional helper-LLM stages, both **non-fatal** on failure.

| Phase | Default | Toggle |
|-------|---------|--------|
| Picker + assemble | **on** | `context_builder: false` |
| Builder LLM | **on** | `context_builder_llm: false` |
| Architect pass | **off** | `architect_pass: true` |
| Host transcript to executor | **off** | `host_transcript: dump` |
| Budget | **on** | `MCP_CODER_CONTEXT_BUDGET_ENABLED=0` |

Without a spec, the picker is **skipped** — only `target_files` go in.

---

## 3. File tiers — the core concept

Every path in the package has a **tier** that determines how much text the executor sees:

| Tier | What Aider sees | When assigned |
|------|-----------------|---------------|
| `edit-full` | Full file text; in Aider's `fnames` (open for editing) | Spec `### Edit` paths |
| `read-full` | Full file text; in prompt as fenced read context block | Spec `### Read` paths; small discovered files |
| `read-excerpt` | Symbol-window extract or head (see §5); fenced block | Read file too large, or demoted by budget |
| `pointer` | Path listed in brief only; no payload | Budget last resort; file unreadable |
| `map-only` | `def`/`class` outline only; in repo map block | Files discovered by picker, not in spec contract |
| `hide` | Not included at all | (Not currently assigned in compile path) |

How a path lands in a tier:

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 8, 'rankSpacing': 18}}}%%
flowchart TB
    P[path] --> E{spec Edit?}
    E -->|yes| EF[edit-full]
    E -->|no| R{Read / hint?}
    R -->|yes| S{≤8 KB?}
    S -->|yes| RF[read-full]
    S -->|no| RE[read-excerpt]
    R -->|no| D{symbol scan?}
    D -->|yes| RE
    D -->|no| MO[map-only]
    RF -.-> RE -.-> PT[pointer]

    style EF fill:#fde0e0
    style PT fill:#eeeeee
```

Solid arrows = assemble-time decisions. Dotted = budget degradation (§7). `edit-full` (red) is the only tier that ever enters Aider's editable `fnames`, and budget can never touch it.

**Try it (playground from §0):**

```bash
mcp-coder inspect-context --workspace "$DEMO" \
  --task 'Add CLI calling `get_user` per spec' \
  --context-summary 'Demo playground' \
  --target-files src/cli.py,src/api.py,src/big_utils.py \
  --spec tasks/demo-01-cli.md \
  | jq -r '.context_package.entries[] | select(.tier != "map-only") | "\(.tier)\t\(.bytes)\t\(.path)"'
```

Expected output (one line per non-map entry):

```
read-full       110    src/api.py        ← spec ### Read, under 8 KB
read-excerpt    11903  src/big_utils.py  ← spec ### Read, over 8 KB → excerpted
edit-full       0      src/cli.py        ← spec ### Edit (empty file, still full fidelity)
read-full       78     src/consumer.py   ← symbol scan found `get_user` — read, never edit
```

(Note the excerpt is nearly as big as the file: `big_utils.py` is *all* `def` lines, so the ±5-line symbol windows merge into almost everything. Symbol-dense files excerpt poorly — the budget passes in §7 are the backstop.)

**Gotcha worth knowing:** when a **spec** is present, `target_files` hints that are *not* in the spec contract are recorded in `metadata.hint_paths` but **not materialized** as payload entries — the spec contract wins. (Without a spec, all `target_files` become `read-full`.) If the executor must see a file, put it in the spec `### Read`, don't rely on extra `target_files`.

**Critical invariant (D-P4-10, compile time):** discovered files from the symbol scan are **always** `read-full` or `map-only` — **never** `edit-full` in the `ContextPackage`. Only spec `files_edit` (or YAML `files_edit`) become `edit-full` at assemble time. Discovery never promotes a path to `fnames`.

This is **not** a hard runtime lock — see §3.5.

**How Aider translates tiers:**

```python
# core/engine/aider_engine.py — translate_context_package()
fnames = [edit-full paths]                      # Aider opens these for editing
prompt += read_block   # fenced payloads for read-full / read-excerpt entries
prompt += map_block    # def/class outlines for map-only entries
```

So `fnames` = what Aider **starts** with as editable files. Read payloads + repo map = injected into the prompt text.

---

## 3.5 Initial context only — the backend loop can go wider

The `ContextPackage` is **initial context**: it is compiled once, then the executor phase runs. For Aider today that is a single `coder.run(prompt)` call — but **inside** that call Aider runs its own **multi-turn agentic loop** (LLM turns, SEARCH/REPLACE edits, etc.). mcp-coder does **not** re-compile or inject more context between those internal turns (see BL-350 for future supervised loops).

### What “initial” means in practice

| Moment | What is fixed | What can still change |
|--------|----------------|------------------------|
| **Before `executor`** | `package.brief`, read/map payloads, `fnames` | — |
| **During Aider’s loop** | Same prompt text (no mcp-coder refresh) | **Disk** — Aider may edit or create paths **not** in `fnames` |
| **After `executor`** | — | mcp-coder diffs workspace → `files_changed`, `files_unexpected`, `scope_violations` |

So D-P4-10 controls **what we open and emphasize at start**, not “only these bytes may ever change on disk.”

### Can Aider edit file Z mid-loop?

**Often yes**, depending on backend behavior. Our Aider adapter declares:

```python
# core/engine/capabilities.py — AIDER_CAPABILITIES
dynamic_add_files=True      # Aider may pull more files into its edit set
dynamic_create_files=True   # Aider may create new files on disk
shell_default=False         # shell commands off unless MCP_CODER_AIDER_SUGGEST_SHELL=1
```

Headless delegations use `InputOutput(yes=True)` — Aider will not block on interactive “add file to chat?” prompts, but the model can still apply edits Aider accepts. If it touches path Z:

- Z appears in `files_changed` (manifest hash walk after the run)
- If Z ∉ spec contract → `files_unexpected`
- If Z ∉ `files_edit` and `edit_scope: strict` → `scope_violations` (optional auto-revert via post_gateway)
- If `edit_scope: discover` (default) → edits stand; spec report lists unexpected paths for the planner

### What we control today (partial)

| Lever | Effect |
|-------|--------|
| **Spec `### Edit` / `files_edit`** | Only these paths get `edit-full` + `fnames` at start |
| **`edit_scope: strict`** | Post-run revert of edits outside `files_edit` (when snapshots on) |
| **`edit_scope: discover`** | Allow out-of-contract edits; audit only |
| **`MCP_CODER_AIDER_SUGGEST_SHELL=0`** (default) | No shell-command tool path from Aider |
| **Read context in prompt** | Other files visible as read-only text — model may still try to edit them |

We do **not** today expose fine-grained “disable dynamic add/create” flags on the Aider adapter — capability fields are declared for the compiler (`core/engine/capabilities.py`) but runtime tool surface is mostly Aider’s defaults minus shell. Tighter per-tool limits would be backend-specific adapter work (or BL-350 outer loop with re-compile between steps).

### Mental model (one delegation)

```mermaid
sequenceDiagram
    participant M as mcp-coder
    participant A as Aider
    participant D as disk
    M->>A: prompt + fnames
    loop agent loop
        A->>A: LLM / edits
        A->>D: may touch file Z
    end
    A->>M: done
    M->>D: post_gateway diff
```

**Takeaway:** `inspect-context` shows **starting** conditions. After a delegate, always check `files_changed`, `files_unexpected`, and `scope_violations` in the JSONL response — that is the ground truth for what the loop actually did.

---

## 4. The file picker — how it finds files

`core/context/file_picker.py` — no LLM, no git dependency.

### Step 1: classify inputs

| Source | Paths | Tier |
|--------|-------|------|
| Spec `### Edit` | `files_edit` | `edit-full` |
| Spec `### Read` | `files_read` | `read-full` |
| Planner `target_files` not in spec | `hint_paths` | `read-full` |

Each path is tagged with its source for the audit: `spec_edit`, `spec_read`, `hint`, or `symbol_scan`.

### Step 2: symbol scan (discover mode only)

When `edit_scope: discover` (default):

1. Extract **symbol queries** from `task` + spec text: backtick-quoted identifiers and `def`/`class` names; capped at 20 queries; path-like strings (containing `/`) and stop-words filtered out.
2. Run `rg -l --fixed-strings <symbol>` per query (Python fallback if `rg` unavailable) across `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.md`, `.yaml`, `.yml`, `.toml`.
3. New hits (not already in contract/hint set) → `discovered_read`; capped at `MCP_CODER_PICKER_MAX_DISCOVERED` (default **30**).

When `edit_scope: strict`: scanner **skipped**, no `discovered_read`, no `suggested_edit_paths`.

### Step 3: suggested edit paths (audit only)

Discovered paths that sit in the **same directory** as any `files_edit` path → `suggested_edit_paths`. These appear in the MCP response and builder prompt as **audit hints only** — they are **never** promoted to `edit-full` without a spec update (D-P4-10). The planner decides whether to expand the spec.

### Ranked output

```
edit_paths (spec) → read_paths (spec) → hint_paths → discovered_read
```

This is what goes to `assemble_context()`.

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 8, 'rankSpacing': 20}}}%%
flowchart TB
    SE[spec Edit/Read] --> RANK[ranked paths]
    TF[target_files] --> RANK
    TK[task + spec] --> SY[symbols] --> RG[rg] --> DR[discovered]
    DR --> RANK
    DR -.-> SUG[suggested edits]
    RANK --> AS[assemble]
```

**Try it — watch the symbol scan work (playground from §0):**

```bash
mcp-coder inspect-context --workspace "$DEMO" \
  --task 'Add CLI calling `get_user` per spec' \
  --context-summary 'Demo playground' \
  --target-files src/cli.py \
  --spec tasks/demo-01-cli.md \
  | jq '.context_package.metadata.candidate_files'
```

You should see `symbol_queries` containing `get_user` (backticked in the task **and** in the spec Goal — both are scanned) and `discovered_read` containing `src/consumer.py` — the picker ran `rg -l get_user` and found it. Note `suggested_edit_paths` also lists `src/consumer.py` (same dir as the edit target) — audit hint only, it stays a read tier.

---

## 5. Assembling the package

`core/context/assemble.py — assemble_context()`

For each path in the ranked list:

| File state | Result |
|------------|--------|
| `edit-full` | Read full text → `edit-full` entry with payload |
| `read-full`, file ≤ 8 192 B (`MCP_CODER_READ_FULL_MAX_BYTES`) | Read full text → `read-full` entry |
| `read-full`, file > threshold | Run excerpt engine (see §6) → `read-excerpt` entry |
| File missing | `payload=None`, `bytes=None` entry; logged in `missing_paths` |

Untracked files (git check) are logged in `untracked_paths` (informational; delegate still proceeds).

Then, if the picker ran and `include_repo_map=True`, **repo map entries** are appended for workspace files not already in the ranked set — `def`/`class` outlines only, `tier=map-only`, capped at `MCP_CODER_REPO_MAP_MAX_FILES` (default **150**).

### The mechanical brief

The bottom of the package brief is built from:

```markdown
## Task
<task>

## Context
<context_summary>

## Goal
<spec ## Goal content>

## Constraints
<spec ## Constraints content>

## Paths

- `src/cli.py` — edit-full
- `src/api.py` — read-full
- `core/utils.py` — read-excerpt
```

This brief is **authoritative**. No LLM ever rewrites or removes it. It is the "mechanical brief."

If the picker found `suggested_edit_paths`, they are appended as a note:

```markdown

Suggested edit paths (not in spec contract): `src/helper.py`
```

**Try it — read the actual mechanical brief (playground from §0):**

```bash
mcp-coder inspect-context --workspace "$DEMO" \
  --task 'Add CLI calling `get_user` per spec' \
  --context-summary "api.py is the step-1 API; CLI is new" \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  | jq -r '.context_package.brief'
```

You'll see exactly the `## Task / ## Context / ## Goal / ## Constraints / ## Paths` stack above (sections with no content are omitted) — this text goes to the executor verbatim, with helper-LLM layers (if any) stacked on top. Note `src/consumer.py` appears both in `## Paths` and as a suggested-edit note: the symbol scan found it.

---

## 6. Excerpt engine

`core/context/excerpts.py`

Read files over the byte threshold get excerpted instead of included in full.

Two strategies:

| Strategy | When | What you get |
|----------|------|--------------|
| `symbol_windows` | File has `def`/`class` lines | Each symbol line ±5 context lines, merged ranges; header `# excerpt from: path` |
| `head_tail` | No symbols | First 80 lines + `… (excerpt truncated, N bytes total)` |

Excerpts are **materialized to disk** at `.mcp-coder/context/excerpts/<path__as__safe_name>.excerpt.txt`. The path is stored in `entry.excerpt_path` and logged in `context_package.metadata.excerpt_paths`.

**Config:** `MCP_CODER_READ_FULL_MAX_BYTES` (default **8 192** bytes). Files below this threshold → full text even for read tier.

**Try it — see an excerpt get materialized (playground from §0):**

```bash
mcp-coder inspect-context --workspace "$DEMO" \
  --task "Refactor helpers" \
  --context-summary 'Demo playground' \
  --target-files src/cli.py,src/big_utils.py \
  --spec tasks/demo-01-cli.md > /dev/null
```

Then read the excerpt file written under the demo workspace:

```bash
head -20 "$DEMO/.mcp-coder/context/excerpts/src__big_utils.py.excerpt.txt"
```

You'll see the `# excerpt from: src/big_utils.py` header followed by `def helper_N` windows — the `symbol_windows` strategy. Then shrink the threshold and watch even `src/api.py` get excerpted:

```bash
MCP_CODER_READ_FULL_MAX_BYTES=50 mcp-coder inspect-context --workspace "$DEMO" \
  --task "Refactor helpers" \
  --context-summary 'Demo playground' \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  | jq -r '.context_package.entries[] | "\(.tier)\t\(.path)"'
```

---

## 7. Budget enforcement

`core/context/budget.py — apply_context_budget()`

A token estimate is computed as `len(brief + all_payloads) // 4` (rough ~4 chars/token). If estimated tokens exceed the budget, three degradation passes run **in order until under budget or no more can be done**:

| Pass | What changes |
|------|--------------|
| 1. `read_full_to_excerpt` | `read-full` → `read-excerpt` (run excerpt engine) |
| 2. `excerpt_shrink` | Shrink excerpt to first 40 lines + `… (budget truncated)` |
| 3. `drop_payload` | `read-excerpt`/`read-full` → `pointer` (payload removed; path listed in brief under `## Paths (budget)`) |

**`edit-full` entries are never degraded.** You always see the full content of files you are editing.

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 8, 'rankSpacing': 16}}}%%
flowchart LR
    EST[estimate] --> P1[① full→excerpt]
    P1 --> P2[② shrink]
    P2 --> P3[③ →pointer]
    P3 --> OK[done]
    EF[edit-full] -. never cut .-> OK
```

If still over budget after all three passes: `metadata.budget_warnings: ["context_budget:still_over_limit"]` (non-blocking; delegation proceeds).

**Try it — force degradation with a tiny budget (playground from §0):**

Two gotchas make a naive `MCP_CODER_CONTEXT_BUDGET_TOKENS=200` prefix silently do nothing: (1) the per-model yaml budget **beats** the env var, so you must also point at a model that isn't in `model_rates.yaml`; (2) the `scripts/mcp-coder` wrapper sources the repo `.env` **after** your prefix vars, clobbering them — bypass with an empty `MCP_CODER_ENV_FILE`.

```bash
touch "$DEMO/empty.env"
MCP_CODER_ENV_FILE="$DEMO/empty.env" AIDER_MODEL=demo/unknown \
MCP_CODER_CONTEXT_BUDGET_TOKENS=200 mcp-coder inspect-context --workspace "$DEMO" \
  --task 'Add CLI calling `get_user` per spec' \
  --context-summary 'Demo playground' \
  --target-files src/cli.py,src/api.py,src/big_utils.py \
  --spec tasks/demo-01-cli.md \
  | jq '{tiers: [.context_package.entries[] | select(.tier != "map-only") | {path, tier}], truncations: [.context_package.metadata.truncations[].reason]}'
```

Verified output — all three passes fire, read tiers collapse to `pointer`, and `src/cli.py` stays `edit-full`, untouched:

```json
{
  "tiers": [
    {"path": "src/api.py",       "tier": "pointer"},
    {"path": "src/big_utils.py", "tier": "pointer"},
    {"path": "src/cli.py",       "tier": "edit-full"},
    {"path": "src/consumer.py",  "tier": "read-excerpt"}
  ],
  "truncations": [
    "read_full_max_bytes",
    "context_budget:read_full_to_excerpt",
    "context_budget:read_full_to_excerpt",
    "context_budget:excerpt_shrink",
    "context_budget:excerpt_shrink",
    "context_budget:excerpt_shrink",
    "context_budget:drop_payload",
    "context_budget:drop_payload"
  ]
}
```

Remove the budget override and the `context_budget:*` truncations disappear.

**Budget resolution order:**

1. `MCP_CODER_CONTEXT_BUDGET_ENABLED=0` → disabled
2. Per-model `context_budget_tokens` from `resources/model_rates.yaml`
3. `MCP_CODER_CONTEXT_BUDGET_TOKENS` env var
4. Default **128 000** tokens

Each truncation is logged in `context_package.metadata.truncations`:

```json
[
  {"reason": "context_budget:read_full_to_excerpt", "path": "core/big_file.py", "bytes_dropped": 12400},
  {"reason": "context_budget:drop_payload", "path": "docs/reference.md", "bytes_dropped": 8192}
]
```

---

## 8. Helper LLM layers on the brief (builder + architect)

Two helper LLMs can annotate `package.brief`. Both are **non-fatal** on failure — delegation proceeds with whatever brief was already assembled.

The final brief is a stack — each optional layer sits **above** the one below, never replacing it:

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 6, 'rankSpacing': 12}}}%%
flowchart TB
    AP[Architect plan] --> BB[Builder brief] --> MB[Mechanical brief]

    style AP fill:#fdf0e0
    style BB fill:#fdf0e0
    style MB fill:#e8f4e8
```

### 8a. Architect pass (opt-in, default off)

`core/context/architect_prompt.py` + `core/engine/architect_pass_llm.py`

When `architect_pass: true` (or `MCP_CODER_ARCHITECT_PASS=1`):

1. Runs **after** `context_assemble`, **before** `builder_llm`.
2. Prompt includes spec summary, mechanical brief paths, picker audit, `task`, `context_summary`, and host transcript (if `host_transcript: dump`).
3. On success, returns a `## Architect plan` block.
4. Plan is **not** merged immediately — it is prepended **after** builder_llm finishes:

```python
# server/mcp_server.py — final merge order
context_package.brief = _merge_architect_plan(architect_plan, context_package.brief)
# architect_plan sits above builder + mechanical brief
```

Use this for harder tasks where you want a structured plan layer before the executor runs. It is separate from `mode=review` (which skips the compile path entirely).

### 8b. Builder LLM (on by default)

`core/context/builder_prompt.py` + `core/engine/context_builder_llm.py`

When `context_builder: true` AND `context_builder_llm: true` (both default **on**):

1. Gathers **builder history** from `workspace_history.db`: up to 5 same-spec delegations + up to 5 project-wide recent delegations (summaries only — `delegation_id`, `outcome`, `created_count`, `modified_count`, `checkpoint_summary`).
2. Assembles a prompt for the builder LLM containing:
   - Preamble (role instructions: narrative bullets only, ≤ 400 words, do not paste code)
   - The mechanical brief
   - Picker audit (ranked paths, discovered reads, symbol queries, path sources)
   - Suggested edit paths (if any)
   - Prior delegation history
   - Host transcript (if `host_transcript: dump` — loaded from Cursor chat JSONL)
   - Planner task + context summary
3. Calls the `context_builder` role model (default: `MCP_CODER_CONTEXT_BUILDER_MODEL`).
4. On success: prepends `## Builder brief\n\n<narrative>\n\n---\n\n` above the mechanical brief. **The mechanical brief is preserved verbatim after the separator.**
5. On failure: logs `builder_llm_error` in `context.metadata`; delegate proceeds with the mechanical brief only. **Non-fatal.**

**Key constraint in builder preamble:** "Do NOT paste file contents, code blocks, or ``` fences. Narrative bullets only." The brief is meant to orient the executor, not duplicate file payloads.

**Result in JSONL:**

```json
"context": {
  "builder_brief_applied": true,
  "builder_brief_applied": false,   // if LLM failed
  "builder_llm_error": "..."         // on failure only
}
```

**History is truncated to fit the builder's token budget** — project-wide rows dropped first, then same-spec rows. Contract (spec paths, mechanical brief) is never truncated.

**Try it — helper layers on `$DEMO` (playground from §0)**

Shared task line (reuse in every command below):

```bash
TASK='Add CLI calling `get_user` per spec'
CTX='Demo playground; argparse CLI for get_user'
```

**A. Mechanical brief only** — no helper LLM calls (free):

```bash
mcp-coder inspect-context --workspace "$DEMO" \
  --task "$TASK" --context-summary "$CTX" \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  | jq -r '.context_package.brief' | head -20
```

No `## Builder brief` or `## Architect plan` — just `## Task` … `## Paths`.

**B. Builder via inspect** — opt-in flag (**uses API**; same model as real delegate):

```bash
mcp-coder inspect-context --workspace "$DEMO" \
  --task "$TASK" --context-summary "$CTX" \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  --run-builder-llm --pretty \
  | jq '{builder: .helper_phases.builder_llm, brief_head: (.context_package.brief[0:400])}'
```

On success: `helper_phases.builder_llm.applied` is `true` and the brief starts with `## Builder brief` above the mechanical stack.

**C. Architect + builder via inspect** — both opt-in (**uses API**):

```bash
mcp-coder inspect-context --workspace "$DEMO" \
  --task "$TASK" --context-summary "$CTX" \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  --run-architect --run-builder-llm --force-helpers --pretty \
  | jq -r '.context_package.brief' | head -15
```

First line should be `## Architect plan`, then `## Builder brief`, then mechanical `## Task` (architect merges above builder — same order as MCP).

**D. Delegate-faithful prepare** — builder runs from **config** (default on), no `--run-*` flags; always returns full Aider prompt:

```bash
mcp-coder delegate --workspace "$DEMO" \
  --task "$TASK" --context-summary "$CTX" \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  --stop-after context --pretty \
  | jq '{
      helpers: .artifacts.helper_phases,
      has_builder_brief: (.artifacts.executor_in.prompt | contains("## Builder brief")),
      prompt_tokens: .artifacts.executor_in.prompt_tokens_est
    }'
```

This is what §9 assembles into `executor_in` — use `jq -r '.artifacts.executor_in.prompt'` to dump the full string.

To enable architect on prepare without inspect flags, add to `$DEMO/.mcp-coder/config.yaml`:

```yaml
architect_pass: true
```

Then re-run **D** — `helper_phases.architect_pass.applied` should be `true` and the prompt starts with `## Architect plan`.

---

## 9. What the executor actually receives (Aider today)

After all phases, the **Aider adapter** (`translate_context_package()` in `core/engine/aider_engine.py`) converts the package. Another backend would translate tiers differently; this is the current executor mapping.

```
prompt = [host transcript]              # Cursor chat dump, only when host_transcript: dump
       + package.brief                  # architect? + builder? + mechanical
       + read_block                     # fenced payloads for read-full / read-excerpt
       + map_block                      # def/class outlines for map-only entries

fnames = [edit-full paths]              # files Aider opens for editing (not read/map)
```

**Cursor → mcp-coder → Aider flow (concrete):**

1. Cursor planner calls `delegate_to_agent(task=..., context_summary=..., spec_path=...)`.
2. mcp-coder compiles `ContextPackage` (picker, tiers, optional builder/architect).
3. If `host_transcript: dump`, mcp-coder reads the active Cursor session JSONL and prepends it to the Aider prompt.
4. Aider receives `prompt` + `fnames`; its internal LLM runs SEARCH/REPLACE on `fnames` only.

The read context block looks like this in Aider's prompt:

```
---

## Read context (read-only — do not edit unless spec allows)

### `src/api.py` (read-full)
```python
<full file content>
```

### `core/big_file.py` (read-excerpt)
```python
# excerpt from: core/big_file.py

def parse_config(...):
    ...

class Builder:
    ...
```
```

The repo map block:

```
---

## Repo map (symbols only — do not edit unless spec allows)

### `core/utils.py` (map-only)
def helper(x):
class Cache:
```

**Pointer entries** (budget dropped) appear only as path names in the brief under `## Paths (budget)` — no payload, no block.

**Try it — what we send to Aider (`$DEMO`, playground from §0)**

Use the same `TASK` / `CTX` variables from §8.

**Step 1 — `fnames` vs read payloads** (editing set vs fenced read blocks):

```bash
mcp-coder delegate --workspace "$DEMO" \
  --task "$TASK" --context-summary "$CTX" \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  --stop-after context \
  | jq '.artifacts.executor_in | {fnames, read_paths_in_prompt, prompt_tokens_est}'
```

Expect `fnames: ["src/cli.py"]` only — `src/api.py` and `src/big_utils.py` land in the prompt as **read** blocks, not editable `fnames`.

**Step 2 — read block inside the prompt** (the fenced `## Read context` section):

```bash
mcp-coder delegate --workspace "$DEMO" \
  --task "$TASK" --context-summary "$CTX" \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  --stop-after context \
  | jq -r '.artifacts.executor_in.prompt' \
  | grep -nE 'Read context|src/api.py|src/big_utils' | head -10
```

You should see `get_user` inside the `src/api.py` fence and an excerpt header for `src/big_utils.py`.

**Step 3 — full brief stack in the prompt** (after running §8 **B** or **D** with builder on):

```bash
mcp-coder delegate --workspace "$DEMO" \
  --task "$TASK" --context-summary "$CTX" \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  --stop-after context \
  | jq -r '.artifacts.executor_in.prompt' | head -35
```

**Step 4 — full round trip** (Aider in + post steps out; **needs API key** — run `mcp-coder test-model` first, T-01):

```bash
mcp-coder test-model
cd "$DEMO"
mcp-coder delegate \
  --task "$TASK" --context-summary "$CTX" \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  --pretty > /tmp/ctx-demo-roundtrip.json
```

Executor input (prompt head):

```bash
jq -r '.artifacts.executor_in.prompt' /tmp/ctx-demo-roundtrip.json | head -15
```

Executor output:

```bash
jq '.artifacts.executor_out | {success, output: (.output[0:200]), files_changed}' \
  /tmp/ctx-demo-roundtrip.json
```

Back to planner (MCP) + post steps:

```bash
jq '{
  caller: .caller_response | {success, outcome, files_changed, spec_report_path},
  post: .artifacts.post_delegate | {pipeline: .delegation_pipeline, scope_violations}
}' /tmp/ctx-demo-roundtrip.json
cat "$DEMO/src/cli.py"
```

`fnames` is what Aider opens for editing; `read_paths_in_prompt` are the fenced blocks; `artifacts.executor_in.prompt` is the exact wire string (brief + read + map blocks).

---

## 10. CLI tools — `inspect-context` and `delegate`

### `inspect-context` — dry-run compiler (Level 1)

No executor, no file edits, no JSONL. Helper LLMs are **opt-in** (§14). Use `$DEMO` from §0:

```bash
mcp-coder inspect-context --workspace "$DEMO" \
  --task 'Add CLI calling `get_user` per spec' \
  --context-summary 'Demo playground' \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md --pretty

# File payloads in entries (large)
mcp-coder inspect-context --workspace "$DEMO" ... --include-payloads

# Full executor prompt on inspect (opt-in)
mcp-coder inspect-context --workspace "$DEMO" ... --include-prompt \
  | jq -r '.adapter_preview.prompt' | head -30
```

### `delegate --stop-after context` — prepare only (Level 2)

Same pre-executor path as a real `delegate_to_agent`: helpers follow **`config.yaml`**, host transcript auto-loaded when `host_transcript: dump`. Always includes full prompt in `artifacts.executor_in`:

```bash
mcp-coder delegate --workspace "$DEMO" \
  --task 'Add CLI calling `get_user` per spec' \
  --context-summary 'Demo playground' \
  --target-files src/cli.py,src/api.py \
  --spec tasks/demo-01-cli.md \
  --stop-after context --pretty \
  | jq '{ok, helper: .artifacts.helper_phases, fnames: .artifacts.executor_in.fnames}'
```

### `delegate` — full pipeline (Level 3)

Pre + Aider + post (`post_gateway`, spec report, optional `auto_verify`). Same JSON envelope as §0 Bonus. See **T-06** §5 for field reference.

### Output structure

```json
{
  "ok": true,
  "compiler_version": "0.3.0",
  "context_package": {
    "brief": "## Task\n...\n## Paths\n...",
    "entries": [
      {"path": "src/cli.py", "tier": "edit-full", "bytes": 1234, "excerpt_path": null},
      {"path": "src/api.py", "tier": "read-full",  "bytes": 800,  "excerpt_path": null},
      {"path": "core/utils.py", "tier": "read-excerpt", "bytes": 600, "excerpt_path": ".mcp-coder/context/excerpts/core__utils.py.excerpt.txt"}
    ],
    "metadata": {
      "bytes_by_tier": {"edit-full": 1234, "read-full": 800, "read-excerpt": 600},
      "token_estimate_preflight": 2158,
      "missing_paths": [],
      "untracked_paths": [],
      "excerpt_paths": [".mcp-coder/context/excerpts/..."],
      "truncations": [],
      "candidate_files": {
        "ranked_paths": ["src/cli.py", "src/api.py"],
        "discovered_read": ["core/utils.py"],
        "suggested_edit_paths": [],
        "symbol_queries": ["Config", "parse_args"]
      },
      "repo_map_count": 42,
      "context_builder_enabled": true
    }
  },
  "auto_merged_read_paths": ["src/api.py"],
  "adapter_preview": {
    "fnames": ["src/cli.py"],
    "read_paths_in_prompt": ["src/api.py", "core/utils.py"],
    "prompt_chars": 8241,
    "prompt_tokens_est": 2060,
    "prompt_hash": "abc123...",
    "prompt": "... only when --include-prompt or delegate prepare ..."
  },
  "helper_phases": {
    "spec_validation": {"ran": false, "would_block_delegate": false},
    "architect_pass": {"ran": false, "applied": false},
    "builder_llm": {"ran": false, "applied": false}
  }
}
```

`mcp-coder delegate` (full or `--stop-after context`) wraps the same compile data under `artifacts` plus `executor_in.prompt` always on prepare/full.

### Key fields to check

| Field | What it tells you |
|-------|-------------------|
| `entries[].tier` | What fidelity each file has |
| `entries[].bytes` | Payload size after excerpting/truncation |
| `adapter_preview.fnames` | Exactly what Aider will open for editing |
| `adapter_preview.read_paths_in_prompt` | Read payloads injected as fenced blocks |
| `adapter_preview.prompt` / `artifacts.executor_in.prompt` | Full string sent to Aider |
| `adapter_preview.prompt_tokens_est` | Estimated total token cost |
| `helper_phases` | Which helper LLMs ran and whether validation would block |
| `metadata.truncations` | What got cut and why |
| `metadata.budget_warnings` | "still_over_limit" if budget enforcement couldn't fit |
| `metadata.candidate_files.discovered_read` | Files the symbol scan found |
| `metadata.candidate_files.suggested_edit_paths` | Discovered files in edit dirs (audit only) |
| `metadata.candidate_files.symbol_queries` | Symbols extracted from task + spec |
| `metadata.missing_paths` | Spec/hint paths that don't exist on disk yet |
| `auto_merged_read_paths` | Spec Read paths the system appended (see T-03 §5) |
| `contract_warnings` | Spec edit paths missing from `target_files` |

---

## 11. What shows in JSONL after a real delegate

In the `context` block of the delegation record:

```json
"context": {
  "context_package": {
    "compiler_version": "0.3.0",
    "entries": [
      {"path": "src/cli.py", "tier": "edit-full",   "bytes": 1234, "excerpt_path": null},
      {"path": "src/api.py", "tier": "read-full",   "bytes": 800,  "excerpt_path": null}
    ],
    "token_estimate_preflight": 2060,
    "excerpt_paths": [],
    "truncations": []
  },
  "builder_brief_applied": true,
  "context_builder_enabled": true,
  "adapter_in": {
    "fnames": ["src/cli.py"],
    "read_paths_in_prompt": ["src/api.py"]
  }
}
```

**Payloads are not stored in JSONL** — `entries` has path/tier/bytes/excerpt_path only. The actual content that went to Aider is not logged to disk by default (the package is assembled fresh on each delegate). Reconstruct with `inspect-context --include-prompt`, `delegate --stop-after context`, or `MCP_CODER_LOG_FULL_PROMPT=1` on a real delegate (T-02).

---

## 12. Config flags

Precedence everywhere: **default → env → `.mcp-coder/config.yaml`** (yaml wins).

| Flag | Default | Effect |
|------|---------|--------|
| `context_builder` | **on** | Picker + assemble runs; without it only `target_files` are used |
| `context_builder_llm` | **on** | Builder LLM narrative brief; requires `context_builder` on |
| `MCP_CODER_READ_FULL_MAX_BYTES` | **8 192** | Byte threshold before excerpting read files |
| `MCP_CODER_PICKER_MAX_DISCOVERED` | **30** | Cap on symbol-scan discovered files |
| `MCP_CODER_REPO_MAP_MAX_FILES` | **150** | Cap on map-only repo map entries |
| `MCP_CODER_CONTEXT_BUDGET_TOKENS` | **128 000** | Token budget (per-model yaml overrides) |
| `MCP_CODER_CONTEXT_BUDGET_ENABLED` | **1** | Set to `0` to disable budget enforcement |
| `MCP_CODER_CONTEXT_BUILDER_LLM` | `1` | Env toggle for builder LLM |
| `MCP_CODER_INSPECT_RUN_BUILDER_LLM` | `0` | Enable builder LLM in inspect CLI |
| `host_transcript` | **none** | `dump` → load Cursor chat JSONL into helper LLMs + executor prompt |
| `architect_pass` | **off** | `true` → `## Architect plan` above builder + mechanical brief |

Turn the context builder off to fall back to the Phase 1/2 path (only `target_files`, no picker, no map):

```yaml
# .mcp-coder/config.yaml
context_builder: false
```

Turn the builder LLM narrative off but keep the picker:

```yaml
context_builder_llm: false
```

---

## 13. Invariants (locked design decisions)

These are locked in the code (not just conventions):

| Invariant | Where | Meaning |
|-----------|-------|---------|
| **D-P4-10** | `file_picker.py`, `assemble.py` | At **compile time**, discovery never grants `edit-full`; only `files_edit` → `fnames`. Runtime edits outside that set are handled by post_gateway (§3.5). |
| Mechanical brief is never rewritten | `builder_prompt.py` | Builder adds narrative **above** a separator; mechanical brief follows verbatim. |
| Budget never degrades `edit-full` | `budget.py` | Edit target content is always delivered in full. |
| Builder/architect failure is non-fatal | `mcp_server.py` | LLM errors in optional stages are logged but pipeline continues. |
| `inspect-context` skips builder LLM by default | `inspect.py` | Dry-run should not make API calls unless explicitly requested. |

---

## 14. Common debugging scenarios

**"The executor edited the wrong file"**

```bash
mcp-coder inspect-context --spec tasks/my-spec.md --task "..." --target-files ...
```

Check `adapter_preview.fnames` — that's the **initial** edit set. If an unexpected file was **changed on disk** after the run, it may have been touched mid-loop even though it wasn't in `fnames` (§3.5) — check `files_changed` / `files_unexpected` in JSONL. If an unexpected file is in `fnames` at inspect time, it's in spec `files_edit`. If the right file is missing from context, add it to spec `### Read` or `target_files`.

**"The executor didn't know about a key API from step 1"**

Check `context_package.entries` for `src/api.py` — is it there? What tier? If missing: add it to spec `### Read` or `target_files`. If `tier=pointer`: budget dropped the payload — enlarge budget or shrink other read files.

**"The executor keeps editing files outside the spec"**

This can happen **mid-loop** even when `inspect-context` showed a tight `fnames` list (§3.5). With `edit_scope: strict`, out-of-contract edits → `scope_violations` and optional revert. With `discover`, edits stand but land in `files_unexpected` on the spec report. Fix: add paths to spec `### Edit`, or use strict + expand contract before re-delegate. Check `suggested_edit_paths` in inspect output for symbol-scan candidates.

**"Token estimate is higher than expected"**

Check `metadata.bytes_by_tier` — which tier is dominating? Check `metadata.repo_map_count` — 150 symbol outlines add up. Lower `MCP_CODER_REPO_MAP_MAX_FILES` or set `context_builder: false` for a quick test.

**Helper LLMs**

| Tool | Helper behavior |
|------|-----------------|
| `inspect-context` | **Opt-in** flags (`--run-builder-llm`, `--run-architect`, `--run-all-helpers`, …). Validation is advisory (does not block exit). |
| `delegate --stop-after context` | **Config-driven** (same as MCP). Builder on by default. |
| `delegate` (full) | Config-driven + executor |

On inspect, spec validation never blocks exit; on a real delegate it can block (`clarification_needed`).

| Phase | inspect flag | Workspace config | Needs host transcript? |
|-------|--------------|------------------|------------------------|
| Spec validation | `--run-spec-validation` | `spec_validation: true` | Yes (`--host-transcript-file` on inspect; auto on delegate when `host_transcript: dump`) |
| Architect pass | `--run-architect` | `architect_pass: true` | Optional |
| Builder LLM | `--run-builder-llm` | `context_builder_llm: true` (default on) | Optional |

Hands-on helper + Aider prompt demos: **§8** (helper layers) and **§9** (wire format + round trip). Quick reference:

| Goal | Where |
|------|--------|
| Mechanical vs builder vs architect | §8 **A–D** |
| `fnames` vs read blocks vs full prompt | §9 Steps 1–3 |
| Full Aider + post steps | §9 Step 4 / §0 Bonus |
| `inspect` opt-in helpers | §8 **B–C** or `--run-all-helpers` |
| Delegate-faithful prepare | §8 **D** or `delegate --stop-after context` |

---

## 15. Code map

| Concern | Module |
|---------|--------|
| Tiers, `ContextPackage`, `PathEntry` | `core/context/package.py` |
| File picker (symbol scan, ranking) | `core/context/file_picker.py` |
| Assemble + tier assignment | `core/context/assemble.py` |
| Excerpt engine | `core/context/excerpts.py` |
| Repo map (map-only entries) | `core/context/repo_map.py` |
| Budget enforcement | `core/context/budget.py` |
| Builder LLM prompt | `core/context/builder_prompt.py` |
| Builder history (from workspace_history.db) | `core/context/builder_history.py` |
| Adapter translation (fnames, read block) | `core/engine/aider_engine.py` → `translate_context_package()` |
| Backend capabilities (dynamic add/create, shell) | `core/engine/capabilities.py` |
| Post-run scope audit / revert | `core/workspace/gateway.py`, `core/workspace/snapshot.py` |
| Dry-run inspect | `core/context/inspect.py` |
| Helper LLM shared pipeline | `core/context/helper_llm_pipeline.py` |
| Delegate-faithful prepare | `core/delegation/prepare.py` |
| CLI artifact envelope | `core/delegation/artifacts.py` |
| CLI entry points | `core/cli/inspect_context.py`, `core/cli/delegate.py` |
| Config flags | `core/config/context_builder.py`, `core/config/auto_merge.py` |

---

## Next

- **T-05 (Workspace history):** why checkpoints vs git, `mcp-coder history` CLI, revert, policy/revert building blocks; builder history is one consumer
- **T-06 (Delegation pipeline):** `mcp-coder delegate` artifact fields, `delegation_pipeline` JSONL, post_gateway / auto_verify — builds on §0 Bonus here
- **BL-335:** token counts in `model_roles` currently `null` for several paths — context builder included; understanding this gap requires T-04 context
