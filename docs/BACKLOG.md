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
| BL-002 | RAG / cross-session memory (`rag_search`, SQLite) | **Phase 5** | Delegation RAG shipped (P3-002-lite); workspace-file RAG + usage → Phase 5 (after Phase 4 context builder reveals real retrieval needs); see § BL-002 |
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
| BL-162 | **Multi-model routing** | Different models per role: cheap for context build / cleanup / topic ID; expensive for execution. **Stage 1 (Phase 4, D-P4-8):** one configurable model per role (executor/review/context builder), each audited with cost. **Stage 2+:** multiple models within a role — tiered escalation (BL-321), critic redo (BL-006), failed-attempt-aware upgrade (P4-008 data), swarm/ensemble (BL-007). See [notes/multi-model-roles.md](./notes/multi-model-roles.md). | BL-007 ensemble; BL-321 escalation; BL-006 critic; env has `AIDER_MODEL` / OpenRouter |
| BL-329 | **Pre-delegate spec validation + clarifying loop** | Builder reads host transcript, checks spec coherence vs session context before delegating; returns `clarification_needed: [...]` if ambiguous. | P4-009 (Wave 4 optional); pairs with BL-161 (pre+post Aider pipeline) and BL-324 (post-delegation judgment loop) |

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
- **BL-162** may land partly in Phase 2 (context-builder model ≠ executor model); full ensemble voting stays later (BL-007). **Stage 1 = one model per role (D-P4-8); Stage 2 = escalation/critic; Stage 3 = swarm.** Full staging in [notes/multi-model-roles.md](./notes/multi-model-roles.md).

---

### BL-329: Pre-delegate spec validation + clarifying loop

**Status:** `idea` — Phase 4 master session 2026-06-09.  
**Target:** Phase 4 Wave 4 optional (P4-009); may defer to Phase 5 if Wave 2 builder proves sufficient.

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

**Status:** `partial` — **delegation RAG shipped** (P3-002-lite, 2026-06-09); workspace-file RAG + usage decisions → **Phase 5**.  
**Code in place:** `core/rag/` (db.py, index.py, search.py, models.py), `core/config/rag.py`, `core/cli/rag.py`; 431 pytest. Enabled by default; opt-out via `rag_enabled: false`.  
**Phase 5 (after Phase 4 context builder):** Phase 4 will reveal which retrieval problems are real and what query shapes the builder needs. Phase 5 then designs + builds the right RAG layer (workspace-file summaries primary; delegation search revise/extend based on actual use; embeddings only if FTS recall proves insufficient).

#### Corpus decisions

| Corpus | Phase | Approach | Rationale |
|--------|-------|----------|-----------|
| **Workspace source files** | **4 — primary** | Hash (SHA-256) + LLM-generated summary per file + FTS5 | Core use case: planner asks "what does this file do?" / "which files are relevant?" before delegating. Hash-based staleness = re-index only on change. File-level granularity is enough for planning; sub-file chunking is overkill. |
| **Delegation records** | 4+ | Wave 1 inspect tools now; FTS5 when scale hurts | `list_delegations` + `get_checkpoint_detail` sufficient at <200 rows. Add keyword search when pain is felt. |
| **Decision log** | 5 | Structured exit notes → FTS5 | Session-end host writes 3–5 key decisions + deferred items. Higher signal than raw chat. |
| **Spec files** | Skip | Grep / direct read | Too small to index (~5–50 files). |
| **Chat transcripts** | Skip | N/A | Rejected ideas and accepted ideas indistinguishable without outcome labels. Good decisions already land in specs/docs. If distillation shows a gap, revisit then — not proactively. |
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

#### Phase 5 plan
Phase 5 = RAG master session after Phase 4 context builder ships. Agenda: what retrieval did Phase 4 actually need? Finalize: indexing trigger (snapshot hook vs on-demand), summary prompt, symbol extraction strategy, DB schema, MCP tool signature. Then implement as first Phase 5 milestone.

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
| 2026-06-09 | BL-310 partial — P4-010 verify loop (310b/c done; 310a deferred) |
| 2026-06-09 | BL-332 added — host-agnostic planner rules sync (deferred; Cursor-coupled today, compile engine reusable) |
| 2026-06-09 | BL-331 added — symbol-scoped/chunked edit files (Phase 5+, executor format change) |
| 2026-06-09 | BL-162 staged (Stage 1 per-role D-P4-8 → escalation → swarm); notes/multi-model-roles.md |
| 2026-06-09 | BL-330 inspect-tool server log audit (P4-ISS-002); PHASE4_ISSUES created |
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
