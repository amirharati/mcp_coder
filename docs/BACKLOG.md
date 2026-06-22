<!--
  STEWARDSHIP — Tier 2 backlog. See docs/VISION_DOCS.md.

  - OK: add BL-* rows, status, links; reprioritize with user or P1-199.
  - NOT OK: delete items silently or contradict IDEA.md vision.
  - Workers: do not edit; propose new BL-* in task § Results for planning session.
-->

# Project backlog

Items deferred from active phases, future ideas, and nice-to-haves. **Not** scheduled for the current worker session unless pulled into [PHASE1_MVP.md](./PHASE1_MVP.md). **Vision:** [IDEA.md](./IDEA.md) · [VISION_DOCS.md](./VISION_DOCS.md).

Status: `idea` | `deferred` | `blocked` | `in_phase` | `done`

---

## Phase 13 active (opened 2026-06-21)

**PM board:** [PHASE13_MVP.md](./PHASE13_MVP.md) · **Issues:** [PHASE13_ISSUES.md](./PHASE13_ISSUES.md)

| Backlog / theme | Milestone | Status | Deferred |
|-----------------|-----------|--------|----------|
| Dogfood + trace analysis | P13-001 | pending | — |
| Doc consolidation | P13-002 | pending | After P13-001 |
| Test hardening | P13-003 | pending | After P13-001 |
| Low-hanging fixes + backlog review | P13-004 | pending | Items TBD after dogfood |

---

## Phase 12 shipped (closed 2026-06-21)

**PM board:** [PHASE12_MVP.md](./PHASE12_MVP.md) · **Issues:** [PHASE12_ISSUES.md](./PHASE12_ISSUES.md)

| Backlog | Milestone | Status |
|---------|-----------|--------|
| BL-544 | P12-001 | ✅ Shipped |
| BL-540 | P12-002 | ✅ Shipped (v1) |
| BL-530/542 | P12-003 | ✅ Shipped |
| BL-541 | P12-004 | ✅ Shipped |
| BL-525 v1 | P12-005 | ✅ Shipped |
| BL-545 | BL-545 v1 | ✅ Shipped |
| P12-ISS-001..004 | — | ✅ Closed |

**Partials → backlog:** BL-543 (B/C), BL-529, BL-525 full, BL-547 (intercept), BL-546 (executor adaptation).

---

## Phase 11 shipped (closed 2026-06-20)

**PM board:** [PHASE11_MVP.md](./PHASE11_MVP.md) · **Issues:** [PHASE11_ISSUES.md](./PHASE11_ISSUES.md) · **Bootstrap:** [notes/phase11-master-session-bootstrap.md](./notes/phase11-master-session-bootstrap.md)

| Backlog | Milestone | Phase 11 scope | Remainder |
|---------|-----------|----------------|-----------|
| BL-521 (new) | P11-001 | ✅ Done — `clarity_check` pipeline phase shipped (opt-in `MCP_CODER_CLARITY_PASS`) | Cross-session intent history → Phase 12 |
| BL-351 | P11-002 | ✅ Done — `SupervisedIO` + `DelegationSupervisor` + decision log + abort-on-escalate shipped | Async outer-loop resume / mid-run async resume → Phase 12 |
| BL-354 | P11-003 | ✅ Done — executor-pull hint v0 shipped (`/read` prompt guidance + audit field) | Full sidecar HTTP tool server → Phase 12 |
| BL-522 (new) | P11-004 | ✅ Done — mid-run human gate shipped (`answer_delegation_question` + Event bridge, timeout fallback) | Protocol-level async gate + late-answer resume (BL-528) → Phase 12 |
| BL-358 | P11-005 | ✅ Done — tier-1 reviewer v0 shipped (`reviewer_pass` + report append, non-fatal on reviewer error) | Tier-2 epic-boundary review → Phase 12 |
| — | P11-006 | ✅ Done — smart architect trigger shipped (spec/env/heuristic precedence + skip-reason detail) | — |
| BL-512 | P11-007 | ✅ Done — host `model_policy` arg shipped (per-role overrides + additive precedence + warning audit) | BL-513 AI-suggested, BL-514 dynamic escalation → Phase 12 |
| — | P11-008 | ✅ Done — naming refactor `architect_pass` → `planner_pass` | Legacy aliases retained with warnings |
| BL-533 | P11-009 | ✅ Done — supervisor agent loop unified (`supervisor_loop_*`) | Live multi-turn rerun wiring in `mcp_server` follow-up |

### Phase 11 carried issues (moved on close)

| Backlog | Source issue | Theme | Status | One-line summary |
|---------|--------------|-------|--------|------------------|
| **BL-535** | P11-ISS-002 | Trace inspect UX | deferred | `trace inspect <id>` should work for specless CLI runs via trace-file fallback when DB index is missing. |
| **BL-536** | P11-ISS-014 | Role attribution completeness | deferred | Ensure every `proxy_llm_call`/`backend_llm_call` has reliable `role`, `model`, `provider`, `ok`, `duration_ms`, token summary. |
| **BL-537** | P11-ISS-017 | Reviewer semantics | deferred | Make reviewer policy explicit in outputs/records (`reviewer_mode`, `reviewer_outcome`, `reviewer_action`) and behavior docs. |
| **BL-538** | P11-ISS-018 | Planner audit normalization | deferred | Normalize planner-pass audit block with same shape/style as clarity/spec-validation/reviewer in records + viewer. |
| **BL-539** | P11-ISS-019 | Clarity telemetry polish | deferred | Expose complete clarity round telemetry (`clarity_round_index`, `clarity_round_cap`, `clarity_auto_passed`) consistently in trace + records. |

---

## Phase 10 shipped (closed 2026-06-18)

**PM board:** [PHASE10_MVP.md](./PHASE10_MVP.md) · **Issues:** [PHASE10_ISSUES.md](./PHASE10_ISSUES.md) · **Bootstrap:** [notes/phase10-master-session-bootstrap.md](./notes/phase10-master-session-bootstrap.md)

| Backlog | Milestone | Phase 10 scope | Remainder |
|---------|-----------|----------------|-----------|
| BL-334 | P10-001 | ✅ Done — `system_prompt_prefix` + `edit_format` wiring + delegation audit shipped | Per-delegation `model_policy` → BL-512 (Phase 11) |
| BL-106 | P10-002 | ✅ Done (POF) — `ctx.info` milestone notifications shipped | Capture→egress bridge, `report_progress`, richer step details → backlog |
| BL-520 | P10-002 | ✅ Done (POF) — `logs tail --latest/--delegation-id` on trace JSONL shipped | `server.jsonl` filter, BL-160b tee → backlog |
| BL-351 | P10-003 | ✅ Done (v0) — stall detect → structured `needs_input` (with `files_requested`) | Full supervisor + `InputOutput` + outer-loop resume → Phase 11 P11-002 |
| BL-517 | P10-004 | ✅ Done — executor `policy_applied.ignored` shipped | — |
| BL-519 | P10-004 | ✅ Done — `MCP_CODER_PROXY_ENABLED` toggle shipped | — |
| BL-516 | P10-004 | ✅ Partial done — `trace inspect --summary` shipped | `mcp-coder log` table, `--no-truncate` → backlog |
| BL-518 | P10-004 | ✅ Partial done — env matrix docs + `.env.example` parity shipped | Unified log level, proxy debug → backlog |

---

## Deferred from Phase 1 (by design → later phases)

| ID | Item | Target | Notes |
|----|------|--------|-------|
| BL-001 | Owned context pipeline (summarize, rank, trim) | Phase 2 | Phase 1 is pass-through only |
| BL-002 | RAG / cross-session memory (`rag_search`, SQLite) | **Phase 5 done** (compile-push) | P5-001…P5-006 shipped; defaults on. Remaining gaps → BL-354, BL-356–357, **BL-365–366**. See § BL-002 |
| BL-003 | Router / janitor LLM inside mcp-coder | Phase 2+ | Cheap orchestrator pattern |
| BL-005 | Dual-mode CLI (`mcp-coder run …`) | Phase 2+ | Same core as MCP; after context system useful |
| BL-006 | Context janitor, critic, test-writer sub-agents | Phase 4 | Composable one-shots |
| BL-007 | Multi-model ensemble | Phase 4+ | IDEA.md § future |
| BL-008 | Skills injection library | Phase 2–3 | Topic → skill file; part of owned context (see § Post–Phase 1 focus) |
| BL-009 | Explicit MCP tools: `continue_session`, `get_session_status` | Phase 3 | Phase 1 uses disk registry + policy |
| BL-010 | ~~DB-backed session persistence~~ | Phase 3 | **P1-130:** disk sessions under `~/.mcp-coder` (not DB) |

---

## Removed / demoted from Phase 1 spine

| ID | Item | Notes |
|----|------|-------|
| BL-505 | SpecStory `.specstory/history/*.md` | Replaced by Cursor host transcript (P1-140) |
| BL-402 | SpecStory freshness window | N/A |
| BL-101 | ~~SpecStory tail truncation cap~~ | **done** — `MCP_CODER_MAX_TRANSCRIPT_BYTES` when `host_transcript: dump` |

---

## Phase 1 optional (if time remains in MVP)

| ID | Item | Notes |
|----|------|-------|
| BL-102 | Fallback `cheap_llm` session classifier | Was P1-131; after P1-130 baseline |
| BL-103 | `inspect_delegations.py` CLI | Home-path aware |
| BL-104 | Aider dry-run mode in MCP | Safe first tests |
| BL-105 | Default Aider → `context_optimizer_proxy` in setup template | Composes with sibling project |
| BL-106 | **MCP live progress + logging notifications** — `ctx.report_progress` / `ctx.log` during long `delegate_to_agent`; capture→egress bridge from pipeline + executor | **Phase 10 — P10-002** (POF: `ctx.info` milestones); remainder → backlog. See § BL-106. |
| BL-107 | `MCP_CODER_MIRROR_LOGS_TO_WORKSPACE` default policy | Migration from P1-100 paths |
| BL-108 | Pick “main” mcp session among N per `host_session_id` | Heuristic TBD |
| BL-109 | `continue_session` by explicit `mcp_session_id` | After P1-130 infra |
| BL-125 | ~~**Persistent MCP server log** + verbosity tiers~~ | **done** — P1-125 (2026-06-05) |
| BL-305 | ~~Server log scope: global vs per-`project_key`~~ | **done** — default `global`; `project` / `both` in yaml/env |

---

## Post–Phase 1 focus (priority after P1-199)

**Direction (locked P1-199, 2026-06-06):** Three layers — **contract** (spec + policies) → **context compiler** (tiers, budget) → **execution adapter** (Aider today). `target_files` is a planner hint; spec Files is the contract when `spec_path` is set. Audit loop: contract → package → adapter input → result. PM board: [PHASE2_MVP.md](./PHASE2_MVP.md). Design: [notes/phase2-owned-context.md](./notes/phase2-owned-context.md).

| Priority | ID | Item | Notes |
|----------|-----|------|--------|
| 1 | **BL-316** | Context builder **file materialization tiers** | Core Phase 2; decouple spec/API from Aider `fnames`; extends BL-001 |
| 2 | BL-001 | Owned context **creation** | Assemble brief: files, constraints, task; cheap LLM or rules + ripgrep |
| 3 | BL-154 | **Context window management** | Telemetry **P2-120**; compiler caps **P2-220** — see § BL-154 |
| 4 | BL-311 | Read-deps validation for implement | P1-ISS-014 — warn/merge spec Files vs `target_files`; convention shipped P1-152 |
| 5 | BL-315 | `edit_scope` + spec `files_edit` / `files_read` YAML | **partial** P2-115; 315c → P2-200 |
| 6 | **BL-309** | **Delegation hardening** (job vs workflow failure) | P1-ISS-012 — cheap-model 500s; see § below |
| 7 | BL-153 | **Topic / task boundary detection** | Smarter session + context slices |
| 8 | BL-008 | Skills + prompt packs | Inject by topic / task type |
| 9 | BL-155 | **Executor cache & multi-turn** | Extend P1-130 rolling delegate context |
| 10 | BL-310 | Planner verify / report status split | P1-ISS-013 |
| 11 | BL-312 | Auto-review policy (optional) | D-SPEC-1 |
| 12 | BL-003 / **BL-162** | Router / janitor + **cheap model for context build** | BL-162 partial overlap Phase 2 |
| — | BL-002 | RAG / cross-session memory | Phase 3 |
| — | ~~BL-150~~ | ~~Spec-based delegation~~ | **done** P1-150/151 |

**Two halves of “owned context” (same program):**

1. **Inputs** — ways to *add* context (spec, skills, RAG later, file pickers, host transcript as optional audit).
2. **Budget** — ways to *manage* the window (summarize, roll, truncate with logged reason, per-model limits).

Phase 1 deferred executor conversation carry-over to here (BL-155); see P1-130 `executor_cache.py` (cache hit only when same `target_files`; lost on MCP restart).

---

## On the list — timing TBD (not required for Phase 2)

**Keep these in the roadmap; decide phase when Phase 2 context basics work.** Not blockers for closing Phase 1.

| ID | Item | Notes | Related |
|----|------|-------|---------|
| BL-161 | **Multi-agent inside MCP** (planner → executor) | Single MCP tool call from Cursor still triggers an **internal pipeline**: architect/planner pass (steps, file plan, risks) **then** executor (Aider). Cursor stays thin; mcp-coder owns substeps, logs each phase. | BL-006 (janitor/critic) is adjacent; BL-503 grades output — this is **upstream planning** |
| BL-162 | **Multi-model routing** | Different models per role: cheap for context build / cleanup / topic ID; expensive for execution. **Stage 1 (Phase 4, D-P4-8):** one configurable model per role (executor/review/context builder), each audited with cost. **Stage 2+:** multiple models within a role — tiered escalation (BL-321), critic redo (BL-006), failed-attempt-aware upgrade (P4-008 data), swarm/ensemble (BL-007). See [notes/multi-model-roles.md](./notes/multi-model-roles.md). | BL-007 ensemble; BL-321 escalation; BL-006 critic; env has `AIDER_MODEL` / OpenRouter |
| BL-329 | **Pre-delegate spec validation + clarifying loop** | Builder reads host transcript, checks spec coherence vs session context before delegating; returns `clarification_needed: [...]` if ambiguous. | P4-009 (Wave 4 optional); pairs with BL-161 (pre+post Aider pipeline) and BL-324 (post-delegation judgment loop) |

### Interactive sessions (BL-160) — options to try later

**Not required for Phase 2.** Cursor stays the planner; you already pass files + context; mcp-coder **reports back when done**. “Interactive” here means **supervision + visibility**, not duplicating Cursor chat in the terminal.

| ID | Option | What | Notes |
|----|--------|------|--------|
| BL-160a | **Supervised complex task** | One MCP call; mcp-coder helps Aider finish a **multi-step** job (internal steps, retries, optional human OK between steps). User does **not** need to chat in Cursor for each micro-step. | Overlaps **BL-161**; lighter than full REPL |
| BL-160b | **Live terminal visibility** | While delegate runs (even “non-interactive”), **tee** Aider command/edit stream to stderr file or terminal tail for **quick review** — without breaking MCP stdout (JSON-only). Today: brief stderr + captured output in tool result only. | `stdio_isolation` blocks raw stdout to Cursor; pairs with **BL-106** (MCP notifications) and **BL-520** (`logs tail` on tee file + trace JSONL) |
| BL-160c | **Handoff to real terminal** | MCP prepares context + opens / prints a command; user continues in **real terminal** with native Aider REPL if they want deep hands-on. | Pairs with **BL-005** CLI |
| BL-160d | **Full interactive via CLI** | `mcp-coder session` — same core as MCP, no Cursor transport; multi-turn chat with executor in terminal. | Lowest priority of the four |

**Default product story (when we pick this up):** BL-160a + BL-160b first; BL-160c/d only if needed.

**Related:** [IDEA.md](./IDEA.md) § interactive mode; P1-100 `InputOutput(yes=True)`; **BL-501** async if runs exceed MCP timeout.

**Notes (2026-06 planning):**

- **BL-161** is not “multiple MCP servers” — one server, multiple **internal** agent steps before/after Aider (could be rules-only v0, LLM planner v1).
- **BL-162** may land partly in Phase 2 (context-builder model ≠ executor model); full ensemble voting stays later (BL-007). **Stage 1 = one model per role (D-P4-8); Stage 2 = escalation/critic; Stage 3 = swarm.** Full staging in [notes/multi-model-roles.md](./notes/multi-model-roles.md).

---

### BL-329: Pre-delegate spec validation + clarifying loop

**Status:** `done` — P4-009 (2026-06-09).

**Status:** `done` — **P4-009** (2026-06-09). Opt-in `spec_validation`; `clarification_needed` blocks executor; rules v14.

**Phase 5 dogfood note (P5-ISS-004):** When validation blocks (`needs_input`), the compile pipeline — including `rag_retrieval` — does not run; `context_refs` stays empty. This is **expected** but easy to misread as a RAG regression. Session `1432fc02-c6b1-4452-aa28-261ce77f896b` entries #2–#4 (`expensesplit-p5-dogfood-v2/v3`, SEARCH/REPLACE-style host tasks). Optional: log `rag_retrieval: skipped (spec_validation_blocked)` in `delegation_pipeline` for blocked delegates (BL-353 observability).

**Goal:** Before delegating, the context builder reads the host session transcript and checks whether the spec is well-aligned with the current conversation. If ambiguous or contradictory, return a `clarification_needed` list to Cursor instead of delegating — forcing the host to answer before retrying.

**Mechanism:**

| Step | Detail |
|------|--------|
| Builder reads `host_transcript` | Uses existing P1-140 infra; same transcript already available for context |
| Cheap-LLM coherence check | Same model as P4-001b; checks spec task + constraints against recent conversation decisions |
| `clarification_needed: [...]` response | New MCP response field; non-empty = delegation withheld; Cursor answers + retries |
| Normal path | Coherence check passes → transparent, no user-visible latency change |

**New MCP response field:** `clarification_needed: list[str] | null`

**Rules addition:** When `clarification_needed` is non-empty, host must answer each item before re-calling `delegate_to_agent` (same enforcement pattern as judgment loop).

**Relation to existing items:**
- **P4-001b** — same builder call; validation is an additional check before finalizing the brief
- **BL-161 / P4-020** — P4-009 is pre-Aider validation; BL-161 is post-validation architect pass — they compose
- **BL-324** — judgment loop is post-delegation; this is pre-delegation; together they close both ends

**Open design question (decide at P4-009 spec time):** Always-on (adds latency to every call) vs opt-in via `validate_spec: true` in config.

---

## Host & integration

| ID | Item | Notes |
|----|------|-------|
| BL-201 | Claude Desktop host adapter | **Low priority** — after Cursor + owned context |
| BL-202 | Windsurf / other IDEs | **Low priority** |
| BL-203 | ~~Read Cursor agent-transcripts~~ | **done** — P1-120 metadata + P1-140 opt-in dump |
| BL-204 | Proxy intercept: save latest Cursor prompt from `context_optimizer_proxy` | Personal workflow |
| BL-205 | Cursor rule / skill snippet for routing to `delegate_to_agent` | Improve auto-routing |
| BL-332 | **Host-agnostic planner rules sync** | Cursor-coupled today; compile engine is reusable — see § BL-332 |
| BL-341 | **`mcp-coder setup` + global env (onboarding DX)** | **CLI slice shipped** (P4.5-001): `setup` subcommand, `install.sh` global wrapper, repo-root `.env` documented. Remaining: pipx packaging, true machine-level config outside repo dir. |
| BL-342 | **`test-model` list/select/all** | **Shipped** (P4.5-001): `test-model --all` pings each role sequentially, pass/fail table, exit 1 on failure. |
| BL-343 | **Structured delegation log viewer** | **Shipped in Phase 9 (P9-013 done, 2026-06-17):** v2 boundary-table viewer with Python middleware (`view_events[]`), chronological boundary rows, detail panel, multi-delegation collapsing, and rich request/context/policy debug visibility. P9-015 pipeline cards superseded by v2 architecture. |
| BL-344 | **Configurable spec granularity (step size / full-epic delegate)** | Workspace config + user opt-in: fine-grained step specs vs larger “big step” specs vs single task covering whole epic (`spec_path` = epic-scale contract). Unlock higher-end models that can do more per delegate; requires experiments on context, scope gateway, reports, versioning. From P4.5-ISS-007 — **Phase 5+**, not 4.5. |
| BL-345 | **Mechanical spec lint (pre-delegate, no LLM)** | `mcp-coder spec lint` + optional delegate gate: required sections, non-empty Goal/Files, placeholder detection, empty `prompt_block` → `invalid_spec`; optional on-disk path warnings. Tiers: warn vs `spec_lint: strict`. Complements `spec_validation` (chat LLM) and `mode=review` (brainstorm). From P4.5-ISS-008 — **Phase 5+**. |
| BL-346 | **Model-aware context budget defaults + cap enforcement** | Per-executor-model input budget defaults (window minus output/overhead reserve); clamp `MCP_CODER_CONTEXT_BUDGET_TOKENS` / yaml overrides to model max; maintain `context_budget_tokens` via provider/OpenRouter refresh or periodic update (today hand-edited `model_rates.yaml`). From P4.5-ISS-009 — **Phase 5+**. |
| BL-347 | **Adaptive context-management policies** | Beyond single 3-step budget: task- and model-sensitive compile (tiers, excerpting, transcript, map depth); integrate with context builder; bust/reuse executor cache correctly on model change; auto-select policy per delegation with minimal user config (BL-162). From P4.5-ISS-010 — **Phase 5+**. |
| BL-348 | **Incremental workspace code-intel cache (high ROI context)** | Today: per-delegate regex `def`/`class` repo map + `rg` symbol scan + raw file payloads — **no** persisted API catalog, import/dep graph, or auto-generated module docs; no AST. **Later:** build + cache richer artifacts under `~/.mcp-coder/projects/<key>/` (or repo `.mcp-coder/`): per-file symbol/API index (signatures, docstrings, exports), import/call edges, optional LLM file summaries — **incrementally updated** when `workspace_history` / manifest hash changes (re-index stale paths only). Feed context picker/builder/compiler tiers instead of re-deriving every delegate. Complements **BL-002** (planner `workspace_search`) and **BL-347** (policy selection). **Phase 5+** — likely high ROI once basics exist. From P4.5-ISS-011. |
| BL-349 | **Recently touched files — session + project, git + manifest fusion** | Today: per-delegation `files_changed` (manifest walk ± git dirty), `get_file_history` (one file → timeline), `list_delegations` — **no** aggregated “recently updated files” view, no MCP `recent_files` / picker hint, no merge of git mtime/status with `workspace_history` file deltas. **Later:** rank paths touched in current MCP session vs project-wide N delegations / time window; attach detail (checkpoint summary, diff snippet, BL-348 symbol summary) when relevant to task/RAG/symbol query; surface to planner MCP + context picker/builder as read hints (not auto edit). **Phase 5+**. From P4.5-ISS-012. |
| BL-350 | **Supervised executor loop — inspect mid-run, inject context, capture thinking** | **Phase 7 partial shipped (P7-002):** bounded outer loop + executor `llm_call` / `tool_call` / `action` events + `executor_turns` stats. **Remaining:** adaptive multi-step continuation protocol and stronger supervised escalation behavior (BL-351). |
| BL-351 | **Simulated interactive + escalate to host (Cursor human intervention)** | **Phase 10 — P10-003** (v0: stall → `needs_input`). **Remainder:** cheap LLM supervisor, supervised `InputOutput`, outer-loop resume → Phase 11. From P4.5-ISS-014. See § BL-351. |
| BL-352 | **Multi-language symbol scan + outlines (C/C++, Go, Rust, …)** | Today: symbol scan hardcoded to 9 extensions (`SCAN_EXTENSIONS` in `file_picker.py`); repo-map/excerpt regex is Python `def`/`class` only — C/C++/Go/Rust/Java/etc. work via **spec contract** but not **auto-discovery** or useful outlines. **Later:** expand/configurable scan globs; per-language outline heuristics (or tie to BL-348 index); goal = “works for money cases” on polyglot/monorepo repos without hand-listing every path. **Phase 5+**. From P4.5-ISS-015. |
| BL-353 | **LLM boundary observability — full pass-through logging** | **Phase 6+7+8+9 done:** helper traces/tokens (P6), executor step events (P7), compile provenance (P7), Aider inner-loop + thinking tokens (P8), write-always + proxy + replay + model registry + policy_applied (P9). BL-367 fully shipped. |
| BL-354 | **Executor context tools (pull) — RAG/history/read during backend loop** | **Dual model:** keep **compile-push (A)** as default; **also** expose read-only mcp-coder tools inside the executor loop (Aider today ignores planner MCP). LLM-driven `rag_search`, `workspace_search`, history, excerpts beside edit tools. **Phase 5+** (pairs with BL-002 usage); see § BL-354. From T-04 pass (2026-06-11). |
| BL-355 | **Optional host CLI toolchain — `rg`, docs, `mcp-coder doctor`** | Today: **ripgrep** optional (Python fallback in file picker); **git** soft-required for diffs/snapshots; tutorials use **jq** / **grep** for inspection. **Later:** curated optional-deps list, `setup`/`doctor` hints (`brew install ripgrep`), perf notes when fallback is used. **Phase 5+** DX; see § BL-355. From T-04 playground (2026-06-11). |
| BL-356 | **RAG-backed context audit refs — lean JSONL + digest provenance** | As **BL-002** indexes digests (chat, delegations, workspace files), stop duplicating bodies in `delegations.jsonl`; store `context_refs[]` + hashes; index-time metadata for replay/retrieval. Pairs with **BL-353** wire log. **Phase 5+** (after RAG corpus); see § BL-356. From T-04 observability pass (2026-06-11). |
| BL-357 | **Storage lifecycle — promote, prune, gc (logs + RAG + traces)** | `~/.mcp-coder` grows without bound (JSONL, traces, RAG DBs, checkpoints, blobs). **Later:** per-layer TTL, promote-then-prune, `mcp-coder maintenance` / gc, archive, global dedupe. Cross-cutting — not RAG-only. **Phase 6+** (after BL-356 lean refs + some RAG corpora); see § BL-357. From RAG planning (2026-06-12). |
| BL-358 | **Post-executor polish pass — reviewer model (comments, tests, alignment)** | After Aider succeeds: optional **cheap / large-context** model reads changed files + module neighbors; adds comments, tests, style alignment, **non-logic** micro-refactors. Distinct from critic redo (BL-006) and `auto_verify`. **Phase 5+**; see § BL-358. Sub-mode of **BL-359**. From planning (2026-06-12). |
| BL-359 | **Workflow turns — refactor, document, digest cadence** | Beyond `implement`/`review`: special turns (refactor, document, onboard/digest) + **when** to run (epic boundary, user, semi-auto suggest). Host rules + planner policy. **Phase 5+**; see § BL-359 + [workflow-turns.md](./notes/workflow-turns.md). From planning (2026-06-12). |
| BL-360 | **Code layout refactor — instance sub-folders, file size audit** | `core/engine/` and `core/host/` mix abstract factories with concrete implementations in flat folders. Later: `core/engine/backends/aider/`, `core/host/hosts/cursor/`; audit + split files > ~400 lines (`server/mcp_server.py` ~1750 today). Pure structural; **no behavior change**. **Phase 5+**. From P4.5-ISS-001. |
| BL-361 | **"One step at a time" / always-review-before-implement delegate mode** | Today: fully automatic implement flow; `inspect-context` + `mode=review` cover manual pause. Later: small config flag for `review_before_implement: true` (always run `mode=review` then confirm before `implement`) or pipeline `pause_after: [file_picker]` style hook for step-by-step inspection without rewriting the whole pipeline. **Phase 5+**. From P4.5-ISS-004. |
| BL-362 | **T-06 + T-07 tutorials — delegation pipeline + end-to-end trace** | T-06 (delegation pipeline full tutorial) exists as skeleton; T-07 (pick a real delegation\_id and trace it JSONL → brief → Aider output) not started. Complete when time allows; not required for Phase 5. From Phase 4.5 deferred. |
| BL-363 | **Architecture sub-pages + guide depth** | `overview.md` + light Phase 5 guide sync done (2026-06-13); four sub-pages pending (context-pipeline, storage-layout, per-role-models, reality-vs-spec). From Phase 4.5 deferred. |
| BL-364 | **Blocked-delegate pipeline skip reasons in JSONL** | **P5-ISS-004** — `spec_validation` block → no `rag_retrieval` / empty `context_refs` (by design; confusing in logs). Log skip reason on blocked delegates. **Phase 5+** / BL-353-5a. Repro: session `1432fc02…` #2–#4. |
| BL-365 | **RAG toolset DX — unified CLI + workspace index stats** | Phase 5 core search/index **shipped**; polish when we care: deprecate/consolidate `mcp-coder rag` vs `search delegations`; symmetric `workspace_rag` stats (today only `rag stats` + `index-workspace` row_count); optional MCP `index_workspace` if planners need it. See § BL-365. **Phase 5+** DX. |
| BL-366 | **RAG retrieval evaluation (P5-005 capstone)** | Recall metric on dogfood tasks; builder token/cost delta with RAG on vs off; embeddings go/no-go vs FTS5. Deferred at Phase 5 exit. See § BL-366. **Phase 5+** / Phase 6. |

### BL-365: RAG toolset DX — unified CLI + workspace index stats

**Status:** `deferred` — 2026-06-13. Phase 5 **minimum toolset shipped** (P5-002/P5-003); this item tracks **cosmetic / operator** gaps only — not missing core RAG.

**Shipped (do not re-track):**

| Capability | CLI | MCP |
|------------|-----|-----|
| Search delegations | `mcp-coder search delegations` (+ legacy `rag search`) | `rag_search` |
| Search workspace files | `mcp-coder search files` | `workspace_search` |
| Index delegations | `mcp-coder rag index` (backfill) | auto each delegate |
| Index workspace files | `mcp-coder index-workspace` | — (CLI only) |
| Builder auto-retrieval | inside `delegate` / `inspect-context` | `delegate_to_agent` |

**Gaps (pull when DX matters):**

1. **Legacy duplicate** — `mcp-coder rag {search,index,stats}` vs `mcp-coder search delegations`; same backend. Consolidate or document deprecation path.
2. **Asymmetric stats** — `rag stats` for `delegation_rag.db` only; no `workspace_rag.db` stats command (only `row_count` in `index-workspace` output).
3. **Index MCP parity** — workspace indexing is CLI-only; add `index_workspace` MCP only if planner workflows need it (dogfood has not required it).
4. **Guide** — [docs/guide/reference/cli.md](./guide/reference/cli.md) synced 2026-06-13; dedicated RAG tutorial walkthrough still optional (**BL-362** adjacency).

**Related:** **BL-002**, **BL-355** (doctor could report RAG DB health), **BL-357** (gc).

---

### BL-366: RAG retrieval evaluation (P5-005 capstone)

**Status:** `deferred` — 2026-06-13. Optional Phase 5 milestone; recommended exit met without it.

**Goal:** Evidence-based decision on whether FTS5 retrieval is enough and whether RAG default-on is worth the token cost.

| Slice | What |
|-------|------|
| **Recall metric** | Fixed task set (e.g. expensesplit dogfood): did builder retrieve expected delegation + file hits? |
| **Cost delta** | Same tasks with RAG flags on vs off — `prompt_tokens_est`, helper tokens, `context_refs` count |
| **Embeddings go/no-go** | If FTS misses are systematic, prototype vector search on one corpus; else stay FTS5 |

**Depends on:** **BL-335** (per-role tokens for cost comparison), dogfood workspace fixtures.

**Related:** **BL-002**, **BL-347** (adaptive policies), [PHASE5_MVP.md](./PHASE5_MVP.md) P5-005.

---

### BL-350: Supervised executor loop (mid-run inspect + context inject)

**Status:** `partial` — 2026-06-13. **Phase 7 shipped P7-002** bounded outer loop + executor step events; follow-on behavior remains.

**Problem:** `ContextPackage` is compiled once; Aider’s internal multi-turn loop is opaque. Executor may need file Z, more read context, or escalation mid-task — today we only detect after the loop (`files_unexpected`, `scope_violations`) or fail with “add files to chat”. No per-step observe → help → continue inside one MCP call.

**Goal:** mcp-coder **supervises** the executor loop: inspect each step (or sub-run), optionally **re-compile context** (expand spec read/edit, BL-348 intel, BL-349 recent touches), and capture **thinking/reasoning tokens** per step for BL-333 / BL-335.

**Three routes (try in order):**

| Route | Mechanism | Pros | Cons |
|-------|-----------|------|------|
| **A — Outer loop (preferred)** | mcp-coder owns `compile → run(bounded sub-task) → inspect → recompile → run` inside one `delegate_to_agent`; log `executor_step_N` in `delegation_pipeline`. Expands `files_edit` only via spec/policy between steps (D-P4-10). | Backend-neutral; clean audit; composes **BL-161**, **BL-160a**, **BL-347**; works with Aider today without forking | Multiple executor calls; step budget / timeout design |
| **B — Stream-and-react** | Enable Aider stream/tee (**BL-160b**); parse output for “add file”, errors, stall; **stop early** → return `needs_input` or auto second pass with expanded context | Lighter than full outer loop; visibility without owning turns | Not true mid-loop inject; reactive not proactive |
| **C — Aider `Coder` subclass / owned run** | Extend or wrap `Coder.run()` for per-LLM-turn hooks: inject messages, add `fnames`, capture `reasoning_content` before Aider strips it | Richest per-turn control; direct thinking-token hook if LiteLLM callback insufficient (**BL-333**) | **High maintenance** — Aider version coupling; violates “thin adapter” spirit; hard to port to **BL-340** Cursor SDK |

**Related:** **BL-354** (executor-pull tools — lighter than outer loop; model fetches context mid-run), **BL-333** (reasoning trace — outer loop + LiteLLM callback are complementary capture points), **BL-335** (per-step token audit), **BL-161** (internal multi-agent pipeline), **BL-160a/b** (supervised + visibility), **BL-340** (turn-based backend may make route A natural without route C), **BL-347** (re-compile policy per step), **BL-349** (inject recent touches between steps), **BL-351** (escalate to host when supervisor cannot auto-decide).

**Open design:** Single `delegation_id` with sub-step records vs child ids; max steps; when to auto-expand context vs return to planner; strict-mode revert per step vs end-only.

---

### BL-351: Simulated interactive mode + host escalation (human intervention)

**Status:** `done` — **Phase 10 P10-003 + Phase 11 P11-002 shipped**: stall detect + structured `needs_input` plus supervised confirm handling (`SupervisedIO` + `DelegationSupervisor`, abort-on-escalate). Remainder deferred: mid-run async resume / outer-loop continuation in Phase 12.

**Problem:** Headless Aider uses `InputOutput(yes=True)` — every confirm (“add file?”, “run shell?”) is auto-approved without mcp-coder judgment. When the model asks for files in prose, we fail the delegation rather than help. There is no path for the **executor to route a decision back to the Cursor planner** for human intervention inside a supervised delegate.

**Goal:** Replace blind `yes=True` with **simulated interactive** supervision:

1. **Cheap supervisor** (helper LLM or rules, `context_builder`-class model) handles routine prompts: add path as read, widen context, continue step, deny out-of-contract edit.
2. **Re-compile** context when supervisor approves expansion (BL-350, BL-347).
3. **Escalate to host** when supervisor is uncertain or policy requires human OK → return structured `needs_input` / `clarification_needed` (same pattern as **BL-329** spec validation) so **Cursor** shows the question; planner answers; delegation resumes via retry / outer-loop step.

**Implementation sketches (compose with BL-350):**

| Sketch | Mechanism |
|--------|-----------|
| **D — Supervised `InputOutput`** | Subclass Aider `InputOutput`: `confirm_ask` / prompts → supervisor LLM instead of `yes=True`; escalate → abort run with host payload |
| **Outer loop + host gate** | BL-350 route A: after each sub-run, supervisor inspects; auto-fix or return to Cursor before next step |
| **Async / long-running** | If human latency exceeds MCP timeout, persist “awaiting_host” state + resume token (**BL-501** adjacency) |

**Why powerful:** Combines automation (cheap model handles 80% of “add `foo.py` as read”) with **human judgment** for contract changes, risky shell, or ambiguous scope — without a real terminal REPL (**BL-160d**). Cursor stays the planner; mcp-coder owns the supervise → escalate → resume protocol.

**Related:** **BL-350**, **BL-329** (`clarification_needed`), **BL-324** (judgment loop), **BL-160a** (supervised complex task), **P1-ISS-016** (add-files-to-chat failure today), **BL-332** (host = Cursor for escalation target).

---

### BL-352: Multi-language picker / repo-map coverage

**Status:** `idea` — 2026-06-10. Surfaced T-04 Q&A on `SCAN_EXTENSIONS` (no C/C++/Go/Rust today).

**Today:**

| Layer | Coverage |
|-------|----------|
| **Spec / `target_files`** | Any path — language-agnostic |
| **Symbol scan (`rg`)** | `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.md`, `.yaml`, `.yml`, `.toml` only — hardcoded `SCAN_EXTENSIONS` |
| **Repo map / excerpts** | Python-style `def`/`class` regex — weak for C/C++/Go/Rust/Java |

**Gap:** Polyglot repos (C/C++ extensions, Go, Rust, Java, Ruby, …) get full payloads only when explicitly listed in the spec; backtick symbol queries won’t discover `parser.c` or `main.cpp`.

**Later (incremental, before full BL-348 AST):**

1. **Widen `SCAN_EXTENSIONS`** — at minimum `.c`, `.h`, `.cpp`, `.hpp`, `.cc`, `.go`, `.rs`, `.java`, `.kt`, `.rb`, `.php`, `.sql`, `.sh`, `.json`; optional workspace config `context_scan_extensions` or detect from repo (`.go` module, `Cargo.toml`, etc.).
2. **Per-language outline patterns** for repo-map / excerpts — e.g. C `^\w+.*\($`, Go `^func `, Rust `^fn ` — v0 regex table, not full AST.
3. **Align** `MAP_EXTENSIONS` vs `SCAN_EXTENSIONS` (today `.json` is map-only, not symbol-scan).
4. **Long-term:** BL-348 language-aware index subsumes regex outlines; BL-352 is the cheap path until then.

**Related:** **BL-348** (proper index), **BL-347** (policy), T-04 §4 symbol scan.

---

### BL-353: LLM boundary observability — full pass-through logging

**Status:** `done` — 2026-06-16. Phase 9 completes this item.

**Target phase:** **Phase 6+7+8+9 fully shipped** — P6 helpers/tokens, P7 executor step events + compile provenance, P8 Aider inner-loop + thinking tokens, P9 write-always + universal proxy + context blob + model registry + policy_applied. BL-367 closed.

**Problem:** Today we audit **intent** more than **reality**. A full `delegate_to_agent` / `mcp-coder delegate` run appends one `delegations.jsonl` row — but most **wire traffic** is missing or only inferable.

#### What full delegate logs today (MCP + CLI)

| Captured in JSONL | Not captured (gap) |
|-------------------|-------------------|
| `delegation_pipeline` — phase name, status, `duration_ms` | Per-phase **input/output bodies** (picker rank list is in `candidate_files`; no assemble/budget before/after snapshots) |
| `context.context_package` — path, tier, bytes, truncations (**no payloads**) | File payloads / fenced read blocks |
| `context.adapter_in` — `fnames`, `read_paths_in_prompt`, prompt size/hash | Same fields duplicated on CLI `artifacts.executor_in` only — **not** in JSONL |
| `context.prompt_preview` (~500 chars); opt-in `prompt_full` (`MCP_CODER_LOG_FULL_PROMPT=1`) | **Final** executor string only — not each Aider turn inside `coder.run()` |
| Helper **flags** — `builder_brief_applied`, `architect_plan_applied`, errors | Helper **input prompts** (`build_builder_llm_prompt`, architect, spec_validation) and **raw completions** |
| `model_roles` — model + duration per role (**tokens often null**, BL-335) | Reasoning / thinking tokens (**BL-333**) |
| `host_transcript_path`, `host_session_id`, hash, `lines_parsed` / `lines_skipped`, truncation bytes | **Source line range** in Cursor JSONL (“used through line N”); which turns were injected vs dropped |
| `inspect-context` / `delegate --stop-after context` | **No JSONL** — stdout only |

Hard to answer: “What exact prompt did the builder LLM see?” “What did Aider get on turn 3?” “Which Cursor transcript lines were in scope at validation vs builder vs executor?”

**Goal:** One **backend-neutral pass-through** at the LLM boundary — every completion crosses a shared hook (no behavior change by default). Plus a **compile provenance bundle** so each LLM call’s inputs are attributable to pipeline stage.

**Recommended mechanism (primary):**

| Piece | Approach |
|-------|----------|
| **Intercept** | `litellm.success_callback` (+ failure hook) at MCP startup; thin `completion()` wrapper all roles use |
| **Coverage** | Executor (**all** Aider turns), `context_builder`, `architect_pass`, `spec_validation`, `test-model`; **BL-354** executor-pull tool calls as separate audit events |
| **Correlation** | `contextvars`: `delegation_id`, `role`, `pipeline_phase`, `step_index`, optional `parent_call_id` |
| **Compile bundle** | Per delegate, structured refs + hashes: `mechanical_brief`, `builder_input`, `builder_output`, `architect_*`, `validation_*`, `final_executor_prompt`, `context_package` entry tiers — “what came from what step” without re-parsing one blob |
| **Host transcript provenance** | Extend `transcript_log_context`: `source_path`, `file_bytes`, `lines_parsed`, **`last_source_line`** (or byte offset range), `truncation_policy`, `bytes_dropped` — enough to slice the Cursor JSONL file for replay |
| **Disk side** | `post_gateway` / `workspace_history` unchanged — LLM log ≠ file edits |

**Phased delivery:**

| Slice | When | Delivers |
|-------|------|----------|
| **5a — tokens + transcript refs** | Phase 5 early | Fix **BL-335**; transcript line/byte provenance; compile bundle **hashes only** in JSONL |
| **5b — helper wire log** | Phase 5 | Store builder/architect/validation request+response in per-delegation trace file (truncated default) |
| **6 — full tap** | Phase 6 | All executor multi-turn + reasoning payloads; viewer timeline (**BL-343**) |

**Storage tiers (config):**

1. **Metadata always** — model, role, tokens, latency, status, content hashes (+ compile bundle hashes).
2. **Truncated bodies** — default in trace file / optional `llm_calls[]` summary on delegation row.
3. **Full bodies opt-in** — `capture_llm_traces: full` or env; `redact_secrets`; size caps. Supersedes ad-hoc `MCP_CODER_LOG_FULL_PROMPT` over time.

**Storage sketch:** `~/.mcp-coder/projects/<key>/sessions/<id>/traces/<delegation_id>.jsonl` (one line per LLM call + optional compile event); slim `delegations.jsonl` row holds pointers + hashes. Long-term: bodies move to **BL-356** RAG refs where corpus-backed (**lean JSONL**).

**Explicit non-goals (v1):** HTTP proxy; replacing canonical `delegations.jsonl` row; auto-indexing raw traces into RAG without curation.

**Composes:** **BL-333**, **BL-335**, **BL-350**, **BL-343**, **BL-354** (tool-call audit), **BL-356** (lean refs once RAG digests exist). Design refs: [AGENTIC_LOOP_LOGGING.md](./OTEHR_RELATED_IDEAS/AGENTIC_LOOP_LOGGING.md), [REASONING_TRACE_REUSE.md](./OTEHR_RELATED_IDEAS/REASONING_TRACE_REUSE.md).

**Open design:** retention/TTL; default hash-only vs truncated bodies for helpers; export/consent for eval; whether CLI `artifacts` envelope is mirrored into JSONL or always resolved via trace file.

---

### BL-354: Executor context tools (pull) — RAG/history/read during backend loop

**Status:** `done` — **Phase 11 P11-003 v0 shipped** (system prefix `/read` hint only, prompt-level behavior). Full sidecar HTTP tool server (Sketch B below) deferred to Phase 12.

**Dual model (intentional):**

| Mode | Who | When | Today |
|------|-----|------|--------|
| **A — Compile-push** | mcp-coder compiler + builder | Before `coder.run()` | **Default** — picker, tiers, brief, `fnames` |
| **B — Executor-pull** | Backend LLM during inner loop | Mid-run, model-chosen | **Not wired** — planner MCP tools (`rag_search`, `history`, …) exist; executor cannot call them |

**Goal:** Keep **A** as the baseline (spec contract, predictable prompt, budget). **Add B** so the executor can organically fetch more context — RAG queries, delegation history, file excerpts, recent touches (**BL-348/349**) — via **specialized read-only tools** alongside normal edit/shell tools. Less mcp-coder micromanagement than **BL-350**; more model-driven than front-loading everything.

**Candidate tool surface (backend-neutral):**

| Tool | Wraps | Read-only |
|------|--------|-----------|
| `search_delegations` / `rag_search` | `core/rag/search.py` | yes |
| `workspace_search` | BL-002 workspace-file RAG (when built) | yes |
| `get_delegation_summary` / `get_file_history` | `core/workspace/history_query.py` | yes |
| `read_path_excerpt` | `core/context/excerpts.py` or on-demand read | yes |
| `list_recent_files` | BL-349 (when built) | yes |
| `ask_planner` / escalate | **BL-351** — human gate, not silent expand | policy |

**Not in v1:** executor tools that widen `files_edit` without spec/policy; arbitrary shell (stays constrained); duplicating planner-only MCP surface wholesale.

**Implementation routes (try in order):**

1. **CLI subprocess from Aider** — e.g. model runs `mcp-coder rag search …` via shell tool (hacky; dogfood whether pull helps).
2. **Backend function tools** — native tool schema on backends that support it; thin wrappers call same `core/` functions as MCP.
3. **BL-340 Cursor SDK** — may be the cleanest first backend for real tool calling.

**Requires:** tool-call audit (**BL-353**); policy per `edit_scope` / spec; likely smarter than blind `yes=True` for tool approval (**BL-351**). **post_gateway** unchanged — disk truth still after loop.

**vs BL-350:** Outer loop = mcp-coder **controls** steps and re-compile. BL-354 = mcp-coder **offers** tools; backend LLM **decides** when to pull. Composable: compile-push defaults + pull on demand; supervisor loop for hard cases.

**Phase:** **5+** — especially once **BL-002** indexes exist; dogfood with delegation RAG first. Evidence from tutorial pass: today we **ignore** executor-side tool access entirely.

**Open design:** which tools on by default; max calls per delegate; inject tool results into Aider chat vs replace compile; compare push-only vs push+pull in eval.

---

### BL-355: Optional host CLI toolchain (`rg`, docs, doctor)

**Status:** `idea` — 2026-06-11. Surfaced T-04 playground — `rg` missing on PATH; file picker still worked via Python fallback.

**Problem:** mcp-coder silently degrades when common dev CLIs are absent. Users discover gaps mid-tutorial (`rg: command not found`) or get slower symbol scan with no visible hint. No single place documents **recommended vs required** host tools.

**Today:**

| Tool | Required? | Used for | If missing |
|------|-----------|----------|------------|
| **git** | Soft (repo workflows) | `files_changed`, dirty snapshot, untracked hints in assemble | Manifest-only diff; untracked warnings weaker |
| **rg** (ripgrep) | No | File picker symbol scan (`file_picker.py`) | Pure-Python scan (slower on large trees) |
| **jq** / **grep** | No | Tutorial / operator inspection of JSON | User picks alternatives |
| **Python 3** | Yes | Runtime | N/A |

**Later (incremental):**

1. **`mcp-coder doctor`** (or `setup --check-tools`) — print found/missing optional binaries + install hints (macOS `brew`, apt, etc.).
2. **Docs** — T-01 “recommended toolchain” box; link from T-04 pitfalls.
3. **Candidates to evaluate** (not committed): `fd` (fast find), `ast-grep` / tree-sitter (BL-352 polyglot), `ctags`/`universal-ctags`, `shellcheck`/`ruff` for verify hooks — only add when a code path needs them.
4. **Optional:** warn once per workspace when picker used Python fallback (`context.metadata` or server log).

**Non-goals:** Bundling binaries in the pip wheel; hard-failing delegate when `rg` absent.

**Phase:** **5+** DX / onboarding polish (pairs with **BL-341** setup, **BL-345** spec lint CLI).

**Related:** **BL-352** (multi-language scan may prefer AST tools over regex+rg), **BL-348** (incremental index may reduce per-delegate rg volume).

---

### BL-356: RAG-backed context audit refs — lean JSONL + digest provenance

**Status:** `idea` — 2026-06-11. Follow-on to T-04 observability discussion + **BL-002** Phase 5 RAG planning.

**Problem:** Today `delegations.jsonl` grows if we store full prompts (`prompt_full`), helper inputs, and inline host chat. Duplication across delegations (same transcript slice, same file summary) does not scale. Conversely, once **BL-353** captures wire traffic, we need a **stable join key** between audit logs and retrievable content — not another copy-paste blob per row.

**Direction:** As **BL-002** (and **BL-348**) build indexed digests, **audit logs store references**, not bodies:

| Content type | Today (inline / opt-in) | After RAG + BL-356 |
|--------------|-------------------------|---------------------|
| Cursor host chat | `host_transcript: dump` → inject full text; hash + line counts in JSONL | **Curated digest** in RAG (session chunks, outcome-labeled where possible); compile pulls **retrieved chunks**; JSONL = `context_refs[]` + query + chunk ids + sha256 |
| Prior delegations / builder history | Summaries from `workspace_history.db` in builder prompt | **Delegation RAG** + checkpoint digests; builder retrieves by spec/project; log refs `delegation_id` + summary doc id |
| Workspace file context | Full read payloads / excerpts in prompt | **BL-002** file summaries + **BL-348** symbol index; prompt gets retrieved snippets; log refs `(path, sha256, chunk_id)` |
| Helper LLM I/O | Not logged (**BL-353** gap) | Trace file or RAG “prompt/response” docs with `role`, `phase`, `delegation_id` metadata |
| Executor prompt | `prompt_full` opt-in | Hash + trace ref; full text in trace store or content-addressed blob |

**Index-time metadata (required for replay):** every digest/chunk row should carry enough to re-fetch and explain provenance without opening JSONL:

- `source_kind` — `cursor_transcript` \| `delegation` \| `workspace_file` \| `spec` \| `llm_trace`
- `source_path` or `delegation_id` / `spec_id`
- `source_line_range` or `byte_range` (for transcripts and files)
- `sha256` of source at index time
- `indexed_at`, `stale_after` / content hash for invalidation
- optional `outcome` / `labels` for chat distillation (accepted vs rejected ideas)

**`delegations.jsonl` shape (lean):** keep timing, outcome, `files_changed`, `delegation_pipeline`, `model_roles`, compile bundle **hashes**, and `context_refs: [{kind, id, sha256, lines?, role?}]`. Full replay = JSONL row + trace file + RAG lookup (**BL-343** viewer).

**Interaction with compile-push vs pull:**

- **BL-354** executor-pull: each `rag_search` / `workspace_search` call logs `query` + `context_refs` returned — same ref schema.
- **BL-350** supervised loop: per-step re-compile appends new refs; timeline shows which retrieval fed which step.

**Phase:** **5+** — design alongside **BL-002** corpus expansion; implement after first workspace-file + delegation digest paths exist. **BL-353** Phase 5a (hashes + transcript line refs) can ship before full RAG refs.

**Non-goals:** Indexing raw Cursor JSONL verbatim without distillation (see BL-002 chat row — revisit only via curated digests); replacing `workspace_history.db` checkpoints.

**Related:** **BL-002**, **BL-348**, **BL-349**, **BL-353**, **BL-354**, **BL-343**, **BL-357** (retention after lean refs exist).

---

### BL-357: Storage lifecycle — promote, prune, gc (logs + RAG + traces)

**Status:** `idea` — 2026-06-12. Surfaced RAG / Phase 5 planning — retention is cross-cutting; will become painful once RAG corpora, trace files, and lean refs accumulate.

**Problem:** mcp-coder stores **many** durable layers under `~/.mcp-coder/projects/<key>/` with no unified lifecycle policy. Everything grows until disk pain:

| Layer | Path / store | Grows how | Default bias |
|-------|----------------|-----------|--------------|
| **Delegation JSONL** | `sessions/<id>/delegations.jsonl` | +1 row per delegate | Project-scoped audit |
| **LLM traces** | `sessions/.../traces/*.jsonl` (**BL-353**) | Per call when enabled | Forensics window |
| **Server log** | `server.jsonl` | Events | Ops |
| **Delegation RAG** | per-project DB (**BL-002**) | Per delegate indexed | Project memory |
| **Workspace-file RAG** | `workspace_rag.db` | Per file summary | Refresh on sha256 |
| **Workspace history** | `workspace_history.db`, checkpoint blobs | Checkpoints, manifests | Restore / audit |
| **Excerpts / context cache** | `.mcp-coder/context/excerpts/` | Per large read | Regenerable |
| **Global / promoted knowledge** | `~/.mcp-coder/global/` (vision) | Outcome-gated patterns (**Corpus 4**) | **Long-term keep** |

We want **good stuff** (worked patterns, promoted digests, spec outcomes) without keeping **everything** forever. Project-scoped delegation noise should be prunable once lessons are promoted.

**Principle — promote then prune:** Never delete project audit/RAG rows until promoted artifacts exist (global Corpus 4, distilled chat, spec report, lean `context_refs[]` per **BL-356**). Replay = JSONL lean row + refs + optional archive — not full prompt bodies forever.

**Later tooling (incremental):**

1. **`mcp-coder maintenance`** (or `storage gc`) — report disk by layer; **dry-run** prune; per-workspace and global totals.
2. **TTL / caps** — config: max delegation JSONL age/rows, max trace size, max per-project RAG rows (defaults conservative).
3. **Promote** — copy digest/pattern to global store with `promoted_from: {workspace, delegation_id}`; dedupe by `sha256`.
4. **Archive** — tar old session JSONL/traces with manifest; keep lean index row.
5. **Stale invalidation** — RAG file rows when sha256 changes; optional “stack tag obsolete” on global patterns.
6. **Integrate** with `view delegations` / **BL-343** — show archived vs live.

**Non-goals (v1):** silent auto-delete without promote path; prune checkpoints user might restore (**BL-322g**); mandatory cloud offload.

**Phase:** **6+** — after **BL-356** lean refs and at least one RAG corpus in dogfood use; thin **report-only** slice could land earlier (disk breakdown, no delete). Pairs with [notes/rag-gap-analysis.md](./notes/rag-gap-analysis.md) § Retention and [notes/storage-and-linking.md](./notes/storage-and-linking.md).

**Related:** **BL-002**, **BL-353**, **BL-356**, **BL-322** (checkpoints), **BL-348** (index staleness), Corpus 4 outcome-gated ingest (rag-gap-analysis).

---

### BL-358: Post-executor polish pass — reviewer model (comments, tests, alignment)

**Status:** `in_phase` — **Phase 11 P11-005 owns tier-1 v0** (cheap model scan on `files_changed`, review note in spec report, opt-in). Tier-2 epic-boundary review + polish pass (v2) deferred to Phase 12.

**Problem:** Aider/executor optimizes for **making the change work** — not for comments, test coverage, naming consistency with the rest of the repo, or light alignment with neighboring modules. Planner or human often does that cleanup in a follow-up pass.

**Proposal:** Optional **post-executor phase** (after `executor`, before or after `post_gateway` / `spec_report`):

| Piece | Intent |
|-------|--------|
| **Input** | `files_changed` from delegate + spec contract + read-tier neighbors (wider than executor `fnames`) |
| **Model** | Cheap, **large context** role (e.g. `context_builder` tier / Flash) — not the executor model |
| **Output** | Second edit pass: docstrings, inline comments, missing tests, import/style alignment, **micro-refactors that preserve behavior** |
| **Guardrails** | `edit_scope` + post_gateway diff; optional `polish_pass: logic_locked` (no semantic changes); spec flag `polish: true` |
| **Audit** | New `delegation_pipeline` phase `polish_pass`; `model_roles.polish` |

**Distinct from adjacent items:**

| Item | Difference |
|------|------------|
| **BL-006 critic** | Grades output → may **redo** executor; polish assumes success and **refines** |
| **`mode=review`** | Pre-implement spec Q&A — before code |
| **`auto_verify`** | Runs external command (pytest) — does not edit files |
| **Architect pass** | Pre-executor plan in brief — no file edits |
| **Executor** | Primary logic/feature implementation |

**Implementation sketch (later):**

1. Config: `polish_pass: true` or spec front matter `polish: comments,tests`.
2. Compile read context for changed files + same-directory / import neighbors (**BL-348** helps).
3. One-shot or small-loop LLM with explicit “no behavior change” prompt; apply via same backend adapter or read-only SEARCH/REPLACE on `files_changed` only.
4. Re-run post_gateway; include polish diff in spec report.

**Risks:** scope creep into second feature implementation; model “improves” logic anyway → need diff review + `logic_locked` tests. **Not RAG** — context is fresh from disk.

**Trigger policy (recommended):** default **off**; run at **epic boundary** (`epic_exit`, last step) or spec `polish: true` — not every delegate. Config: `polish_trigger: off | epic_exit | spec | always`.

**Phase:** **5+** (after D-P4-8 role audit stable; pairs with **BL-162** Stage 2, **BL-006** if critic and polish share infrastructure).

**Related:** **BL-359** (umbrella workflow turns), [notes/multi-model-roles.md](./notes/multi-model-roles.md), **BL-335**, **BL-351**.

---

### BL-359: Workflow turns — refactor, document, digest cadence

**Status:** `idea` — 2026-06-12. **Horizon:** Phase 5+ / later (not near-term). **North star:** formalize the developer workflow into named turns while automating easy, repetitive tasks (digest, polish, verify, cadence hints) — judgment stays with planner/human.

**Living note:** [notes/workflow-turns.md](./notes/workflow-turns.md)

**Problem:** Today: `mode=review` (pre-spec Q&A) + `mode=implement` (+ optional `auto_verify`). Missing first-class turns for:

| Turn | User need | Today |
|------|-----------|-------|
| **Polish** | Comments, tests, alignment after feature works | — → **BL-358** |
| **Refactor** | Structure/renames/extracts; behavior unchanged | Ad-hoc implement (risky scope) |
| **Document** | Module docs, README, epic narrative | Planner manual / outside MCP |
| **Digest / audit / onboard** | After N phases: understand code, gaps, debt | `inspect-context`, history CLI — no guided “pause & report” turn |

**Goal:** Named workflow turns with **own rules**, compiler/executor behavior, and **cadence policy** — user-initiated, spec-flagged, or **semi-auto suggest** to planner (host rules help Cursor offer the right turn).

**Cadence (default bias):**

| When | Suggested turns |
|------|-----------------|
| **Per step** | `implement` only |
| **Epic boundary / pause** | `digest` (read-only report) → optional `polish` / `refactor` |
| **User explicit** | Any turn via spec front matter or MCP arg |
| **Semi-auto** | After epic step N or M delegations: `suggested_turn: digest` in MCP response — planner accepts/skips |

**Semi-auto is not autonomous:** mcp-coder **suggests**; Cursor planner or human decides (pairs with **BL-351** escalate).

**Host / planner:** Cursor rules for when to offer digest vs review vs refactor; generic content can live in managed rules (**BL-332** deferred).

**Implementation paths (incremental):**

1. **Digest** — `mode=digest` or spec `turn: audit`: wide read compile + delegation/history summary; LLM report artifact (no executor); cheapest first slice.
2. **Polish** — **BL-358** post-executor phase.
3. **Refactor** — `mode=refactor` + spec contract; wider `files_edit`; stronger `logic_locked` + verify required.
4. **Document** — edit doc paths only; or planner writes digest markdown without delegate.

**Distinct from:** **BL-006** critic (grade/redo), **BL-329** spec validation (pre-block), RAG (retrieval corpora — digest may *use* RAG).

**Phase:** **5+** — digest/report slice can precede polish/refactor; host rule text can land early without new modes.

**Related:** **BL-358**, **BL-332**, **BL-351**, [spec-review-loop.md](./notes/spec-review-loop.md), **BL-002** (digest input).

---

### BL-332: Host-agnostic planner rules sync

**Status:** `deferred` — **keep Cursor-only for now** (2026-06-09). Revisit when a second host (BL-201 Claude Desktop, BL-202 other IDE) is prioritized.

**Problem:** Managed planner guidance is **Cursor-specific** end-to-end, even though MCP may run under other hosts:

| Layer | Today | Coupling |
|-------|-------|----------|
| **Call site** | `main.py` always calls `sync_workspace_cursor_rules(ws)` on stdio startup | Unconditional — not gated on `MCP_CODER_HOST` or host provider |
| **Destination** | `.cursor/rules/*.mdc` | Cursor-only path + frontmatter (`alwaysApply`, `mcp_coder_managed`, …) |
| **Module naming** | `core/host/cursor_rules.py`, `cursor_rules_policy.py` | Implies Cursor even though logic is mostly generic file sync |
| **Host abstraction** | `HostProvider` covers session + transcript (`cursor.py`, `null.py`) | **No** `sync_rules()` / `planner_guidance()` hook — rules live outside the provider |

**What is already host-neutral (2026-06-09):**

- Rule **content** is plain markdown guidance (delegate flow, spec paths, judgment loop, context builder notes).
- **Compile-at-sync:** `<!-- @include use-mcp-coder.shared.md -->` in bundled sources → `_resolve_includes()` inlines shared sections into one file before write. Workspaces never see include markers.
- **`manifest.yaml`** maps `src` → `dest` per policy (`default` / `strict`); `includes:` marks source-only fragments (not synced standalone).

**Why not fix now:** Cursor is the only supported host in practice; BL-201/202 are low priority. Premature abstraction risks wrong dest formats before a second host is dogfooded.

**Possible solutions (pick when revisiting):**

| Option | Sketch | Pros | Cons |
|--------|--------|------|------|
| **A — Gate + skip** | If `host_provider != cursor`, skip sync (like `is_mcp_coder_source_root`) | Minimal change; honest about support matrix | Other hosts get no managed guidance |
| **B — Host hook** | Add `HostProvider.sync_planner_rules(ws) -> dict`; Cursor impl writes `.mdc`; `NullHost` no-op | Clean seam; `main.py` stops importing Cursor module directly | Still one adapter per host |
| **C — Manifest per host** | Extend `manifest.yaml`: `hosts: { cursor: { rules: [...] }, claude: { rules: [{ dest: AGENTS.md, … }] } }` | Reuse compile engine + shared content; one content tree | Need to learn each host's instruction format and load semantics |
| **D — Compiled markdown only** | Sync host-neutral `use-mcp-coder.md` (no `.mdc` frontmatter); host adapters wrap or copy | Content fully portable | Each host may need different wrapping (always-on vs file-scoped) |

**Recommendation (tentative):** **B + C** — host hook that reads a host section from manifest; Cursor stays default; second host adds a row + thin writer. Keep `_resolve_includes()` and `use-mcp-coder.shared.md` as the single content source.

**Related:** BL-205 (routing snippet), BL-324 (judgment loop in rules), BL-325 (spec paths in rules), P4-ISS-012 (context builder / `target_files` guidance — shipped in rules v13).

---

## Reliability & executor (Phase 2+)

### BL-309: Delegation hardening (job failure vs workflow failure)

**Status:** `deferred` — **P1-ISS-012** (`wontfix-p1` at Phase 1 exit). **Wave 1:** P2-125 (309a/b).

**Goal:** A delegation may fail because the model or upstream provider failed the **task**. It must not break the **workflow** (browser storms, empty files, 3+ minute opaque hangs, confusing partial repo state).

**Job failure (acceptable):** bad edits, tests fail, `success: false`, spec § Blockers updated.

**Workflow failure (fix):** side effects and operator confusion beyond a clean failure record.

| Sub | Item | Notes |
|-----|------|-------|
| BL-309a | Headless URL policy | `MCP_CODER_AIDER_DETECT_URLS=0` default for MCP; never `webbrowser.open` on exceptions when `yes=True` / headless (`core/config/aider_runtime.py`, Aider `check_and_open_urls`) |
| BL-309b | Classified errors to Cursor | Map to `upstream_5xx`, `rate_limit`, `context_overflow`, `edit_format`, `config`; strip HTTP headers from `output` |
| BL-309c | MCP-layer transient retry | 1–2 retries on 5xx with backoff (optional `AIDER_MODEL_FALLBACK`) |
| BL-309d | Empty-file guard | Roll back or skip 0-byte stubs when delegation fails after Aider pre-create |
| BL-309e | Bounded run time | Per-delegation timeout; fail fast vs 200s Aider retry loops |
| BL-309f | `partial` outcome | `success: true` but `files_changed: []` → failure or explicit `partial` |
| BL-309g | Conversational implement | **partial done P1-151** — `infer_run_success` rejects “add files to chat” (P1-ISS-016) |

**Code touchpoints:** `core/config/aider_runtime.py` (`detect_urls`, `infer_run_success`, `create_delegation_io`), `core/engine/aider_engine.py`, `server/mcp_server.py` (tool response), LiteLLM `finish_reason: error` handling (upstream).

#### How to replicate (2026-06-05 E2E)

Use this to verify fixes or confirm regressions.

**1. Environment**

```bash
# mcp-coder repo .env (or MCP env in consumer mcp.json)
AIDER_MODEL=openrouter/qwen/qwen-2.5-coder-32b-instruct
OPENROUTER_API_KEY=<key>
```

**2. Consumer workspace**

- Path: `mcp_coder_phase1_e2e` (or fresh clone with same layout)
- `.mcp-coder/config.yaml`:
  ```yaml
  session_policy: align_host
  host_transcript: none
  cursor_rules_policy: strict
  ```
- Spec: `.mcp-coder/specs/tasks/expense-splitter.md` (step 1 — multi-file)

**3. Sanity check (should pass)**

```bash
cd /path/to/mcp_coder
mcp-coder test-model          # Aider path, tiny prompt
mcp-coder test-model --via both
```

**4. Trigger failure mode**

- Open E2E workspace in Cursor; new or existing chat
- Delegate step 1 with **6 target files** and full spec (multi-file task), e.g. models + splitter + tests + sample JSON + pyproject
- Or replay logged task from session `1462cdef-daed-42e9-b25b-2551332d2ba1`

**5. Logs to inspect**

| Log | Path |
|-----|------|
| Server audit | `~/.mcp-coder/server.jsonl` — `delegation_received` / `delegation_failed` |
| Session delegations | `~/.mcp-coder/projects/5f18f39de273e250c92ba63c0d1e082fb0e77022dc5d27fa2142d05fe6f755b0/sessions/1462cdef-daed-42e9-b25b-2551332d2ba1/delegations.jsonl` |
| Spec run log | `.mcp-coder/specs/tasks/expense-splitter.md` § Run log |

**Failed delegation IDs (Qwen run):** `84fc7701`, `e25021a2`, `693ae958`, `a1b40348`, `cf42535f`.

**6. Expected symptoms (pre-fix)**

- `response_to_cursor.output` contains `provider: Cloudflare`, `finish_reason: 'error'`, `code: 500`
- LiteLLM `OpenrouterException - Invalid response object` / pydantic `literal_error` on `finish_reason`
- URLs in output: `https://checkout.stripe.com`, `https://js.stripe.com`, `https://errors.pydantic.dev/...` (from error dump headers, not task)
- Browser may open those URLs (macOS)
- Empty or partial files under `expense_splitter/`
- Duration often **87–250s** before fail

**7. Control (same workspace, stronger model)**

```bash
AIDER_MODEL=openrouter/anthropic/claude-sonnet-4
mcp-coder test-model
```

Repeat step 1 delegate → **success** observed `da11a5cd` (~29s, 4 files), follow-up `cb5da42a` (~8s). Confirms mcp-coder wiring; isolates cheap-model / upstream route.

**8. Acceptance after BL-309 ship**

Re-run steps 3–4 with Qwen; expect `success: false` with short classified error, **no** browser tabs, **no** new 0-byte stubs, completion within configured timeout.

---

### BL-310: Planner verify / report status split

**Status:** `partial` — **BL-310b/c done** P4-010 (2026-06-09); **BL-310a deferred**.

**Goal:** Make the split between **MCP run succeeded** and **step acceptance met** visible in reports and tool responses.

| Sub | Item | Status |
|-----|------|--------|
| BL-310a | Report status `verified_ok` (planner sets?) vs MCP `delegated_ok` / `reviewed` / `blocked` | deferred |
| BL-310b | Optional MCP hook: run `pytest` (configurable command) post-implement | **done** P4-010 — `auto_verify` opt-in; `verify_result` on MCP + JSONL |
| BL-310c | `outcome: partial` when edits applied but tests fail (if hook enabled) | **done** P4-010 — `apply_verify_outcome()` |

**Today:** Planner runs `pytest` in Cursor by default; workspaces may opt in via `auto_verify: true` / `MCP_CODER_AUTO_VERIFY=1`. Live dogfood TBD (P4-ISS-019).

---

### BL-311: Read-deps from spec Files section

**Status:** BL-311a `done` (P2-110); **BL-311b `done`** (P3-311, 2026-06-09).

**Goal:** Reduce cross-step API guessing when implement `target_files` omits files listed under task spec **Files** (read deps).

| Sub | Item |
|-----|------|
| BL-311a | Warn in tool response when `mode=implement` and spec Files paths ⊄ `target_files` — **done** P2-110 |
| BL-311b | Auto-merge read-only paths into delegate context from spec Files — **done** P3-311 |
| BL-311c | Cursor rule generator: split Files into “edit” vs “read” in delegate call hints — deferred |

**E2E:** Step 2 implement #1 without `splitter.py` → wrong `load_expenses` signature; fixed by planner delegates #2–3.

---

### BL-312: Auto-review policy (optional)

**Status:** `deferred` — D-SPEC-1 locked at P1-199 ([PHASE1_MVP.md](./PHASE1_MVP.md)).

**Goal:** Decide whether MCP or rules should **suggest** `mode=review` when task spec references prior-step files or epic step > 1.

Not shipped — review remains planner/user triggered.

---

### BL-314: Honest delegation file reporting

**Status:** `deferred` — **partial done** P1-152 (2026-06-06).

**Goal:** Full visibility when executor scope expands beyond planner intent.

| Sub | Item | Status |
|-----|------|--------|
| BL-314a | `files_changed` = all git-touched paths during delegation | **done** P1-152 |
| BL-314b | `files_unexpected` in tool response + JSONL | **done** P1-152 |
| BL-314c | Spec report **Scope expansion** section when `files_unexpected` non-empty | deferred |
| BL-314d | Tie to `edit_scope: strict` enforcement | deferred → BL-315 |

**Source:** P1-ISS-017 (closed at P1-152).

---

### BL-315: `edit_scope` + spec Files YAML

**Status:** `partial` — BL-315a/b **done** P2-115; BL-315c → P2-200 context compiler.

**Goal:** Structured spec contract for edit vs read paths; MCP enforcement policy.

| Sub | Item |
|-----|------|
| BL-315a | YAML front matter: `files_edit`, `files_read` — **done** P2-115 |
| BL-315b | `edit_scope: discover` \| `strict` — post-check `scope_violation` — **done** P2-115 |
| BL-315c | Builder reads spec as primary contract when `spec_path` set — **P2-200** |

Phase 1 uses markdown `### Edit` / `### Read` only (P1-152).

---

### BL-316: Context builder file materialization tiers

**Status:** `deferred` — **Phase 2 Wave 2** ([PHASE2_MVP.md](./PHASE2_MVP.md) P2-200, P2-210).

**Goal:** mcp-coder **context compiler** (L2) decides per path how content enters the executor prompt — **behavioral contract**, not Aider `fnames` passthrough. Adapters (L3) map `ContextPackage` to backend-specific calls.

| Tier | Use |
|------|-----|
| `edit-full` | May edit; full body |
| `read-full` | Context only; full body |
| `read-excerpt` | Snippet / symbol slice |
| `pointer` | Path + summary line |
| `map-only` | Tree / index |
| `hide` | Omit |

**Flow:** L1 contract (spec policies) → `assemble_context()` → `ContextPackage` → `BackendCapabilities` + adapter translate → `ExecutionResult` with audit fields. Extends BL-001.

**Tasks:** P2-200 (assembler), P2-205 (excerpts), P2-210 (adapter hinge), P2-212 (capabilities), P2-215 (inspect dry-run). **Design:** [notes/phase2-owned-context.md](./notes/phase2-owned-context.md) (D-P2-1–7).

**Source:** P1-199 thesis; bridges P1-152 read-deps + `files_unexpected`.

---

### BL-317: Cursor project slug robustness

**Status:** `deferred` — **P1-ISS-002** (`carried` at P1-199).

**Goal:** Reduce slug heuristic failures mapping workspace → `.cursor/projects/<slug>/`.

| Sub | Item |
|-----|------|
| BL-317a | README troubleshooting (env `MCP_CODER_CURSOR_PROJECT_SLUG`) — partial in README |
| BL-317b | Cache resolved slug in workspace `.mcp-coder/project.json` after first success |
| BL-317c | Optional scan fallback across slug variants |

---

### BL-318: `project_key` alias on repo move

**Status:** `deferred` — **P1-ISS-005** (`carried` at P1-199).

**Goal:** When repo is cloned/moved, link old `~/.mcp-coder/projects/<old_key>/` to new `project_key` or provide import tool.

By design today: `project_key` = SHA-256(resolved path).

---

### BL-002: RAG / cross-session memory

**Status:** `partial` — **Phase 5 compile-push slice done** (2026-06-13). Milestones P5-001…P5-004 + P5-006 dogfood fix; optional P5-005 capstone deferred.
**Delegation RAG:** indexed post-delegate (Phase 3); wired into builder + `rag_retrieval` (P5-002).
**Workspace-file RAG:** `workspace_rag.db`, `index-workspace`, `search files`, picker/builder hints (P5-003…P5-004).
**Defaults:** `builder_history_rag`, `workspace_file_rag`, `workspace_file_hints` → **on** (opt-out via yaml/env).
**Living design note:** [notes/rag-gap-analysis.md](./notes/rag-gap-analysis.md)
**Code:** `core/rag/`, `core/config/rag.py`, `core/cli/search.py`, `core/cli/index_workspace.py`

**Still open (Phase 5+):** see table below — corpora, integration modes, DX polish, measurement. **Not** “RAG missing from CLI” (core toolset shipped).

| Gap | Backlog | Notes |
|-----|---------|-------|
| Executor-pull (RAG mid Aider loop) | **BL-354** | Compile-push default; planner MCP exists, executor cannot call |
| Chat / decision-log corpora | **BL-356**, corpus table below | Raw chat skipped; curated digests |
| Lean JSONL / digest provenance | **BL-356** | `context_refs[]` partial shipped P5-001 |
| Cross-project RAG | **BL-002** | Single workspace scope today |
| Storage gc / maintenance | **BL-357** | No `mcp-coder maintenance` |
| Richer code intel (AST, deps) | **BL-348** | Beyond file-summary RAG |
| CLI/MCP DX polish | **BL-365** | Legacy `rag` vs `search`; workspace stats |
| Recall / cost / embeddings | **BL-366** (P5-005) | Deferred capstone |
| Live token audit | **BL-335** | **done** (partial) — delegation-level; inner-loop → BL-350 |
| Validation-block observability | **BL-364** | Empty `context_refs` confusing |

#### Corpus decisions

| Corpus | Phase | Approach | Rationale |
|--------|-------|----------|-----------|
| **Workspace source files** | **4 — primary** | Hash (SHA-256) + LLM-generated summary per file + FTS5 | Core use case: planner asks "what does this file do?" / "which files are relevant?" before delegating. Hash-based staleness = re-index only on change. File-level granularity is enough for planning; sub-file chunking is overkill. |
| **Delegation records** | 4+ | Wave 1 inspect tools now; FTS5 when scale hurts | `list_delegations` + `get_checkpoint_detail` sufficient at <200 rows. Add keyword search when pain is felt. |
| **Decision log** | 5 | Structured exit notes → FTS5 | Session-end host writes 3–5 key decisions + deferred items. Higher signal than raw chat. |
| **Spec files** | Skip | Grep / direct read | Too small to index (~5–50 files). |
| **Chat transcripts** | Skip (raw) | N/A | Raw JSONL not indexed — noise vs signal. **Revisit via BL-356:** curated session digests with outcome/metadata for builder/RAG retrieval; inline `host_transcript: dump` remains until then (**BL-353** transcript line provenance bridges gap). |
| **Cursor rules / config** | Skip | Direct read | Planner reads these directly; no search needed. |

#### Architecture (locked for Phase 4)

```
Index:   workspace source files only (Phase 4 start)
Entry:   (path, sha256, llm_summary, symbol_list, indexed_at)
Update:  on workspace_snapshot or post-delegation hook
         if sha256(file) != stored_hash → re-summarize
Search:  FTS5 on summary + symbols → ranked file list
Tool:    workspace_search(query) → [(path, summary, symbols)]
Storage: ~/.mcp-coder/projects/<key>/workspace_rag.db
```

#### What we explicitly don't do (Phase 4)
- No sub-file chunking (file-level is enough for planning context)
- No vector embeddings (FTS5 BM25 sufficient for code symbol/summary search; add later if recall proves insufficient)
- No delegation history in same DB (different lifecycle and access pattern)
- No raw chat transcript indexing

#### Phase 5 outcome (2026-06-13)

Phase 5 shipped compile-push RAG: `rag_retrieval` pipeline phase, `search delegations|files`, `index-workspace`, `workspace_search` MCP, defaults on. Dogfood exit met. Optional P5-005 → **BL-366**. DX polish → **BL-365**.

#### Shipped CLI/MCP toolset (reference)

| Capability | CLI | MCP |
|------------|-----|-----|
| Search delegations | `search delegations`, `rag search` | `rag_search` |
| Search workspace files | `search files` | `workspace_search` |
| Index workspace | `index-workspace` | — |
| Backfill delegation index | `rag index` | auto on delegate |
| Builder retrieval | `delegate`, `inspect-context` | `delegate_to_agent` |

**Observability coupling:** RAG entries should ship with **BL-356** index-time metadata (source line range, sha256, `delegation_id`/`spec_id` links) so `delegations.jsonl` can stay lean — refs not bodies — and **BL-353** trace replay can join on `context_refs[]`.

---

### BL-320: Failed-delegate attempt archive (spec-adjacent)

**Status:** `done` — Phase 3 Wave 2 rules-only ([PHASE3_MVP.md](./PHASE3_MVP.md) P3-320); P3-ISS-002 closed.

**Problem:** Planner-facing `specs/reports/*.md` tracks **current** step status; failed retries are either buried in Run log (truncated) or only in JSONL. No first-class “attempt history” per step.

**Proposal:**

| Piece | Notes |
|-------|--------|
| BL-320a | Workspace config `retain_failed_attempts: true` (default off or `on_failure_only`) |
| BL-320b | Write `.mcp-coder/specs/attempts/<spec_id>/<delegation_id>.md` (or JSONL) on **failed** implement/review — model, duration, `error_class`, sanitized output, link to JSONL |
| BL-320c | Main report stays lean: Status + latest success; **Attempts** section lists links to failed archives (last N) |
| BL-320d | Optional MCP tool `list_delegation_attempts(spec_path)` for Cursor — wraps JSONL + attempt files |

**Not in scope:** Replacing `delegations.jsonl` (still canonical); duplicating full Aider transcripts unless `MCP_CODER_LOG_VERBOSE`.

**Target:** Phase 3 Wave 2 — P3-320a/b/c/d.

---

### BL-322: Workspace history — delegation-granularity version control

**Status:** `partial` — **Wave 1 shipped** (BL-322a–f, P3-322a–322f); restore/fork sub-items deferred ([PHASE3_MVP.md](./PHASE3_MVP.md)). Designed 2026-06-07 (chat [Phase 2 tail review](d44a5b15-2ed4-4834-bc91-91f776e5dd02)).  
**Full design:** [docs/OTEHR_RELATED_IDEAS/WORKSPACE_HISTORY.md](./OTEHR_RELATED_IDEAS/WORKSPACE_HISTORY.md)

**Problem addressed:** P2-ISS-002 (`files_changed` misses new files without git); strict scope enforcement that reports violations but leaves workspace dirty; inability to time-travel to any MCP call boundary across a project lifecycle.

**Core insight:** mcp-coder can own a lightweight, delegation-scoped version control layer — SQLite delta store, independent of git, invisible to the user, automatic. Hash the whole workspace before each delegation; store unified diffs (not full copies) of what changed; accumulate checkpoints across sessions. Purpose-built for the "what did the AI do between calls?" question that no existing tool answers at this granularity.

**Why it matters:** AI coding tools either ignore the audit problem, force auto-commits (pollutes git), or depend on git (fails for untracked files, dirty workspaces, non-git repos). This approach is non-invasive — user's git, WIP, and untracked files are untouched — and works at exactly the right granularity (per delegation call = per human review opportunity).

**Storage:** `~/.mcp-coder/projects/<key>/workspace_history.db` — SQLite, stdlib only. Delta + content-addressable blobs. ~6–10MB for months of work on a typical project.

---

#### Phase 3 sub-items

| Sub | Item | Notes |
|-----|------|-------|
| **BL-322a** | **Workspace hash snapshot** (manifest) | Before delegation: SHA-256 walk → in-memory manifest; persist delegation row + file deltas in `~/.mcp-coder/projects/<key>/workspace_history.db` (see [WORKSPACE_HISTORY.md](./OTEHR_RELATED_IDEAS/WORKSPACE_HISTORY.md)). After delegation: diff manifests → `created` / `modified` / `deleted`. Replaces fragile mtime fallback. Git-primary when git works; manifest when `used_git=False` or env override. |
| **BL-322b** | **Content snapshot for contract files** | Store full content of `files_edit` + `files_read` files (not hashes) before delegation. Enables **revert** of violation files to pre-delegation state. Other files: hash-only. |
| **BL-322c** | **Post-delegation gateway** (diff vs policy) | After diff computed, check against spec `files_edit` / `files_read`. `strict`: revert violation files using BL-322b content + block. `discover`: report only (current P2-305 behavior). New `gateway` mode: surface diff to human or pass to reviewer model (see BL-322d). |
| **BL-322d** | **Diff in MCP response + CLI history** | `delegation_diff` on delegate response; MCP `get_delegation_diff`; CLI `history list\|diff\|revert`. Pairs with BL-151 pre-gate for full cycle. **`done`** P3-322d. |
| **BL-322e** | **Checkpoint metadata (dataset labels)** | `checkpoint_summary`, telemetry, `spec_path` on `snapshots` rows; JSONL `checkpoint` block; D-P3-9. **`done`** P3-322e. |
| **BL-322f** | **History inspect (browse DB)** | MCP `list_delegations`, `get_checkpoint_detail`, `get_file_history`; CLI `show\|latest\|file`; `spec_report_path` pointer. **`done`** P3-322f. |
| **BL-322g** | **Restore to checkpoint** (`restore_to_checkpoint`) | Write **post-delegation** file content from `content_hash` blobs to disk (opposite of `revert_to_before`). Read-only `file_at(delegation_id, path)` for MCP. CLI `history checkout <id> [--paths …]`. **`deferred`** — P3-322g; trigger after P3-401 dogfood if bisect hurts. |
| **BL-322h** | **Checkpoint fork / sandbox try** | Non-destructive: materialize checkpoint state in a **copy dir** or ephemeral overlay so user can run tests without mutating live workspace. Optional MCP `fork_checkpoint`. **`deferred`** — design after BL-322g; pairs with **BL-502** (git worktree) for git-native teams. |

**Shipped undo (not restore):** `revert_to_before` + CLI `history revert` (BL-322b) undoes **one delegation** on selected paths — distinct from BL-322g “go back to known-good state.”

---

#### What to include in snapshot scan

```text
SKIP (hard exclusions — by directory):
  node_modules/  .venv/  venv/  env/  __pycache__/
  .git/  dist/  build/  .tox/  .mypy_cache/  .pytest_cache/
  .mcp-coder/             ← entire tree skipped (workspace-owned MCP metadata)

SKIP (by extension or binary heuristic):
  .pyc  .so  .dll  .exe  .jpg  .png  .gif  .pdf  .zip  .tar  .gz

INCLUDE everything else — including:
  .env  config files  new untracked files  files outside spec contract
```

**Key:** No `.gitignore` dependency. Binary detection by extension + UTF-8 decode attempt. Size cap: skip files > configurable limit (default 1 MB, configurable `MCP_CODER_SNAPSHOT_MAX_FILE_MB`).

---

#### How this upgrades scope violation detection

Today (P2-115 / P2-305):
```
scope_violations = files_changed ∩ (not in files_edit)
                   ↑ incomplete in non-git workspaces
```

With BL-322a:
```
scope_violations = snapshot_delta.all_changes ∩ (not in files_edit)
                   ↑ complete — catches everything including new files,
                     modified untracked files, files outside target_files
```

---

#### Relation to existing items

| Item | Relation |
|------|----------|
| **P2-ISS-002** | Closed by BL-322a (non-git attribution) |
| **BL-314** | BL-322a completes the "honest file reporting" story |
| **BL-151** (gatekeeper MCP) | BL-322c is the post-run gate; BL-151 is the pre-run gate — together form full enforcement cycle |
| **BL-502** (git worktree / diff return) | BL-322 is the simpler, non-git version; BL-322h (sandbox fork) is the non-git “try without touching live tree”; BL-502 remains git-native task branches |
| **P2-305** (scope expansion report) | BL-322c replaces soft reporting with hard enforcement when configured |

---

#### Performance estimate

Typical Python project (~500 text files, avg 5 KB each):
- SHA-256 scan: ~20ms — negligible vs 30–200s delegation
- Manifest JSON: ~100 KB — trivial
- Content snapshot (files_edit only, e.g. 5 files × 10 KB): ~50 KB

Node project without `node_modules`: similar. With `node_modules` included: 50k+ files — **must exclude** (already in hard skip list).

---

#### Rollback design (BL-322b + BL-322c strict)

```text
Before delegation:
  snapshot/contents/src/splitter.py  ← saved content of files_edit

Aider runs, also modifies config/settings.py (violation)

Post-gate (strict):
  config/settings.py → revert to pre-delegation content from snapshot
  src/splitter.py    → accept (was in files_edit)
  src/utils.py       → revert (was created, not in files_edit)

Result: workspace has ONLY the contract-allowed changes
```

**Strict mode with teeth** — today strict reports violations but leaves workspace dirty. With BL-322b: strict mode can enforce a clean post-state.

---

**Target:** BL-322a–f **done** (397 pytest). Next: **BL-322g** restore/checkout if dogfood needs it; **BL-322h** fork/sandbox; or **BL-502** git worktree for teams with git.

---

### BL-323: Context budget override semantics (dev ergonomics)

**Status:** `idea` — from P2-ISS-009 (frozen at Phase 2 exit).

**Problem:** `MCP_CODER_CONTEXT_BUDGET_TOKENS` loses to per-model `context_budget_tokens` in `model_rates.yaml` — dogfood budget tests require fake model id.

**Options:** (a) env overrides yaml when set, (b) `MCP_CODER_CONTEXT_BUDGET_OVERRIDE_TOKENS`, (c) `inspect-context --budget-tokens N` only, (d) document yaml-wins.

**Target:** Not Phase 3 core — ship when touching P2-220 / INSTALL docs.

---

### Phase 3 exit — carried from [PHASE3_ISSUES.md](./PHASE3_ISSUES.md) (P3-499, 2026-06-09)

| ID | Source | Phase | Summary |
|----|--------|-------|---------|
| BL-324 | P3-ISS-005 | 4 | Planner inspect-tool adoption (judgment loop) |
| BL-325 | P3-ISS-006 | 4 | Spec paths only under `.mcp-coder/specs/` |
| BL-326 | P3-ISS-007 | 4 | Read-deps `(none` parse fix |
| BL-327 | P3-ISS-008 | 4 | Surface failed delegations in host summary |
| BL-328 | P3-ISS-009 | 4+ | Dogfood spec `v2` retry workflow |
| BL-330 | P4-ISS-002 | 4+ | `server.jsonl` events for inspect MCP tool calls |
| BL-331 | Wave 2 discussion | 5+ | Symbol-scoped / chunked edit files (executor format change) |

#### BL-324: Planner inspect-tool adoption (judgment loop)

**Status:** `deferred` — **P3-ISS-005** (`wontfix-p3` at P3-499 exit).

**Problem:** `workspace-history.mdc` v3 requires `get_delegation_diff` / inline `delegation_diff` after implement; hosts use file `Read` + `pytest` instead.

**Evidence:** P3-499 transcript `d43d06f7` — no inspect MCP calls; earlier step-3 dogfood `e7966a6c` — same pattern.

**Candidate fixes:** Stricter rules; judgment checklist on MCP response; `server.jsonl` inspect-tool events; CLI UUID prefix for `history show`.

**Target:** Phase 4 (rules + optional MCP UX).

#### BL-325: Spec path convention — `.mcp-coder/specs/` only

**Status:** `deferred` — **P3-ISS-006**.

**Problem:** Host created `specs/epics/` and `specs/tasks/` at **repo root**; first delegate failed:

```
spec_path must be under .mcp-coder/specs/tasks/ (got 'specs/tasks/tip-calc-01-core-v1.md')
```

Delegation `58bb9846` failed; host recovered silently with duplicate spec tree.

**Target:** Phase 4 — `use-mcp-coder.mdc` explicit ban on repo-root `specs/`; optional MCP error message improvement.

#### BL-326: Read-deps `(none` parse glitch

**Status:** `deferred` — **P3-ISS-007**.

**Problem:** Spec Read `(none — greenfield)` → JSONL `auto_merged_read_paths: ["(none"]`.

**Target:** Phase 4 — `core/specs/read_deps_merge.py` treats none-sentinel as empty list.

#### BL-327: Surface failed delegations to host

**Status:** `deferred` — **P3-ISS-008**.

**Problem:** Failed attempt `58bb9846` absent from host final summary; visible only in JSONL/`server.jsonl`.

**Target:** Phase 4 — rules + optional delegate response hint when chaining retries.

#### BL-328: Spec `v2` retry workflow dogfood

**Status:** `deferred` — **P3-ISS-009**.

**Problem:** P3-499 happy path only — `v1` naming OK; no `v2` retry exercised.

**Target:** Phase 4+ optional dogfood step or acceptance test.

#### BL-330: Inspect-tool audit in `server.jsonl`

**Status:** `deferred` — **P4-ISS-002** (Wave 1 dogfood 2026-06-09).

**Problem:** `server.jsonl` logs delegation lifecycle only — cannot audit whether host called `get_delegation_diff` / `list_delegations` vs quoted inline `judgment_checklist` only.

**Target:** Phase 4+ optional — `inspect_tool_invoked` events for read-only MCP tools; pairs with P4-006 rules.

---

### BL-331: Symbol-scoped / chunked edit files

**Status:** `idea` — Phase 4 Wave 2 discussion, 2026-06-09. **Phase 5+ / executor-capability.**

**Problem:** Today `edit-full` sends the entire file to the executor — correct for Aider SEARCH/REPLACE but wasteful for large files. Chunked edit would send only the target function/class + surrounding signatures, reducing token cost.

**Why not now:**
- Aider SEARCH/REPLACE requires full file text to produce valid patches. Partial input → broken patch (`pyproject.toml` duplication in dogfood is this class of bug).
- Needs a new executor edit format (symbol-scoped patches, line-range anchors, or two-pass locate+edit) — adapter-level change, not context-compiler.
- Only worth building once Phase 4 telemetry shows how often large edit files actually blow the budget.

**Pre-requisites:** D-P4-11 backend-neutral repo map (symbol awareness); Phase 4 cost/token telemetry; executor edit format decision (Aider or replacement).

**What the data model already has:** `TIER_EDIT_FULL` sits alongside `TIER_READ_EXCERPT` / `TIER_POINTER` in `core/context/package.py`. A future `edit-excerpt` tier slot is implicit. No re-architecture needed when the executor format is ready.

**Target:** Phase 5+ — after Phase 4 reveals which files are actually large + frequently edited.

---

### Phase 4 exit — carried from [PHASE4_ISSUES.md](./PHASE4_ISSUES.md) (P4-EXIT partial, 2026-06-09)

**Phase 4 closed** with core Waves 1–4 shipped. Open issues below moved to backlog for **Phase 5 planning review** — pull into a phase milestone when ready; items marked **mandatory** block informed multi-model routing (BL-162 Stage 2), reasoning capture (BL-333), or cost-aware RAG (BL-002).

### Phase 6 exit (2026-06-13)

**Phase 6 closed** with recommended exit + P6-006…P6-008 post-dogfood fixes. Open/carried issues from [PHASE6_ISSUES.md](./PHASE6_ISSUES.md) → backlog for **Phase 7+** planning.

| ID | Source | Pull by | Summary |
|----|--------|---------|---------|
| BL-350 | P6-ISS-006 | **Phase 7 (shipped, partial)** | P7-002 delivered executor step events + bounded loop; continuation/escalation follow-ons remain |
| BL-368 | P6-ISS-002 | **Phase 7 (shipped)** | P7-001 delivered unified LlmGateway for owned callsites |
| BL-333 | P6-ISS-007, P6-ISS-009 | Phase 7+ | Extend reasoning capture (builder/architect); cross-session persistence |
| BL-367 | Phase 6 exit decision | **Phase 9** | Full-capture substrate — verbosity as display-only filter (Phase 8 closes Aider capture gaps first) |
| BL-357 / AGENTIC_LOOP_LOGGING | P6-ISS-010 | Phase 7+ | Novelty filter / curation pipeline (bootstrap: log raw first) |
| BL-321 | P6-ISS-011 | Phase 7+ | Escalation heuristic on reasoning capture signal |

**Partial shipped:** **BL-353** — P6 helper wire/tokens + P7 executor step events + P7 compile provenance bundle in trace. **Not shipped:** backend-complete interception parity and replay-grade full completeness (BL-367/BL-371).

| ID | Source | Pull by | Mandatory? | Summary |
|----|--------|---------|------------|---------|
| BL-309 | P4-ISS-006 | Phase 5+ | recommended | Executor leaves bad partial state → v2 retry (SEARCH/REPLACE quality); see § BL-309 |
| BL-309e | P4-ISS-004, P4-ISS-018 | Phase 5 | **yes** if long delegates common | Delegation timeout storms; 217s engine_run on full-file replace; document `MCP_CODER_DELEGATION_TIMEOUT_S` in templates |
| BL-328 | P4-ISS-007 | Phase 5+ | optional | Spec v2 retry after implement failure — **partially dogfooded** P4-EXIT (`prior_failed_attempts` on stats v2–v3); failure-driven versioned retry workflow still thin |
| BL-330 | P4-ISS-002 | Phase 5+ | optional | Inspect-tool calls not auditable in `server.jsonl` |
| BL-335 | P4-ISS-014, P4-ISS-015, **P5-ISS-001**, **P6-002/P6-008** | **done** | **done** | Helpers + executor tokens now resolved with authoritative precedence after Phase 8 cleanup: callback/backend capture → Aider attrs → stdout parse last-resort fallback. `owned_completion.py` shim removed; parser fallback demoted and tested (P8-005). |
| BL-336 | P4-ISS-003 | Phase 5+ | optional | `judgment_checklist` nested under `response_to_cursor` in JSONL only |
| BL-337 | P4-ISS-005 | Phase 5+ | optional | `config_deprecated` noise in `server.jsonl` (e.g. `MCP_CODER_FALLBACK_SESSION` in consumer `mcp.json`) |
| BL-338 | P4-ISS-016, P4-ISS-020 | **Phase 5** | **yes** before BL-321 | Executor `edit_format` / constraint blindness on cheap models (gpt-4o-mini); model-selection guidance or auto-escalation |
| BL-339 | P4-ISS-021 | Phase 5+ | optional | Spec validation dogfood: retry-history in spec masks deliberate format trap; validation works — improve trap methodology or spec template |

#### BL-335: Per-role token audit in delegation JSONL

**Status:** `done` (partial) — **P6-002/P6-008** closed live null-token gap for helpers; executor via `aider_output_parse`. **Remaining:** per-step executor token audit inside Aider inner loop → **BL-350**.

**Shipped (Phase 6):** LiteLLM callback + `owned_helper_llm.py` Route B; dogfood v3 `f9cb07fc` — all four `model_roles.*.tokens` non-null.

**Historical replicate (pre-P6, Phase 5):** delegation `712a04d9` — all tokens null (fixed by Phase 6).

**Why mandatory later:** BL-162 Stage 2, BL-333, BL-002 RAG cost budgeting, BL-353 observability — per-role usage now available at delegation level; inner-loop granularity needs BL-350.

#### BL-336: Top-level JSONL audit fields for judgment loop

**Status:** `deferred` — **P4-ISS-003**.

**Problem:** `judgment_checklist` and `delegation_diff` live only under `response_to_cursor` in `delegations.jsonl`. Log grep scripts report false "absent". MCP response to Cursor is correct.

**Mandatory?** No — ops/PM convenience only.

**Target:** Phase 5+ optional — duplicate keys on JSONL record top-level, or document in `storage-and-linking.md` / `history show`.

#### BL-337: Deprecated config noise in server log

**Status:** `deferred` — **P4-ISS-005**.

**Problem:** `config_deprecated` warn events clutter `server.jsonl` each delegation — likely `MCP_CODER_FALLBACK_SESSION` or legacy keys in consumer `mcp.json`.

**Mandatory?** No — cleanup / operator ergonomics.

**Target:** Phase 5+ — clean e2e MCP env template; document deprecated keys in INSTALL.md.

#### BL-338: Executor model quality — `edit_format` and constraint blindness

**Status:** `deferred` — **P4-ISS-016**, **P4-ISS-020** (P4-EXIT session `2f01bb11`).

**Problem:** gpt-4o-mini repeatedly fails multi-file delegates: malformed SEARCH/REPLACE (`edit_format`), ignores "stdlib only" (`import yaml`), partial apply leaves broken syntax. Architect pass + builder brief correctly state constraints; executor model ignores them. P4-EXIT stats step: 3 failed delegates, host applied v3 spec manually.

**Why mandatory before BL-321:** Auto-escalation needs a reliable failure signal + a stronger fallback model. Without documented model tiers or escalation on `edit_format`, operators hit 3× retry loops on every multi-file task.

**Fix options:** (a) model-selection doc in INSTALL / cursor rules (cheap vs multi-file); (b) BL-321 tiered retry on `edit_format`; (c) BL-334 executor system prefix reinforcing constraints; (d) whole-file edit format for small brownfield files.

**Target:** **Phase 5** — at minimum documentation + cursor rules; BL-321 implementation when escalation ships.

#### BL-339: Spec validation dogfood — retry-history vs format trap

**Status:** `deferred` — **P4-ISS-021**.

**Problem:** Deliberate YAML-vs-plaintext validation trap was overtaken by retry-history ambiguity in spec ("per v1 spec" vs v2/v3 narrative). Validation correctly blocked (`c56ad89c`); clarification was about version confusion, not output format.

**Mandatory?** No — validation feature works; this is dogfood methodology + optional spec template guidance (keep retry notes out of Constraints; use fresh v1 for format traps).

**Target:** Phase 5+ optional — spec template note or validation prompt tweak.

#### BL-364: Blocked-delegate pipeline skip reasons in JSONL

**Status:** `deferred` — **P5-ISS-004** (Phase 5 dogfood 2026-06-13).

**Problem:** When `spec_validation` blocks (`needs_input`), the compile pipeline — including `rag_retrieval` — does not run. JSONL has empty `context_refs` and no `delegation_pipeline` RAG rows. **Expected behavior** but easy to misread as a RAG regression when grepping logs.

**Replicate:** `spec_validation: true` + ambiguous or SEARCH/REPLACE-style host task → `needs_input`. Session `1432fc02-c6b1-4452-aa28-261ce77f896b` entries #2–#4 (`expensesplit-p5-dogfood-v2/v3`).

**Fix:** Emit `delegation_pipeline` skip entries on blocked delegates, e.g. `rag_retrieval: skipped (spec_validation_blocked)`.

**Target:** Phase 5+ / **BL-353**-5a observability. Related: **BL-329** dogfood note.

**BL-309e note (P4-ISS-004/018):** Four `delegation_timeout` storms before MCP restart (Wave 1 dogfood); stats v2 full-file replace hit 217s at `MCP_CODER_DELEGATION_TIMEOUT_S=200`. Operator fix: raise to 300s. **Pull into Phase 5** if bounded run time + clearer timeout errors not yet shipped (see § BL-309e).

---

### BL-321: Progressive / tiered executor model selection

**Status:** `deferred` — Phase 4 optional; **P3-ISS-004** (`wontfix-p3` at P3-499 exit).

**Problem:** Single global `AIDER_MODEL`; operator manually swaps `.env` and restarts MCP. Cursor can *suggest* upgrades but cannot *invoke* tiered retry without human.

**Two-layer model (user proposal):**

1. **Planner (Cursor)** — vague intent: `model_tier: mid` or natural language (“use a stronger model”); not enforced.
2. **MCP** — fine-grained pick from **annotated catalog** + heuristics (task file count, prior `error_class`, step revision).

**Proposal:**

| Piece | Notes |
|-------|--------|
| BL-321a | `resources/model_tiers.yaml` — tiers (`cheap`, `mid`, `strong`, `control`) → ordered OpenRouter ids + notes (speed, coding, cost); merge workspace override |
| BL-321b | Catalog maintenance: offline script (`mcp-coder models refresh`) and/or OpenRouter list + `test-model` smoke; optional auto-annotations (latency from JSONL percentiles) |
| BL-321c | Delegate param `model_tier` (optional) → MCP resolves id; JSONL logs `model_tier` + `model_resolved` |
| BL-321d | **Auto step-up** (config): on `timeout` / `upstream_5xx` / `unknown`, retry once with next tier in same tool call or return `suggested_tier` + `retry_hint` |
| BL-321e | **Auto step-down** (optional): after success on trivial step, suggest cheaper tier for next delegate (hint only) |
| BL-321f | Failure signals for step-up: classified `error_class`, pytest hook (BL-310b), or planner `mode=review` blocked |

**Relation to BL-007:** Ensemble is multi-model parallel; this is **sequential escalation** on one task.

**Target:** Phase 2 late (post-P2-200) or Phase 3 — needs stable usage telemetry (P2-120) and error taxonomy (P2-125).

---

### BL-319: Dynamic model rates (usage cost)

**Status:** `deferred` — static table shipped **P2-120** (`resources/model_rates.yaml`).

**Goal:** Keep `cost_est_usd` accurate as models and OpenRouter pricing change — without manual yaml edits for every new `AIDER_MODEL`.

| Sub | Item |
|-----|------|
| BL-319a | Refresh from **OpenRouter pricing API** (or documented endpoint) on MCP startup or periodic cache |
| BL-319b | Fallback: lightweight **scraper** / provider docs for non-OpenRouter models |
| BL-319c | Optional **workspace override** `.mcp-coder/model_rates.yaml` merged over bundled rates |
| BL-319d | CLI `mcp-coder rates refresh` or master-session doc for manual sync |

Until then: add rows to bundled `model_rates.yaml` when switching models; unknown model → `cost_est_usd.source: unknown_model`.

**Implements:** Post–P2-120 enhancement; pairs with usage telemetry (JSONL + MCP `usage` block).

---

## Observability & ops

| ID | Item | Notes |
|----|------|-------|
| BL-301 | Delegation log web UI | Extend viewer for `~/.mcp-coder` |
| BL-302 | Redaction policy doc for logs (secrets) | Required before sharing logs |
| BL-303 | Metrics export (Prometheus / statsd) | Enterprise-ish; low priority |
| BL-304 | Global index `hosts/cursor/<id>/index.json` | Cross-project session lookup — **P1-ISS-008** (`carried` at P1-199); one Cursor chat delegating to multiple repos |
| BL-317 | Cursor project slug robustness | **P1-ISS-002** — see § BL-317 |
| BL-318 | `project_key` alias on repo move | **P1-ISS-005** — see § BL-318 |
| BL-319 | Dynamic model rates for usage cost | **P2-120** static table; API/scraper later — see § BL-319 |
| BL-320 | Failed-delegate attempt archive | Wild test P2-ISS-007 — see § BL-320 |
| BL-321 | Tiered / progressive model selection | Wild test P2-ISS-008 — see § BL-321 |
| BL-305 | ~~Persistent MCP **server** log (process audit)~~ | **done** — P1-125 |
| BL-308 | Global `server.jsonl` locking / per-pid subfiles | P1-ISS-011; only if garbled lines in practice |
| BL-306 | Startup **code version / git hash** in MCP stderr | Detect stale process (P1-ISS-009) |
| BL-307 | `MCP_CODER_SINGLETON=all` aggressive global kill | Escape hatch; default stays per-workspace |

---

## Experiments to schedule (outcomes → backlog or phases)

| ID | Experiment | Outcome drives |
|----|------------|----------------|
| BL-401 | `always_new` vs `align_host` | Default `MCP_CODER_SESSION_POLICY` — **partial:** E2E favors `align_host` for test sandbox; keep default `always_new` globally |
| BL-403 | Prompt size vs failure rate per model | **Deferred** at P1-199; transcript cap partial P1-140 |
| BL-404 | Cursor `target_files` reliability | Schema / inference rules |
| BL-405 | Tool name/description for routing | MCP tool description |

---

## After Phase 1 — adapt our dev workflow to the product

| ID | Item | Notes |
|----|------|-------|
| BL-150 | ~~**Spec-based delegation**~~ | **done** — P1-150/151; [notes/spec-based-development.md](./notes/spec-based-development.md) |
| BL-151 | Gatekeeper MCP for protected specs | [OTEHR_RELATED_IDEAS/GATEKEEPING_MCP.md](./OTEHR_RELATED_IDEAS/GATEKEEPING_MCP.md) — **still deferred** post-P1-151 |
| BL-152 | Mirror `delegations.jsonl` + reports in product UX | Partial: `specs/reports/` mirrors delegation audit; viewer TBD |

---

## Execution backends (beyond Aider)

| ID | Item | Target | Notes |
|----|------|--------|-------|
| **BL-340** | **Cursor SDK executor backend** | later phase | See § BL-340 — practical OpenRouter bypass + Composer models + multi-backend routing; **not Phase 5** |
| BL-004 | **OpenCode adapter** (subprocess) | deferred | Aider-only until product is useful; adapter interface exists (`core/engine/`) |
| — | Claude Code / Codex CLI adapters | deferred | Same tier as BL-004 — not on roadmap until explicit need |

### BL-340: Cursor SDK as execution backend (beside Aider)

**Status:** `deferred` — 2026-06-09. **Backlog only** — pull into a **later phase** when multi-backend / provider choice is prioritized; **not Phase 5** (Phase 5 = RAG + builder improvements per [PHASES.md](./PHASES.md)).

**One-liner:** Add a second **execution adapter** that runs implement work via the [Cursor SDK](https://cursor.com/docs/sdk/python) (`cursor-sdk` / `Agent.prompt` local runtime) instead of Aider+OpenRouter — so users can delegate with **Cursor subscription models** (e.g. Composer) and without bringing their own LLM API key for the executor role.

**Host vs backend (important):**

| Layer | What it is today | BL-340 changes |
|-------|------------------|----------------|
| **Host** (BL-201/202) | Cursor IDE calls `delegate_to_agent` MCP tool | Unchanged — Cursor remains the planner/orchestrator |
| **Execution backend** | Aider only (`core/engine/aider_engine.py`) | Add `cursor_sdk_engine.py` — same `ExecutionEngine` contract, different runtime |

This is **not** a host adapter. Cursor-as-host + Cursor-SDK-as-executor is a valid and desirable combo: mcp-coder still owns context compiler, spec contract, pipeline, verify — only the edit engine swaps.

**Why useful:**

1. **No forced OpenRouter** — executor can use models bundled with Cursor; lowers setup friction for personal/small-team use.
2. **Cursor-native models** — access to Composer and other Cursor-routed models not exposed cleanly via Aider/LiteLLM today.
3. **Multi-backend routing (BL-162)** — MCP can pick `backend=aider` vs `backend=cursor_sdk` per delegation (or auto-route on task type / failure). Enables parallel experiments: cheap Aider path vs Cursor path; fallback on `edit_format` (BL-338) without operator env swap + MCP restart.
4. **Pairs with BL-321** — escalation step-up can mean "retry on Cursor SDK with Composer" instead of only "swap OpenRouter model id."

**Proposed architecture (backend-neutral rule holds):**

```text
delegate_to_agent(backend=…)
  → context compiler (unchanged)
  → ExecutionEngine factory
       aider        → AiderEngine (today)
       cursor_sdk   → CursorSdkEngine (new)
  → workspace manifest delta for files_changed (BL-322 — backend-agnostic)
```

| Piece | Location | Notes |
|-------|----------|-------|
| Config resolver | `core/config/executor_backend.py` | `default_backend`, per-role override, env `MCP_CODER_EXECUTOR_BACKEND` |
| Adapter | `core/engine/cursor_sdk_engine.py` | Translate `ContextPackage` → SDK prompt; `Agent.prompt` / `Agent.create` + `send` for multi-turn if needed |
| Audit | `delegations.jsonl` | `backend: cursor_sdk`, `model` from SDK result, tokens if exposed |
| MCP param | `delegate_to_agent` | `backend` already exists — extend factory beyond `aider` |

**Implementation routes (evaluate in spike):**

| Route | How | Trade-offs |
|-------|-----|------------|
| **A — Cursor SDK (preferred)** | Python `cursor_sdk.Agent` with `local: { cwd: workspace }`, model e.g. `composer-2.5`; one-shot `prompt()` v0, `create`+`send` v1 for follow-ups | Clean API; beta surface; need spike on file-edit reliability, `files_changed` extraction, auth (`CURSOR_API_KEY` vs local session) |
| **B — SDK cloud runtime** | Same SDK, cloud VM against cloned repo | CI/automation without local IDE; different auth/billing; not primary for Cursor-as-host dogfood |
| **C — Intercept / subprocess** | Fallback if SDK lacks file-scoped control: shell out to `cursor` CLI or IDE automation | Fragile, host-coupled; only if Route A cannot produce auditable edits |

**Spike acceptance (before full milestone):**

- [ ] `backend=cursor_sdk` completes a 1-file implement delegate on e2e workspace
- [ ] `files_changed` matches manifest delta (same as Aider path)
- [ ] `delegation_pipeline` + JSONL audit parity (`backend`, `model`, duration)
- [ ] Document auth: what the user must configure vs Aider+OpenRouter

**Multi-backend / parallel (later-phase stretch):**

- Config allowlist: `executor_backends: [aider, cursor_sdk]`
- BL-162 router: pick backend by spec hint, file count, or prior failure (`edit_format` on Aider → auto-retry cursor_sdk)
- **Not** literal parallel double-run by default — routing + fallback first; true parallel race (two backends, take first good result) is BL-007 ensemble territory

**Open questions (decide at spec time):**

1. Does local SDK use the user's IDE session auth or require separate `CURSOR_API_KEY`?
2. Token/cost audit parity with Aider (ties **BL-335** — mandatory for any backend comparison)?
3. SEARCH/REPLACE vs agentic file writes — does SDK return structured edits or only natural-language result?
4. MCP recursion: SDK agent with mcp-coder MCP enabled vs mcp-coder orchestrating SDK as dumb executor only (prefer latter for v1).
5. Relationship to **BL-334** — Cursor backend may not need Aider `system_prompt_prefix`; separate prompt translation in adapter.

**Related:** BL-004 (alternate engines pattern), BL-162/321 (routing/escalation), BL-338 (executor quality — Cursor path may reduce `edit_format` pain), BL-335 (token audit for backend comparison), BL-332 (host rules stay Cursor; this is execution layer).

**Target:** **Later phase (6+ or when scheduled)** — not on Phase 5 roadmap. Natural fit alongside BL-162 Stage 2 multi-backend routing, BL-321 escalation, or when operator demand for non-OpenRouter executor path is clear. Optional early spike only if product direction commits before Phase 5 closes.

---

## Ideas (unscoped)

| ID | Item |
|----|------|
| BL-501 | Job ID + async delegation (poll / MCP notification) for long Aider runs |
| BL-502 | Git worktree / task-branch per delegation — git-native audit trail + rollback (pairs with BL-322; alternative to BL-322h fork for git repos) |
| BL-503 | Grade executor output with cheap model before returning to Cursor |
| BL-504 | Global `~/.mcp-coder/config.yaml` defaults | Per-repo `config.yaml` shipped P1-130 |
| BL-506 | Generic `transcript.md` watch folder (non-Cursor hosts) |
| **BL-333** | **Reasoning trace capture + cross-delegation context feed** | See § BL-333 + [REASONING_TRACE_REUSE.md](./OTEHR_RELATED_IDEAS/REASONING_TRACE_REUSE.md); wire capture is part of umbrella **BL-353** |
| **BL-353** | **LLM boundary observability — full pass-through logging** | See § BL-353 + [AGENTIC_LOOP_LOGGING.md](./OTEHR_RELATED_IDEAS/AGENTIC_LOOP_LOGGING.md); **Phase 6+7 partial shipped**; backend-complete capture/replay completeness remains |
| **BL-354** | **Executor context tools (pull)** — RAG/history/read during backend loop | See § BL-354; dual with compile-push (A); **Phase 5+** |
| **BL-355** | **Optional host CLI toolchain** — `rg`, doctor, recommended deps | See § BL-355; **Phase 5+** DX |
| **BL-356** | **RAG-backed context audit refs** — lean JSONL, digest provenance | See § BL-356; pairs with BL-002 + BL-353; **Phase 5+** |
| **BL-357** | **Storage lifecycle** — promote, prune, gc (logs + RAG + traces) | See § BL-357; **Phase 6+** |
| **BL-358** | **Post-executor polish pass** — reviewer model (comments, tests, alignment) | See § BL-358; sub-mode of BL-359; **Phase 5+** |
| **BL-359** | **Workflow turns** — refactor, document, digest cadence | See § BL-359 + [workflow-turns.md](./notes/workflow-turns.md); **Phase 5+** |
| **BL-364** | **Blocked-delegate skip reasons in JSONL** | See table; **Phase 5+** |
| **BL-365** | **RAG toolset DX** — unified CLI, workspace stats | See § BL-365; **Phase 5+** |
| **BL-366** | **RAG evaluation (P5-005)** — recall, cost, embeddings | See § BL-366; **Phase 5+** |
| **BL-367** | **Full-capture substrate** — write-always storage + replay | **Phase 9 done** — P9-001 (write-always), P9-002 (context blob), P9-003 (proxy), P9-004 (replay CLI), P9-005 (GC), P9-006 (compare). See § BL-367. |
| **BL-368** | **Unified LlmGateway completion proxy** — single LLM boundary | **Phase 7 shipped (P7-001)** for owned callsites; backend-internal interception strategy tracked in BL-371 |
| **BL-369** | **CLI gateway bootstrap hardening** | **Done (Phase 8 / P8-003):** shared `ensure_observability_bootstrap()` path for server + CLI entry points |
| **BL-370** | **Host transcript byte-range provenance** | **Done (Phase 8 / P8-004):** `validation_input` compile events include `byte_start`/`byte_end` alongside `source_path`/`last_source_line` |
| BL-371 | **Backend-specific interception strategy for full in/out capture** | **Phase 8 delivered for Aider (P8-001 + P8-002 + P8-006 hardening).** Remaining: non-Python backends (Claude Code, Codex, OpenCode) via Phase 10+ HTTP proxy. |
| **BL-507** | **Thinking token capture verification** | **Phase 9 done** — `MCP_CODER_EXECUTOR_REASONING_EFFORT=high` → `reasoning:{effort:high}` in proxy raw_request; `thinking_tokens=38` in `backend_llm_call`; compare CLI: `proxy_thinking=True backend_thinking=True`. BL-507 resolved 2026-06-16. |
| **BL-508** | **Universal internal HTTP proxy** — `LocalLlmProxy` between litellm and real provider; all in-process callers route through it; model-prefix routing from env vars | **Phase 9 done (P9-003, P9-009)**; same proxy extended to out-of-process backends in Phase 10+ via base URL config |
| **BL-509** | **Content-addressable dedup for trace bodies** — replace repeated large text fields in trace events with sha256 refs; store blobs once in CAS store | Post-Phase 9 once corpus exists to measure dedup ratio; context package blob (P9-002) is the proof-of-concept |
| **BL-510** | **Remove `should_log_full_prompt` write gate from delegation row** | **Phase 9 done (P9-008)** — `MCP_CODER_LOG_FULL_PROMPT` gate removed; `prompt_full` written unconditionally; `should_log_full_prompt()` retired as no-op. |
| **BL-511** | **Model registry Stage 1** — `core/config/model_registry.py` + unified helper path + generation params + `policy_applied` | **Phase 9 done (P9-011 + P9-012)** — both shipped 2026-06-16; `reasoning_effort=high` → thinking tokens verified end-to-end. See [model-policy-layer.md](./notes/model-policy-layer.md). |
| **BL-512** | **Model policy layer — Stage 2: host-set policy** — MCP host passes `model_policy` block inside `delegate_to_agent` call; overrides env layer for that delegation; host can set per-role model, thinking budget, cost cap | Future (Phase 11+) — depends on BL-511; see [model-policy-layer.md](./notes/model-policy-layer.md) Stage 2 |
| **BL-513** | **Model policy layer — Stage 3: AI-suggested parameters** — lightweight pre-delegation analysis step (cheap LLM or heuristic) that examines the incoming task and suggests policy overrides (e.g. hard refactor → higher thinking budget); suggestion logged as `policy_suggestion` trace event; can be accepted/rejected/overridden | Future — depends on BL-511/BL-512; see [model-policy-layer.md](./notes/model-policy-layer.md) Stage 3 |
| **BL-514** | **Model policy layer — Stage 4: dynamic escalation** — outer-loop controller modifies active policy mid-delegation in response to runtime signals (retry exhausted → larger model; critic reject → more thinking; cost cap → downgrade); connects to BL-321/BL-006 signals | Future — depends on BL-511/BL-512/BL-513 and a critic or supervisor being in place; see [model-policy-layer.md](./notes/model-policy-layer.md) Stage 4 |
| **BL-516** | **CLI log health table + `trace inspect --summary`** — cross-delegation scan table (`mcp-coder log`), per-delegation health scorecard, `--no-truncate` on `trace inspect --field` | **Phase 10 — P10-004** (partial: `--summary` only); `mcp-coder log` table + `--no-truncate` → backlog. See § BL-516. |
| **BL-517** | **Executor `policy_applied` ignored-params** — don't imply `temperature`/`top_p`/`max_tokens` were applied when Aider owns them | **Phase 10 — P10-004** (full). See § BL-517. |
| **BL-518** | **Runtime log level / verbosity DX** — consolidate or document logging knobs; `.env.example` coverage; optional proxy debug logging | **Phase 10 — P10-004** (partial: docs + `.env.example`); unified master level + proxy debug → backlog. See § BL-518. |
| **BL-519** | **`MCP_CODER_PROXY_ENABLED` env toggle** — enable/disable `LocalLlmProxy` at bootstrap without code changes | **Phase 10 — P10-004** (full). See § BL-519. |
| **BL-106** | **MCP live progress + logging notifications** — FastMCP `report_progress` / `ctx.log` during `delegate_to_agent`; filtered egress from Phase 9 capture | **Phase 10 — P10-002** (POF). See § BL-106. |
| **BL-520** | **Live log tail / follow delegation** — `mcp-coder logs tail` on trace JSONL, server.jsonl, optional executor tee file while run is in flight | **Phase 10 — P10-002** (POF: trace tail). See § BL-520. |
| **BL-334** | **Backend prompt customization** (system prefix + edit-format control) | **Phase 10 — P10-001** (v0). See § BL-334 |
| **BL-340** | **Cursor SDK execution backend** (beside Aider) | See § Execution backends — BL-340 |

### BL-333: Reasoning trace capture + cross-delegation context feed

**Status:** `partial` — **P6-004 shipped** (executor reasoning capture + session hot buffer → builder brief). **Remaining:** builder/architect reasoning accumulation, cross-session persistence (P6-ISS-007, P6-ISS-009).
**Full design + motivation:** [docs/OTEHR_RELATED_IDEAS/REASONING_TRACE_REUSE.md](./OTEHR_RELATED_IDEAS/REASONING_TRACE_REUSE.md)

**One-liner:** High-end reasoning models emit a hidden `reasoning_content` trace per call which Aider discards (`remove_reasoning_content()`). Capture it once and it powers **three axes**: (1) **model upgrade/escalation** signal inside the MCP loop (or suggestion-only), (2) **transfer intelligence** — feed traces as context into later *cheaper* calls so a mid-tier model inherits the expensive thinking, (3) **training data** — `(task, context, trace, outcome)` tuples for distillation and for replacing hand-written modules (picker, builder, validation) with learned e2e components. "Reason once expensively, propagate downhill" + a data flywheel.

**Capture route (recommended):** LiteLLM `success_callback` at MCP startup — backend-neutral, covers builder/validation/architect *and* Aider executor calls; no Aider patching. Alternatives (`model.reasoning_tag = None`, Coder subclass) in the design doc.

**Storage:** `delegation_reasoning_summary` (truncated) in JSONL + in-memory session dict; optional `workspace_history.db` column for cross-session. Inject via `gather_builder_history()` (P4-001b) under existing token budget.

**Related:** **BL-353** (umbrella wire logging — reasoning capture is one payload type), BL-162 (multi-model routing — this is the propagation mechanism), BL-321 (reasoning trace = escalation trigger), BL-334 (backend prompt control — both modify what we send/receive at the LLM boundary), P4-001b builder history (injection point), P4-ISS-014/015 (token tracking; reasoning tokens extend the same gap).

---

### BL-334: Backend prompt customization (system prompt prefix + edit-format control)

**Status:** `done` — **Phase 10 P10-001 shipped** (v0: env/yaml wiring + audit). Per-delegation override remains deferred to BL-512 Stage 2 (Phase 11).

**Origin:** Same Phase 4 discussion. We hand Aider a prompt, but Aider wraps it with **its own** system prompt (`main_system`), hard-coded example conversations, and a SEARCH/REPLACE `system_reminder`. We currently pass content only; we don't shape Aider's framing.

**Aider hooks available (no forking):**

| Hook | What it does | mcp-coder use |
|------|--------------|---------------|
| `model.system_prompt_prefix` | String prepended to Aider's `main_system` before the LLM call (Aider uses it for `/no_think`, "Formatting re-enabled."). | Inject delegation-level constraints / persona / "respect spec contract" reminder ahead of Aider's generic prompt. Set on the `Model` in `aider_engine.py` before `Coder.create()`. |
| `Coder.create(edit_format=…)` | Selects edit format (editblock, whole-file, udiff, …) → different `gpt_prompts` + system reminder. | Per-delegation or per-model edit-format choice (e.g. whole-file for tiny files, editblock default). Already partly model-driven; expose as config. |
| Subclass `gpt_prompts` | Replace `main_system` / `system_reminder` wholesale. | Heavier; only if we want to fundamentally change executor instructions. Out of scope for v1. |

**Proposed scope (v1, small):**

| Sub | Item |
|-----|------|
| BL-334a | `core/config/` resolver for an optional **executor system prompt prefix** (env `MCP_CODER_EXECUTOR_SYSTEM_PREFIX` + yaml `executor_system_prefix`); applied via `model.system_prompt_prefix` in `aider_engine.py`. Default: none (byte-identical to today). |
| BL-334b | Optional **edit-format override** (env/yaml `executor_edit_format`) passed into `delegation_coder_kwargs()` / `Coder.create()`. Default: model's native format. Audit chosen format in JSONL `context` block. |
| BL-334c | Audit: record `system_prefix_applied: bool` and `edit_format` on the delegation record so prompt-shaping is visible in history. |

**Backend-neutral rule:** the *resolver* lives in `core/config/` (no Aider terms); the *application* (`system_prompt_prefix`, `edit_format`) stays in `core/engine/aider_engine.py` / `aider_runtime.py`. Other backends ignore unknown knobs.

**Why useful:** lets mcp-coder steer the executor (tone, constraints, format) without rewriting prompts per call, and is a prerequisite for per-role/per-model prompt tuning under BL-162. Pairs with BL-333 at the same LLM boundary (334 = what we send; 333 = what we keep from the response).

**Open question:** does prefix injection interfere with Aider's prompt caching (cache key includes system prompt)? Measure before enabling by default.

---

### BL-367: Full-capture substrate — LlmGateway proxy + verbosity as display-only filter

**Status:** `done` — 2026-06-16. **Phase 9 complete.** P9-001 (write-always), P9-002 (context blob), P9-003 (universal proxy), P9-004 (replay CLI), P9-005 (GC), P9-006 (compare), P9-007–P9-010 (attribution, prompt_full, gzip fix, trace inspect), P9-011 (unified helper path + registry), P9-012 (generation params + policy_applied). All Phase 9 north-star criteria verified including BL-507 (thinking tokens at HTTP boundary).

**Origin:** Phase 6 exit review. Phase 6 shipped the observability seam and helper traces — but verbosity still controls **what gets written to disk**, meaning at `lean` or `standard` verbosity, prompt bodies and executor turns are permanently lost. This is the wrong direction: training-data quality, forensic replay, and debugging all require that **nothing is ever silently dropped at write time**.

#### The architectural shift

| Phase 6 (current) | BL-367 target |
|-------------------|---------------|
| `verbosity: lean` → writes hashes only; previews lost | Always write 100% to disk at the capture boundary |
| `verbosity: standard` → writes 500-char previews; bodies lost | Verbosity = display/export filter only (viewer, CLI, RAG promotion) |
| `verbosity: full` → writes bodies | Same result, but now the **default** for storage |
| Executor inner loop: opaque (no data) | Executor loop owned → every turn captured |
| Helpers via `litellm.completion` Route B | All LLM calls through unified `LlmGateway` proxy |

**Why "capture everything first, filter after":** the AGENTIC_LOOP_LOGGING bootstrap sequence says *log everything raw — no filtering — until you have enough data to train a classifier*. Filtering before that destroys signal you didn't know you needed. Storage cost for one heavy user is trivial (~10–18 MB/day raw; see [AGENTIC_LOOP_LOGGING.md](./OTEHR_RELATED_IDEAS/AGENTIC_LOOP_LOGGING.md) §Storage). The current verbosity tiers remain useful as **retention / promotion policy** (what gets indexed into RAG, what gets exported for training) — not as a capture gate.

#### What this requires

| Piece | Blocker | BL ref |
|-------|---------|--------|
| Unified `LlmGateway` completion proxy | Single boundary for every LLM call (helpers + executor), replacing LiteLLM callback shim | **BL-368** |
| Executor loop ownership | See every Aider turn, tool call, retry — not just outer litellm callback hits | **BL-350** |
| Write-always trace store | Trace file always written (not gated on verbosity); verbosity flag only controls viewer output and RAG promotion | small refactor of `core/observability/trace.py` + config |
| Context package blob storage | Store full package (not just hash) so any delegation is fully replayable from disk alone | new `session_dir/context_packages/<hash>.json` sidecar |
| Systematic replay path | Given a `delegation_id`, reconstruct exact prompt + context from local store without needing Cursor chat | ties together all the above |

#### Non-goals (still deferred)

- Novelty filter / curation / classifier → BL-357 / P6-ISS-010
- Cross-session reasoning accumulation → P6-ISS-009
- Training dataset export UI → AGENTIC_LOOP_LOGGING product scope
- HTTP proxy / network tap → out of scope

#### Verbosity after BL-367

| Tier | Storage | Viewer | RAG promotion | Training export |
|------|---------|--------|---------------|-----------------|
| `lean` | 100% captured | Hashes + counts only | No | No |
| `standard` | 100% captured | Previews (500 chars) | Summaries | No |
| `full` | 100% captured | Full bodies | Full bodies | Opt-in tuples |

**Composes:** **BL-350** (executor loop), **BL-353** (wire log — BL-367 is its graduation), **BL-356** (lean JSONL — pointers still valid; bodies now always on disk), **BL-333** (reasoning capture — same proxy), **BL-368** (LlmGateway design). Design refs: [AGENTIC_LOOP_LOGGING.md](./OTEHR_RELATED_IDEAS/AGENTIC_LOOP_LOGGING.md) §Bootstrap sequence.

---

### BL-368: Unified LlmGateway completion proxy

**Status:** `done` — 2026-06-13. **Phase 7 (P7-001) shipped** for owned callsites. From **P6-ISS-002**.

**Origin:** Phase 6 shipped two capture paths — LiteLLM `success_callback` (Route A, executor + shim) and `owned_helper_llm.py` + `record_owned_completion()` (Route B, helpers). Both work but are transitional. Long-term: **one completion proxy** at the LLM boundary for every send/receive.

**Goal:** Replace per-backend capture hacks with `LlmGateway` (or equivalent) in `core/observability/` — single boundary for helpers, executor, `test-model`, and future backends. Scope broader than logging: tokens, trace bodies, reasoning, budget caps, redaction, rate limits.

**Prerequisite for:** **BL-367** (full-capture substrate — proxy must exist before capture-everything-always makes sense).

**Acceptance sketch (shipped for owned paths):**
- All owned LLM calls route through proxy (no direct `litellm.completion` scattered in engine modules)
- Executor path: proxy tap even when still using Aider adapter (until BL-350 owns loop)
- `NullObservability` / tests can swap proxy for no-op
- Callback becomes thin shim or removed once proxy covers all paths

**Related:** **BL-350** (executor loop — proxy alone cannot see inner Aider turns), **BL-353** (umbrella wire log — partial shipped Phase 6+7), **BL-367** (Phase 8 full capture), **BL-371** (backend-specific interception strategy), [AGENTIC_LOOP_LOGGING.md](./OTEHR_RELATED_IDEAS/AGENTIC_LOOP_LOGGING.md).

---

### BL-369: CLI gateway bootstrap hardening

**Status:** `done` — 2026-06-14. Carry from P7-ISS-005.

**Problem:** Some CLI paths self-heal `LlmGateway` initialization ad hoc. This works but is inconsistent and fragile if new CLI entry points are added.

**Goal:** Centralize gateway bootstrap in shared observability initialization so all CLI commands have a consistent owned LLM boundary without per-command guards.

**Scope sketch:** lazy `set_llm_gateway(LlmGateway(get_observability()))` in a shared bootstrap path; remove command-local fallback branches.

**Shipped:** P8-003 (`core/observability/bootstrap.py`) with server + `test-model` bootstrap wiring and tests.

---

### BL-370: Host transcript byte-range provenance

**Status:** `done` — 2026-06-14. Carry from P7-ISS-006.

**Problem:** `validation_input` compile provenance includes `source_path` / `last_source_line`, but not precise `byte_start` / `byte_end`, limiting replay slicing precision.

**Goal:** Extend host transcript resolution metadata so compile events can include exact byte ranges for replay-grade provenance.

**Shipped:** P8-004 — transcript loader computes `source_byte_start`/`source_byte_end`; `validation_input` compile events emit byte ranges for replay slicing.

---

### BL-371: Backend-specific interception strategy for full in/out capture

**Status:** `partial` — 2026-06-14. Carry from P7-ISS-007.

**Problem:** Phase 7 achieved owned-callsite gateway capture + executor outer-loop events, but not uniform backend-internal interception across all present/future backends.

**Goal:** Define a backend matrix:
- preferred strong interception path per backend (native hook / owned boundary)
- guaranteed fallback capture path that always works
- explicit confidence tier per backend

**Planning note:** This is a Phase 8 architecture item. **Phase 8 resolution:** Aider interception via `ObservableModel` subclass (P8-001) + `InterceptionProfile` contract per adapter (P8-002). Non-Python backends (Claude Code, Codex, OpenCode) deferred to Phase 10+ via HTTP proxy base-URL pattern. Full-complete logging milestone moves to Phase 9 (write-always storage).

---

### BL-507: Thinking token capture verification

**Status:** `done` — 2026-06-16. Resolved in Phase 9. `MCP_CODER_EXECUTOR_REASONING_EFFORT=high` → `reasoning:{effort:high}` in proxy `raw_request`; `thinking_tokens=38` in `backend_llm_call.thinking_tokens`; `compare` CLI confirms `proxy_thinking=True, backend_thinking=True`. Litellm preserves thinking tokens through normalization; nothing is stripped.

**Problem:** Live dogfood of Phase 8 (`ObservableModel`) with `openrouter/anthropic/claude-sonnet-4` produced no `thinking_text`/`thinking_tokens` fields on `backend_llm_call` events, even for a complex task. Phase 8 capture infrastructure is correct (fields exist in schema and `extract_thinking_from_response()` is wired), but the provider/litellm path may not expose these fields for that model/route.

**Goal:** Verify thinking field capture end-to-end:
1. Identify a known thinking-enabled model+provider path (e.g. `claude-3-7-sonnet` with `thinking` budget enabled, or direct Anthropic API with extended thinking params).
2. Run a delegation and confirm `thinking_text` and `thinking_tokens > 0` appear on `backend_llm_call` events in the trace.
3. If absent: determine whether litellm is stripping the field, or whether the capture needs the HTTP proxy dual path (Phase 9/10 experiment).

**Target:** Phase 9 (opportunistic check during write-always validation) or Phase 10 (if proxy is needed as dual capture path).

**Related:** P8-ISS-004, notes/llm-interception-strategies.md § thinking blocks, BL-371, BL-353.

---

### BL-508: Universal internal HTTP proxy

**Status:** `done` — 2026-06-16. Phase 9 (P9-003 + P9-009 gzip fix). `LocalLlmProxy` running as a local HTTP server; all in-process litellm calls route through it; `proxy_llm_call` events with call_index attribution, raw request/response bodies, and `Accept-Encoding: identity` for readable payloads.

**Problem:** Phase 8's `ObservableModel` captures Aider inner-loop calls above litellm's normalization layer. Whatever litellm silently drops (thinking blocks, provider extensions) is permanently lost before we see it. There is no way to prove "100% captured" from user-space instrumentation alone.

**Goal:** A local HTTP proxy (`LocalLlmProxy`) that sits between litellm and the real provider. All in-process LLM callers (LlmGateway helpers + AiderEngine via litellm) route through it. Proxy captures raw HTTP request + response before litellm normalization, emits `proxy_llm_call` events, and cross-checks against Phase 8 `backend_llm_call` events.

**Architecture:**
- Async HTTP server (aiohttp or httpx-based) on `localhost:PORT`
- `api_base` globally overridden to `http://localhost:PORT` at bootstrap (`ensure_observability_bootstrap`)
- Model-prefix routing table built from env vars (`openrouter/*` → OpenRouter, `anthropic/*` → Anthropic, etc.)
- Attribution: reads `delegation_id_var` + `step_index_var` from active context store per request
- Streaming: SSE tee — capture while forwarding (same pattern as `_StreamCaptureWrapper`)
- Raw response body stored on `proxy_llm_call` event before litellm normalization

**Phase 10+ extension:** Same proxy extended to out-of-process backends (Claude Code, Codex, OpenCode) by pointing their base URL at it — no new proxy code. See notes/llm-interception-strategies.md § Per-backend audit.

**Related:** BL-371, BL-507, BL-350, BL-353, notes/llm-interception-strategies.md § Phase 9 proxy architecture.

---

### BL-510: Remove `should_log_full_prompt` write gate from delegation row

**Status:** `done` — 2026-06-16. Phase 9 (P9-008). `MCP_CODER_LOG_FULL_PROMPT` gate removed from `delegation_log.py` and `mcp_server.py`; `prompt_full` now written unconditionally; `should_log_full_prompt()` retired as a deprecated no-op.

**Problem:** `should_log_full_prompt()` (env var `MCP_CODER_LOG_FULL_PROMPT`) gates whether the executor prompt is written to the `prompt_full` field of the `delegations.jsonl` row in `core/logging/delegation_log.py`. This is a separate write gate from the trace file verbosity gate fixed in P9-001, but it violates the same D-P9-8 principle: write-always; no runtime gate on what reaches disk.

**Target:** Remove the `should_log_full_prompt()` conditional from `build_delegation_record()` and the call site in `server/mcp_server.py`. Write `prompt_full` unconditionally. Retire the `MCP_CODER_LOG_FULL_PROMPT` env var (or demote to deprecated no-op).

**Scope:** `core/logging/delegation_log.py`, `server/mcp_server.py`, `core/observability/base.py` + `local.py` + `null.py` (`should_log_full_prompt` abstract method), tests.

**Phase:** Phase 9 follow-up — after P9-001 lands. Not blocking any Phase 9 acceptance criterion.

---

### BL-509: Content-addressable deduplication for trace event bodies

**Status:** `idea` — 2026-06-14. Surfaced during Phase 9 proxy planning.

**Problem:** A large fraction of captured trace data is identical text repeated across events and delegations:
- Same system prompt appears in every `proxy_llm_call` and `backend_llm_call` in a session
- Same file contents appear in multiple context packages across delegations
- Same response body appears in both the proxy event and the `ObservableModel` event for the **same call** (two copies of the same bytes)
- Same RAG context passages included in multiple delegations

Writing everything inline inflates trace files significantly. A single heavy delegation (large repo context + long response) can generate 100KB+ of redundant bytes across events.

**Goal:** Content-addressable storage (CAS) for large text fields in trace events. Instead of inline text, store a sha256-keyed blob once and reference it by hash:

```jsonl
{"event_type": "proxy_llm_call", "request_body_ref": "sha256:abc123", "response_body_ref": "sha256:def456", ...}
```

Blobs stored at `sessions/<id>/blobs/<sha256>` (or a session-shared store). At analysis/replay time, dereference by hash. Two events referencing the same prompt body → one file on disk.

**Precedent:** Context package blob (P9-002) already uses this pattern for full context packages. This generalizes it to individual fields in any trace event.

**Phase 9 stance:** Phase 9 writes raw inline text (simple, no capture risk). This optimization is post-Phase 9 once we have real data to measure the dedup ratio. A quick 2-delegation comparison will reveal how repetitive the data actually is before committing to the refactor.

**Target:** Phase 10 (storage optimization pass) or as a standalone BL pull once Phase 9 corpus exists.

**Related:** BL-367 (write-always storage), P9-002 (context package blob precedent), BL-357 (storage lifecycle).

---

### BL-511: Model registry Stage 1 (front door + unified helper path + params + logging)

**Status:** `done` — 2026-06-16. Phase 9 (P9-011 + P9-012). 924 passed, 2 skipped. BL-507 end-to-end verified.  
**Design note:** [docs/notes/model-policy-layer.md](./notes/model-policy-layer.md)  
**Specs:** [P9-011](./tasks/P9-011-model-policy-layer-v1.md) (unify helper path + registry front door), [P9-012](./tasks/P9-012-generation-params-logging-v1.md) (params + weak model + logging)

**Problem:** Generation params (thinking/temperature/etc.) are set nowhere. Two helper paths emit `llm_call`; a third (`workspace_summarizer`, `spec_review`) bypasses the gateway and emits no trace event. Proxy confirmed `proxy_llm_call.raw_request` carries no `thinking` field. Model ID + budget are *already* centralized in `role_models.py` — reuse, do not rewrite.

**Architecture:** Single front door `model_registry.resolve(role, workspace) → CallParams` reusing `role_models` for id/budget; generation params + weak model layered on top with per-field `sources` provenance. One helper path (`LlmGateway`); `ExecutionEngine` stays pluggable; Aider is a read-only metadata source.

**P9-011 (refactor):** remove legacy direct-`Model()` helper calls (route through `LlmGateway`); create `model_registry.py` skeleton (id + budget only). Behaviour-neutral apart from new uniform logging.

**P9-012 (params + logging):** generation-param env vars; weak-model default-fill (Sonnet/Opus→Haiku, logged, opt-out via `=self`); wire `model.extra_params` + litellm kwargs; `policy_applied` on `backend_llm_call` + `llm_call`.

**New env vars (P9-012, all optional):** `MCP_CODER_<ROLE>_REASONING_EFFORT`, `_THINKING_BUDGET`, `_MAX_TOKENS`, `_TEMPERATURE`, `_TOP_P`, `_EXTRA_PARAMS` (JSON), `_WEAK_MODEL`. `reasoning_effort` is the portable thinking knob; `drop_params=True` always.

**Related:** BL-162, BL-321, BL-512, BL-513, BL-514, BL-515 (tiers).

---

### BL-512: Model policy layer — Stage 2 (host-set policy)

**Status:** `in_phase` — **Phase 11 P11-007 owns Stage 2** (`model_policy` arg on `delegate_to_agent`, host > env precedence, all roles configurable).  
**Design note:** [docs/notes/model-policy-layer.md § Stage 2](./notes/model-policy-layer.md)

**What:** The MCP host (Cursor, Claude Code, CI automation) passes an optional `model_policy` object inside the `delegate_to_agent` call arguments. This overrides the env layer for the duration of that single delegation. The host knows its own context (latency budget, cost cap, task urgency) better than a static `.env` file does.

**Sketch:**
```json
{
  "task": "...",
  "model_policy": {
    "executor": { "thinking_budget": 8000 },
    "context_builder": { "model": "gemini/gemini-2.5-flash-preview-04-17", "temperature": 0.2 }
  }
}
```

**Precedence position:** host policy > env vars > code defaults. Sits one level above Stage 1 in the chain.

**Related:** BL-511 (Stage 1 prerequisite), BL-513.

---

### BL-513: Model policy layer — Stage 3 (AI-suggested parameters)

**Status:** `idea` — 2026-06-16; depends on BL-511/BL-512.  
**Design note:** [docs/notes/model-policy-layer.md § Stage 3](./notes/model-policy-layer.md)

**What:** A lightweight pre-delegation analysis step (cheap LLM call or rule-based heuristic) examines the incoming task and recommends policy overrides. Examples:

- Large diff / architectural refactor → `executor.thinking_budget = 10000`
- Simple docstring / formatting task → `executor.thinking_budget = 0`, cheaper model
- Task touches > N files → `executor.max_tokens += 2000`

Suggestions are logged as a `policy_suggestion` trace event (fully auditable). In automatic mode the suggestion is accepted unless a Stage 1 env var or Stage 2 host override is present.

**Related:** BL-511, BL-512, BL-514.

---

### BL-514: Model policy layer — Stage 4 (dynamic escalation)

**Status:** `idea` — 2026-06-16; depends on BL-511–513 and a critic/supervisor (BL-321/BL-006).  
**Design note:** [docs/notes/model-policy-layer.md § Stage 4](./notes/model-policy-layer.md)

**What:** The outer-loop controller can mutate the active policy mid-delegation in response to runtime signals:

- Executor hit max retries with current model → switch to a larger/stronger model.
- Critic (BL-006) rejects output after N attempts → increase thinking budget.
- Running cost exceeds cap → downgrade remaining calls to a cheaper model.

This is the full outer-loop control capability. Stages 1–3 lay the resolver infrastructure; Stage 4 activates it.

**Related:** BL-321 (tiered escalation), BL-006 (critic), BL-511–513, BL-515 (model tiers prerequisite).

---

### BL-515: Model tiers and classes

**Status:** `idea` — 2026-06-16; depends on BL-511 (registry infrastructure). Prerequisite for BL-514 (escalation).  
**Design note:** [docs/notes/model-policy-layer.md § Model tiers and classes](./notes/model-policy-layer.md)

**What:** Assign every model a tier enum so the outer loop can escalate or downgrade automatically:

```
Tier 0: nano      ← gpt-4o-mini, claude-haiku, gemini-flash-8b, flash-lite
Tier 1: balanced  ← claude-sonnet, gpt-4o, gemini-flash, deepseek-chat
Tier 2: powerful  ← claude-opus, gpt-4.5, gemini-pro
Tier 3: thinking  ← claude-opus-thinking, o3, gemini-2.5-pro (high thinking)
```

**Capabilities:**
- `get_tier(model_id) → ModelTier` — for logging, audit, cost bucketing
- `best_model_for_tier(tier, provider_pref) → model_id` — for runtime escalation in BL-514
- Auto weak-model selection: pick Tier 0 as `weak_model` when Aider registry has `None` for Tier 1+ models
- `CallParams.tier` field for policy expressions like `"tier": "balanced"` instead of explicit model IDs
- Integration with `resolve()` — `resolve(role, max_tier=1)` respects cost caps

**Why deferred:** Tier assignments need research and will drift as models release. Phase 9 proxy already logs the `model` field in every trace event — tier can be derived post-hoc for now. Phase 10 outer-loop work (BL-321 + BL-514) is the right time.

**Related:** BL-511 (registry), BL-514 (escalation needs tiers), BL-321 (tiered escalation).

---

### BL-516: CLI log health table + `trace inspect --summary`

**Status:** `partial_done` — **Phase 10 P10-004 shipped `trace inspect --summary`**. Cross-delegation `mcp-coder log` table + `--no-truncate` remain backlog.

**What:** Three CLI conveniences for batch R&D scanning across delegations:

1. **`mcp-coder trace inspect --summary`** — single-shot health scorecard per delegation: event counts by type, token totals, `policy_applied` coverage %, proxy↔backend alignment %.
2. **`mcp-coder log`** (new subcommand) — cross-delegation table: last N delegations, one row each with health indicators (alignment, missing events, token anomalies).
3. **`--no-truncate`** on `trace inspect --field` — pipe-friendly full field content for scripting.

**Why deferred:** Phase 9 exit criteria met without these. `mcp-coder compare`, `trace inspect`, `replay`, `view delegations`, and the v2 boundary viewer already support per-delegation audit. Pull when scanning many delegations in a row becomes painful.

**Related:** P9-010 (trace inspect shipped), P9-006 (compare), P9-013 (v2 viewer), BL-343 (structured viewer — shipped).

---

### BL-517: Executor `policy_applied` ignored params

**Status:** `done` — **Phase 10 P10-004 shipped**. Migrated from Phase 9 issue **P9-ISS-007**.

**What:** `_apply_executor_model_params` applies `reasoning_effort`, `thinking_budget`, `extra_params`, and `weak_model` to the Aider `Model` — but **not** `temperature`, `top_p`, or `max_tokens` (Aider owns those). Today `policy_applied()` can still log env-resolved values for those fields, implying they were applied.

**Resolution options:**
- Add `"ignored": ["temperature", "top_p", ...]` (and optional `note`) to executor `policy_applied`.
- Or filter executor-inapplicable fields from `policy_applied` entirely (simpler; loses "you set it but it had no effect" signal).

**Workaround:** Force via `MCP_CODER_EXECUTOR_EXTRA_PARAMS={"temperature": 0.5}` — passed into Aider `extra_params` and forwarded by litellm.

**Related:** BL-511 (model registry + `policy_applied`), P9-012 (generation params logging), [PHASE9_ISSUES.md](./PHASE9_ISSUES.md) P9-ISS-007.

---

### BL-518: Runtime log level / verbosity DX

**Status:** `partial_done` — **Phase 10 P10-004 shipped env matrix docs + `.env.example` parity**. Unified master level + proxy debug logging remain backlog.

**Problem:** Logging and verbosity knobs are fragmented across several env vars and yaml keys with overlapping names and different semantics:

| Knob | What it controls today |
|------|------------------------|
| `MCP_CODER_SERVER_LOG_LEVEL` / `server_log_level` | `server.jsonl` audit log minimum level |
| `MCP_CODER_LOG_BRIEF` | stderr receive/send one-liners (MCP-safe) |
| `MCP_CODER_LOG_VERBOSE` | stderr extra line when JSONL row appended |
| `MCP_CODER_OBS_VERBOSITY` / `observability_verbosity` | trace **display/export** filter (`lean`/`standard`/`full`) — not write gate since P9-001 |
| `MCP_CODER_CAPTURE_REASONING` | whether reasoning text is captured in traces |
| Proxy (`LocalLlmProxy`) | no env-controlled debug/access logging; `log_message` suppressed |

Operators tuning dogfood/debug runs must know this matrix by heart; `.env.example` documents server + stderr knobs but not observability env vars.

**Proposed scope (TBD — pick subset in planning session):**

1. **Documented matrix** in guide/README — what each knob affects (write vs display vs stderr).
2. **Optional unified master level** — e.g. `MCP_CODER_LOG_LEVEL=debug` fans out to server log + stderr + proxy debug (with per-knob overrides).
3. **`.env.example` + config.yaml parity** — add `MCP_CODER_OBS_VERBOSITY`, `MCP_CODER_CAPTURE_REASONING`, and related observability env stubs.
4. **Proxy access logging** — opt-in debug lines for routing decisions, upstream errors, attribution header presence (off by default).

**Why deferred:** Phase 9 shipped write-always capture and dual-capture proxy; no exit blocker on log ergonomics. Pull when dogfood/debug friction justifies a planning pass.

**Related:** BL-125 (server log shipped), P9-001 (write-always), BL-516 (CLI log scanning), [storage-and-linking.md](./notes/storage-and-linking.md).

---

### BL-519: `MCP_CODER_PROXY_ENABLED` env toggle

**Status:** `done` — **Phase 10 P10-004 shipped**.

**Problem:** `ensure_observability_bootstrap()` always starts `LocalLlmProxy` and rewrites `OPENROUTER_API_BASE` / `OPENAI_API_BASE` / `ANTHROPIC_API_BASE` to the local proxy URL. There is no env escape hatch to run litellm direct-to-provider without editing code or test hooks.

**Proposed scope (TBD):**

- `MCP_CODER_PROXY_ENABLED=0` (or yaml `local_llm_proxy: false`) skips proxy start and leaves provider `*_API_BASE` env vars untouched.
- Default **on** — preserves Phase 9 dual-capture behavior and north-star acceptance.
- When disabled: `proxy_llm_call` events absent; `backend_llm_call` + litellm callback paths still run (partial capture).
- Bootstrap + CLI paths share the same resolver (`core/observability/bootstrap.py`).
- Document tradeoff in README/guide: disabling proxy loses HTTP ground-truth and BL-507-style verification for that run.

**Use cases:** isolate proxy routing bugs vs provider bugs; faster local iteration when proxy overhead matters; CI scenarios that mock providers without spinning localhost proxy; emergency workaround if proxy misroutes a model prefix.

**Why deferred:** Proxy is core Phase 9 infrastructure and should stay on by default; toggle is convenience/DX, not missing functionality.

**Related:** BL-508 (proxy shipped P9-003), P9-003 bootstrap, [llm-interception-strategies.md](./notes/llm-interception-strategies.md).

---

### BL-106: MCP live progress + logging notifications

**Status:** `done` (POF) — **Phase 10 P10-002 shipped** (`ctx.info` milestones + thread bridge). Capture→egress bridge + `report_progress` remain backlog follow-ups. Cursor chat rendering is host-version dependent.

**Problem:** Long `delegate_to_agent` runs show only a spinner in Cursor until the tool returns. Today mcp-coder emits **brief stderr** (`MCP_CODER_LOG_BRIEF`) at start/end and writes **full detail to disk** (trace JSONL, `server.jsonl`) — but does not send **MCP protocol notifications** mid-run. Users cannot see pipeline phase or executor step progress in the host UI.

**What (POF → MVP):**

1. **Inject FastMCP `Context`** into `delegate_to_agent` (and optionally other long tools).
2. **`ctx.report_progress(progress, total, message)`** at pipeline milestones — compile, builder, architect, validation, executor step N/M. Requires host `progressToken` (Cursor: version-dependent; no-op if absent).
3. **`ctx.info` / `ctx.log`** for short redacted status lines (throttled; reuse `redact_secrets`).
4. **Capture → egress bridge** — subscribe to observability events already written to trace; map to live notifications (phase boundaries first; optional executor highlights later). Full bodies stay on disk (D-P9-8).
5. **Thread bridge** — executor runs in worker thread; queue async `ctx.log` on MCP event loop (cannot call async context from Aider thread directly).

**POF scope:** pipeline milestones only (~6–8 messages per delegation).  
**MVP scope:** + executor step index + “edited `path`” highlights; spike Cursor UI for progress vs MCP Logs panel.

**Not in scope v1:** streaming raw Aider tokens into chat; duplicating Phase 9 trace bodies over MCP.

**Related:** **BL-160b** (tee to file), **BL-520** (CLI tail when host UI weak), **BL-351** (stall → `needs_input`), P9-001 write-always (trace append enables tail), [PHASE2_MVP.md](./PHASE2_MVP.md) Q6.

---

### BL-520: Live log tail / follow delegation

**Status:** `done` (POF) — **Phase 10 P10-002 shipped** (`mcp-coder logs tail` on trace JSONL with `--latest` / `--delegation-id`). `server.jsonl` filter + BL-160b tee remain backlog follow-ups.

**Problem:** Even with **BL-106**, host UIs vary (Cursor progress visibility flaky across versions). Operators need a **reliable local view** while a delegation runs without opening the full viewer.

**What:**

1. **`mcp-coder logs tail`** (or extend existing maintenance/log CLIs):
   - `--delegation-id <id>` or `--follow latest` (most recent open delegation in session)
   - Tail `traces/<delegation_id>.jsonl` as new events append (**enabled by Phase 9 write-always**)
   - Optional: tail `server.jsonl` (global/project scope) filtered by `delegation_id`
   - Optional: tail executor tee file when **BL-160b** writes `sessions/<id>/executor_tee.log`
2. **Human-readable line format** — one line per trace event: `compile_event`, `llm_call`, `proxy_llm_call`, `executor_stall`, etc. (not raw JSON dump by default).
3. **`make logs-tail`** / docs pointer for dogfood workflow: terminal 2 runs tail while terminal 1 delegates in Cursor.

**POF:** tail trace JSONL by delegation id with jq-friendly or built-in formatter.  
**MVP:** `--follow latest`, event-type filter, integrate with `server.jsonl`.

**Why now (post-Phase 9):** capture is complete on disk; tail is read-side only — no MCP stdout risk.

**Related:** **BL-106**, **BL-160b**, **BL-516** (post-hoc health scan), P9-010 trace inspect, `make server-logs-last`.

---

### BL-521: Pre-delegation spec clarity pass *(Phase 11 P11-001)*

**Status:** `done` — **Phase 11 P11-001 shipped** 2026-06-19. Remainder: cross-session intent history in clarity context → Phase 12.

**Problem:** Delegations start immediately from whatever spec text is given. If the task is ambiguous, the executor either stalls (wastes 2–3 minutes) or produces a misaligned output. There is no pre-flight check that verifies the task is clear enough to delegate with confidence.

**Goal:** A cheap LLM call before delegation checks whether the task description and spec Files contract are sufficient. If key decisions are missing or ambiguous, return `clarification_needed` with 2–3 targeted questions. Only run the executor after the task is validated as `CLEAR`.

**Design:**
- New pipeline phase `clarity_check` inserted before `compile` when `clarity_pass: true` (spec yaml) or `MCP_CODER_CLARITY_PASS=1` (env)
- Cheap model (Flash/Haiku tier), small context: task description + spec Files section + last 3 delegation titles in session (~3k tokens)
- Prompt: "What is unclear or missing? List at most 3 specific questions. If nothing is unclear, return CLEAR."
- On `CLEAR` → proceed normally (latency overhead = one cheap LLM call, ~100ms)
- On questions → return `clarification_needed: [...]` early (same field shape as BL-329 spec validation)
- Distinct from BL-329: validation checks spec coherence; clarity pass checks task completeness and intent
- Trace event: `clarity_check_result: {status: clear | clarification_needed, questions: [...]}

**Related:** BL-329 (spec validation), BL-351 (supervised IO), P11-001.

---

### BL-522: Mid-run human gate — `answer_delegation_question` *(Phase 11 P11-004, experimental)*

**Status:** `in_phase` — **Phase 11 P11-004**. Added 2026-06-18.

**Problem:** When the supervisor (P11-002) determines that a decision requires human judgment, the current path is abort-and-resume. The Aider thread stops, the delegation returns `needs_input`, and the user must re-delegate from scratch. The coder loses its in-run context.

**Goal:** Instead of aborting, the supervisor blocks the Aider thread on a `threading.Event` and emits `ctx.info` with the question. A new MCP tool `answer_delegation_question(delegation_id, answer)` from Cursor sets the event. The Aider thread unblocks with the human answer and continues from where it paused. No restart, no re-run.

**Design:**
- `core/engine/question_registry.py`: in-process registry `{delegation_id: {question, event: threading.Event, answer: str | None}}`
- `SupervisedIO` escalation path: posts to registry, emits `ctx.info` with question + `delegation_id`, then `event.wait(timeout=120s)`
- On timeout (120s default): falls back to abort-and-resume (P10-003 pattern); no deadlock
- New MCP tool `answer_delegation_question(delegation_id: str, answer: str)`: looks up registry, sets answer, signals event
- Trace events: `supervisor_human_gate_opened`, `supervisor_human_gate_answered | supervisor_human_gate_timeout`
- **Experimental:** depends on Cursor MCP client supporting concurrent tool calls from the same session. If not supported, timeout path always triggers. Dogfood will determine viability.

**Related:** BL-351 (supervised IO), P11-002, P11-004, BL-501 (async/long-running adjacency).

---

### BL-528: Late-answer resume after human-gate timeout

**Status:** `idea` — 2026-06-19.  
**Related:** BL-522 (mid-run human gate), BL-351 (needs_input fallback), BL-350 (outer-loop planner ownership).

**Problem:** In P11-004, when `escalate` waits 120s and times out, the in-flight registry entry is popped and delegation exits via `needs_input`. If the human answer arrives later, `answer_delegation_question` returns `not_found`, so there is no native continuation from the exact paused state.

**Goal:** Preserve a resumable continuation point when human-gate timeout occurs, so a late answer can continue from the last paused execution state rather than forcing full re-delegation from scratch.

**Design sketch (Phase 12 candidate):**
- On gate timeout, persist a `resume_token` artifact keyed by `delegation_id` (question, risk tier, minimal executor context digest, TTL).
- Extend `needs_input` payload with `resume_token` + `resume_expires_at`.
- Add MCP tool: `resume_delegation_question(resume_token: str, answer: str)`.
- If token valid and executor context still reconstructable, resume from paused checkpoint; otherwise degrade gracefully to normal re-delegation with prefilled answer/context.
- Keep strict TTL + single-use semantics to avoid stale/ambiguous resumes.

**Why separate from BL-522:** BL-522 validates concurrent in-flight gating. BL-528 addresses the post-timeout path when concurrency windows are missed in real host UX.

---

### BL-529: Supervisor context window — task + spec + Aider output tail

**Status:** `partial` — 2026-06-21. **Phase 12:** tier-2 pull via `SupervisorToolRunner` (P12-003). **Deferred:** full context window assembly / pre-assembly upgrade.
**Related:** BL-351 (supervised IO), BL-530 (on-demand context retrieval), BL-532 (inter-model communication).

**Problem:** `DelegationSupervisor.evaluate()` currently receives only `question` + `risk_tier` + `target_files`. It cannot see the task description, spec contract, or what Aider has done so far in the run. This makes every risk judgment context-free — the supervisor cannot distinguish "add `config.py` which is in the spec Files contract" from "add `config.py` which is out of scope".

**Goal:** Pass a `SupervisorContext` struct into `evaluate()` containing: task summary, spec_path, files_contract, and a rolling tail of the last N lines of Aider's output stream. Supervisor prompt is rewritten to include this context before the confirm_ask question.

**Design sketch:**
- Add `context: SupervisorContext | None` param to `DelegationSupervisor.__init__()` and `evaluate()`
- Populate from the compiled `ContextPackage` at engine start; update `output_tail` via `_executor_output_tail()` before each `confirm_ask`
- Keep prompt additions concise (task + contract paths + last 20 lines) to stay within cheap model budget
- Emit `supervisor_context_bytes` in trace for observability

---

### BL-530: On-demand context retrieval — `SupervisorToolRunner` (Phase 12 implementation)

**Status:** `done` — 2026-06-21. **Phase 12 P12-003 shipped** (commit 367ba27). Phase 13+ tools deferred below.
**Related:** BL-542 (context routing), BL-354 (executor-pull sidecar), BL-531 (multi-turn loops), BL-540 (project state).

**Problem:** All helper models receive a single compiled context snapshot at call time and cannot request additional information. If the supervisor needs to check what changed in the last delegation before approving a risky action, or the planner needs to see a past decision before planning, they simply don't — the result is lower quality decisions with no recourse.

**Goal:** Give the Supervisor and Planner a tool-calling loop (`SupervisorToolRunner`) where the LLM reasons about what context it needs and calls tools on demand. Uses a **two-tier context model**: Tier 1 (slow-changing base: spec, plan, decision log) assembled once per turn; Tier 2 (action-specific) pulled via tool calls based on the LLM's own reasoning.

**Phase 12 tool set (P12-003):**
- `get_project_state()` — decisions, risks, hot areas from `project_state.json`
- `get_delegation_history(spec_path, n)` — last N delegation summaries + files changed
- `read_file(path)` — file content (truncated to budget)
- `get_diff(delegation_id)` — unified diff from a past delegation
- `get_reviewer_findings(files)` — classified findings for specific files (available after P12-004)

**Phase 13+ tool set (deferred):** `search_past_decisions(query)` (RAG over decision history), cross-project queries, full `HelperToolRunner` for clarity/reviewer roles, sidecar HTTP tool server for executor (BL-354 full).

**Phase placement:** Phase 12, P12-003. Depends on BL-540 (project state) for `get_project_state` tool data.

---

### BL-531: Multi-turn loops for helper models

**Status:** `idea` — 2026-06-19. **Phase 12 candidate.**
**Related:** BL-530 (on-demand context), BL-350 (outer-loop planner ownership), BL-532 (inter-model communication).

**Problem:** All helper models are single-shot today: one prompt → one response. This is fine for simple tasks but breaks down for complex ones — the planner can't ask a clarifying question before writing its plan, the reviewer can't look at a related test file before flagging a bug, and the supervisor can't escalate with a proposed resolution.

**Goal:** Allow each helper model to run an internal loop (up to N turns): produce → evaluate → optionally request context or ask a follow-up → produce final output. The loop is bounded by turn count and time budget. The host sees only the final output; intermediate turns are traced.

**Design sketch:**
- Wrap each helper call site in a `HelperLoop(max_turns=3, timeout_s=30)` harness
- On each turn: model either produces `{done: true, result: ...}` or `{done: false, tool_call: ...}`
- Tool calls handled by `HelperToolRunner` (BL-530); result appended to next turn context
- Final `result` is what the pipeline consumes (same interface as today)
- Trace records all turns as `helper_turn` events

---

### BL-532: Inter-model communication — Aider → pipeline, pipeline → Aider

**Status:** `idea` — 2026-06-19. **Phase 12 candidate.**
**Related:** BL-529 (supervisor context), BL-531 (multi-turn loops), BL-354 (executor sidecar), BL-350 (outer loop).

**Problem:** Today all models are isolated silos. The planner writes a plan and never hears back. The supervisor makes decisions but Aider doesn't know why. The reviewer flags issues but the executor never sees them. There is no mechanism for mid-run signals in either direction.

**Goal:** A structured message bus for inter-model signals within one delegation:
- **Aider → supervisor/planner**: status events ("I edited file X", "I need context on Y") streamed via the existing tee/stall infrastructure
- **Planner → executor**: mid-run guidance injection (if planner detects the executor is going off-track, it can append a correction to the system prompt prefix for the next Aider message)
- **Reviewer → re-delegation**: reviewer result is fed back into the next delegation's context package as `prior_review_notes` — closes the feedback loop across steps
- **Supervisor → context builder**: escalation can trigger a context-enrichment step before handing back to human

**Why this matters:** Without inter-model communication, each model operates on a stale snapshot. With it, the delegation becomes a true multi-agent loop rather than a waterfall pipeline.

---

### BL-540: Persistent project state — cross-delegation planner notebook

**Status:** `done` — 2026-06-21. **Phase 12 P12-002 shipped** (v1 store; commit 16dfe7b). Full corpus/RAG → Phase 13+.

**Problem:** BL-525 scopes the Planner as session-bounded — its state lives only within one MCP session and is lost on Cursor restart. Real projects span many sessions over days or weeks. The Planner has no memory of what was built two sessions ago, what decisions were made, or what risks were surfaced. Every delegation starts from scratch regardless of project history.

**Goal:** A `project_state` object stored in `~/.mcp-coder/projects/<key>/project_state.json` that persists across sessions and is maintained by the Planner. Contains:
- What the project is (inferred and confirmed over time; editable by host)
- Decisions made and why (pulled from spec reports + past `context_summary` fields + planner summaries)
- Current "hot areas" — files/subsystems recently touched and what happened
- Open risks / known gaps surfaced across delegations (fed by reviewer, supervisor, planner)
- A compact rolling summary (≤ 2k tokens) that fits into every helper's context without blowing budget

**Lifecycle:**
- **Before delegation:** Planner reads project state, incorporates it into planning context
- **After delegation:** Planner updates project state with what was decided/built/discovered (spec report + reviewer findings as input)
- **Reviewer → state:** Serious reviewer findings can be promoted to project state risks (BL-541)
- **Supervisor → state:** Repeated escalation patterns noted in project state for future reference
- **Host write:** Host can add/edit entries via a future `update_project_state` MCP tool

**Invariant:** Project state must be compact enough (~2k tokens) that all helpers can receive it without dominating their budget. Not a log — a living summary. Old detail is summarised or pruned.

**Phase placement:** Phase 12. Prerequisite for BL-525 full Planner role.

---

### BL-541: Reviewer findings feedback loop — close the loop across delegations

**Status:** `done` — 2026-06-21. **Phase 12 P12-004 shipped** (commit 604f317). Tier-2 epic review → Phase 13+.

**Problem:** The tier-1 reviewer (`reviewer_pass`, shipped P11-005) runs after each executor turn and appends its findings to the spec report. But that's where the chain ends — findings are written to a file that no subsequent delegation reads. The next delegation's planner, supervisor, and context builder have no idea what the reviewer found. The reviewer might as well not exist from the perspective of future delegations.

**Goal:** Close the feedback loop so reviewer findings actually influence future work:

1. **`prior_review_notes` in planner context** — after a delegation completes, reviewer findings (if any) are summarised and stored alongside the spec in a `<spec>-review-summary.md`. The next delegation on the same spec has this summary injected into the planner's context prefix.

2. **Serious findings → project state** — findings above a severity threshold (missing error handling, broken interface contract, obvious test gap) are promoted to `project_state.open_risks` (BL-540) so they persist across specs/sessions.

3. **Supervisor can consult reviewer history** — when a supervisor decision involves a file or area that has recent reviewer findings, a `reviewer_history_summary` field is included in the supervisor's context (BL-529 extension).

**What this is NOT:** Not a re-delegation trigger. Not automated re-work. The reviewer is still advisory — findings surface to the Planner and state, not auto-fix.

**Phase placement:** Phase 12. Depends on BL-540 (project state) for item 2; item 1 can land independently.

---

### BL-542: Dynamic context routing — two-tier Supervisor/Planner context model

**Status:** `done` — 2026-06-21. **Phase 12 P12-003 shipped** (SupervisorToolRunner; commit 367ba27).
**Related:** BL-530 (SupervisorToolRunner mechanism), BL-540 (project state), BL-541 (reviewer findings).

**Problem:** The Supervisor and Planner often need context that spans multiple sources (project state, past delegation outcomes, reviewer findings, specific files) and the right selection depends on what they're doing at that moment. A pre-assembled fixed context slice misses the adaptive nature of the need.

**Goal:** The two-tier context model (D-ARCH-11): Tier 1 (slow-changing, assembled at turn start) + Tier 2 (on-demand via the Supervisor's own tool calls based on its reasoning). This is the product-level scoping of BL-530 for the Supervisor and Planner roles specifically. BL-530 is the mechanism; BL-542 is the design decision about which sources matter and how they compose.

Key constraint: all tool calls logged as `supervisor_tool_call` trace events. Budget enforcement: total retrieved context stays within the role's D-ARCH-1/11 budget. Max 3 tool rounds per decision call (configurable).

**Phase placement:** Phase 12, P12-003. Implemented as part of `SupervisorToolRunner` with the Phase 12 tool set. Full RAG/search tools deferred to Phase 13.

---

### BL-543: Supervisor-owned context lifecycle — refresh at checkpoints and confirm_ask enrichment

**Status:** `partial` — 2026-06-21. **Phase 12:** host clarification on resume only (`## Host clarification`). **Deferred:** checkpoint B (confirm_ask enrichment), checkpoint C (full continuation brief for turn 2+).
**Related:** BL-529 (supervisor context), BL-530 (on-demand retrieval), BL-540 (project state), BL-542 (context routing), BL-351 (SupervisedIO).

**Problem:** Context is compiled once before the executor runs and handed as a static package. This is correct for `max_turns=1`. For multi-turn supervisor loops it breaks down: after turn 1 the workspace has changed (files edited, files created), the executor produced output the Supervisor has seen but the next executor turn has not, and reviewer findings exist that the executor knows nothing about. The second turn runs with stale context — it may redo work, contradict what turn 1 did, or miss the reviewer's concern entirely.

A second gap: during execution, every `confirm_ask` is a natural mid-execution pause where Aider is waiting. The Supervisor currently returns only approve/deny. This is a missed opportunity — the Supervisor knows what the question is about, can pull relevant context, and can inject that context into its response so Aider continues with enriched understanding rather than just a boolean.

**Goal:** Make the Supervisor the owner of context lifecycle inside the execution loop. Three checkpoints:

**Checkpoint A — Pre-delegation (infrastructure, unchanged)**
The existing pipeline (clarity → context_compile → builder_llm) produces the initial `ContextPackage`. The Supervisor receives this and uses it for turn 1. No change to the compiler.

**Checkpoint B — `confirm_ask` mid-turn (new)**
When Aider fires `confirm_ask` and the Supervisor evaluates:
- Supervisor may pull context via BL-542 router (`rag_search`, `read_file`, `get_project_state`) targeted at the specific question
- Supervisor's decision response can include a `context_injection: str` field — additional context appended to Aider's next message before it resumes
- The `confirm_ask` gate becomes a context enrichment point, not just a yes/no gate
- Example: Aider asks "add `auth_utils.py`?" → Supervisor: "yes, and keep the existing `validate_token()` signature intact — it is used by 3 callers"

**Checkpoint C — Post-turn / pre-next-turn (new)**
After an executor turn completes and the Supervisor decides to rerun:
- Supervisor reads fresh content of `files_changed` from this turn
- Assembles a "continuation brief": what was done + what reviewer found + what remains from the plan
- The executor's prompt for turn 2 is NOT the original brief — it is the continuation brief prepended above the original spec/map sections
- Cost: a short LLM summary call (~500 tokens) + file reads of `files_changed` only

**Invariant:** The infrastructure compiler (checkpoint A) is never re-invoked mid-loop. Checkpoints B and C are Supervisor responsibility only — lightweight delta updates, not full recompiles.

**Trace events:**
- `supervisor_context_inject` — when Supervisor enriches a `confirm_ask` response with context
- `supervisor_context_refresh` — when Supervisor assembles a continuation brief for next turn

**Phase placement:** Phase 12. Checkpoint B (confirm_ask enrichment) can ship independently of checkpoint C. Both depend on BL-529 (supervisor context window) and BL-542 (context routing) for the pull mechanism.

---

### BL-544: Supervisor pause/resume — stateful agent across multiple delegate_to_agent calls

**Status:** `done` — 2026-06-21. **Phase 12 P12-001 shipped** (implicit resume P12-ISS-001; singleton P12-ISS-002; commit 16dfe7b+).
**Related:** BL-528 (late-answer resume, specific case), BL-351 (SupervisedIO), BL-543 (context lifecycle), BL-350 (outer-loop continuation).

**Problem:** When the Supervisor escalates to the host mid-loop (needs human input, needs a decision from the planner, needs clarification), the current model aborts the delegation and returns `needs_input`. The next `delegate_to_agent` call is a completely fresh start: clarity, spec_validation, context_compile, planner_pass all re-run from scratch. The Supervisor has no memory of what turn 1 did. Files on disk reflect turn 1's edits but the Supervisor's context does not. The second call is expensive and potentially wrong.

This breaks real multi-step work. If a task requires two or three turns with a host question in between, the system cannot maintain coherence across them.

**Goal:** A general pause/resume mechanism for the Supervisor agent. On escalation, the Supervisor serializes its full state. The host gets a `resume_token` with the response. When the host calls `delegate_to_agent` again with that token, the Supervisor resumes from exactly where it paused — no re-running of pipeline stages already completed.

**Supervisor state (serialized on pause):**
```
SupervisorState {
    resume_token:      UUID
    spec_path:         str
    turn_index:        int          # turns completed so far
    plan:              str          # from Planner — still valid unless host changes scope
    decision_log:      list         # all confirm_ask decisions from completed turns
    completed_turns:   list[{       # artifacts from each completed turn
        files_changed, output_tail, reviewer_findings
    }]
    pause_reason:      str          # needs_input | needs_clarification | ...
    questions:         list[str]    # what the Supervisor is asking
    context_ref:       str          # delegation_id → original context package on disk
    paused_at:         ISO8601
    expires_at:        ISO8601      # TTL (e.g. 24h)
}
```

Stored in `~/.mcp-coder/projects/<key>/supervisor_states/<resume_token>.json`.

**Resume call:**
```
delegate_to_agent(resume_token="sv_abc123", answer="yes, also add rate limiting")
  → skip: clarity_check, spec_validation, context_compile, planner_pass, turn 1
  → load: SupervisorState from resume_token
  → inject: host's answer into continuation brief (BL-543 checkpoint C)
  → Supervisor may ask Planner to revise plan incorporating the answer (optional)
  → run: turn N (next turn from saved turn_index)
```

**What does NOT re-run on resume:**

| Stage | Fresh call | Resume call |
|---|---|---|
| clarity_check | runs | skipped |
| spec_validation | runs | skipped |
| context_compile | runs (~16k tokens) | skipped — loaded from context_ref |
| planner_pass | runs | skipped — plan in state (may be revised if host answer changes scope) |
| completed executor turns | n/a | skipped — already on disk |
| next executor turn | runs | runs |

**Host's answer as context:** The `answer` param on resume is injected into the continuation brief (BL-543) as a `## Host clarification` section before the executor sees it. The Planner can optionally revise the remaining plan to incorporate the answer before turn N runs.

**Relationship to BL-528:** BL-528 covers the specific case where the human gate timed out but a late answer arrived. BL-544 is the general pause/resume mechanism that BL-528 would be implemented on top of.

**Why this matters for real production use:** Without pause/resume, every escalation is a cold restart. Complex tasks that require host input mid-way (common in real projects: "I found an ambiguity", "should I also update the tests?", "I need to know the auth strategy before continuing") cannot be handled with continuity. The Supervisor can't be trusted as a real agent without it.

**Phase placement:** Phase 12. Depends on BL-543 (continuation brief) and BL-540 (project state). New `resume_token` param on `delegate_to_agent` MCP tool — backward compatible (optional).

---

### BL-545: Supervisor-owned executor session lifecycle (v1 — control plane)

**Status:** `done` — 2026-06-21. **BL-545 v1 shipped** (commit 2d7307b). Smart adaptation → BL-546.
**Related:** BL-544 (pause/resume), BL-543 (context lifecycle), BL-546 (deferred adaptation), P12-ISS-002/003 (shipped interim fixes).

**Problem:**
Aider session lifetime is currently controlled by `session_policy` (env var / workspace config) keyed on the **host Cursor session ID** — an external signal that has nothing to do with the project's needs. This leads to two problems:

1. **Wrong owner.** The host (Cursor) decides when to reset Aider's context; the Supervisor — the only component with project knowledge — has no say.
2. **Stale session after pause/resume.** When a delegation pauses and resumes, a cached pre-pause Coder can be reused (P12-ISS-003 now passes real `mcp_session_id` on resume). That session predates the pause gap and is stale.

**Goal (v1 — infrastructure-first):** Put the *control* of executor-session reset in the Supervisor and wire the plumbing end to end. **Not** smart context adaptation — keep current session/context behavior except where correctness forces a reset. Improve the reset *mechanism* later (see **BL-546**).

**v1 scope (ships now):**

Extend `ExecutorFn` with a `reset_session` hint:
```python
ExecutorFn = Callable[[int, str | None, bool], ExecutionResult]
#                      turn  correction  reset_session
```

`SupervisorAgent` signals `reset_session=True` only when:
- **First turn after a resume** (`_resumed_from_pause`) — correctness requirement
- **Optional every-N turns** via `MCP_CODER_SUPERVISOR_SESSION_RESET_EVERY` — **default OFF** (env unset = never); proves the control plane without changing normal behavior

On reset, v1 only calls `drop_coder(mcp_session_id)` in `mcp_server.py`; the existing Coder creation path rebuilds context exactly as today (no new context logic).

`mcp_server.py` handles Aider-specific eviction inside `_executor_fn` — no Aider API in `supervisor_agent.py`.

**Interim fixes (shipped):**
- P12-ISS-002: `drop_coder` on pause (`needs_input` / escalated outcome).
- P12-ISS-003: resume path receives acquired `mcp_session_id` after `SessionStore().acquire(...)`.

**Deferred → BL-546:** hot-area drift, `session_policy` as Supervisor hint, token-window signals, smarter context rebuild on reset.

**Phase placement:** Phase 12 close-out (after P12-005 + P12 issues). Depends on P12-ISS-002/003.

---

### BL-546: Executor session context adaptation (smarter reset policy)

**Status:** `deferred` — 2026-06-21. **Later phase** (post BL-545 v1 control plane).
**Related:** BL-545 (control plane), BL-543 (context lifecycle), BL-542 (two-tier context).

**Problem:**
BL-545 v1 only lays plumbing: Supervisor can signal `reset_session`, but the policy is deliberately trivial (resume-first-turn + optional every-N). Real value comes from resetting (and rebuilding) executor context when the session's loaded files / conversation no longer match what the delegation needs.

**Goal:** Richer, project-aware reset decisions and context adaptation **after** the BL-545 control plane is in place and stable.

**Candidate signals (not v1):**
- Hot-area drift — files actually changed diverge from what the executor session loaded
- Turn / token budget — context window growth beyond a threshold
- `session_policy` becomes a default hint; Supervisor policy takes precedence
- Workspace yaml config for reset interval (not env-only)
- Smarter rebuild on reset — selective re-inject of project state, hot areas, plan (pairs with BL-543)

**Design constraint:** keep backend-neutral signals in Supervisor; Aider-specific eviction/rebuild stays in `server/` / `core/session/`.

**Phase placement:** Phase 13+ candidate. Do not block BL-545 v1.

---

### BL-547: Supervisor autonomous interception (D-ARCH-8)

**Status:** `deferred` — 2026-06-21. **Phase 13+ candidate** (not Phase 13 cleanup scope).
**Related:** BL-543 (confirm_ask enrichment), BL-529 (supervisor context), D-ARCH-8 (PHASE12_MVP).

**Problem:**
Phase 12 north-star #3 and D-ARCH-8 call for the Supervisor to resolve blocking sub-helper questions (Clarity, `confirm_ask`, spec validation) from `project_state` / `decision_log` / plan **before** escalating to the host. No `supervisor_intercept` logic shipped in Phase 12 — infrastructure (state store, tool runner, singleton) is in place; interception behaviour is not.

**Goal:**
When a sub-helper would block on a question answerable from known project context, the Supervisor resolves it autonomously and logs `supervisor_intercept` in trace (`question`, `resolution_source`, `answer`, `reasoning`). Escalate only when context is insufficient.

**Phase placement:** After Phase 13 dogfood validates the Phase 12 stack. Pairs naturally with BL-543 checkpoint B once confirm_ask enrichment is scoped.

---

### BL-548: Mid-loop crash recovery (per-turn agent checkpoint)

**Status:** `deferred` — 2026-06-21. **Phase 13+ candidate** (not Phase 13 cleanup scope).
**Related:** P13-007 (steady-state agent checkpoint at delegation boundaries), BL-544 (pause/resume), BL-545 (executor session lifecycle).

**Problem:**
P13-007 shipped `AgentCheckpoint` — a steady-state snapshot of the `SupervisorAgent` written at the end of **every delegation** (success / error / escalated) to `projects/<project_key>/agent_state.json`, rehydrated by `_get_or_create_supervisor()` on a fresh process. This makes the agent genuinely stateful across restarts **between delegations**: CLI ≡ server invariant holds, the in-memory `_SUPERVISOR_REGISTRY` is a cache of the on-disk truth.

But P13-007 deliberately does **not** cover **mid-loop crash recovery**. If a process dies at turn 3 of a 5-turn delegation (laptop sleep, OOM, deploy, Ctrl-C), the `AgentCheckpoint` on disk reflects the *previous* delegation's end-state — not turn 3 of the in-flight one. On restart, `_get_or_create_supervisor()` rehydrates to the prior delegation's checkpoint, and the in-flight delegation's turn progress (`_cur_turn`, `_decisions`, `_completed_turn_artifacts`) is lost. The host would have to re-run the delegation from turn 0.

Today this is acceptable because:
- Most delegations are short (1–3 turns).
- `SupervisorState` (escalation-only, expiring) already handles the *intentional* pause case — the host paused to answer a question.
- The unintentional crash case is rare and the cost of re-running a short delegation is low.

**Goal (BL-548):**
Checkpoint the agent's **intra-delegation turn state** periodically during the loop, so a crash at turn N can resume from turn N (or N-1) rather than restarting the delegation. Distinct from `SupervisorState` (which is for *intentional* pause/resume with a host answer) and `AgentCheckpoint` (which is steady-state between delegations).

**Candidate approaches (not committed):**
- **Per-turn checkpoint:** write a `turn_state.json` after each `complete_turn()` with `_cur_turn`, `_decisions`, `_completed_turn_artifacts`, `executor_result` summary. On restart, detect an unfinished delegation and offer resume.
- **Write-ahead log:** append-only JSONL of turn events; replay on restart. Heavier but survives partial writes.
- **Hybrid:** checkpoint every N turns (configurable) to bound disk writes; crash loses at most N-1 turns of progress.

**Open questions:**
- How does the host learn a delegation was in-flight on restart? (Response payload field? CLI flag? Auto-detect via unfinished `turn_state.json`?)
- Should mid-loop resume re-run the executor for the lost turn, or trust the last `executor_result`? (Re-running is safer; trusting is faster but may double-apply file edits.)
- How does this interact with `SupervisorState` (escalation pause)? Two resume paths could confuse the host.

**Cost/benefit:**
Defer until delegations routinely span many turns or long wall-clock time, OR until a real crash causes meaningful lost work. P13-007's steady-state checkpoint is the high-value 80%; BL-548 is the long-tail 20%.

**Phase placement:** Phase 13+ candidate. Do not block P13-007 on this.

---

## Done

| ID | Item | Completed |
|----|------|-----------|
| BL-154 (partial) | Usage telemetry (preflight + actual + static cost) | 2026-06-06 — P2-120; window budget enforcement → P2-220 |
| BL-314 (partial) | Honest `files_changed` + `files_unexpected` | 2026-06-06 — P1-152; report Scope expansion → remaining |
| BL-150 | Spec-based delegation (v0 + v2 + review loop) | 2026-06-05 — P1-150 `spec_path`/outcomes; P1-151 epics/tasks/reports, `mode=review\|implement`, cursor rules v6; E2E `mcp_coder_phase1_e2e` |
| BL-125 | Persistent MCP server log | 2026-06-05 — P1-125 |
| BL-305 | Server log scope | 2026-06-05 — P1-125 |
| BL-101 | Transcript tail cap | 2026-06-05 — P1-140 |
| BL-203 | Cursor agent-transcripts | 2026-06-05 — P1-120 + P1-140 |
| BL-322 (partial) | Workspace history Wave 1 (322a–322f) | 2026-06-08 — manifest, blobs/revert, gateway, diff/CLI, metadata, inspect; P3-ISS-001 closed; 397 pytest |

---

---

### BL-525: Planner role — session-bounded, mutable plan, RAG-aware

**Status:** `partial` — 2026-06-21. **Phase 12 P12-005 shipped** (pre-injection v1; commit 69d93d8). Full tool-calling Planner → Phase 13+.
**Related:** BL-350 (outer loop), BL-161 (internal pipeline), BL-526 (Architect), BL-351 (Supervisor — possible merge in Phase 12).
**Design note:** [docs/notes/multi-model-roles.md § Role hierarchy](./notes/multi-model-roles.md)

**Problem:** The current `architect_pass` is a one-shot task-level planner — it fires once before the executor and produces a static prompt prefix. There is no role that owns a mutable plan for the full task lifecycle (before / during / after executor) or that carries session context across delegations.

**Goal:** Formalise a **Planner** role (senior engineer / manager tier) that:
- Owns a mutable plan artifact for the current task
- Fires before the executor with RAG access to prior similar plans and delegation history
- Receives updates from the Supervisor when executor surfaces questions/scope changes
- Reviews executor report at end; decides "done" or "needs another step"
- Is session-bounded: plan state persists across multiple delegations in the same MCP session

**Relationship to Supervisor (P11-002):** Both Planner and Supervisor operate at task scope with similar context budgets. They may merge into one "task intelligence" role in Phase 12 once the plan object exists. For now, keep separate: Supervisor is reactive (intercepts decisions), Planner is proactive (owns the plan). Review post-Phase-11 dogfood.

**Naming:** Current `architect_pass` in code is actually a task-level planner. Rename → `planner_pass` at end of Phase 11 (P11-008) to free up "architect" for the epic-level role (BL-526).

**Phase placement:** Phase 12 (depends on plan object from Phase 12). P11-008 is prerequisite (naming + role constants).

---

### BL-526: Architect role — CTO, epic-boundary, high-level context only

**Status:** `idea` — 2026-06-19.  
**Related:** BL-525 (Planner), BL-006 (critic/reviewer at epic boundary), BL-350 (outer loop).  
**Design note:** [docs/notes/multi-model-roles.md § Role hierarchy](./notes/multi-model-roles.md)

**Problem:** No role today holds the strategic view of an epic. Each delegation is planned in isolation. When a task decision contradicts an earlier epic direction, there is no role to catch that.

**Goal:** Formalise an **Architect** role (CTO tier) that:
- Fires at epic open and epic boundary reviews (not per delegation)
- Receives only high-level context: epic goal, milestones delivered, outstanding risks — NO diffs, NO file contents, NO implementation details
- Job: "Is this epic evolving correctly? Does the next planned step fit the overall direction?"
- Can flag strategic misalignment back to the Planner or Host
- Context budget: ~4k tokens (epic brief only — strictly enforced)

**What Architect does NOT do:**
- Read code diffs or file contents
- Plan individual task implementations (that's Planner)
- Intercept individual executor decisions (that's Supervisor)

**Phase placement:** Phase 12+ — depends on epic/plan object. Tier-2 epic-boundary review (BL-006) is the adjacent concept.

---

### BL-527: Host capability hedging principle

**Status:** `idea` — 2026-06-19.  
**Related:** BL-523 (host escalation), BL-524 (host detection), BL-525/526 (internal roles).  
**Design note:** [docs/notes/multi-model-roles.md § Host layer](./notes/multi-model-roles.md)

**Principle:** mcp-coder's internal layers (Planner, Architect, Supervisor, Reviewer) must **hedge** the host's capability gaps. The system should work correctly regardless of whether the host is a cheap or expensive model.

| Host tier | mcp-coder compensation |
|-----------|----------------------|
| Cheap / junior | Planner does heavier planning; clarity pass catches gaps; Architect holds epic integrity |
| Mid (typical) | Balanced — mcp-coder adds judgment; host handles routing + doc updates |
| Expensive | Internal layers can be lighter / optional; host may do its own planning |

**Consequence for design:** mcp-coder must never assume a capable host. Every quality gate (clarity, planning, supervision, review) must be independently effective. A cheap host + strong mcp-coder layers should produce comparable results to an expensive host + no mcp-coder layers.

**Corollary:** When host declares its model (BL-524), mcp-coder can adapt layer weights — but this is an optimisation, not a correctness dependency.

**Phase placement:** Direction principle, not a discrete milestone. Influences design of every new mcp-coder role. BL-524 (host detection) is the implementation prerequisite for adaptive behaviour.

---

### BL-523: Host-tier model escalation — "junior PM" host + senior for spec/epic tasks

**Status:** `idea` — 2026-06-19.  
**Related:** BL-162 (multi-model executor roles), BL-321 (tiered escalation), BL-512 (host-set policy), BL-524 (host model detection).  
**Design note:** [docs/notes/multi-model-roles.md § Host layer](./notes/multi-model-roles.md)

**Problem:** The host (Cursor) runs the same model for everything — lightweight status updates and heavyweight spec authoring use the same budget. Expensive model time is wasted on junior-PM work; cheap model is insufficient for high-stakes decisions.

**Framing:** Treat the host as a **junior PM** by default:
- Routine work (user chat, updating doc status rows, small planning decisions, filling `§ Results`) → cheap/mid model is sufficient.
- High-value one-shots (authoring a new spec, planning an epic, architecture decision, initial delegation plan) → warrant a senior model.

**Two escalation paths:**

| Path | Mechanism | Notes |
|------|-----------|-------|
| **User-triggered** | User manually switches host model for the heavy task, switches back | Works today; random/manual |
| **MCP-facilitated** | mcp-coder exposes a tool (e.g. `plan_task`, `draft_spec`) that runs a senior-model call internally, returns structured output | Host stays cheap; expensive call is a bounded one-shot inside mcp-coder |

The MCP-facilitated path is the architectural win: the junior PM host calls `mcp-coder.plan_task(task, context)` and gets back a detailed plan without needing to be a senior model itself. mcp-coder controls the model tier for that call (e.g. Sonnet-class), keeps it bounded (D-ARCH-1 context frugality), and logs the usage.

**Concrete examples where senior model is warranted:**
- Authoring a new worker spec (P11-002, P11-003 …)
- Decomposing an epic into steps
- Initial architect pass on a large refactor
- Reviewing whether a phase should be closed (PM judgment call)

**Phase placement:** Phase 12+ (depends on multi-step plan object from Phase 12). MCP-facilitated tools (e.g. `draft_spec`, `plan_task`) can be added independently as new MCP tools.

**See also:** The `architect_pass` (Phase 4) is already a bounded senior-model call inside mcp-coder — this generalises that pattern to the orchestration layer.

---

### BL-524: Host model detection + suggestion

**Status:** `idea` — 2026-06-19.  
**Related:** BL-523 (host escalation), BL-512 (host-set policy).

**Problem:** mcp-coder has no visibility into which model the host is currently using. When a host running a cheap model delegates a complex spec-authoring task, there is no way to surface "this task would benefit from a stronger model" to the user.

**Goal:** mcp-coder detects (or receives) the host model and can emit a suggestion when the task complexity warrants an upgrade.

**Detection approaches (in order of preference):**
1. **Host declares it** — new optional `host_model` field in `delegate_to_agent` args; host sets it when known.
2. **Infer from behavior** — if `model_policy.executor.thinking_budget` is unset and architect pass is producing thin plans, heuristic flag.
3. **Response metadata** — return `suggested_host_model_upgrade: true` in delegation response when complexity signals warrant it (file count, epic keywords, prior failed attempts).

**Not in scope early:** automatic model switching for the host (MCP doesn't control the host's model). Only detection + advisory.

**Phase placement:** Phase 12+ or as a small BL-512 extension. Advisory `ctx.info` message is the v0.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-21 | **BL-548 added** — mid-loop crash recovery (per-turn agent checkpoint). Deferred from P13-007, which shipped steady-state checkpoint at delegation boundaries only. Long-tail 20% after P13-007's high-value 80%. |
| 2026-06-21 | **Phase 12 closed** — P12-001..P12-005 + issues + BL-545 v1 shipped; partial items (BL-543, BL-529, BL-525) and D-ARCH-8 → **BL-547** deferred; Phase 13 opened (stabilize + dogfood). |
| 2026-06-21 | **BL-547 added** — D-ARCH-8 supervisor autonomous interception (`supervisor_intercept`); deferred post–Phase 12 infra. |
| 2026-06-21 | **BL-545 added** — Supervisor-owned executor session lifecycle: Supervisor decides when to reset Aider session (turn count, hot-area drift, post-resume); `ExecutorFn` gains `reset_session` hint; interim fix (drop stale Coder on pause, pass `mcp_session_id` to resume) ships in P12-ISS-002. End of Phase 12 / Phase 13. |
| 2026-06-20 | **BL-530 + BL-542 updated** — revised to reflect two-tier context model (D-ARCH-11) and `SupervisorToolRunner` as the Phase 12 implementation. Tier 1 = slow-changing base context; Tier 2 = on-demand tool calls driven by Supervisor LLM reasoning. Phase 13+ tools (RAG search, cross-project) deferred. |
| 2026-06-20 | **BL-544 added** — Supervisor pause/resume: stateful agent across multiple `delegate_to_agent` calls via `resume_token`; skips already-completed pipeline stages on resume; host answer injected into continuation brief. High priority for real production use. |
| 2026-06-20 | **BL-543 added** — supervisor-owned context lifecycle: confirm_ask enrichment and continuation brief. |
| 2026-06-20 | **BL-540, BL-541, BL-542 added** — persistent project state, reviewer findings feedback loop, dynamic context routing for planner/supervisor. |
| 2026-06-20 | **Phase 11 closed** — § Phase 11 table marked shipped/closed; carry-over issues moved from PHASE11_ISSUES to backlog items BL-535..BL-539; BL-533 marked done in P11-009 and BL-534 added for reasoning-capture fidelity. |
| 2026-06-19 | **P11-007 shipped** — BL-512 Stage 2 done: host `model_policy` arg with per-role overrides, additive precedence (host > env > defaults), and warning audit fields. |
| 2026-06-19 | **P11-006 shipped** — smart architect trigger v0 shipped (spec/env/heuristic precedence + skip-reason audit detail). |
| 2026-06-19 | **P11-005 shipped** — BL-358 Phase 11 slice done (`reviewer_pass` + report append + non-fatal error path). |
| 2026-06-19 | **BL-528 added** — late-answer resume after P11-004 human-gate timeout (`resume_token` continuation concept). Tracks the gap where late `answer_delegation_question` currently returns `not_found`. |
| 2026-06-19 | **P11-003 shipped** — BL-354 Phase 11 slice done (prompt-only `/read` hint + audit). Full sidecar/tool-server remains Phase 12. |
| 2026-06-19 | **P11-002 shipped** — BL-351 Phase 11 scope done (`SupervisedIO` + `DelegationSupervisor` + abort-on-escalate); async/mid-run resume remains deferred to Phase 12. |
| 2026-06-19 | **BL-525 + BL-526 + BL-527 added** — Planner role (session-bounded, mutable), Architect role (CTO, epic-boundary), host capability hedging principle. Full role hierarchy captured in `multi-model-roles.md`. P11-008 naming refactor planned. |
| 2026-06-19 | **BL-523 + BL-524 added** — host-tier model escalation ("junior PM" host) and host model detection; Phase 12+ direction. See `multi-model-roles.md § Host layer`. |
| 2026-06-19 | **P11-001 shipped** — `clarity_check` pipeline phase (BL-521 Phase 11 scope done); opt-in `MCP_CODER_CLARITY_PASS`; 16 tests; cross-session intent → Phase 12. |
| 2026-06-18 | **Phase 11 opened.** BL-521 (new) + BL-351 → P11-002; BL-354 (v0) → P11-003; BL-522 (new) → P11-004; BL-358 (v0) → P11-005; BL-512 (Stage 2) → P11-007. § Phase 11 active table added; BL-351/354/358/512 status updated to `in_phase`. Cross-arch decisions D-ARCH-1..6 locked. See [PHASE11_MVP.md](./PHASE11_MVP.md). |
| 2026-06-18 | **Phase 10 closed.** Promoted backlog items moved from `in_phase` to `done` (v0/POF/partial as scoped); § Phase 10 table frozen. Residuals: BL-516/518 partial, BL-106/520 follow-ups, BL-351 full vision → Phase 11. |
| 2026-06-18 | **P10-004 shipped** — BL-517/519 completed; BL-516/518 partial shipped (`trace inspect --summary`, env matrix docs + `.env.example` parity). |
| 2026-06-18 | **P10-003 shipped** — BL-351 v0 completed (regex stall classification, structured `needs_input` with `files_requested`, optional one-shot auto-retry, delegation stall audit fields). Real Cursor-host dogfood validated in `mcp_coder_phase9_e2e` (delegation `79eb11a6-0d38-42e1-a10f-2ab325c28b0a`). |
| 2026-06-18 | **P10-002 shipped** — BL-106 POF + BL-520 POF completed (`ctx.info` milestones + thread bridge; `mcp-coder logs tail` with `--latest`/`--delegation-id`). Follow-up scope remains in backlog. |
| 2026-06-18 | **P10-001 shipped** — BL-334 v0 completed (executor `system_prompt_prefix` + `edit_format` wiring + delegation audit fields + env docs + tests). BL-334 status moved to `done`; Phase 11 keeps BL-512 per-delegation override. |
| 2026-06-18 | **Phase 10 opened.** BL-334 → **P10-001**; BL-106 + BL-520 → **P10-002**; BL-351 (v0) → **P10-003**; BL-516/517/518/519 → **P10-004**. Status `in_phase` on promoted items; § Phase 10 active table added. See [PHASE10_MVP.md](./PHASE10_MVP.md). |
| 2026-06-17 | **BL-106** expanded (MCP `report_progress` + `ctx.log` + capture→egress bridge) and **BL-520** added (`logs tail` / follow delegation on trace + server JSONL). Phase 9 closed — live visibility is Phase 10 read/notify layer on top of write-always capture. |
| 2026-06-17 | **BL-518** (runtime log level / verbosity DX) and **BL-519** (`MCP_CODER_PROXY_ENABLED` toggle) added — post-Phase 9 operational polish; scope TBD. |
| 2026-06-17 | **Phase 9 formally closed.** P9-014 deferred → **BL-516** (CLI log health table + `trace inspect --summary`). P9-ISS-007 deferred → **BL-517** (executor `policy_applied` ignored params). No open Phase 9 issues. |
| 2026-06-17 | **Phase 9 A-to-Z dogfood complete** — 6 delegations; 6/6 proxy↔llm_call exact alignment. Three post-dogfood fixes: P9-ISS-008 proxy routing catch-all (`google/*` → OpenRouter), P9-ISS-009 streaming token counts (`stream_options: include_usage`), P9-ISS-010 executor `llm_call.policy_applied` (contextvar re-derive + step builder). Guide synced 2026-06-17. |
| 2026-06-16 | BL-511–514 added — model policy layer Stages 1–4; design note at [model-policy-layer.md](./notes/model-policy-layer.md). BL-511 implemented in Phase 9 (P9-011 + P9-012, done same day). BL-507/508/510 closed. BL-367/BL-353 fully done. |
| 2026-06-13 | **Phase 7 closeout sync** — BL-350/353/368 statuses updated to reflect P7 shipment; BL-369/370/371 added from carried P7 issues |
| 2026-06-13 | **Phase 6 closed** — PHASE6_MVP + PHASE6_ISSUES frozen; P6-ISS-002 → BL-368; Phase 6 exit table added; BL-335 done (partial); BL-353 partial |
| 2026-06-13 | BL-368 added — unified LlmGateway completion proxy (P6-ISS-002); Phase 7 target |
| 2026-06-13 | Phase 6 planning locked — BL-335 → P6-002, BL-353 → P6-002/003, BL-333 → P6-004; phase refs updated |
| 2026-06-13 | BL-365–366 added — RAG toolset DX gaps + P5-005 evaluation capstone; BL-002 § gaps table + shipped CLI/MCP reference; BL-363 guide sync note |
| 2026-06-13 | BL-360–363 added — code layout refactor, always-review mode, T-06/T-07 tutorials, arch sub-pages (from Phase 4.5 handoff); BL-002 status updated to `active`; Phase 5 planning locked in PHASE5_MVP.md |
| 2026-06-12 | BL-359 added — workflow turns (refactor, document, digest cadence; semi-auto suggest); [workflow-turns.md](./notes/workflow-turns.md) |
| 2026-06-12 | BL-358 added — post-executor polish pass (reviewer model: comments, tests, non-logic alignment); Phase 5+ |
| 2026-06-12 | BL-357 added — storage lifecycle (promote/prune/gc) for logs, RAG, traces, checkpoints; Phase 6+ (RAG planning) |
| 2026-06-11 | BL-356 added — RAG-backed context audit refs (lean JSONL, digest provenance); pairs with BL-002/BL-353 (T-04 observability pass) |
| 2026-06-11 | BL-353 expanded — full-delegate audit gaps (helper inputs, transcript line provenance, compile bundle, phased 5a/5b/6); BL-002 chat corpus note |
| 2026-06-11 | BL-354 added — executor context tools (pull): dual compile-push + RAG/history/read tools during backend loop; Phase 5+ (T-04 pass) |
| 2026-06-11 | BL-353 added — LLM boundary observability (full pass-through logging); Phase 6 TBD; high ROI for gap-finding and dev direction (T-04 pass) |
| 2026-06-09 | BL-340 added — Cursor SDK execution backend (deferred, later phase — not Phase 5) |
| 2026-06-09 | Phase 4 exit — P4-ISS-002–007/014–021 carried; BL-335–339 added; BL-309e/328/330 cross-linked |
| 2026-06-09 | BL-329 done — P4-009 spec validation + clarifying loop |
| 2026-06-09 | BL-310 partial — P4-010 verify loop (310b/c done; 310a deferred) |
| 2026-06-09 | BL-332 added — host-agnostic planner rules sync (deferred; Cursor-coupled today, compile engine reusable) |
| 2026-06-09 | BL-331 added — symbol-scoped/chunked edit files (Phase 5+, executor format change) |
| 2026-06-09 | BL-162 staged (Stage 1 per-role D-P4-8 → escalation → swarm); notes/multi-model-roles.md |
| 2026-06-09 | BL-330 inspect-tool server log audit (P4-ISS-002); PHASE4_ISSUES created |
| 2026-06-09 | BL-334 added — backend prompt customization (system prompt prefix + edit-format control; small Aider-adapter knobs) |
| 2026-06-09 | BL-333 expanded — three axes (model upgrade/escalation, transfer intelligence, training/distillation + learned modules) added to REASONING_TRACE_REUSE.md |
| 2026-06-09 | BL-333 design doc — OTEHR_RELATED_IDEAS/REASONING_TRACE_REUSE.md; backlog entry condensed to pointer |
| 2026-06-09 | BL-333 added — reasoning trace capture + cross-delegation context feed (idea; LiteLLM callback route recommended) |
| 2026-06-09 | BL-329 added — pre-delegate spec validation + clarifying loop (Phase 4 master session; P4-009 optional Wave 4) |
| 2026-06-09 | **P3-499 exit** — BL-324–328 from frozen PHASE3_ISSUES; BL-321 deferred Phase 4 |
| 2026-06-09 | BL-002 design decisions locked — corpus scope, architecture; RAG → Phase 5 (Phase 4 = context builder first); P3-002-lite delegation RAG shipped |
| 2026-06-08 | BL-322a–f done; BL-322g/h deferred (restore + fork/sandbox); BL-502 cross-link |
| 2026-06-08 | Phase 3 start — BL-320/322 `scheduled`; BL-323 budget override; BL-322a storage aligned to WORKSPACE_HISTORY |
| 2026-06-07 | Wild test done — BL-320 failed-attempt archive; BL-321 tiered model selection (P2-ISS-007/008) |
| 2026-06-07 | BL-322 workspace hash snapshot + post-delegation gateway — Phase 3 design (chat [Phase 2 tail review](d44a5b15-2ed4-4834-bc91-91f776e5dd02)) |
| 2026-06-06 | P2-120 done — usage telemetry; BL-319 dynamic rates deferred; BL-154 partial |
| 2026-06-06 | P1-199 exit — Post–Phase 1 focus reordered; BL-314 partial, BL-315–318 added; P1 issues migrated |
| 2026-06-05 | BL-309–312 from expense-splitter E2E; BL-150 done |
