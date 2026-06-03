# Phase 1 MVP — Product manager doc

**Status:** Planning  
**Host:** Cursor only (experiments)  
**Technical reference:** [PHASES.md](./PHASES.md) § Phase 1  
**Vision:** [IDEA.md](./IDEA.md)  
**Deferred work:** [BACKLOG.md](./BACKLOG.md)

---

## Purpose of this doc

- **What:** Track Phase 1 scope, tasks, status, and acceptance criteria.
- **How we build:** Same pattern we want from the product—**delegate focused work to a worker session** with a tight spec, then review logs/artifacts.
- **Not here:** Phase 2+ delivery (see [PHASES.md](./PHASES.md)); unscheduled ideas go to [BACKLOG.md](./BACKLOG.md).

---

## Phase 1 summary (one paragraph)

Prove Cursor → MCP → Aider delegation with **pass-through context** (Cursor summary or SpecStory transcript), **structured JSONL logs** on every call, and **configurable session policies** (fallback: default `always_new`; SpecStory: hash/path). No owned context pipeline, no RAG. Optional: cheap LLM for fallback session boundary (no SpecStory) if time permits.

---

## Workflow (planning chat ↔ worker session)

| Step | Where | What |
|------|--------|------|
| **1. Plan** | **This chat** (architect / PM) | Pick task; draft scope in § below; **create** `docs/tasks/P1-{…}.md` from [TASK_SPEC_TEMPLATE.md](./TASK_SPEC_TEMPLATE.md) (**local, never commit**) |
| **2. Implement** | **New session** (worker) | Attach `docs/tasks/P1-{…}.md` only — *Implement per attached spec; that scope only.* |
| **3. Report** | **Back to this chat** | Results in that local file § Results + short summary here → update task board below (git) |
| **4. Next** | This chat | Mark task `done`, unblock next, or revise spec and re-run worker |

Same pattern we want from the product: **thin planner, focused executor, closed loop.**

**Rules for each worker session:**

1. **One milestone only** (e.g. 1.0, not 1.0+1.2).
2. Spec doc lists: goal, files to create, out-of-scope, env vars, done-when checklist.
3. Worker does **not** expand scope; unknowns go to [BACKLOG.md](./BACKLOG.md) or open questions below.
4. After run: worker writes **one sample** `delegations.jsonl` line + notes in **local** `docs/tasks/P1-{…}.md` § Results (still not committed).

**Local spec path (examples):** `docs/tasks/P1-1.0-barebones-mcp-aider.md`, `docs/tasks/P1-1.1-schema-fields.md` — copy template, fill from § Task details below.

---

## Milestones & task board

| Milestone | Task ID | Status | Local spec (`docs/tasks/`, gitignored) | Summary |
|-----------|---------|--------|----------------------------------------|---------|
| **1.0** Barebones + logging | P1-100 | `todo` | `P1-1.0-barebones-mcp-aider.md` | MCP + Aider adapter + fallback summary + JSONL log + `always_new` |
| **1.1** Richer schema | P1-110 | `blocked` | `P1-1.1-schema-fields.md` | After 1.0 done |
| **1.2** SpecStory mode | P1-120 | `blocked` | `P1-1.2-specstory.md` | After 1.1 done |
| **1.3** Session policies | P1-130 | `blocked` | `P1-1.3-session-policies.md` | After 1.2 done |
| **1.3 opt** Cheap LLM classifier | P1-131 | `optional` | `P1-1.3-cheap-llm-classifier.md` | Fallback only; if time |

Scope bullets for each task stay in **§ Task details** below (git). The `docs/tasks/*.md` file is the filled-in handoff copy for the worker.

Status values: `todo` | `in_progress` | `done` | `blocked` | `optional`

---

## Task details

### P1-100 — Milestone 1.0: Barebones delegation + logging

**Goal:** Cursor can call `delegate_to_agent`; Aider edits files; one JSONL record explains the call.

**In scope**

- [ ] Python package layout (`pyproject.toml`, `main.py --mcp`)
- [ ] MCP stdio server, tool `delegate_to_agent`
- [ ] Tool params: `task`, `target_files`, `context_summary`
- [ ] `ExecutionEngine` protocol + `AiderEngine` (Python API, `InputOutput(yes=True)`)
- [ ] Assemble prompt: `context_summary` + `task`; `fnames=target_files`
- [ ] `core/logging/delegation_log.py` → `.mcp-coder/logs/delegations.jsonl`
- [ ] Log fields per [PHASES.md](./PHASES.md) § Observability (minimal set for 1.0)
- [ ] Session: `MCP_CODER_FALLBACK_SESSION=always_new`; `session_policy=fallback:always_new`
- [ ] Return: `success`, `output` (tail), `files_changed` (best-effort), `session_reused=false`, `session_reason`
- [ ] `.gitignore`: `.mcp-coder/logs/`, venv, `.env`
- [ ] README: install, Cursor `mcp.json` snippet, env vars

**Out of scope**

- SpecStory, session reuse, heuristic, cheap_llm classifier
- `explicit_constraints` / `code_snippets_from_chat`
- RAG, router LLM, CLI mode, OpenCode adapter
- Full prompt in logs (preview only unless debug env)

**Done when**

- [ ] Cursor invokes tool on a real repo; file changes appear in editor
- [ ] `delegations.jsonl` has one complete line: timing, model, mcp_request, context preview/hash, response
- [ ] Experiment note filled in worker spec § Results

**Local spec:** Create `docs/tasks/P1-1.0-barebones-mcp-aider.md` from template using this section (not committed).

---

### P1-110 — Milestone 1.1: Smarter MCP schema (fallback)

**Depends on:** P1-100 `done`

**In scope**

- [ ] Add `explicit_constraints`, `code_snippets_from_chat` to schema + prompt assembly
- [ ] Tune tool description for Cursor to populate fields
- [ ] Log new fields inside `mcp_request` / context hashes

**Done when**

- [ ] Experiment: nuance (hex code, exact API name) reaches Aider prompt (verify via log preview or `MCP_CODER_LOG_FULL_PROMPT=1`)

---

### P1-120 — Milestone 1.2: SpecStory context mode

**Depends on:** P1-110 `done`

**In scope**

- [ ] `core/context/specstory.py` — newest `.specstory/history/*.md`, freshness window
- [ ] `context_mode=specstory` when used; else fallback
- [ ] Log `specstory_path`, `specstory_hash`, `specstory_bytes`
- [ ] Docs: recommend SpecStory extension

**Out of scope**

- SpecStory session reuse (that’s 1.3)

**Done when**

- [ ] With SpecStory on: long chat → delegate → log shows full transcript injected
- [ ] Without SpecStory: fallback unchanged

---

### P1-130 — Milestone 1.3: Session policies

**Depends on:** P1-120 `done`

**In scope**

- [ ] `core/session.py` — in-process singleton, metadata
- [ ] SpecStory: reuse if path+hash unchanged; else new (`specstory:context`)
- [ ] Fallback: `heuristic` policy (time, files, summary hash)
- [ ] Env: `MCP_CODER_FALLBACK_SESSION`, `MCP_CODER_REUSE_MAX_AGE_SEC`
- [ ] MCP return + log: `session_reused`, `session_reason`, `session_policy`
- [ ] Run experiments 1–4 from [PHASES.md](./PHASES.md) § 1.3; write summary in this doc § Experiment results

**Done when**

- [ ] Policies configurable and always logged
- [ ] Short write-up: preferred policy per mode (fallback vs SpecStory)

---

### P1-131 — Optional: Cheap LLM session classifier (fallback only)

**Depends on:** P1-130 in progress or done  
**Priority:** Only if time

**In scope**

- [ ] `MCP_CODER_FALLBACK_SESSION=cheap_llm`
- [ ] One mini/Flash call: new vs reuse; log `session_classifier` block
- [ ] Compare to `always_new` / `heuristic` in experiment notes

**Done when**

- [ ] Decision documented: keep, defer to backlog, or adopt as default

---

## Phase 1 success checklist (release MVP)

Copy from [PHASES.md](./PHASES.md); check when **P1-130** (and experiments) complete:

- [ ] Cursor uses tool for non-trivial coding when prompted
- [ ] Low token use on Cursor side (tool + summary, not full agent loop on host)
- [ ] Aider completes scoped file edits; user reviews in Cursor
- [ ] Mode A vs Mode B limitations documented (README or `docs/`)
- [ ] Every delegation has complete JSONL record
- [ ] Experiment notes captured for Phase 2 planning (grounded in logs)

---

## Open questions (PM track)

| # | Question | Owner | Resolution |
|---|----------|-------|------------|
| Q1 | Does Cursor pass `target_files` reliably? | Experiment 1.0+ | |
| Q2 | Best tool name/description for routing? | Experiment + BL-405 | |
| Q3 | SpecStory freshness window default? | Experiment 1.2 | |
| Q4 | Prompt size vs model failure threshold? | Experiment + BL-403 | |
| Q5 | Default session policy after 1.3? | Experiment results § below | |

---

## Experiment results (fill as we go)

### 1.0 — First delegation

| Field | Value |
|-------|-------|
| Date | |
| Repo | |
| delegation_id | |
| Notes | |

### 1.3 — Session policy comparison

| Policy | Follow-up quality | `prompt_tokens_est` | Notes |
|--------|-------------------|---------------------|-------|
| `always_new` | | | |
| `heuristic` | | | |
| `cheap_llm` | | | |
| SpecStory hash | | | |

---

## Next action

1. In planning chat: `cp docs/TASK_SPEC_TEMPLATE.md docs/tasks/P1-1.0-barebones-mcp-aider.md` and fill from § P1-100.
2. New worker session: attach **`docs/tasks/P1-1.0-barebones-mcp-aider.md`** — *Implement per attached spec; scope 1.0 only.*
3. Report back: § Results in that local file + update P1-100 → `done` here; unblock P1-110.

---

## After Phase 1 (product ideas from our workflow)

We are dogfooding **plan → local spec → worker → report**. Once P1 works, consider product adaptations — e.g. **spec-based delegation** so executors get a structured task contract instead of only full chat history. See [notes/spec-based-development.md](./notes/spec-based-development.md) and backlog BL-150.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-03 | Initial PM doc; docs moved to `docs/` |
| 2026-06-03 | Note: spec-based development (post-P1) |
