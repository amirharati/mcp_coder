# Phase 10 issues

**Status:** **Active** — Phase 10 opened 2026-06-18.
**Open:** none
**Promoted from backlog:** BL-334, BL-106, BL-520, BL-351 (v0), BL-516 (partial), BL-517, BL-518 (partial), BL-519 — see below
**Related PM board:** [PHASE10_MVP.md](./PHASE10_MVP.md)

---

## Promoted from backlog → Phase 10 milestones

*(Planning session 2026-06-18. Full vision for BL-351 / BL-106 / BL-516 remains in [BACKLOG.md](./BACKLOG.md); only the scoped slices below are Phase 10 work.)*

| Backlog | Milestone | Scope in Phase 10 | Full vision deferred |
|---------|-----------|-------------------|----------------------|
| **BL-334** | **P10-001** | Wire `system_prompt_prefix` + `edit_format` from `CallParams`; audit on delegation row (BL-334a/b/c) | Per-delegation override via `model_policy` → BL-512 Stage 2 (Phase 11) |
| **BL-106** | **P10-002** | POF: `ctx.info` at pipeline milestones + thread bridge (D-P10-2, D-P10-3) | Capture→egress bridge, `report_progress`, executor highlights → post-Phase 10 |
| **BL-520** | **P10-002** | POF: `mcp-coder logs tail --latest` on trace JSONL | `server.jsonl` filter, executor tee (BL-160b), `make logs-tail` → post-Phase 10 |
| **BL-351** | **P10-003** | v0: stall pattern detect → `needs_input` + optional auto-read-retry (D-P10-1) | Supervised `InputOutput`, cheap LLM supervisor, outer-loop resume → Phase 11 |
| **BL-517** | **P10-004** | `policy_applied.ignored` for executor-inapplicable params (D-P10-6) | — (complete in Phase 10) |
| **BL-519** | **P10-004** | `MCP_CODER_PROXY_ENABLED=0` toggle (D-P10-7) | — (complete in Phase 10) |
| **BL-516** | **P10-004** | Partial: `trace inspect --summary` only | `mcp-coder log` cross-delegation table, `--no-truncate` → post-Phase 10 |
| **BL-518** | **P10-004** | Partial: env-var matrix documentation + `.env.example` stubs | Unified master log level, proxy debug logging → post-Phase 10 |

---

## P10-BL-334 → P10-001 — Executor options resolved but never applied

**Type:** Backlog promotion → active milestone
**Milestone:** P10-001
**Severity:** medium — reduces stall frequency; prerequisite for dogfood behavior shaping
**Status:** `done` — implemented 2026-06-18 (worker session)
**Opened:** 2026-06-18 (planning session)
**Backlog:** [BL-334](./BACKLOG.md#bl-334-backend-prompt-customization-system-prompt-prefix--edit-format-control)

### Summary

`model_registry.resolve(ROLE_EXECUTOR)` returns `CallParams` with `system_prompt_prefix` and `edit_format`, but `_apply_executor_model_params` never passes them to Aider. Pure wiring gap identified during Phase 9 model registry work.

### Phase 10 slice

Apply both fields via `aider_runtime.py`; audit `system_prefix_applied` + `edit_format` on delegation record. Global env/yaml only (D-P10-4).

### Exit criteria

See [PHASE10_MVP.md](./PHASE10_MVP.md) § P10-001.

### Result summary

- Resolver now maps `MCP_CODER_EXECUTOR_SYSTEM_PREFIX` / `MCP_CODER_EXECUTOR_EDIT_FORMAT` into executor `CallParams`.
- Runtime applies `model.system_prompt_prefix` and forwards `edit_format` through coder kwargs on cached + non-cached paths.
- Delegation logging now captures `system_prefix_applied` and `edit_format` audit fields.
- `.env.example` updated with both env vars.
- Tests: focused `32/32` passed; full suite `986 passed`, `1 skipped`, `1 pre-existing failure` (`test_schema_migration_from_322a_db`).

---

## P10-BL-106 + P10-BL-520 → P10-002 — No live visibility during delegation

**Type:** Backlog promotion → active milestone
**Milestone:** P10-002
**Severity:** high — blocks confident real-project dogfood on long runs
**Status:** `promoted` — pending worker spec
**Opened:** 2026-06-18 (planning session)
**Backlog:** [BL-106](./BACKLOG.md#bl-106-mcp-live-progress--logging-notifications) · [BL-520](./BACKLOG.md#bl-520-live-log-tail--follow-delegation)

### Summary

Long `delegate_to_agent` runs show only a spinner in Cursor. Phase 9 write-always storage means trace JSONL is appendable during the run — tail is read-side only. FastMCP `Context` is available but not wired into `delegate_to_agent`.

### Phase 10 slice

- Part A: `ctx.info` at ~6 pipeline milestones + asyncio thread bridge (D-P10-2, D-P10-3)
- Part B: `mcp-coder logs tail --latest` CLI with human-readable event lines

### Exit criteria

See [PHASE10_MVP.md](./PHASE10_MVP.md) § P10-002.

---

## P10-BL-351 → P10-003 — Blind `yes=True` + silent stall failures

**Type:** Backlog promotion → active milestone (v0 only)
**Milestone:** P10-003
**Severity:** high — trust gap for real-project use
**Status:** `promoted` — pending worker spec
**Opened:** 2026-06-18 (planning session)
**Backlog:** [BL-351](./BACKLOG.md#bl-351-simulated-interactive-mode--host-escalation-human-intervention)

### Summary

`InputOutput(yes=True)` auto-approves all Aider prompts. When Aider asks to add files, `_IMPLEMENT_QUESTION_MARKERS` detects the pattern but returns a generic failure — Cursor cannot act on it.

### Phase 10 slice (v0)

Post-run output parsing → `needs_input` structured response with `files_requested[]`. Optional `MCP_CODER_STALL_AUTO_RETRY=1` for one auto-read-retry. No `InputOutput` subclass (D-P10-1).

### Remaining (BL-351 full — Phase 11)

Cheap LLM supervisor, supervised `InputOutput`, outer-loop re-compile on expansion, async resume token.

### Exit criteria

See [PHASE10_MVP.md](./PHASE10_MVP.md) § P10-003.

---

## P10-BL-516/517/518/519 → P10-004 — Phase 9 deferred polish

**Type:** Backlog promotion → active milestone (batch)
**Milestone:** P10-004
**Severity:** low–medium — logging correctness + operator DX
**Status:** `promoted` — pending worker spec
**Opened:** 2026-06-18 (planning session)
**Backlog:** [BL-516](./BACKLOG.md#bl-516-cli-log-health-table--trace-inspect-summary) · [BL-517](./BACKLOG.md#bl-517-executor-policy_applied-ignored-params) · [BL-518](./BACKLOG.md#bl-518-runtime-log-level--verbosity-dx) · [BL-519](./BACKLOG.md#bl-519-mcp_coder_proxy_enabled-env-toggle)

### Summary

Four items deferred at Phase 9 close (P9-014 → BL-516; P9-ISS-007 → BL-517; operational DX → BL-518/519). High ROI, small scope, directly supports Phase 10 dogfood debugging.

### Phase 10 slice

- BL-517: full (`policy_applied.ignored`)
- BL-519: full (proxy toggle)
- BL-516: partial (`trace inspect --summary` only)
- BL-518: partial (env matrix docs + `.env.example` stubs)

### Exit criteria

See [PHASE10_MVP.md](./PHASE10_MVP.md) § P10-004.

---

## Open implementation issues

*None yet — issues opened here during worker sessions (P10-ISS-NNN format).*
