---
epic_id: ""          # slug, e.g. expense-splitter (matches epics/<epic_id>.md)
created: ""          # ISO date
status: open         # planner: open | in_progress | done
---

# Epic spec

> **Planner-owned** — north star for a multi-step feature.  
> Create **one step task** per delegation: `.mcp-coder/specs/tasks/<epic_id>-<step>.md`  
> Pass that step path as `spec_path` on `delegate_to_agent`. Keep completed step specs for audit.

---

## Goal

What the whole feature delivers and why.

---

## Steps

Track step task specs (create a new file before each implement step; do not recycle one file for all steps):

| Step | Task spec | Planner status |
|------|-----------|----------------|
| 1 | `tasks/<epic_id>-01-….md` | open / done |
| 2 | `tasks/<epic_id>-02-….md` | open / done |

After each delegate: read `reports/<same-name>.md` for Run log; update this table and step spec `Done when` when verified.

---

## Out of scope

What this epic explicitly does not include.
