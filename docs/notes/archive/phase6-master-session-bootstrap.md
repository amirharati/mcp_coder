# Phase 6 master session bootstrap

**Created:** 2026-06-13  
**Purpose:** Frozen summary of Phase 6 planning session decisions. Use as context for future master sessions and worker sessions.  
**Status:** Frozen at Phase 6 exit (2026-06-13) — P6-001…P6-008 shipped; issues → BACKLOG § Phase 6 exit.  
**Authoritative PM docs:** [PHASE6_MVP.md](../../PHASE6_MVP.md) (frozen) · [PHASE6_ISSUES.md](../../PHASE6_ISSUES.md) (frozen)  
**Design ideas (read before dispatching workers):**  
- [AGENTIC_LOOP_LOGGING.md](../../OTEHR_RELATED_IDEAS/AGENTIC_LOOP_LOGGING.md) — long-horizon product vision; Phase 6 is its POC/MVP  
- [REASONING_TRACE_REUSE.md](../../OTEHR_RELATED_IDEAS/REASONING_TRACE_REUSE.md) — reasoning token capture + in-product uses (BL-333 substrate)  
- [CONTEXT_AS_GIT.md](../../OTEHR_RELATED_IDEAS/CONTEXT_AS_GIT.md) — "stored context vs runtime context" mental model; informs hot buffer design  
**Related backlog:** BL-335, BL-353, BL-333, BL-334, BL-357, BL-366

---

## Why Phase 6 — the ROI case

After Phase 5 (RAG), we can retrieve relevant history — but we are blind to **what actually happened inside a delegation**:

- Helper LLM inputs/outputs not logged (BL-353) → can't debug context quality
- `model_roles.*.tokens` often null (BL-335) → can't measure cost or credit attribution
- Reasoning traces (`thinking` blocks) captured by nobody → high-value signal discarded
- No session memory of what a delegate reasoned about → builder must start cold each time
- If we want to know "do we need escalation?", "is the loop thrashing?", "what's worth RAG-indexing?" — we have no signal

The fix is a **central observability layer** designed as a POC/MVP for the `AGENTIC_LOOP_LOGGING` separate product: semi-autonomous code, extractable, swappable, training-data ready.

---

## What Phase 6 is NOT

This is *not* a log aggregation product, a new UI, or a full agentic loop debugger. It is the **substrate** that makes those things possible:

- Refactor scatter → clean seam (P6-001)
- Fix token accounting (P6-002)
- Wire LLM boundary logging (P6-002/003)
- Capture + reuse reasoning tokens (P6-004)
- Training-data schema foundations (P6-005, optional)

---

## Phase 6 one-line goal

> Replace scattered logging calls with a clean `ObservabilityBackend` adapter, then build live tokens + trace files + reasoning hot buffer on top.

---

## Milestones locked

| Milestone | One-line | Exit tier |
|-----------|----------|-----------|
| P6-001 | `core/observability/` adapter seam; consolidate all logging; no behavior change | **Prerequisite for all** |
| P6-002 | LiteLLM `success_callback` + BL-335 live token fix; first new capability | **Minimum exit** |
| P6-003 | Per-delegation trace files at verbosity tiers; helper I/O captured | Recommended |
| P6-004 | `reasoning_content` capture + session hot buffer → builder brief injection | Recommended |
| P6-005 | Training opt-in schema; maintenance stats CLI; summarization policy stub | Optional capstone |

Minimum exit: P6-001 + P6-002.  
Recommended exit: P6-001 through P6-004.

---

## Locked design decisions (D-P6-1 through D-P6-7)

| ID | Decision |
|----|----------|
| D-P6-1 | `ObservabilityBackend` abstract interface in `core/observability/base.py`; local implementation `core/observability/local.py`. This is the adapter seam for future product extraction. |
| D-P6-2 | LiteLLM Route A (`litellm.success_callback` at MCP startup) is the primary capture mechanism. Backend-neutral; covers all LiteLLM-routed roles. No Aider patching for non-reasoning executor turns. |
| D-P6-3 | Trace files are **separate** from `delegations.jsonl`. Canonical JSONL stays lean; trace files hold bodies. Path: `~/.mcp-coder/projects/<key>/sessions/<id>/traces/<delegation_id>.jsonl`. |
| D-P6-4 | Three verbosity tiers: `lean` (hashes + counts), `standard` (summaries + truncated I/O, **default**), `full` (all bodies + reasoning verbatim). Config key `observability_verbosity`. |
| D-P6-5 | Hot buffer = in-memory session dict `{delegation_id: reasoning_summary}`. Optional N-row persistence in `workspace_history.db`. TTL = session by default, configurable. |
| D-P6-6 | Training capture is opt-in: `capture_for_training: false` default. When on: `(task, context_hash, reasoning_summary, outcome, verify_result)` + version tags (git SHA, model IDs, pipeline flags, config fingerprint) written to `traces/<delegation_id>-training.json`. Schema version-tagged for AGENTIC_LOOP_LOGGING ingestion. |
| D-P6-7 | P6-001 is **refactor only** — no behavior changes. All existing tests pass. Seam is validated by `NullObservability` swap-in in new unit tests. |

---

## Current logging surface (P6-001 scope)

Workers implementing P6-001 must consolidate all of these behind `ObservabilityBackend`:

| Module | Public surface | Call sites |
|--------|---------------|------------|
| `core/logging/delegation_log.py` | `build_delegation_record`, `append_delegation_record`, `log_host_resolved`, `log_delegation_received`, `log_delegation_sent`, verbosity helpers | `server/mcp_server.py` (primary consumer) |
| `core/logging/server_log.py` | `ServerLog` singleton, `server_log_emit`, `server_log_warn`, `resolve_config` | `server/mcp_server.py` |
| `core/pipeline/phases.py` | `PipelinePhase`, `PipelineRecorder` | `server/mcp_server.py` |
| `core/usage/telemetry.py` | `UsageReport`, `build_usage_report`, `format_usage_run_log_line`, `build_usage_warnings` | `server/mcp_server.py` |
| `core/usage/litellm_tokens.py` | `extract_litellm_model_tokens` | `server/mcp_server.py` (BL-335: not reaching live path) |
| `core/usage/role_audit.py` | `build_role_usage_record`, `merge_model_roles` | `server/mcp_server.py` |
| `core/usage/aider_tokens.py` | `extract_aider_tokens` (returns None — Aider scrape path) | `server/mcp_server.py` |
| `core/usage/rates.py` | Cost rate table | `telemetry.py` |
| `core/usage/policy.py` | Preflight warnings | `server/mcp_server.py` |

`mcp_server.py` has ~18 direct calls into this surface. After P6-001, it calls `obs.*` only.

---

## Confusion traps for Phase 6 workers

1. **Refactor first, add later.** P6-001 = no new behavior. If a PR includes new features alongside the seam, reject and split.
2. **LiteLLM callback only for LiteLLM-routed calls.** Aider executor (direct API) is captured differently. Don't over-scope the callback.
3. **Trace files ≠ `delegations.jsonl`.** The canonical JSONL stays unchanged and lean. Trace files are additive, separate storage.
4. **Hot buffer ≠ RAG.** Hot buffer = ephemeral in-memory session context. It does not go into `delegation_rag.db`. If you want cross-session reasoning reuse, that's BL-333 Phase 6+ scope — not P6-004.
5. **`ObservabilityBackend` is an interface, not a God object.** Methods should be small and focused. If a method needs 15 parameters, it's probably two methods.
6. **Token fix (BL-335) is P6-002, not P6-001.** P6-001 is purely structural. BL-335 needs the LiteLLM callback to land correctly.
7. **Phase 6 is NOT Phase 7.** Supervised loop control, escalation hooks, mid-loop injections — those require the observability substrate to exist first. Phase 6 captures data; Phase 7 acts on it.
8. **Training flag off by default.** Never flip `capture_for_training: true` in production config or tests. It writes extra files and is by design user-opt-in.
9. **`core/observability/` is semi-autonomous.** It should have no imports from `server/` or `core/engine/aider_engine.py`. The dependency arrow is inward only. This makes it extractable.

---

## Open questions deferred

| Q | Deferred to |
|---|-------------|
| Embeddings on trace files (semantic search) | AGENTIC_LOOP_LOGGING separate product |
| Escalation hook (act on reasoning signal) | Phase 7 / BL-350 |
| Summarization + GC policy (enforcement) | Full BL-357 |
| Cross-session reasoning persistence | BL-333 Phase 6+ after hot buffer proven |
| Community dataset schema / open-source extract | After Phase 6 substrate validated |
| FTS recall metrics for RAG | P5-005 / BL-366 |

---

## Worker rules (enforce when dispatching P6-* workers)

- Single source of truth: attached `docs/tasks/P6-<NNN>-<name>-v1.md` only (gitignored)
- Fill `§ Results` in spec; propose PM changes under **§ Results → Suggested for master session**
- Do NOT edit IDEA, PHASES, PHASE*_MVP, BACKLOG, PHASE*_ISSUES, VISION_DOCS unless task spec explicitly lists them
- No Aider API terms (`fnames`, `yes=True`, `Coder`) in `core/observability/` — backend-neutral rule
- `core/observability/` must have no imports from `server/` or `core/engine/aider_engine.py` (extractability constraint)
- Worker specs: `docs/tasks/P6-NNN-name-v1.md`

---

## Phase 5 exit (frozen reference)

Phase 5 closed 2026-06-13 (recommended exit). RAG retrieval defaults on. Open carries: **BL-335** (tokens), **BL-364** (validation blocks rag_retrieval). See [phase5-master-session-bootstrap.md](./phase5-master-session-bootstrap.md).
