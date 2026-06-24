# Terminology

Short glossary of terms used across mcp-coder docs, code, and JSONL logs. When a word is ambiguous in the wider LLM-tooling world, this is what *we* mean by it.

For the operator mental model see [how-it-works.md](./how-it-works.md); for modules and paths see [code-structure.md](./code-structure.md). For refined design decisions see [../notes/system-design-overview.md](../notes/system-design-overview.md).

**Last updated:** 2026-06-23 (Phases 1–13 shipped vocabulary).

---

## Actors & layers

| Term | Meaning |
|------|---------|
| **Host** | The agent/UI the user talks to that calls our MCP tools. *Today:* Cursor. Sits behind a host adapter (`core/host/`, `HostContextProvider`) — **not locked in**; other hosts are expected. Relays user intent; does **not** own mcp-coder project memory. |
| **SupervisorAgent** | mcp-coder's persistent project workflow agent (`core/engine/supervisor_agent.py`). Owns post-planning delegation lifecycle, pause/resume, project-state writes, subagent/tool routing, and checkpoint persistence. Reached by the host through `delegate_to_agent`. |
| **Planner** | Task-level planning helper inside mcp-coder — *not* the host. Produces an implementation plan prepended to the executor brief (`planner_pass`). May read `project_state.json`. |
| **Executor** | The backend in its edit-running role — the model + loop that produces file edits for a delegation. *Today:* Aider via `core/engine/aider_engine.py`. |
| **Reviewer** | Post-execution quality helper (`reviewer_pass`). Returns findings; Supervisor decides what persists into project state. |
| **Helper / subagent / worker** | A scoped component the Supervisor coordinates: clarity check, spec validation, planner, builder, reviewer, executor, future specialists. Usually stateless per call; context is injected per invocation. |
| **Architect** | Deferred future role (epic/CTO scope). **Not** the same as `planner_pass` or legacy `architect_pass` naming. |
| **Backend / Engine** | Execution backend abstraction (`core/engine/`, `ExecutionEngine`). *Today:* Aider. |
| **Adapter** | The seam that keeps `core/` neutral. Host adapter and engine adapter let us swap Cursor/Aider without touching pipeline logic. |

## The work

| Term | Meaning |
|------|---------|
| **Delegation** | One `delegate_to_agent` call and everything it produces. The atomic unit of work. Has a `delegation_id`. |
| **Mode** | `implement` (executor edits files; full pipeline) or `review` (LLM answers questions, no edits, `target_files` must be empty). |
| **Pipeline** | Ordered pre-executor and post-executor phases (`spec_read → … → auto_verify`). Recorded as `delegation_pipeline` with per-phase status + timing. |
| **Lifecycle envelope** | Agent-owned trace wrapper for a delegation: `delegation_lifecycle_start/end` plus `phase_start/end` for `preloop`, `loop`, `postloop`. Emitted by `SupervisorAgent`. |
| **Phase** | One named pipeline step **or** one lifecycle slice (`preloop` / `loop` / `postloop`). Pipeline phase status: `ok \| skipped \| error \| blocked`. |
| **Outcome** | Result label: `success`, `partial`, `needs_input`, `error`. Distinct from the boolean `success` — e.g. applied edits + failing verify ⇒ `partial`. |
| **Blocked** | A pre-executor gate (clarity or spec validation) found real ambiguity → executor may not run; host gets `needs_input` + questions. |
| **Paused** | Supervisor stopped mid-delegation for host input or clarity-block re-entry. Returns `resume_token`; resume skips completed stages where policy allows. |

## Supervisor & persistent state

| Term | Meaning |
|------|---------|
| **Project state** | Durable cross-delegation memory at `~/.mcp-coder/projects/<key>/project_state.json` — decisions, risks, hot areas, reviewer finding summaries. Owned by Supervisor writes; helpers return data, Supervisor persists. |
| **AgentCheckpoint** | Non-expiring steady-state snapshot at `agent_state.json` per project. Saved at delegation end; rehydrates Supervisor across process restarts (CLI ≡ server). |
| **SupervisorState** | Expiring in-flight pause state under `supervisor_states/<resume_token>.json` — turn index, plan, decision log, questions, completed turns. Used for pause/resume within/across host round-trips. |
| **`resume_token`** | Opaque id returned when a delegation pauses. Pass on the next `delegate_to_agent` to resume without cold-restarting completed work. |
| **Tier-1 / tier-2 context** | Supervisor context model: slow baseline context refreshed at turn/delegation boundaries (tier 1) vs on-demand tool-pulled context mid-decision (tier 2). |
| **`SupervisorToolRunner`** | Multi-turn tool loop for Supervisor internal decisions (`get_project_state`, `read_file`, `get_diff`, etc.). |
| **`SupervisedIO`** | Routes executor `confirm_ask` to the Supervisor LLM for approve/deny/abort/escalate — finer granularity than inter-turn lifecycle decisions. |
| **`DelegationSupervisor`** | Legacy name for the confirm-ask interception LLM path in `core/engine/supervisor.py`; distinct from `SupervisorAgent` lifecycle ownership. |

## Spec & contract

| Term | Meaning |
|------|---------|
| **Spec / task spec** | A markdown file under `.mcp-coder/specs/tasks/` defining one step: front-matter + `## Goal / ## Files / ## Constraints / ## Done when`. The contract for a delegation. |
| **Epic** | A multi-step parent spec under `.mcp-coder/specs/epics/`; individual task specs link to it via `epic:` front-matter. |
| **Files contract** | The `## Files` section (`files_edit` / `files_read`). Defines what *may* be edited; enforced after the fact by the gateway. |
| **`auto_merge_spec_read`** | **Code/config name — misleading.** Means “append spec Read paths to the executor file list”, not git merge. Guide docs call this **auto-adding read deps**. JSONL field: `auto_merged_read_paths`. |
| **`effective_target_files`** | The file list actually passed to the executor after read-dep auto-add (if any). Planner's original list is preserved as `mcp_request.target_files` in JSONL. |
| **Report** | Audit section mcp-coder appends to `.mcp-coder/specs/reports/<spec-name>.md` after a delegation. |

## Context compiling

| Term | Meaning |
|------|---------|
| **ContextPackage** | The structured object (`core/context/package.py`) holding everything assembled for the executor: entries, tiers, budget, brief. |
| **Tier** | Fidelity level a file enters the package at: full payload → read-only payload → excerpt → map-only (outline). Budget trims from the bottom. |
| **(File) Picker** | Rules-based candidate selection: spec paths + ripgrep symbol scan + repo map → ranked `CandidateFilesResult`. Discovers context; **never grants edit rights**. |
| **Repo map** | def/class outline of workspace files (`TIER_MAP_ONLY`), cheap structural awareness without full payloads. |
| **Mechanical brief** | The authoritative, code-generated brief (paths + tiers). No LLM ever rewrites it. |
| **Builder brief** | Optional narrative prepended *above* the mechanical brief by the builder LLM. Annotates, doesn't replace. |
| **Planner plan** | Optional `## Planner plan` (or legacy `## Architect plan` in older traces) prepended by `planner_pass`. Legacy code/env may still say `architect_pass`. |
| **`context_summary`** | The host/planner's own words — chat decisions the executor can't otherwise see. A required `delegate_to_agent` arg. |
| **`target_files`** | Repo-relative paths passed on `delegate_to_agent`. For implement + spec: should list edit paths; read paths should be listed too — or mcp-coder may auto-add reads when `auto_merge_spec_read` is on. |
| **inspect-context** | Dry-run that builds the would-be prompt with no backend call. CLI (`mcp-coder inspect-context`) or `inspect_context` MCP tool. |

## Models & roles

| Term | Meaning |
|------|---------|
| **Role** | Named slot for model resolution: `executor`, `context_builder`, `planner_pass`, `supervisor`, `reviewer_pass`, `clarity_check`, `spec_validation`, `review`, `critic`. Precedence: host `model_policy` → env → yaml → registry default. |
| **`model_policy`** | Per-delegation host override for role models and generation params (Phase 9+). Resolved via `core/config/model_registry.py`. |
| **`model_roles`** | JSONL block auditing each role's model, tokens, duration, cost estimate for a delegation. |
| **`policy_applied`** | Trace event field showing which model/params were resolved for an LLM call. |
| **Cost estimate** | `cost_est_usd` computed from static `resources/model_rates.yaml` × token counts (not a billed figure). |

## Memory & storage

| Term | Meaning |
|------|---------|
| **Session** | A group of delegations under one `mcp_session_id`. Caches an executor instance for reuse. |
| **Session policy** | How a delegation maps to a session: `always_new` or `align_host` (try to match the host's chat). |
| **Project key** | `sha256` of the resolved workspace path; names the per-project dir under `~/.mcp-coder/projects/`. |
| **Workspace history** | `workspace_history.db` (SQLite) — per-file hashes, delegation checkpoints, diffs. Git-independent change truth. |
| **Snapshot** | SHA-256 manifest of the workspace taken before/after the executor; diffed to compute `files_changed`. |
| **Checkpoint (workspace)** | A recorded delegation point in workspace history (inspectable via `get_checkpoint_detail`). Distinct from **AgentCheckpoint**. |
| **Delegation log** | `delegations.jsonl` — one lean record per delegation, canonical audit row. |
| **Trace** | `traces/<delegation_id>.jsonl` — full event stream (compile, LLM, supervisor, proxy, tool calls). |
| **RAG index (delegations)** | `delegation_rag.db` (FTS5) over past delegations. Auto-indexed each delegate. |
| **`workspace_rag.db`** | FTS5 index of per-file LLM summaries. Built by `mcp-coder index-workspace`. |
| **`rag_retrieval`** | Pipeline phase: FTS over delegations + workspace files → brief section + `context_refs[]`. |
| **`context_refs[]`** | JSONL list of retrieval hits (source, id, snippet, score) for audit. |
| **`prior_failed_attempts`** | Past failures on the same spec surfaced into the next delegation response. |

## Observability & traces

| Term | Meaning |
|------|---------|
| **`ObservabilityBackend`** | Seam for trace emission (`core/observability/`). `LocalObservability` writes JSONL traces; `NullObservability` for tests. |
| **`llm_call` / `backend_llm_call`** | Trace events for helper vs executor-backend LLM traffic. |
| **`proxy_llm_call`** | Raw provider traffic captured via local HTTP proxy (Phase 9). |
| **`compile_event`** | Context compiler / pipeline stage visibility in traces. |
| **`view_events[]`** | Viewer-facing event list produced by `core/cli/delegation_view_enrich.py` from raw trace + delegation records. |
| **`supervisor_decision`** | Per-turn Supervisor action: `rerun_aider`, `done`, or `escalate_host`. |
| **`supervisor_paused` / `supervisor_resumed`** | Pause/resume lifecycle markers (clarity-block vs escalation paths differ). |

## Verification & trust

| Term | Meaning |
|------|---------|
| **Gateway** | Post-delegation check comparing `files_changed` to the Files contract; flags out-of-scope edits. |
| **`files_changed` / `files_unexpected`** | Files actually created/modified/deleted (from snapshots) vs those outside the contract. |
| **Judgment checklist** | Structured checklist in the response so the *host/planner* makes the final call. mcp-coder informs; host decides. |
| **Auto-verify** | Opt-in post-delegate command (e.g. `pytest -q`); runs only after a successful executor pass; failure downgrades `success → partial`. |

## Config flags (quick ref)

Precedence everywhere: **default → env → `.mcp-coder/config.yaml`** (yaml wins unless host `model_policy` overrides models).

| Flag | Default | Effect |
|------|---------|--------|
| `context_builder` | on | file picker + repo map |
| `context_builder_llm` | on | builder LLM narrative brief |
| `spec_validation` | on | pre-delegate coherence check (can block) |
| `clarity_pass` | on | pre-delegate task clarity check (can block / pause) |
| `planner_pass` | on | planner plan in brief (legacy alias: `architect_pass`) |
| `reviewer_pass` | on | post-execution reviewer scan |
| `auto_verify` | off | post-delegate verify command |
| `auto_merge_spec_read` | on | append spec Read paths to executor file list |
| `host_transcript` | off | dump host transcript tail for helper LLMs |
| `builder_history_rag` | on | cross-spec delegation RAG in builder |
| `workspace_file_rag` | on | workspace-file corpus + search |
| `workspace_file_hints` | on | file-summary hints in picker/builder |
| `supervisor_max_turns` | 1 | max Supervisor loop turns (`MCP_CODER_SUPERVISOR_MAX_TURNS`) |

## Conventions in docs/code

| Term | Meaning |
|------|---------|
| **D-Pn-m / D-ARCH-n** | Locked design decision from phase *n* or architecture note. |
| **BL-nnn** | A backlog item ([../BACKLOG.md](../BACKLOG.md)). |
| **P*n*-ISS-mm** | A phase issue ([../PHASE*_ISSUES.md](../)). |
| **Backend-neutral** | Code that must not mention Aider/provider specifics. Everything in `core/` except `core/engine/aider_engine.py` and `core/config/aider_runtime.py`. |
| **Vision vs notes** | [IDEA.md](../IDEA.md) = product vision/brainstorming; `docs/notes/` = refined design grounded in shipped reality. |
