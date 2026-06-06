# Worker spec: {TASK_ID} — {MILESTONE_TITLE}

**Task ID:** {TASK_ID}  
**PM doc:** [PHASE1_MVP.md](./PHASE1_MVP.md)  
**Technical ref:** [PHASES.md](./PHASES.md)  

> **Template only** — lives in git so we can copy it. **Never commit** the copy.  
>  
> `cp docs/TASK_SPEC_TEMPLATE.md docs/tasks/P2-{milestone}-{name}.md` (or `P1-…` for legacy)  
> Fill from [PHASE2_MVP.md](./PHASE2_MVP.md) or [PHASE1_MVP.md](./PHASE1_MVP.md) § {TASK_ID}.  
> **Worker uses only the attached `docs/tasks/…` file** — self-contained spec with links; no PM doc edits. See `.cursor/rules/mcp-coder-vision.mdc`.

---

## Files policy (workers must follow)

### Workers **may** edit

- `core/`, `server/`, `main.py`, `tests/`
- Root **`README.md`**, **`.env.example`**, `pyproject.toml` (if required for the task)
- **`docs/notes/`** files **explicitly listed** in this spec under Docs (e.g. `storage-and-linking.md`)
- **`docs/examples/`** only if this spec says so

### Workers **must not** edit (master / planning session only)

- **`docs/IDEA.md`** — vision; not a working doc. No milestone updates, no status churn.
- **`docs/PHASES.md`**, **`docs/PHASE1_MVP.md`**, **`docs/PHASE2_MVP.md`**, **`docs/BACKLOG.md`**
- **`docs/PHASE1_ISSUES.md`**, **`docs/PHASE2_ISSUES.md`** — worker lists IDs in § Results; **master** updates trackers
- **`docs/notes/phase2-owned-context.md`** — unless explicitly listed in § Scope
- Other `docs/tasks/*.md` (sibling specs)
- Do not expand scope into Makefile / singleton / config.yaml unless **listed in § Scope** below

If something belongs in IDEA or the PM board, write it under **§ Results → Suggested for master session** (bullets only).

**Phase 2:** No Aider-specific logic in `core/specs/` or `core/context/` — validate **behavioral contract** only; backend code stays in `core/engine/`.

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
