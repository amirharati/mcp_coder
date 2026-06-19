# Terminology

Short glossary of terms used across mcp-coder docs, code, and JSONL logs. When a word is ambiguous in the wider LLM-tooling world, this is what *we* mean by it.

For the full mental model see [how-it-works.md](./how-it-works.md); for the module map see [code-structure.md](./code-structure.md).

---

## Actors & layers

| Term | Meaning |
|------|---------|
| **Host** | The agent/UI the user talks to that calls our MCP tools. *Today:* Cursor. Sits behind a host adapter (`core/host/`, `HostContextProvider`) — **not locked in**; other hosts are expected. |
| **Planner** | The host agent acting in its planning role: writes specs, decides what to delegate, judges results. Stays high-level. |
| **Backend / Engine** | The thing that actually edits files. *Today:* Aider + an LLM provider. Sits behind `core/engine/` (`ExecutionEngine`, `factory.py`) — **not locked in** (see BL-340 for a Cursor-SDK backend). |
| **Executor** | The backend in its edit-running role — the model + loop that produces file edits for a delegation. |
| **Helper LLM** | A supporting model call that is *not* the executor: spec validation, builder brief, architect pass, review. Routed by **role** (§ Models below). "Helper" ≠ "cheap" — model choice per role is a tuning decision. |
| **Adapter** | The seam that keeps `core/` neutral. Host adapter and engine adapter let us swap Cursor/Aider without touching pipeline logic. |

## The work

| Term | Meaning |
|------|---------|
| **Delegation** | One `delegate_to_agent` call and everything it produces. The atomic unit of work. Has a `delegation_id`. |
| **Mode** | `implement` (executor edits files; full pipeline) or `review` (LLM answers questions, no edits, `target_files` must be empty). |
| **Pipeline** | The ordered phases a delegation runs through (`spec_read → … → auto_verify`). Recorded as `delegation_pipeline` with per-phase status + timing. |
| **Phase** | One named step in the pipeline. Status is `ok | skipped | error | blocked`. |
| **Outcome** | Result label: `success`, `partial`, `needs_input`, `error`. Distinct from the boolean `success` — e.g. applied edits + failing verify ⇒ `partial`. |
| **Blocked** | Spec validation found real ambiguity → executor never runs, planner gets `needs_input` + `clarification_needed`. |

## Spec & contract

| Term | Meaning |
|------|---------|
| **Spec / task spec** | A markdown file under `.mcp-coder/specs/tasks/` defining one step: front-matter + `## Goal / ## Files / ## Constraints / ## Done when`. The contract for a delegation. |
| **Epic** | A multi-step parent spec under `.mcp-coder/specs/epics/`; individual task specs link to it via `epic:` front-matter. |
| **Files contract** | The `## Files` section (`files_edit` / `files_read`). Defines what *may* be edited; enforced after the fact by the gateway. |
| **`auto_merge_spec_read`** | **Code/config name — misleading.** Means “append spec Read paths to the executor file list”, not git merge. Guide docs call this **auto-adding read deps**. JSONL field: `auto_merged_read_paths`. Rename in code/config deferred; see T-03 §5. |
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
| **Architect plan** | Optional `## Architect plan` prepended by the architect-pass LLM (plan/brainstorm step). |
| **`context_summary`** | The planner's own words — chat decisions the executor can't otherwise see. A required `delegate_to_agent` arg. |
| **`target_files`** | Repo-relative paths the planner passes on `delegate_to_agent`. For implement + spec: should list edit paths; read paths should be listed too — or mcp-coder may auto-add reads when `auto_merge_spec_read` is on. |
| **inspect-context** | Dry-run that builds the would-be prompt with no backend call. CLI (`mcp-coder inspect-context`) or `inspect_context` MCP tool. |

## Models & roles

| Term | Meaning |
|------|---------|
| **Role** | A named slot a model is assigned to: `executor`, `context_builder`, `review`, `critic`. Each independently configurable; precedence default → env → yaml. |
| **`model_roles`** | JSONL block auditing each role's model, tokens, duration, cost estimate for a delegation. |
| **Cost estimate** | `cost_est_usd` computed from static `resources/model_rates.yaml` × token counts (not a billed figure). |

## Memory & storage

| Term | Meaning |
|------|---------|
| **Session** | A group of delegations under one `mcp_session_id`. Caches an executor instance for reuse. |
| **Session policy** | How a delegation maps to a session: `always_new` or `align_host` (try to match the host's chat). |
| **Project key** | `sha256` of the resolved workspace path; names the per-project dir under `~/.mcp-coder/projects/`. |
| **Workspace history** | `workspace_history.db` (SQLite) — per-file hashes, checkpoints, diffs. The "what changed" truth, git-independent. |
| **Snapshot** | SHA-256 manifest of the workspace taken before/after the executor; diffed to compute `files_changed`. |
| **Checkpoint** | A recorded delegation point in workspace history (inspectable via `get_checkpoint_detail`). |
| **Delegation log** | `delegations.jsonl` — one record per delegation, the canonical audit trail. |
| **RAG index (delegations)** | `delegation_rag.db` (FTS5) over past delegations. Auto-indexed each delegate; searched by planner (`rag_search`) and **builder** (`rag_retrieval`, default on). |
| **`workspace_rag.db`** | FTS5 index of per-file LLM summaries. Built by `mcp-coder index-workspace`; searched by `workspace_search` / builder file hints. |
| **`rag_retrieval`** | Pipeline phase (after `file_picker`, before `context_assemble`): FTS over delegations + workspace files; merges hits into brief + `context_refs[]`. |
| **`context_refs[]`** | Top-level JSONL list of retrieval hits (source, id, snippet, score) for audit — delegation + workspace-file corpora. |
| **`prior_failed_attempts`** | Past failures on the same spec, surfaced into the next delegation's response so the planner can adjust. |

## Verification & trust

| Term | Meaning |
|------|---------|
| **Gateway** | Post-delegation check comparing `files_changed` to the Files contract; flags out-of-scope edits. |
| **`files_changed` / `files_unexpected`** | Files actually created/modified/deleted (from snapshots) vs those outside the contract. |
| **Judgment checklist** | Structured checklist in the response so the *planner* makes the final call. mcp-coder informs; planner decides. |
| **Auto-verify** | Opt-in post-delegate command (e.g. `pytest -q`); runs only after a successful executor pass; failure downgrades `success → partial`. |

## Config flags (quick ref)

Precedence everywhere: **default → env → `.mcp-coder/config.yaml`** (yaml wins).

| Flag | Default | Effect |
|------|---------|--------|
| `context_builder` | on | file picker + repo map |
| `context_builder_llm` | on | builder LLM narrative brief |
| `spec_validation` | off | pre-delegate coherence check (can block) |
| `planner_pass` | off | planner plan in brief (was: `architect_pass`, deprecated) |
| `auto_verify` | off | post-delegate verify command |
| `auto_merge_spec_read` | on | append spec Read paths to executor file list (list union — not git merge) |
| `host_transcript` | off | dump host transcript tail for helper LLMs |
| `builder_history_rag` | on | cross-spec delegation RAG in builder |
| `workspace_file_rag` | on | workspace-file corpus + search |
| `workspace_file_hints` | on | file-summary hints in picker/builder |

## Conventions in docs/code

| Term | Meaning |
|------|---------|
| **D-Pn-m** | A locked design decision from phase *n* (e.g. `D-P4-10`). Cited inline where enforced. |
| **BL-nnn** | A backlog item ([../BACKLOG.md](../BACKLOG.md)). |
| **P*n*-ISS-mm** | A phase issue ([../PHASE*_ISSUES.md](../)). |
| **Backend-neutral** | Code that must not mention Aider/provider specifics. Everything in `core/` except `core/engine/aider_engine.py` and `core/config/aider_runtime.py`. |
