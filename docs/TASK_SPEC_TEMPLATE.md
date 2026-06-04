# Worker spec: {TASK_ID} — {MILESTONE_TITLE}

**Task ID:** {TASK_ID}  
**PM doc:** [PHASE1_MVP.md](./PHASE1_MVP.md)  
**Technical ref:** [PHASES.md](./PHASES.md)  

> **Template only** — lives in git so we can copy it. **Never commit** the copy.  
>  
> `cp docs/TASK_SPEC_TEMPLATE.md docs/tasks/P1-{milestone}-{name}.md`  
> Fill from [PHASE1_MVP.md](./PHASE1_MVP.md) § {TASK_ID}. Worker session uses **only** the `docs/tasks/…` file.

---

## Files policy (workers must follow)

### Workers **may** edit

- `core/`, `server/`, `main.py`, `tests/`
- Root **`README.md`**, **`.env.example`**, `pyproject.toml` (if required for the task)
- **`docs/notes/`** files **explicitly listed** in this spec under Docs (e.g. `storage-and-linking.md`)
- **`docs/examples/`** only if this spec says so

### Workers **must not** edit (master / planning session only)

- **`docs/IDEA.md`** — vision; not a working doc. No milestone updates, no status churn.
- **`docs/PHASES.md`**, **`docs/PHASE1_MVP.md`**, **`docs/BACKLOG.md`**
- **`docs/PHASE1_ISSUES.md`** — worker lists issue IDs in § Results; **master** updates the tracker
- Other `docs/tasks/*.md` (sibling specs)
- Do not expand scope into Makefile / singleton / config.yaml unless **listed in § Scope** below

If something belongs in IDEA or the PM board, write it under **§ Results → Suggested for master session** (bullets only).

---

## Goal

{One paragraph.}

---

## Scope

### Create

- {files / modules}

### Behavior

- {tool name, params, returns}

### Config env

```
# document env vars
```

---

## Out of scope

- {explicit exclusions}

---

## Done when

- [ ] {acceptance criteria}

---

## Results (worker fills after implementation)

**Date:**  
**Sample `delegation_id`:**  
**Notes / blockers:**  

```json
// paste one sample delegations.jsonl line
```
