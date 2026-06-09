<!--
  STEWARDSHIP — Tier 2 backlog. See docs/VISION_DOCS.md.

  - OK: add BL-* rows, status, links; reprioritize with user or P1-199.
  - NOT OK: delete items silently or contradict IDEA.md vision.
  - Workers: do not edit; propose new BL-* in task § Results for planning session.
-->

# Project backlog

Items deferred from active phases, future ideas, and nice-to-haves. **Not** scheduled for the current worker session unless pulled into [PHASE1_MVP.md](./PHASE1_MVP.md). **Vision:** [IDEA.md](./IDEA.md) · [VISION_DOCS.md](./VISION_DOCS.md).

Status: `idea` | `deferred` | `blocked` | `done`

---

## Deferred from Phase 1 (by design → later phases)

| ID | Item | Target | Notes |
|----|------|--------|-------|
| BL-001 | Owned context pipeline (summarize, rank, trim) | Phase 2 | Phase 1 is pass-through only |
| BL-002 | RAG / cross-session memory (`rag_search`, SQLite) | Phase 3 | See [IDEA.md](./IDEA.md) data models |
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
| BL-106 | MCP progress notifications for long Aider runs | Avoid Cursor timeout perception |
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
| BL-162 | **Multi-model routing** | Different models per role: cheap for context build / cleanup / topic ID; expensive for execution. Likely **needed early** for Phase 2 owned context — track explicitly even if first ship is one cheap + one executor model. | BL-007 ensemble (Phase 4+); env already has `AIDER_MODEL` / OpenRouter |

### Interactive sessions (BL-160) — options to try later

**Not required for Phase 2.** Cursor stays the planner; you already pass files + context; mcp-coder **reports back when done**. “Interactive” here means **supervision + visibility**, not duplicating Cursor chat in the terminal.

| ID | Option | What | Notes |
|----|--------|------|--------|
| BL-160a | **Supervised complex task** | One MCP call; mcp-coder helps Aider finish a **multi-step** job (internal steps, retries, optional human OK between steps). User does **not** need to chat in Cursor for each micro-step. | Overlaps **BL-161**; lighter than full REPL |
| BL-160b | **Live terminal visibility** | While delegate runs (even “non-interactive”), **tee** Aider command/edit stream to stderr file or terminal tail for **quick review** — without breaking MCP stdout (JSON-only). Today: brief stderr + captured output in tool result only. | `stdio_isolation` blocks raw stdout to Cursor |
| BL-160c | **Handoff to real terminal** | MCP prepares context + opens / prints a command; user continues in **real terminal** with native Aider REPL if they want deep hands-on. | Pairs with **BL-005** CLI |
| BL-160d | **Full interactive via CLI** | `mcp-coder session` — same core as MCP, no Cursor transport; multi-turn chat with executor in terminal. | Lowest priority of the four |

**Default product story (when we pick this up):** BL-160a + BL-160b first; BL-160c/d only if needed.

**Related:** [IDEA.md](./IDEA.md) § interactive mode; P1-100 `InputOutput(yes=True)`; **BL-501** async if runs exceed MCP timeout.

**Notes (2026-06 planning):**

- **BL-161** is not “multiple MCP servers” — one server, multiple **internal** agent steps before/after Aider (could be rules-only v0, LLM planner v1).
- **BL-162** may land partly in Phase 2 (context-builder model ≠ executor model); full ensemble voting stays later (BL-007).

---

## Host & integration

| ID | Item | Notes |
|----|------|-------|
| BL-201 | Claude Desktop host adapter | **Low priority** — after Cursor + owned context |
| BL-202 | Windsurf / other IDEs | **Low priority** |
| BL-203 | ~~Read Cursor agent-transcripts~~ | **done** — P1-120 metadata + P1-140 opt-in dump |
| BL-204 | Proxy intercept: save latest Cursor prompt from `context_optimizer_proxy` | Personal workflow |
| BL-205 | Cursor rule / skill snippet for routing to `delegate_to_agent` | Improve auto-routing |

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

**Status:** `deferred` — **P1-ISS-013** (`wontfix-p1` at Phase 1 exit).

**Goal:** Make the split between **MCP run succeeded** and **step acceptance met** visible in reports and tool responses.

| Sub | Item |
|-----|------|
| BL-310a | Report status `verified_ok` (planner sets?) vs MCP `delegated_ok` / `reviewed` / `blocked` |
| BL-310b | Optional MCP hook: run `pytest` (configurable command) post-implement before `delegated_ok` |
| BL-310c | `outcome: partial` when edits applied but tests fail (if hook enabled) |

**Today:** Planner runs `pytest` in Cursor; strict rules forbid marking task `done` without verify ([PHASE1_MVP.md](./PHASE1_MVP.md) D-SPEC-3).

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

### BL-320: Failed-delegate attempt archive (spec-adjacent)

**Status:** `scheduled` — Phase 3 Wave 2 ([PHASE3_MVP.md](./PHASE3_MVP.md)); P3-ISS-002.

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

### BL-321: Progressive / tiered executor model selection

**Status:** `scheduled` — Phase 3 optional ([PHASE3_MVP.md](./PHASE3_MVP.md) P3-321); P3-ISS-004.

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

## Very low priority — other execution engines

| ID | Item | Notes |
|----|------|-------|
| BL-004 | **OpenCode adapter** (subprocess) | **Deferred indefinitely** — Aider-only until product is useful; adapter interface exists (`core/engine/`) if ever needed |
| — | Claude Code / Codex CLI adapters | Same tier as BL-004 — not on roadmap until explicit need |

---

## Ideas (unscoped)

| ID | Item |
|----|------|
| BL-501 | Job ID + async delegation (poll / MCP notification) for long Aider runs |
| BL-502 | Git worktree / task-branch per delegation — git-native audit trail + rollback (pairs with BL-322; alternative to BL-322h fork for git repos) |
| BL-503 | Grade executor output with cheap model before returning to Cursor |
| BL-504 | Global `~/.mcp-coder/config.yaml` defaults | Per-repo `config.yaml` shipped P1-130 |
| BL-506 | Generic `transcript.md` watch folder (non-Cursor hosts) |

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

## Changelog

| Date | Change |
|------|--------|
| 2026-06-08 | BL-322a–f done; BL-322g/h deferred (restore + fork/sandbox); BL-502 cross-link |
| 2026-06-08 | Phase 3 start — BL-320/322 `scheduled`; BL-323 budget override; BL-322a storage aligned to WORKSPACE_HISTORY |
| 2026-06-07 | Wild test done — BL-320 failed-attempt archive; BL-321 tiered model selection (P2-ISS-007/008) |
| 2026-06-07 | BL-322 workspace hash snapshot + post-delegation gateway — Phase 3 design (chat [Phase 2 tail review](d44a5b15-2ed4-4834-bc91-91f776e5dd02)) |
| 2026-06-06 | P2-120 done — usage telemetry; BL-319 dynamic rates deferred; BL-154 partial |
| 2026-06-06 | P1-199 exit — Post–Phase 1 focus reordered; BL-314 partial, BL-315–318 added; P1 issues migrated |
| 2026-06-05 | BL-309–312 from expense-splitter E2E; BL-150 done |
