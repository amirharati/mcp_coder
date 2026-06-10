# T-04: Context compiler deep-dive

**Goal:** Understand exactly what the executor (Aider) sees and why. By the end you can run `mcp-coder inspect-context`, read every field, and confidently adjust specs or config when the executor misses context or costs too much.

**Why this matters:** the executor cannot see your Cursor chat. What it gets is a compiled `ContextPackage` — a tiered, budgeted, optionally LLM-enriched prompt. Understanding how it's built is the difference between "why did the executor change the wrong file?" and "I know exactly what I need to fix in the spec."

**Prerequisites:** T-01 (one delegation ran) and T-03 (spec structure).

**Estimated time:** 25–35 min.

---

## 1. The fundamental distinction: prompt ≠ chat history

When `delegate_to_agent` runs, the executor does **not** see:

- Your Cursor chat
- Prior delegation outputs
- Aider's own previous sessions (unless the same MCP session is reused, which gives Aider in-process memory only)

What it **does** see — in every delegation — is a compiled `ContextPackage`:

```
brief                  ←  task + context_summary + spec Goal/Constraints + file paths list
file payloads          ←  full text or excerpts, injected as fenced read context blocks
repo map               ←  def/class outlines for files not otherwise included
```

Plus optionally:
```
## Builder brief       ←  LLM narrative prepended above the brief (opt-in)
## Architect plan      ←  LLM plan prepended above that (opt-in)
host transcript tail   ←  recent chat injected by the Aider adapter (opt-in policy)
```

The `context_summary` field on every `delegate_to_agent` call is **your one guaranteed channel** — it is always included. It's the planner's voice to the executor.

---

## 2. Pipeline: file_picker → assemble → budget → builder_llm

For `mode=implement` with a valid spec and `context_builder` enabled (default on), phases run in this order:

```
file_picker       rules-based: spec contract + planner hints + symbol scan → ranked candidates
context_assemble  materialize candidates → PathEntry list with tiered payloads + mechanical brief
budget            trim read-tier payloads until estimated tokens ≤ model budget
builder_llm*      helper LLM adds ## Builder brief above mechanical brief
───────────────── executor sees the assembled prompt ─────────────────
architect_pass*   (runs in the full delegate pipeline, before builder_llm)
```

`*` = opt-in. The picker + assemble always run when `context_builder: true`. Budget always runs. Builder LLM runs when both `context_builder` and `context_builder_llm` are on (both default **true**).

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

**Critical invariant (D-P4-10):** discovered files from the symbol scan are **always** `read-full` or `map-only` — **never** `edit-full`. Only spec `files_edit` (or YAML `files_edit`) can be `edit-full`. Discovery never grants edit rights.

**How Aider translates tiers:**

```python
# core/engine/aider_engine.py — translate_context_package()
fnames = [edit-full paths]                      # Aider opens these for editing
prompt += read_block   # fenced payloads for read-full / read-excerpt entries
prompt += map_block    # def/class outlines for map-only entries
```

So `fnames` = what Aider treats as editable. Read payloads + repo map = injected into the prompt text.

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

If still over budget after all three passes: `metadata.budget_warnings: ["context_budget:still_over_limit"]` (non-blocking; delegation proceeds).

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

## 8. Builder LLM (optional narrative layer)

`core/context/builder_prompt.py` + `core/engine/context_builder_llm.py`

When `context_builder: true` AND `context_builder_llm: true` (both default **on**):

1. Gathers **builder history** from `workspace_history.db`: up to 5 same-spec delegations + up to 5 project-wide recent delegations (summaries only — `delegation_id`, `outcome`, `created_count`, `modified_count`, `checkpoint_summary`).
2. Assembles a prompt for the builder LLM containing:
   - Preamble (role instructions: narrative bullets only, ≤ 400 words, do not paste code)
   - The mechanical brief
   - Picker audit (ranked paths, discovered reads, symbol queries, path sources)
   - Suggested edit paths (if any)
   - Prior delegation history
   - Host transcript tail (if `host_transcript` policy on)
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

---

## 9. What Aider actually receives

After all phases, `translate_context_package()` in `core/engine/aider_engine.py` converts the package:

```
prompt = package.brief                  # mechanical brief (+ builder/architect on top)
       + read_block                     # fenced payloads for read-full / read-excerpt
       + map_block                      # def/class outlines for map-only entries

fnames = [edit-full paths]              # files Aider opens for editing
```

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

---

## 10. `inspect-context` — dry-run without a backend call

The single most useful debugging tool. No LLM call, no file edits, no JSONL log.

```bash
# Basic — just target_files
mcp-coder inspect-context \
  --task "Add a config loader that reads .mcp-coder/config.yaml" \
  --target-files core/config/loader.py \
  --context-summary "New module; no existing loader yet"

# With spec (mirrors the real delegate call exactly)
mcp-coder inspect-context \
  --task "Implement CLI per spec" \
  --target-files src/cli.py,src/api.py \
  --context-summary "argparse CLI; api.py from step 1" \
  --spec tasks/my-feature-02-cli.md

# Pretty-print
mcp-coder inspect-context --task "..." --target-files foo.py --pretty

# Include file payloads in output (can be large)
mcp-coder inspect-context --task "..." --target-files foo.py --include-payloads
```

**Builder LLM is skipped by default in inspect** (to avoid surprise API calls). Enable with:

```bash
MCP_CODER_INSPECT_RUN_BUILDER_LLM=1 mcp-coder inspect-context ...
```

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
    "prompt_hash": "abc123..."
  }
}
```

### Key fields to check

| Field | What it tells you |
|-------|-------------------|
| `entries[].tier` | What fidelity each file has |
| `entries[].bytes` | Payload size after excerpting/truncation |
| `adapter_preview.fnames` | Exactly what Aider will open for editing |
| `adapter_preview.read_paths_in_prompt` | Read payloads injected as fenced blocks |
| `adapter_preview.prompt_tokens_est` | Estimated total token cost |
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

**Payloads are not stored in JSONL** — `entries` has path/tier/bytes/excerpt_path only. The actual content that went to Aider is not logged to disk (the package is assembled fresh on each delegate). Use `inspect-context` to reconstruct it.

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
| **D-P4-10** | `file_picker.py`, `assemble.py` | Discovery never grants `edit-full`. Only spec `files_edit` → edit-full. |
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

Check `adapter_preview.fnames` — that's the edit set. If an unexpected file is there, it's in spec `files_edit` or YAML `files_edit`. If the right file is missing, it's not in the spec contract and not in `target_files`.

**"The executor didn't know about a key API from step 1"**

Check `context_package.entries` for `src/api.py` — is it there? What tier? If missing: add it to spec `### Read` or `target_files`. If `tier=pointer`: budget dropped the payload — enlarge budget or shrink other read files.

**"The executor keeps editing files outside the spec"**

With `edit_scope: strict`, out-of-contract edits → `scope_violation`. Check `suggested_edit_paths` in inspect output — those are candidates for adding to spec `### Edit`.

**"Token estimate is higher than expected"**

Check `metadata.bytes_by_tier` — which tier is dominating? Check `metadata.repo_map_count` — 150 symbol outlines add up. Lower `MCP_CODER_REPO_MAP_MAX_FILES` or set `context_builder: false` for a quick test.

**"I want to see what the builder LLM would say"**

```bash
MCP_CODER_INSPECT_RUN_BUILDER_LLM=1 mcp-coder inspect-context --spec tasks/my-spec.md --task "..." --target-files ... --pretty
```

Check `context_package.brief` for the `## Builder brief` section.

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
| Dry-run inspect | `core/context/inspect.py` |
| CLI entry point | `core/cli/inspect_context.py` |
| Config flags | `core/config/context_builder.py`, `core/config/auto_merge.py` |

---

## Next

- **T-05 (Workspace history & RAG):** `workspace_history.db`, `list_delegations`, `get_delegation_diff` — what the history layer stores and how the builder history is populated
- **T-06 (Phase 4 pipeline):** full `delegation_pipeline` JSONL; flag matrix; all optional phases wired together
- **BL-335:** token counts in `model_roles` currently `null` for several paths — context builder included; understanding this gap requires T-04 context
