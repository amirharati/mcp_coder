# T-03: Specs — contract, paths, versioning

**Goal:** Understand the spec file contract end-to-end — where files live, what the planner writes vs what mcp-coder owns, how `spec_path` is resolved, how the Files section becomes enforcement, and how review → implement → retry fits together.

**The mental model (read first):**

- **Planner (Cursor agent)** authors **task specs** and **epic specs** under `.mcp-coder/specs/`. You normally do not hand-write these; synced rules tell the planner when and how. This tutorial explains the contract so you can *read* and *debug* what the planner produced.
- **mcp-coder** owns **delegation reports** — one parallel file per task spec — and appends Run log entries after every `delegate_to_agent` call that uses `spec_path`.
- **Versioning is two-layered (planner-managed, not MCP-automated):**
  - **Filename:** synced rules tell the planner to create `…-v1.md` from the first attempt; on **implement failure**, create `…-v2.md` (keep v1 + its report as audit). mcp-coder never renames or creates these files — it only pairs reports by matching filename.
  - **Front matter `revision`:** bump on the **same** file when refining after `mode=review` (before first implement). Not used for v1→v2 file hops.
  - **No `specs/attempts/` archive in code** (BL-320b deferred); audit trail = versioned spec+report pairs + JSONL.

**Prerequisites:** T-01 (one delegation ran) and T-02 (you can read a JSONL record).

**Estimated time:** 20–25 min.

---

## 1. Two kinds of markdown

| Kind | Path | Who writes | Purpose |
|------|------|------------|---------|
| **Epic spec** | `.mcp-coder/specs/epics/<slug>.md` | Planner | North star for a multi-step feature; linked from task specs via `epic:` front matter |
| **Step task spec** | `.mcp-coder/specs/tasks/<name>.md` | Planner | One delegatable step; passed as `spec_path` on `delegate_to_agent` |
| **Delegation report** | `.mcp-coder/specs/reports/<same-filename>.md` | mcp-coder | Audit trail: Run log, Status, Worker feedback, Blockers |

Templates are copied into the workspace on first server startup or first delegate:

```
.mcp-coder/
  spec-template.md              ← copy of resources/spec-template.md
  spec-epic-template.md
  spec-report-template.md
  specs/
    tasks/                      ← planner step specs
    epics/                      ← planner epic specs
    reports/                    ← mcp-coder audit (parallel filenames)
```

`ensure_workspace_spec_layout()` creates the directories and templates if missing; it never overwrites an existing template.

---

## 2. `spec_path` — accepted forms and errors

`delegate_to_agent` accepts an optional `spec_path` pointing at a **step task** only.

**Accepted:**

| You pass | Normalized to |
|----------|----------------|
| `tasks/my-feature-01-core.md` | `.mcp-coder/specs/tasks/my-feature-01-core.md` |
| `.mcp-coder/specs/tasks/my-feature-01-core.md` | (unchanged) |

**Rejected:**

- Paths under `specs/epics/` or `specs/reports/` — those are not step tasks
- Legacy repo-root `specs/tasks/...` — error message suggests moving to `.mcp-coder/specs/tasks/`
- Missing file — `outcome: invalid_spec` with a hint to copy `spec-template.md`

Example MCP call (planner-side):

```json
{
  "task": "Implement CLI entrypoint per spec",
  "target_files": ["src/cli.py", "src/api.py"],
  "context_summary": "User wants argparse CLI; api.py is read-only dep from step 1.",
  "spec_path": "tasks/my-feature-02-cli.md",
  "mode": "implement"
}
```

---

## 3. Task spec anatomy

Open `.mcp-coder/spec-template.md` (or any file in `specs/tasks/`) as the canonical shape.

### Front matter (YAML)

| Field | Who sets | Meaning |
|-------|----------|---------|
| `spec_id` | Planner | Stable slug for this step (often matches filename stem) |
| `epic` | Planner | Slug → loads `.mcp-coder/specs/epics/<epic>.md` into the executor prompt when present |
| `step` | Planner | Optional label (e.g. `2` or `cli`) |
| `revision` | Planner | Integer; **bump manually** when Scope/Constraints change after review |
| `created` | Planner | ISO date |
| `status` | Planner | `draft` → `ready` → `done` (planner convention; not enforced by mcp-coder) |
| `supersedes` | Planner | Optional prior `spec_id` this step replaces — **documentation only**; code does not auto-archive old files |

**Optional delegation policies** (YAML lists override the markdown `## Files` section when non-empty):

```yaml
files_edit:
  - src/cli.py
files_read:
  - src/api.py
edit_scope: discover    # discover | strict
allow_create: true
untracked_policy: materialize   # parsed + logged; gateway enforcement is edit_scope / files_edit today
```

Defaults when omitted: `edit_scope: discover`, `allow_create: true`, `untracked_policy: materialize`.

### Body sections (planner-owned)

These `##` headings are compiled into the executor prompt (in order):

1. **Goal**
2. **Scope**
3. **Files**
4. **Constraints**
5. **Done when**
6. **Plan** (optional)

Empty sections are skipped. If the epic file exists and `epic:` is set, **Goal**, **Steps**, and **Out of scope** from the epic are prepended under `## Epic context (linked)`.

The compiled block is stored in the delegation record as part of the prompt path; JSONL also carries `spec_path`, `spec_sha256`, and `delegation_policies` when the spec was valid.

---

## 4. The `## Files` contract

The Files section defines what the executor may touch. Parse rules (`core/specs/files_contract.py`):

### Preferred shape

```markdown
## Files

### Edit

Files this step creates or modifies:

- `src/cli.py`

### Read (include in target_files)

Dependency files the executor must see but not edit:

- `src/api.py` — public API from step 1
```

- Paths are repo-relative, usually in backticks.
- Placeholders like `(none)` or `n/a` are ignored.

### Fallback

If there are no `### Edit` / `### Read` subsections, every bullet under `## Files` is treated as **edit** paths.

### YAML override

If `files_edit` or `files_read` in front matter is a **non-empty** list, that list wins over the markdown subsection for that side.

`delegation_policies` in the JSONL record is the resolved contract:

```json
{
  "files_edit": ["src/cli.py"],
  "files_read": ["src/api.py"],
  "edit_scope": "discover",
  "allow_create": true,
  "untracked_policy": "materialize"
}
```

---

## 5. `target_files` and auto-adding read deps

> **Not git merge. Not an Aider feature.**  
> The config flag is named `auto_merge_spec_read`, but mcp-coder only **unions two lists**: your `target_files` + spec **`files_read`** paths that were omitted. It does **not** merge branches, apply patches, or let the executor edit outside the spec contract.

The planner passes `target_files` on every delegate. For **`mode=implement`** with a valid **`spec_path`** and a non-empty Files contract:

| Step | What mcp-coder does |
|------|---------------------|
| 1 | Start from planner `target_files` → `effective_target_files` |
| 2 | If **`auto_merge_spec_read`** is on (default **true**), append any spec **`files_read`** path not already in the list — recorded as `auto_merged_read_paths` in the response / JSONL |
| 3 | **`files_edit` paths are never auto-added** — if an edit path is missing from `target_files`, you get a non-blocking **`contract_warnings`** entry (MCP response + JSONL + server log) |
| 4 | Pass **`effective_target_files`** to the executor so Aider **opens** those files (read deps get full text in context) |

**When merge is off** (`auto_merge_spec_read: false` in `.mcp-coder/config.yaml` or `MCP_CODER_AUTO_MERGE_SPEC_READ=0`): no list union; warnings fire for **any** spec path (edit **or** read) missing from `target_files`.

**Without `spec_path`:** this whole path is skipped — only what the planner sent is used.

**Rule of thumb for planners:** still list every **Edit** and **Read** path in `target_files`. Auto-add is a safety net so step N+1 doesn’t fail when read-deps were declared in the spec but forgotten on the MCP call.

**Example:** spec Read lists `src/api.py`; planner sends `target_files: ["src/cli.py"]` only.

```
planner target_files     →  ["src/cli.py"]
auto_merged_read_paths   →  ["src/api.py"]        # added by mcp-coder
effective_target_files   →  ["src/api.py", "src/cli.py"]   # passed to Aider
mcp_request.target_files →  ["src/cli.py"]        # original call preserved in audit
```

Cross-step case (from the template): step 2 edits `cli.py` but must read `api.py` from step 1 — ideal call is `target_files: ["src/cli.py", "src/api.py"]`; if the planner omits `api.py`, auto-add covers it when enabled.

Dry-run without a backend:

```bash
mcp-coder inspect-context \
  --task "CLI per spec" \
  --target-files src/cli.py,src/api.py \
  --context-summary "Step 2 CLI" \
  --spec tasks/my-feature-02-cli.md
```

Inspect `effective_target_files` / adapter preview in the output.

### Naming: guide vs code (align later)

This guide says **auto-adding read deps** on purpose. The **code and config keys still say “merge”**, which reads like git/Aider merge:

| What you read here | Identifier in code / config / JSONL |
|--------------------|-------------------------------------|
| auto-add read deps (on/off) | `auto_merge_spec_read` in `.mcp-coder/config.yaml`; env `MCP_CODER_AUTO_MERGE_SPEC_READ` |
| paths mcp-coder appended | `auto_merged_read_paths` in delegate response + JSONL |
| implementation | `core/config/auto_merge.py`, `core/specs/read_deps_merge.py` |

Behavior is defined by the code above; the guide vocabulary is the intended mental model. Renaming config keys / JSONL fields for clarity is **not done yet** — track as naming cleanup when we touch config or a major doc pass (no behavior change required).

---

## 6. Delegate modes: review → implement

| `mode` | File edits | `target_files` | Typical use |
|--------|------------|------------------|-------------|
| `implement` (default) | Yes | Non-empty (paths to open in executor) | Ship the step |
| `review` | No | **Must be `[]`** | Spec review LLM asks questions; output appended to report **Worker feedback** |

**Review workflow** (planner convention, encoded in templates and cursor rules):

1. `mode=review`, `spec_path=tasks/...`, `target_files=[]` — no file changes.
2. Read `.mcp-coder/specs/reports/<same-name>.md` → **Worker feedback** and **Suggested next**.
3. Planner updates the **task spec** (clarify Scope/Files/Constraints; bump `revision`; set `status: ready`).
4. `mode=implement` with full `target_files`.

If you pass non-empty `target_files` with `mode=review`, the delegate fails early with a clear error (no backend run).

**Outcomes** when `spec_path` is set (`core/specs/outcome.py`):

| Outcome | Typical cause |
|---------|----------------|
| `invalid_spec` | Bad path, missing file, invalid policy YAML |
| `review` | `mode=review` succeeded |
| `success` | Implement succeeded with at least one file changed |
| `partial` | Implement succeeded but no files changed (or verify downgrade) |
| `failed` | Backend error, review failure, etc. |
| `needs_input` | Failure with blockers written to report |
| `scope_violation` | `edit_scope: strict` and executor edited outside `files_edit` |

---

## 7. Post-delegation gateway (`edit_scope`)

After the executor runs, mcp-coder compares `files_changed` to `files_edit`:

- **`edit_scope: discover`** (default): edits outside `files_edit` are allowed but recorded. Non-strict violations appear in JSONL as `files_unexpected`; the report may get a **Scope expansion** section suggesting you update the spec.
- **`edit_scope: strict`**: paths outside `files_edit` trigger **scope_violation**; strict mode may revert those paths (when snapshot data exists). Report gets **Blockers** and **Suggested next** pointing back to the spec.

This phase appears in JSONL as `context.delegation_pipeline.post_gateway` (implement + valid spec + Phase 4+).

---

## 8. Delegation reports (what mcp-coder writes)

On first delegate with a given `spec_path`, mcp-coder creates `specs/reports/<same-filename>.md` from the report template (if missing), linking `task_spec` and `spec_id`.

After each delegate, `apply_post_delegation_report_updates()` appends:

| Section | Content |
|---------|---------|
| **Run log** | Timestamped entry: `delegation_id`, mode, success, `files_changed`, output preview, errors |
| **Status** | `delegated_ok`, `blocked`, or `reviewed` (YAML `status` synced) |
| **Worker feedback** | Review-mode success output |
| **Scope expansion** | Discover-mode unexpected paths, or strict violation detail |
| **Blockers / questions** | Failure text or scope violations |
| **Suggested next** | Hints (e.g. bump revision, re-delegate) |

**Planner still owns** the task spec body and front matter (`revision`, `status: done`, Done when checkboxes). mcp-coder does not edit task specs.

---

## 9. Versioning and retries

There are **two planner conventions** (synced cursor rules v14 — `use-mcp-coder.default` / `.strict`). mcp-coder implements neither automatically; it only reads whatever `spec_path` you pass and writes the matching report.

### A. Review refine (same file)

After optional `mode=review`, the planner updates the **same** spec file:

- Bump `revision` in front matter; set `status: ready`
- Optional note in `## Revision log`
- Then `mode=implement` with the same `spec_path`

Locked since Phase 1 (D-SPEC-5): one task file for review + first implement.

### B. Implement failure retry (new filename)

After a failed implement (or judgment loop says retry), synced rules say:

1. **Do not edit** the failed spec (e.g. `calc-02-cli-v1.md`) — it stays frozen as that attempt’s contract.
2. **Create** `calc-02-cli-v2.md` with fixes (Files, constraints, `### Retry note`).
3. Delegate with `spec_path` pointing at **v2**. mcp-coder creates `reports/calc-02-cli-v2.md` automatically (name pairing).

```
.mcp-coder/specs/tasks/calc-02-cli-v1.md    ← attempt 1 (planner: do not touch after delegate)
.mcp-coder/specs/reports/calc-02-cli-v1.md ← attempt 1 audit (mcp-coder-owned)
.mcp-coder/specs/tasks/calc-02-cli-v2.md    ← retry spec (planner creates)
.mcp-coder/specs/reports/calc-02-cli-v2.md  ← retry audit
```

Shipped as **rules-only** in Phase 3 (P3-320 / D-P3-6) — no MCP rename step required because reports already mirror task filenames.

### What mcp-coder code does

| Mechanism | In code? |
|-----------|----------|
| Read `revision` / `supersedes` from front matter | Yes (parse only; never bumps or enforces) |
| Pair report path to task filename | Yes (`report_path_for_task_spec`) |
| `prior_failed_attempts` on delegate response | Yes — recent failures for same session/spec (JSONL + `workspace_history.db`) |
| Auto-create `…-v2.md` | **No** |
| Write `specs/attempts/<id>/…` archive files | **No** (BL-320b still backlog) |
| Enforce filename `-vN` pattern | **No** — convention lives in synced rules |

`supersedes` in front matter is documentation for humans/planner; code does not move or archive files.

Use `list_delegations(spec_path=…)` (T-05) to see all attempts when filenames or sessions differ.

---

## 10. Optional pre-delegate spec validation

Off by default. Enable per workspace:

```yaml
# .mcp-coder/config.yaml
spec_validation: true
```

Or `MCP_CODER_SPEC_VALIDATION=1`.

When on, an LLM pass may block implement with `clarification_needed` before the executor runs. JSONL fields: `spec_validation_ran`, `spec_validation_passed`, and `model_roles.spec_validation` when it ran.

Try this in a later experiment (T-06 / Phase 4.5 Track 3); not required for the basic review → implement loop.

---

## 11. What to check in JSONL after a spec-backed delegate

Open the record (T-02) or `mcp-coder view delegations`:

| Field | What to verify |
|-------|----------------|
| `spec_path` | Normalized `.mcp-coder/specs/tasks/...` path |
| `spec_sha256` | Changes when the planner edits the task spec |
| `delegation_policies` | Resolved edit/read lists and `edit_scope` |
| `files_requested` vs `files_changed` | Planner intent vs executor result |
| `auto_merged_read_paths` | Spec **Read** paths mcp-coder appended to `effective_target_files` (not git merge) |
| `contract_warnings` / `spec_files_missing_from_target` | Spec paths missing from planner `target_files` (edit paths always; read too if auto-add off) |
| `scope_violations` / `files_unexpected` | Gateway findings |
| `outcome` | See table in §6 |
| `context.delegation_pipeline` | Phase timings (implement + valid spec only) |
| `model_roles` | Per-role models with live token counts and `policy_applied` provenance (Phase 9) |

MCP tool responses expose some fields at the top level (e.g. `delegation_pipeline`); JSONL nests pipeline under `context` — see T-02.

---

## 12. Epic + multi-step sketch

```
.mcp-coder/specs/
  epics/expense-splitter.md          ← Goal, Steps table, Out of scope
  tasks/expense-splitter-01-api.md   ← step 1 implement
  tasks/expense-splitter-02-cli.md   ← step 2; epic: expense-splitter; Read lists 01 deliverables
  reports/expense-splitter-01-api.md ← mcp-coder Run log for step 1
  reports/expense-splitter-02-cli.md
```

Step N+1 **implement** should list step N deliverables under **Read** and include them in `target_files` (epic template calls this out).

---

## 13. Quick reference — code map

| Concern | Module |
|---------|--------|
| Path normalization | `core/specs/paths.py` |
| Read + prompt compile | `core/specs/read.py`, `sections.py` |
| Files parsing | `core/specs/files_contract.py` |
| Policies | `core/specs/delegation_policies.py` |
| Read-deps list union (`auto_merge_spec_read`) | `core/specs/read_deps_merge.py` |
| Report updates | `core/specs/write.py` |
| Bootstrap | `core/specs/bootstrap.py` |
| MCP wiring | `server/mcp_server.py` (`delegate_to_agent`) |

Bundled templates: `resources/spec-template.md`, `spec-epic-template.md`, `spec-report-template.md`.

---

## Next

- **T-04 (Context compiler):** `inspect-context` dry-run — tiers, builder LLM, what Aider actually sees for a spec-backed delegate
- **T-06 (Delegation pipeline):** full `delegate_to_agent` phase list and config flag matrix
- **BL-343:** structured delegation viewer is now shipped in Phase 9 (`view_events[]` middleware + boundary-table UI in `mcp-coder view delegations`)
