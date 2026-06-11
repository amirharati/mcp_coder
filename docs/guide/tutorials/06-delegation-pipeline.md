# T-06: The delegation pipeline

**Goal:** Understand every phase that runs on `delegate_to_agent` — in order, with timing, and with the config flags that turn each on or off. By the end you can read a `delegation_pipeline` JSON block and know exactly which phases ran, which were skipped, and where time went.

**Why this matters:** The pipeline is the whole machine. T-04 covers context compile in depth; T-05 covers history/revert. T-06 is how those pieces wire together end-to-end, plus the stages T-04/T-05 didn't cover: spec validation, post_gateway, spec report, and auto_verify.

**Prerequisites:** T-02 (JSONL records), T-03 (specs), T-04 (context compiler), T-05 (workspace history).

**Estimated time:** 20 min (skim); 40 min (run examples against a real delegation).

---

## 1. Ten phases, one delegate call

```
delegate_to_agent(mode=implement, spec_path=..., task=..., ...)
  │
  ├─ 1  spec_read          parse spec contract — Files, policies, outcome rules
  ├─ 2  spec_validation*   cheap LLM — spec vs host transcript → clarification_needed?
  ├─ 3  file_picker        rg + spec paths + hints → candidate_files   [T-04 §4]
  ├─ 4  context_assemble   tiers → ContextPackage → mechanical brief   [T-04 §5]
  ├─ 5  architect_pass*    cheap LLM → ## Architect plan above brief   [T-04 §8a]
  ├─ 6  builder_llm        cheap LLM → ## Builder brief merged on top  [T-04 §8b]
  ├─ 7  executor           Aider: SEARCH/REPLACE on fnames
  ├─ 8  post_gateway       manifest diff → files_changed; scope audit  [T-05 §3]
  ├─ 9  spec_report        write .mcp-coder/specs/reports/*.md
  └─ 10 auto_verify*       pytest → outcome: success / partial

* = opt-in (default off except builder_llm which is on by default)
```

Phases 3–6 are covered in T-04. Phases 8, 9 touch T-05 history. This tutorial is the full picture and fills in 2, 7, 9, 10.

---

## 2. What `delegation_pipeline` looks like in JSONL

Every phase emits a record:

```json
"delegation_pipeline": [
  {"phase": "spec_read",        "status": "ok",      "duration_ms": 12},
  {"phase": "spec_validation",  "status": "skipped", "duration_ms": 0},
  {"phase": "file_picker",      "status": "ok",      "duration_ms": 85},
  {"phase": "context_assemble", "status": "ok",      "duration_ms": 140},
  {"phase": "architect_pass",   "status": "skipped", "duration_ms": 0},
  {"phase": "builder_llm",      "status": "ok",      "duration_ms": 820},
  {"phase": "executor",         "status": "ok",      "duration_ms": 14200},
  {"phase": "post_gateway",     "status": "ok",      "duration_ms": 55},
  {"phase": "spec_report",      "status": "ok",      "duration_ms": 8},
  {"phase": "auto_verify",      "status": "skipped", "duration_ms": 0}
]
```

**Status values:** `ok` | `skipped` | `error` | `blocked`

`skipped` = phase is disabled by config or not applicable (e.g. no spec → spec_validation skips). `blocked` = spec_validation returned `clarification_needed` and stopped the pipeline. `error` = non-fatal failure (execution continued with best-effort result).

---

## 3. Phase-by-phase

### 1 — `spec_read`

Parses the spec file (T-03): front matter, `## Files`, policies, outcome rules.

- Runs when `spec_path` is provided.
- On failure (bad YAML, missing file): `status: error`; pipeline continues without spec contract.
- Outputs: `files_edit`, `files_read`, `edit_scope`, outcome rule list.

### 2 — `spec_validation` (opt-in, off by default)

A cheap LLM checks the spec against context (task, host transcript if available) and can return `clarification_needed` — which **blocks** the pipeline and returns the question to the planner before any file edits happen. Useful for catching under-specified tasks early.

Enable:

```yaml
# .mcp-coder/config.yaml
spec_validation: true
```

or `MCP_CODER_SPEC_VALIDATION=1`.

When blocked: JSONL `status: blocked`; response contains `clarification_needed: "..."`.

### 3 — `file_picker` → 4 — `context_assemble` → 5 — `architect_pass` → 6 — `builder_llm`

See **T-04** §4–§8 for full detail. Quick summary here:

| Phase | What it does | Opt-in? |
|-------|-------------|---------|
| `file_picker` | rg symbol scan + spec contract → ranked candidates | On when `context_builder: true` (default) |
| `context_assemble` | Tiers, payloads, mechanical brief, budget | Same |
| `architect_pass` | `## Architect plan` layer above brief | Off by default; `architect_pass: true` |
| `builder_llm` | `## Builder brief` narrative on top | On by default; `context_builder_llm: false` disables |

### 7 — `executor`

Aider runs `coder.run(prompt)` with `fnames` (edit paths). This is where file edits happen on disk.

Key facts:
- Duration typically dominates the pipeline (LLM call inside Aider).
- Aider may touch files **not** in `fnames` mid-loop (§3.5 in T-04).
- Error here → `status: error`; `files_changed` still computed from manifest diff.
- Same-session caching: Aider `Coder` instance is reused across delegates in the same MCP session when workspace/model match → `executor_reused: true` in JSONL (faster; skips Aider init).

### 8 — `post_gateway`

After the executor finishes:

1. **Manifest diff** (`walk_workspace` before vs after) → `files_changed`, `files_unexpected`.
2. **Scope violations** — paths changed outside `files_edit`; with `edit_scope: strict` + snapshots → auto-revert from blobs (T-05 §2).
3. **`judgment_checklist`** — structured list of what was touched, for the planner to review (T-03 §5).
4. **History commit** — `file_deltas`, unified diffs written to `workspace_history.db` (T-05).

### 9 — `spec_report`

Writes `.mcp-coder/specs/reports/<spec-filename>.md` with a Run log entry: timestamp, outcome, `files_changed`, `files_unexpected`, planner notes. Appends on retry (versioned specs T-03). Skips when no `spec_path`.

### 10 — `auto_verify` (opt-in, off by default)

Runs `pytest` (or configured verify command) after a successful delegate. Sets `outcome` to `success` (tests pass) or `partial` (tests fail). Result feeds into spec report and builder history for the next attempt.

Enable:

```yaml
# .mcp-coder/config.yaml
auto_verify: true
auto_verify_cmd: "pytest tests/ -q"
```

---

## 4. Config flag matrix

| Flag | Default | Phases affected |
|------|---------|-----------------|
| `context_builder` | **on** | Phases 3–6 (picker, assemble, architect, builder) |
| `context_builder_llm` | **on** | Phase 6 only (builder brief) |
| `architect_pass` | **off** | Phase 5 |
| `spec_validation` | **off** | Phase 2 |
| `host_transcript` | `none` | Phases 2, 5, 6 (helper LLMs see transcript when `dump`) |
| `auto_verify` | **off** | Phase 10 |
| `edit_scope` | `discover` | Phase 8 (`strict` → auto-revert violations) |
| `MCP_CODER_CONTEXT_BUDGET_ENABLED` | `1` | Phase 4 budget degradation |
| `MCP_CODER_DISABLE_WORKSPACE_SNAPSHOT` | `0` | Phase 8 (off → no manifest diff, no blobs) |

---

## 5. Reading a real `delegation_pipeline` record

*(This section will be filled in with a live run — see T-07 for end-to-end trace.)*

```bash
# Get the pipeline block from the most recent delegation JSONL
# (replace <session_id> with yours from ~/.mcp-coder/projects/<key>/sessions/)
cat ~/.mcp-coder/projects/*/sessions/*/delegations.jsonl \
  | jq -s 'sort_by(.timestamp_start) | last | .context.delegation_pipeline'
```

Key things to check:

| Field | What to look for |
|-------|-----------------|
| `builder_llm.duration_ms` | +500–1500 ms is normal; higher = slow model |
| `executor.duration_ms` | Dominates; usually 10–60 s |
| Any `status: error` | Which phase failed; delegate may have continued |
| Any `status: blocked` | `spec_validation` caught something; check `clarification_needed` |
| `post_gateway.duration_ms` | Includes manifest walk; proportional to workspace size |

---

## 6. Mode differences

The pipeline does **not** run the same way for every mode:

| `mode` | Phases that run |
|--------|----------------|
| `implement` | All 10 (opt-ins depend on config) |
| `review` | Skips phases 3–7 (no context compile, no executor); spec_validation, spec_report may run |
| No `spec_path` | Phase 1 skipped; phases 2, 9 skip; 3–6 still run without spec contract |

---

## 7. Code map

| Concern | Location |
|---------|----------|
| Full pipeline orchestration | `server/mcp_server.py` — `delegate_to_agent` handler |
| Pipeline recorder | `server/mcp_server.py` — `PipelineRecorder` class |
| Spec read | `core/specs/read.py` |
| Spec validation LLM | `core/engine/spec_validation_llm.py` |
| Context phases | `core/context/` — T-04 code map |
| Executor adapter | `core/engine/aider_engine.py` |
| Post-gateway scope audit | `core/workspace/gateway.py` |
| Spec report write | `core/specs/write.py` |
| Auto-verify | `core/config/auto_verify.py`, `core/engine/auto_verify.py` |

---

## Next

- **T-07 (End-to-end trace):** pick a real `delegation_id`; walk JSONL → `history show` → `history diff` → spec report → `inspect-context` reconstruction — using all the tools from T-01–T-06
