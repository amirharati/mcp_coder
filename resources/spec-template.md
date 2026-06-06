---
spec_id: ""          # step slug, e.g. expense-splitter-02-cli (Cursor fills)
epic: ""             # epic slug → .mcp-coder/specs/epics/<epic>.md
step: ""             # optional step number or label
revision: 1          # planner bumps when Scope/Constraints change after worker review
created: ""          # ISO date, e.g. 2026-06-05
status: draft        # planner: draft | ready | done
supersedes: ""       # optional prior step spec_id this replaces
---

# Step task spec

> **Planner-owned only** — one file per delegatable step; reuse across **review** and **implement** delegates.  
> **MCP reports:** `.mcp-coder/specs/reports/<same-filename>.md` (Run log, Worker feedback).  
> **Workflow:** optional `mode=review` → update spec (`revision++`, `status: ready`) → `mode=implement`.

---

## Goal

One paragraph: what this **step** achieves.

---

## Scope

What is in / out for **this step** only.

---

## Files

Repo-relative paths for **implement** — list in the spec, then pass **all** of them in `target_files`.

### Edit

Files this step creates or modifies:

- `path/to/new_module.py`

### Read (include in target_files)

Prior-step or dependency files Aider must see (full text loaded; not edited this step):

- `path/to/step1_api.py` — public API from step 1

**Cross-step example:** step 2 implements CLI that imports `step1_api.py` → `target_files` = `[cli.py, step1_api.py]` even though only `cli.py` is edited.

---

## Constraints

- Decisions, APIs, style, env, “do not change X”

---

## Done when

- [ ] Observable acceptance criterion 1
- [ ] …

---

## Plan (optional)

Notes for this step.

1. …

---

## Revision log

<!-- planner: brief note when revision front matter bumps -->

- r1 — initial
