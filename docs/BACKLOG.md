<!--
  STEWARDSHIP — Tier 2 backlog INDEX. See docs/VISION_DOCS.md.

  LLM quick ref (full recipes: docs/backlog/README.md § For LLMs):
  - READ: this file only (~300 lines); grep deferred.md/done.md for full text.
  - UPDATE: change index row here AND **Status:** in deferred.md (or done.md) together.
  - SHIP: move ### BL-NNN section deferred → done.md; set index status done; changelog.
  - NEW: add ### BL-NNN under cluster in deferred.md + index row + changelog.
  - Workers: do NOT edit; propose BL-* in task § Results → master session.
  - NOT OK: full bodies here, silent deletes, contradict IDEA.md.
-->

# Project backlog (index)

Items deferred from active phases, future ideas, and nice-to-haves. **Vision:** [IDEA.md](./IDEA.md) · [VISION_DOCS.md](./VISION_DOCS.md).

**Read pattern:** scan this index → `grep "^### BL-NNN" docs/backlog/deferred.md` for full text.

**Update pattern (LLMs):** [backlog/README.md](./backlog/README.md) § For LLMs — always sync index row + full-text `**Status:**`; workers propose only.

Status: `idea` | `deferred` | `partial` | `blocked` | `in_phase` | `done` | `watch`

---

## Active (candidates for next phase)

| BL-ID | What | Status |
|-------|------|--------|
| BL-528 | Late-answer resume after human-gate timeout (`resume_token` continuation) | deferred |
| BL-516 | CLI log health table (`mcp-coder log`) + `trace inspect --no-truncate` | partial |
| BL-518 | Unified runtime log level / verbosity DX + proxy debug logging | partial |

---

## Watch for evidence (fixed-pending-verify → confirm in future runs)

When running log analysis or dogfood, check these conditions and close the source issue if confirmed.

| BL | Watch item | What to check | Source |
|----|-----------|---------------|--------|
| BL-554 | Executor error classification — confirm non-config for edit-flow failures | On executor error, `error_detail.error_class` must NOT be `config` for edit/patch/format failures; true config errors still `config` | [P13-ISS-006](./PHASE13_ISSUES.md) |
| BL-555 | Unknown loop failure typed cause — confirm row/view fields populated | On `worker_outcome=unknown`, row has `error_class=unknown` + `error_message`; viewer surfaces typed fields in `mcp→host` | [P13-ISS-015](./PHASE13_ISSUES.md) |
| BL-553 | Escalation pause resume semantics — verify mid-loop `needs_input` / `max_turns_reached` | Dogfood scenarios that trigger escalation pauses; verify resume with/without `answer`; define proper behavior | Phase 13 deferred |

---

## Index by cluster


### Supervisor & orchestration

| BL-ID | What | Status |
|-------|------|--------|
| BL-525 | Planner as agent — tool-calling loop, mutable plan, RAG-aware (mirror SupervisorToolRunner) | partial |
| BL-526 | Architect role — CTO, epic-boundary, high-level context only | deferred |
| BL-528 | Late-answer resume after human-gate timeout (`resume_token` continuation) | deferred |
| BL-529 | Supervisor context window — task + spec + Aider output tail | partial |
| BL-531 | Multi-turn loops for helper models | deferred |
| BL-532 | Inter-model communication — Aider → pipeline, pipeline → Aider | deferred |
| BL-533 | Supervisor agent loop unified (`supervisor_loop_*`) — P11-009 shipped | done |
| BL-535 | Trace inspect UX — specless CLI runs via trace-file fallback when DB index missing | deferred |
| BL-536 | Role attribution completeness — every proxy/backend LLM call has role/model/provider/ok/duration | deferred |
| BL-537 | Reviewer semantics — explicit `reviewer_mode`/`reviewer_outcome`/`reviewer_action` in outputs | deferred |
| BL-538 | Planner audit normalization — same shape as clarity/spec-validation/reviewer blocks | deferred |
| BL-539 | Clarity telemetry polish — `clarity_round_index`/cap/auto_passed in trace + records | deferred |
| BL-543 | Supervisor-owned context lifecycle — refresh at checkpoints and confirm_ask enrichment | partial |
| BL-546 | Executor session context adaptation (smarter reset policy) | deferred |
| BL-547 | Supervisor autonomous interception (D-ARCH-8) | deferred |
| BL-548 | Mid-loop crash recovery (per-turn agent checkpoint) | deferred |
| BL-553 | Escalation pause resume semantics — verify mid-loop `needs_input` / `max_turns_reached` | deferred |

### Context & RAG

| BL-ID | What | Status |
|-------|------|--------|
| BL-002 | RAG / cross-session memory | partial |
| BL-347 | Adaptive context-management policies | deferred |
| BL-348 | Incremental workspace code-intel cache (high ROI context) | deferred |
| BL-349 | Recently touched files — session + project, git + manifest fusion | deferred |
| BL-356 | RAG-backed context audit refs — lean JSONL + digest provenance | deferred |
| BL-357 | Storage lifecycle — promote, prune, gc (logs + RAG + traces) | deferred |
| BL-364 | Blocked-delegate pipeline skip reasons in JSONL | deferred |
| BL-365 | RAG toolset DX — unified CLI + workspace index stats | deferred |
| BL-366 | RAG retrieval evaluation (P5-005 capstone) | deferred |

### Observability & logging

| BL-ID | What | Status |
|-------|------|--------|
| BL-301 | Delegation log web UI | deferred |
| BL-302 | Redaction policy doc for logs (secrets) | deferred |
| BL-303 | Metrics export (Prometheus / statsd) | deferred |
| BL-304 | Global index `hosts/cursor/<id>/index.json` | deferred |
| BL-306 | Startup code version / git hash in MCP stderr | deferred |
| BL-307 | `MCP_CODER_SINGLETON=all` aggressive global kill | deferred |
| BL-308 | Global `server.jsonl` locking / per-pid subfiles | deferred |
| BL-333 | Reasoning trace capture + cross-delegation context feed | partial |
| BL-336 | `judgment_checklist` nested under `response_to_cursor` in JSONL only | deferred |
| BL-337 | `config_deprecated` noise in `server.jsonl` (e.g. stale `mcp.json` keys) | deferred |
| BL-509 | Content-addressable deduplication for trace event bodies | deferred |
| BL-516 | CLI log health table (`mcp-coder log`) + `trace inspect --no-truncate` | partial |
| BL-518 | Unified runtime log level / verbosity DX + proxy debug logging | partial |
| BL-549 | Viewer full-fidelity output mode (no digest-only blind spots) | deferred |
| BL-550 | Output truncation policy controls + clear UX labeling | deferred |
| BL-551 | Pointer-first short log + viewer resolve-to-full flow | deferred |
| BL-552 | Logging policy review — default full-fidelity capture + retention tradeoffs | deferred |

### Executor & backends

| BL-ID | What | Status |
|-------|------|--------|
| BL-004 | OpenCode adapter (subprocess) | deferred |
| BL-160 | Full interactive via CLI | deferred |
| BL-331 | Symbol-scoped / chunked edit files | deferred |
| BL-338 | Executor `edit_format` / constraint blindness on cheap models | deferred |
| BL-340 | Cursor SDK as execution backend (beside Aider) | deferred |
| BL-350 | Supervised executor loop (mid-run inspect + context inject) | partial |
| BL-352 | Multi-language symbol scan + outlines (C/C++, Go, Rust, …) | deferred |
| BL-355 | Optional host CLI toolchain (`rg`, docs, doctor) | deferred |
| BL-358 | Post-executor polish pass — reviewer model (comments, tests, alignment) | deferred |

### Models & policy

| BL-ID | What | Status |
|-------|------|--------|
| BL-007 | Multi-model ensemble | deferred |
| BL-162 | Router / janitor + cheap model for context build | deferred |
| BL-321 | Progressive / tiered executor model selection | deferred |
| BL-512 | Model policy layer — Stage 2 (host-set policy) | deferred |
| BL-513 | Model policy layer — Stage 3 (AI-suggested parameters) | deferred |
| BL-514 | Model policy layer — Stage 4 (dynamic escalation) | deferred |
| BL-515 | Model tiers and classes | deferred |
| BL-523 | Host-tier model escalation — "junior PM" host + senior for spec/epic tasks | deferred |
| BL-524 | Host model detection + suggestion | deferred |
| BL-527 | Host capability hedging principle | deferred |

### Host & integration

| BL-ID | What | Status |
|-------|------|--------|
| BL-201 | Claude Desktop host adapter | deferred |
| BL-202 | Windsurf / other IDEs | deferred |
| BL-204 | Proxy intercept: save latest Cursor prompt from `context_optimizer_proxy` | deferred |
| BL-205 | Cursor rule / skill snippet for routing to `delegate_to_agent` | deferred |
| BL-332 | Host-agnostic planner rules sync | deferred |
| BL-341 | `mcp-coder setup` + global env (onboarding DX) | done |

### Specs & workflow

| BL-ID | What | Status |
|-------|------|--------|
| BL-312 | Auto-review policy (optional) | deferred |
| BL-315 | `edit_scope` + spec Files YAML | partial |
| BL-324 | Planner inspect-tool adoption (judgment loop) | deferred |
| BL-325 | Spec paths only under `.mcp-coder/specs/` | deferred |
| BL-326 | Read-deps `(none` parse fix | deferred |
| BL-327 | Surface failed delegations in host summary | deferred |
| BL-328 | P3-ISS-009 | deferred |
| BL-330 | P4-ISS-002 | deferred |
| BL-344 | Configurable spec granularity (step size / full-epic delegate) | deferred |
| BL-345 | Mechanical spec lint (pre-delegate, no LLM) | deferred |
| BL-346 | Model-aware context budget defaults + cap enforcement | deferred |
| BL-359 | Workflow turns — refactor, document, digest cadence | deferred |
| BL-361 | "One step at a time" / always-review-before-implement delegate mode | deferred |
| BL-362 | T-06 done; T-07/T-08 tutorial stubs — full walkthroughs pending | partial |
| BL-363 | Guide synced Phase 12/13; architecture sub-pages still pending | partial |

### Storage & lifecycle

| BL-ID | What | Status |
|-------|------|--------|
| BL-322 | Workspace history — delegation-granularity version control | partial |

### Reliability & error handling

| BL-ID | What | Status |
|-------|------|--------|
| BL-309 | Delegation hardening (job failure vs workflow failure) | deferred |
| BL-310 | Planner verify / report status split | partial |
| BL-311 | Read-deps from spec Files section | done |
| BL-314 | Honest delegation file reporting | deferred |
| BL-316 | Context builder file materialization tiers | deferred |
| BL-317 | Cursor project slug robustness | deferred |
| BL-318 | `project_key` alias on repo move | deferred |
| BL-323 | Context budget override semantics (dev ergonomics) | deferred |
| BL-339 | P4-ISS-021 | deferred |
| BL-556 | Dogfood integration test hardening (P13-003 carry) — multi-delegation project_state, pause/resume, reviewer→planner | deferred |
| BL-558 | Supervisor swallow-counter health endpoint — surface `get_supervisor_swallow_counts()` snapshot + reset on delegation boundaries so a dashboard can show "N swallowed errors in the last delegation" (P14-ISS-010 follow-up) | deferred |
| BL-559 | Helper `proxy_llm_call` full bodies — v1 emits metadata-only (`attribution_source="gateway"`); add `raw_request`/`raw_response` if the viewer's helper-triple join needs them (P14-ISS-009 follow-up; depends on viewer feedback from Phase 14 dogfood) | deferred |

### Architecture & transport (Phase 15 refactor / Phase 16 rename)

| BL-ID | What | Status |
|-------|------|--------|
| BL-560 | Long-lived daemon (server) with localhost API owning all business logic + state | deferred |
| BL-561 | Async delegation jobs — submit/poll/status on the daemon so jobs survive client disconnect; blocking compat wrapper for hosts | deferred |
| BL-562 | Thin MCP adapter — stdio shim proxying to the daemon API; no business logic in MCP layer | deferred |
| BL-563 | CLI as daemon API client — CLI/MCP become peers over the same API | deferred |
| BL-564 | Single daemon multi-workspace + lifecycle — auto-start, `mcp-coder serve`, PID/lock, health endpoint; replaces per-project stdio singleton (B026) | deferred |
| BL-565 | Localhost security — bind 127.0.0.1, optional token, no network exposure by default | deferred |
| BL-566 | Migration / forward-compat — keep stdio-as-server working during transition; existing `.cursor/mcp.json` forward-compat | deferred |
| BL-567 | Full product rename — package, CLI, docs, env prefix, on-disk paths + deprecation/compat shim (Phase 16) | deferred |

### Ideas / unscoped

| BL-ID | What | Status |
|-------|------|--------|
| BL-001 | Owned context pipeline (summarize, rank, trim) | deferred |
| BL-003 | Router / janitor LLM inside mcp-coder | deferred |
| BL-005 | Dual-mode CLI (`mcp-coder run …`) | deferred |
| BL-006 | Context janitor, critic, test-writer sub-agents | deferred |
| BL-008 | Skills injection library | deferred |
| BL-009 | Explicit MCP tools: `continue_session`, `get_session_status` | deferred |
| BL-010 | ~~DB-backed session persistence~~ | deferred |
| BL-151 | Gatekeeper MCP for protected specs | deferred |
| BL-152 | Mirror `delegations.jsonl` + reports in product UX | partial |
| BL-161 | Multi-agent inside MCP (planner → executor) | deferred |
| BL-360 | Code layout refactor — instance sub-folders, file size audit | deferred |
| BL-401 | `always_new` vs `align_host` | partial |
| BL-403 | Prompt size vs failure rate per model | partial |
| BL-404 | Cursor `target_files` reliability | deferred |
| BL-405 | Tool name/description for routing | deferred |
| BL-501 | If human latency exceeds MCP timeout, persist “awaiting_host” state + resume token (BL-501 adjacency) | deferred |
| BL-502 | Git worktree / task-branch per delegation — git-native audit trail + rollback (pairs with BL-322; alternative to BL-3... | deferred |
| BL-503 | Grade executor output with cheap model before returning to Cursor | deferred |
| BL-504 | Global `~/.mcp-coder/config.yaml` defaults | done |
| BL-506 | Generic `transcript.md` watch folder (non-Cursor hosts) | deferred |
| BL-522 | Mid-run human gate — `answer_delegation_question` *(Phase 11 P11-004, experimental)* | deferred |

### Uncategorized

| BL-ID | What | Status |
|-------|------|--------|
| BL-101 | ~~SpecStory tail truncation cap~~ | done |
| BL-102 | Fallback `cheap_llm` session classifier | deferred |
| BL-103 | `inspect_delegations.py` CLI | deferred |
| BL-104 | Aider dry-run mode in MCP | deferred |
| BL-105 | Default Aider → `context_optimizer_proxy` in setup template | deferred |
| BL-106 | MCP live progress + logging notifications | done |
| BL-107 | `MCP_CODER_MIRROR_LOGS_TO_WORKSPACE` default policy | deferred |
| BL-108 | Pick “main” mcp session among N per `host_session_id` | deferred |
| BL-109 | `continue_session` by explicit `mcp_session_id` | deferred |
| BL-125 | ~~Persistent MCP server log + verbosity tiers~~ | done |
| BL-150 | ~~Spec-based delegation~~ | done |
| BL-153 | Topic / task boundary detection | deferred |
| BL-154 | Context window management | deferred |
| BL-155 | Executor cache & multi-turn | deferred |
| BL-203 | ~~Read Cursor agent-transcripts~~ | done |
| BL-305 | ~~Server log scope: global vs per-`project_key`~~ | done |
| BL-319 | Dynamic model rates (usage cost) | done |
| BL-320 | Failed-delegate attempt archive (spec-adjacent) | done |
| BL-329 | Pre-delegate spec validation + clarifying loop | done |
| BL-334 | Backend prompt customization (system prompt prefix + edit-format control) | done |
| BL-335 | Phase 5 early | done |
| BL-342 | `test-model` list/select/all | done |
| BL-343 | Structured delegation log viewer | done |
| BL-351 | Simulated interactive mode + host escalation (human intervention) | done |
| BL-353 | LLM boundary observability — full pass-through logging | done |
| BL-354 | Executor context tools (pull) — RAG/history/read during backend loop | done |
| BL-367 | Full-capture substrate — LlmGateway proxy + verbosity as display-only filter | done |
| BL-368 | Unified LlmGateway completion proxy | done |
| BL-369 | CLI gateway bootstrap hardening | done |
| BL-370 | Host transcript byte-range provenance | done |
| BL-371 | Backend-specific interception strategy for full in/out capture | partial |
| BL-402 | SpecStory freshness window | deferred |
| BL-505 | SpecStory `.specstory/history/*.md` | deferred |
| BL-507 | Thinking token capture verification | done |
| BL-508 | Universal internal HTTP proxy | done |
| BL-510 | Remove `should_log_full_prompt` write gate from delegation row | done |
| BL-511 | Model registry Stage 1 (front door + unified helper path + params + logging) | done |
| BL-517 | Executor `policy_applied` ignored params | done |
| BL-519 | `MCP_CODER_PROXY_ENABLED` env toggle | done |
| BL-520 | Live log tail / follow delegation | done |
| BL-521 | Pre-delegation spec clarity pass *(Phase 11 P11-001)* | done |
| BL-530 | On-demand context retrieval — `SupervisorToolRunner` (Phase 12 implementation) | done |
| BL-540 | Persistent project state — cross-delegation planner notebook | done |
| BL-541 | Reviewer findings feedback loop — close the loop across delegations | done |
| BL-542 | Dynamic context routing — two-tier Supervisor/Planner context model | done |
| BL-544 | Supervisor pause/resume — stateful agent across multiple delegate_to_agent calls | done |
| BL-545 | Supervisor-owned executor session lifecycle (v1 — control plane) | done |


---


## Changelog

| Date | Change |
|------|--------|
| 2026-06-30 | **BL-560..BL-567 added (Phase 15 refactor track / Phase 16 rename).** Epic 7 dogfood (`idealabs_web`, rev `2fb976e`) proved the stdio-as-center model is the reliability root cause — 0/6 complete MCP delegations; product work landed via host fallback. Added a new "Architecture & transport" cluster: BL-560 (long-lived daemon + localhost API owning all business logic/state), BL-561 (async delegation jobs surviving client disconnect + blocking compat wrapper), BL-562 (thin MCP adapter, no business logic in MCP layer), BL-563 (CLI as daemon API client — CLI/MCP peers), BL-564 (single daemon multi-workspace + lifecycle — replaces per-project stdio singleton / B026), BL-565 (localhost security), BL-566 (migration/forward-compat), BL-567 (full product rename + env/path compat shim — Phase 16). The refactor (BL-560..BL-566) is a **Phase 15 track** (milestone P15-040) to finish dogfooding; the rename (BL-567) is **Phase 16**, run after the refactor settles. Core rule: business logic lives only in the server; CLI and MCP are thin clients. PHASES.md updated with the Phase 15 refactor-track section + Phase 16 rename section. |
| 2026-06-25 | **BL-558 + BL-559 added** — follow-ups from P14-ISS-FIX closure batch. BL-558: wire `get_supervisor_swallow_counts()` to a health endpoint (snapshot + reset on delegation boundaries; P14-ISS-010 v1 left the counters exposed but unread). BL-559: add `raw_request`/`raw_response` bodies to helper `proxy_llm_call` if the viewer's helper-triple join needs them (P14-ISS-009 v1 emitted metadata-only to avoid trace bloat; depends on viewer feedback from Phase 14 dogfood). |
| 2026-06-24 | **BL-525 reframed** — Planner as agent: tool-calling loop + mutable plan + RAG-aware. Updated to reflect the real gap surfaced in Phase 14 — the Supervisor already has a bounded tool-calling agent loop (`SupervisorToolRunner`, BL-530) but the Planner is still one-shot `run_owned_helper_completion()`. Planner should mirror the Supervisor's loop pattern with its own tool set (`read_file`, `get_project_state`, `get_delegation_history`, `rag_search`). Cross-linked BL-557 (sharing layer — a tool-calling Planner can pull prior reasoning via RAG, the high-value path for the intelligence cascade). Post-Phase-14. |
| 2026-06-24 | **BL-557 added (reframed)** — cross-model reasoning sharing layer: peer-to-peer normalized reasoning summaries + curated shared store, with implicit (supervisor-mediated) + explicit (RAG) retrieval seams. Extends BL-333 beyond executor-only; depends on Phase 14 (P14-003c/P14-004) to verify reasoning-capture substrate first. Forcing-prompt convention for non-reasoning models included as deliverable (a). Reframed from "cascade downhill" to "peer-to-peer sharing among role-specific models" after user clarification. |
| 2026-06-23 | **Phase 13 closed** — P13-003 deferred → **BL-556** (dogfood integration tests); BL-362/363 → `partial` (T-06 + guide sync done; T-07/T-08 stubs + arch sub-pages remain). |
| 2026-06-23 | **Backlog split** — BACKLOG.md is now index-only; full text in `docs/backlog/deferred.md` + `docs/backlog/done.md`; archive at `docs/backlog/_source-full.md`. |
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
| 2026-06-16 | BL-511–514 added — model policy layer Stages 1–4; design note at [model-policy-layer.md](./notes/archive/model-policy-layer.md). BL-511 implemented in Phase 9 (P9-011 + P9-012, done same day). BL-507/508/510 closed. BL-367/BL-353 fully done. |
| 2026-06-13 | **Phase 7 closeout sync** — BL-350/353/368 statuses updated to reflect P7 shipment; BL-369/370/371 added from carried P7 issues |
| 2026-06-13 | **Phase 6 closed** — PHASE6_MVP + PHASE6_ISSUES frozen; P6-ISS-002 → BL-368; Phase 6 exit table added; BL-335 done (partial); BL-353 partial |
| 2026-06-13 | BL-368 added — unified LlmGateway completion proxy (P6-ISS-002); Phase 7 target |
| 2026-06-13 | Phase 6 planning locked — BL-335 → P6-002, BL-353 → P6-002/003, BL-333 → P6-004; phase refs updated |
| 2026-06-13 | BL-365–366 added — RAG toolset DX gaps + P5-005 evaluation capstone; BL-002 § gaps table + shipped CLI/MCP reference; BL-363 guide sync note |
| 2026-06-13 | BL-360–363 added — code layout refactor, always-review mode, T-06/T-07 tutorials, arch sub-pages (from Phase 4.5 handoff); BL-002 status updated to `active`; Phase 5 planning locked in PHASE5_MVP.md |
| 2026-06-12 | BL-359 added — workflow turns (refactor, document, digest cadence; semi-auto suggest); [workflow-turns.md](./notes/archive/workflow-turns.md) |
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
