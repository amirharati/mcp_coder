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

Repo-relative paths the executor may touch on **implement** (include files to **read** for imports, not only edits):

- `path/to/file.py`

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
