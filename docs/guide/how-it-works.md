# How mcp-coder works

**Purpose:** the mental model. Everything you need to keep in your head to operate, debug, or extend the system. Re-read when coming back after a break.

**Covers:** Phases 1–13 as shipped. **Last updated:** 2026-06-23.

Deeper detail: [architecture/overview.md](./architecture/overview.md), [code-structure.md](./code-structure.md), [terminology.md](./terminology.md), [reference/](./reference/). Refined design map: [../notes/system-design-overview.md](../notes/system-design-overview.md).

---

## 1. What it is, in one paragraph

mcp-coder is an MCP server where a **host agent** (Cursor today) delegates implementation work through `delegate_to_agent`, while mcp-coder owns the disciplined middle: spec contract, context compiling, scoped subagents (planner, clarity, reviewer, …), a **persistent Supervisor agent** that runs the delegation lifecycle, executor orchestration, verification, audit trails, and **project memory across delegations**.

The host stays user-facing and strategic. The executor gets a focused prompt. mcp-coder is the partner layer that makes that split safe, observable, and continuous across many delegations — not a stateless subprocess that forgets everything each call.

**Why this split is worth it:**

1. **Right-sized model per role, with escalation as a future direction** — executor is not assumed cheap; helpers (validation, planner, supervisor, reviewer) can use different tiers. Host `model_policy` and the registry resolve this today; auto-escalation remains backlog (BL-162).
2. **An imposed workflow that improves execution** — spec → compiled context → supervised execution → gateway → verify → audit raises first-pass success rate and shortens repair loops.

---

## 2. The actors

```
User <-> Host agent (Cursor)
              |
              | delegate_to_agent / answer / inspect / search …
              v
         mcp-coder
              |
              +-- preloop helpers (clarity, spec validation, planner, context compile)
              +-- SupervisorAgent (lifecycle, pause/resume, project memory, subagent routing)
              |       +-- Executor (Aider today)
              |       +-- Reviewer, confirm-ask supervision, tools
              +-- storage, traces, RAG, viewer
```

| Actor | Role today | Notes |
|-------|------------|-------|
| **Host** | Cursor (+ rules) | Talks to user, calls MCP tools, judges results. Does **not** own mcp-coder project memory. |
| **SupervisorAgent** | `core/engine/supervisor_agent.py` | Persistent **project workflow agent** inside mcp-coder. Owns post-planning lifecycle, pause/resume, checkpoint, project-state writes. |
| **Helpers / subagents** | clarity, validation, planner, builder, reviewer | Stateless per call; Supervisor or preloop pipeline coordinates them. |
| **Executor** | Aider + provider | Edits files; only sees compiled `ContextPackage`. |

> **Adapter rule:** Cursor-specific code lives in `core/host/`; Aider-specific code in `core/engine/aider_engine.py` + `core/config/aider_runtime.py`. Everything else in `core/` is backend-neutral.

---

## 3. The unit of work: a delegation

Everything revolves around `delegate_to_agent(task, target_files, context_summary, spec_path?, mode?, model_policy?, answer?, start_fresh?)`.

| Mode | Behavior |
|------|----------|
| **`implement`** | Full pipeline; executor may edit files. |
| **`review`** | Questions only; `target_files` must be `[]`. |

Each delegation produces:

- a **response payload** for the host (`success`, `outcome`, `files_changed`, `judgment_checklist`, …)
- a **lean row** in `delegations.jsonl` + a **trace** in `traces/<delegation_id>.jsonl`
- workspace history + RAG index updates
- optional spec report append
- **project state** updates (decisions, risks, reviewer findings) when Supervisor persists them
- **`agent_state.json` checkpoint** at delegation end (cross-process Supervisor continuity)

### Pause and resume

A delegation can **pause** instead of finishing:

- **Clarity-block** — preloop questions; host may edit spec Q&A and re-delegate; clarity-block path can auto-resume on host return.
- **Escalation pause** — Supervisor needs host input mid-loop; host passes **`answer`** on the next `delegate_to_agent` (or uses `answer_delegation_question` while in-flight when supported).

Use **`start_fresh=true`** to abandon a paused state and run a cold delegation. Completed preloop work should not replay blindly on resume when policy allows skip.

---

## 4. The delegation pipeline

For `mode=implement` with a valid spec, think in two layers:

**Preloop (server + helpers):**

```
spec_read → spec_validation* → clarity_check* → file_picker → rag_retrieval*
→ context_assemble → planner_pass* → builder_llm*
```

**Supervisor-owned loop (`preloop` / `loop` / `postloop` lifecycle envelope):**

```
SupervisorAgent.begin()
  loop: executor (+ confirm_ask supervision) → reviewer_pass* → supervisor decision
SupervisorAgent.finish()
→ post_gateway → spec_report → auto_verify*
```

`*` = conditional / default-on for most helpers today (see §9). `spec_validation` and `clarity_check` can **block** before expensive executor work.

**Key properties:**

- Helper LLM failures (builder, planner) are usually **non-fatal** — mechanical context still runs.
- Validation/clarity blocks are **closed** — no executor tokens spent.
- **Supervisor** owns inter-turn decisions (`done`, `rerun_aider`, `escalate_host`) and lifecycle trace events.

---

## 5. Context compiling

The executor sees a **ContextPackage**, not raw chat history:

1. **Spec is the contract** — `## Files` defines edit rights; gateway enforces post-hoc.
2. **Tiers control cost** — edit-full → read → excerpt → map-only; budget trims from the bottom.
3. **Picker discovers; assembler materializes** — discovery never grants edit rights.
4. **Layered brief** — mechanical brief (authoritative) + optional RAG `## Relevant prior work` + builder narrative + **planner plan** (legacy traces may say "Architect plan").
5. **`context_summary`** — host/planner decisions the executor cannot infer from the spec alone.

Dry-run without executor cost: `mcp-coder inspect-context` or MCP `inspect_context`.

---

## 6. Per-role models

Many LLM calls per delegation, each resolved independently:

| Role | Typical job |
|------|-------------|
| `executor` | Aider edit loop |
| `context_builder` | Builder brief |
| `planner_pass` | Planner plan in brief |
| `clarity_check` | Pre-delegate task clarity |
| `spec_validation` | Spec/task coherence |
| `supervisor` | confirm_ask + inter-turn decisions |
| `reviewer_pass` | Post-execution advisory review |
| `review` | `mode=review` only |

Precedence: host **`model_policy`** → env → `config.yaml` → registry default. Every call is audited in `model_roles` and trace events (`policy_applied`, `llm_call`, `backend_llm_call`).

---

## 7. Memory: what persists where

```
<workspace>/.mcp-coder/          IN repo (user-visible)
  config.yaml, specs/, reports/, session.json

~/.mcp-coder/projects/<key>/     OUTSIDE repo
  project_state.json             cross-delegation Supervisor memory
  agent_state.json               Supervisor checkpoint (last delegation position)
  supervisor_states/<token>.json pause/resume payloads (expiring)
  workspace_history.db           snapshots, checkpoints, file diffs
  delegation_rag.db / workspace_rag.db
  sessions/<mcp_session_id>/
    delegations.jsonl            lean audit rows
    traces/<delegation_id>.jsonl full event stream
```

Cross-delegation memory: **project state**, RAG, `prior_failed_attempts`, planner reading project state, Supervisor tools (`get_project_state`, `get_delegation_history`, …).

**Sessions:** group delegations under `mcp_session_id`; Aider `Coder` may be cached per session (`always_new` vs `align_host` policy).

---

## 8. Trust and verification

- **Snapshots, not git** — `files_changed` from pre/post SHA-256 manifests.
- **Scope gateway** — compare changes to spec `Files` contract → `files_unexpected`.
- **Outcomes** — `success | partial | needs_input | error`.
- **Judgment checklist** — host makes final call; mcp-coder informs.
- **Auto-verify (opt-in)** — e.g. `pytest -q` after successful edits.

---

## 9. Configuration in one view

Precedence: **default → env → `.mcp-coder/config.yaml`** (host `model_policy` overrides models per delegation).

| Flag | Default | Effect |
|------|---------|--------|
| `context_builder` | on | picker + repo map |
| `context_builder_llm` | on | builder narrative |
| `spec_validation` | on | can block |
| `clarity_pass` | on | can block / pause |
| `planner_pass` | on | planner plan (alias: `architect_pass`) |
| `reviewer_pass` | on | post-exec review |
| `auto_verify` | off | post-delegate verify |
| `builder_history_rag` / `workspace_file_rag` / `workspace_file_hints` | on | retrieval in brief |
| `supervisor_max_turns` | 1 | multi-turn Supervisor loop (2–3 for retry) |

Full env tables: [reference/cli.md](./reference/cli.md).

---

## 10. Invariants worth memorizing

1. **Spec is the contract** — edit rights come from spec `Files`, not picker discovery.
2. **Host and backend are adapters** — Cursor and Aider are current instances, not the architecture.
3. **Supervisor owns orchestration state** — helpers do not silently persist project memory.
4. **Helpers annotate; mechanical brief is truth** — tiers/paths from assembler are authoritative.
5. **Validation/clarity block closed; most other helper failures open.**
6. **Audit everything** — start debugging from `delegations.jsonl`, `traces/*.jsonl`, or `mcp-coder view delegations`.
7. **mcp-coder never overwrites user `config.yaml`.**

---

## 11. Where to go deeper

| Want | Go to |
|------|-------|
| Terms | [terminology.md](./terminology.md) |
| Modules / paths | [code-structure.md](./code-structure.md) |
| CLI & MCP tools | [reference/cli.md](./reference/cli.md), [reference/mcp-tools.md](./reference/mcp-tools.md) |
| Layer map (guide) | [architecture/overview.md](./architecture/overview.md) |
| Refined design | [../notes/system-design-overview.md](../notes/system-design-overview.md) |
| Tutorials | [tutorials/](./tutorials/) |
| Backlog / phases | [../PHASES.md](../PHASES.md), [../BACKLOG.md](../BACKLOG.md) |
