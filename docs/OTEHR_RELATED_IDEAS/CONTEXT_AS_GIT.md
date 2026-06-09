<!--
  STEWARDSHIP — Tier 3 related idea (not canonical). See docs/VISION_DOCS.md.

  - May inform BL-* items; does not override docs/IDEA.md.
  - Do not treat as shipped product design without user + backlog entry.
  - Related: GATEKEEPING_MCP.md, WORKSPACE_HISTORY.md
-->

# Context as Git — Conversation History as a Versioned, Branchable Document

**Status:** Idea — captures framing from Grok brainstorm session + design insight from mcp-coder development (2026-06-09)  
**Related:** [GATEKEEPING_MCP.md](./GATEKEEPING_MCP.md) · [WORKSPACE_HISTORY.md](./WORKSPACE_HISTORY.md)

---

## The core idea

Treat conversation context — the chat history, active files, summaries, and decisions — as a **Git repository**. Not as a linear append-only log but as a versioned document that can be branched, forked, merged, and discarded.

The same operations developers already use for code apply to context:

| Git operation | Context equivalent |
|--------------|-------------------|
| `commit` | Checkpoint the current context state |
| `branch` | Fork into a new sub-task or experiment without polluting main |
| `checkout` | Switch back to a previous context state |
| `merge` | Bring only the relevant summary of a branch back into main |
| `discard / reset` | Drop a bad experiment cleanly |

This solves several problems that pure append-only history and summarization do not:

- **Topic drift** — old irrelevant topics accumulate even after summarization; branching lets you drop them cleanly
- **Experimentation risk** — trying something in a branch means failure doesn't corrupt the main context
- **Long-session bloat** — heavy sub-tasks run in a fresh branch; only their outcome merges back
- **Undo without loss** — roll back to any checkpoint without losing the full stored history

---

## Two distinct layers — stored vs runtime

This is the most important design distinction:

**Stored context (the Git document)**
- Full raw history: every turn, every tool call, every file edit
- Persists across sessions; never truncated; lives on disk
- Branched and versioned; can be searched, retrieved, and audited
- This is analogous to your Git repo — the complete record

**Runtime context (the LLM projection)**
- Built fresh before each LLM call from the stored document
- Aggressively filtered: only relevant turns, summarized history, selected files
- Strictly token-budgeted
- Ephemeral — thrown away after the call; never stored as-is
- This is analogous to a compiled binary — derived from source, optimized for execution

The cheap-model context router's job is exactly this transformation: stored → runtime. It reads the full Git document and decides what the expensive model actually needs to see.

---

## The agentic loop pattern

At the onset of a new user request, the transformation is heavy:
- Summarize old turns, drop irrelevant topics, select relevant files, build the runtime context

Inside the agentic loop (multi-step tool calling), the transformation is light:
- Mostly append the latest tool output + agent step
- Trigger a heavier re-projection only when the window fills or topic shifts detectably

At the end of a major task, checkpoint the result back into the stored document as a clean commit.

---

## Heavy tasks — fork, clean spec, merge summary

For anything more than a simple edit, the right pattern is:

1. **Fork** — create a new context branch from the current state
2. **Clean spec** — generate a minimal spec document for the sub-agent: goal, constraints, relevant files, acceptance criteria; reference to main history if needed (pointer, not full copy)
3. **Sub-agent runs** — its own full multi-turn loop, tool calls, edits, retries — completely internal
4. **Merge summary only** — the sub-agent produces an updated spec + short outcome summary; the internal tool chatter is never merged back into main
5. **Main context stays clean** — no topic drift from the sub-task's internals

This is deliberately hierarchical: the main session sees only what the sub-agent decided, not how it got there.

---

## The insight: mcp-coder already implements this

The most important observation from reviewing this idea against the existing codebase:

**mcp-coder is the "git for context" system.** The delegation model maps directly:

| "Git for context" concept | mcp-coder implementation |
|--------------------------|--------------------------|
| Fork context into clean sub-session | `delegate_to_agent` — each call is a fresh Aider session |
| Clean spec as sub-agent's context document | Spec file attached to the delegation |
| Sub-agent runs its own loop internally | Aider's internal loop — invisible to Cursor |
| Merge only a summary back | Spec report — structured outcome, not raw Aider transcript |
| Stored context on disk | `delegations.jsonl` + `workspace_history.db` |
| Runtime context projection | `ContextPackage` assembled by the context compiler |
| Cheap model decides what to include | Phase 4 BL-001 — context builder (not yet built) |
| Branch / discard bad attempt | Spec versioning (`-v1`, `-v2`) — retry with new attempt, old preserved |

The Grok brainstorm was designing what mcp-coder already implements at the delegation level. **Phase 4's context builder closes the last gap** — the cheap model that curates what goes into the spec before forking, replacing the current pattern where the planner manually lists all relevant files.

---

## Scope of the analogy (what it is and isn't)

**Git is an analogy for repair and checkpointing** — not a mandate to run real `git` on chat transcripts.

mcp-coder today does **not** manage **host context** (Cursor chat history, Composer loop, @-mentions). It owns the **delegation boundary**: code snapshots, specs, reports, versioning. The analogy applies most directly there:

| Kind of context | Who owns it | Checkpoint / repair today |
|-----------------|-------------|---------------------------|
| **Planner (host)** | Cursor | Rules + tool responses only; no stored transcript |
| **Delegation** | mcp-coder | Spec + report + `workspace_history.db` per delegation |
| **Cross-session memory** | mcp-coder (partial) | `delegations.jsonl`, RAG (Phase 5 scope) |

What we already checkpoint without versioning chat:

- **Code** — manifest walk, blobs, diffs per delegation
- **Contract** — spec under `.mcp-coder/specs/tasks/` + `-vN` attempt archives
- **Outcome** — spec report (structured merge-back, not executor tool chatter)

Being **more explicit** about checkpoint semantics (named checkpoints, clearer merge-back fields, repair/rewind UX) is a natural follow-on in Phase 4/5+ — still delegation-centric, not “we version Cursor.”

A **future mcp-coder host** (CLI/TUI interactive session — see BL-160) could expose the same primitives in chat form. That would be a product where we *do* own stored vs runtime context end-to-end.

---

## Relevance: current mode vs long interactive chat mode

Two product shapes share this doc; only the first is shipped:

| Mode | Shape | Context problem |
|------|--------|-----------------|
| **Delegate (current)** | Thin host → `delegate_to_agent` → report back | Bounded by design: fork = delegation, merge = report |
| **Chat / brainstorm (future)** | Long multi-turn MCP session (“focus group”, architecture chat) | Same as Cursor: drift, token bloat, lossy summarization — **unless** we add checkpoints |

**Delegate mode** already avoids long linear context in the host because each call is an isolated work unit. The git analogy maps to **work checkpoints** (code + spec + report), not planner chat.

**Interactive MCP chat** — if we add it — inherits Cursor’s problems by construction if it is “append messages and call the model each turn” with no boundaries. To make it worthwhile we would need the same separation this doc describes, but **inside** mcp-coder:

- **Stored session** — full transcript on disk (e.g. `session.jsonl` in MCP home); never truncated
- **Runtime projection** — cheap model or rules each turn: relevance filter, topic drop, token budget
- **Explicit checkpoints** — named decision snapshots; optional link to workspace delegation
- **Graduate to delegate** — brainstorm ends in an **artifact** (epic, ADR, spec), not more chat; then `delegate_to_agent` executes

Useful framing:

- **Delegate = checkpointed work** (contractual context)
- **Chat = uncheckpointed talk** unless we add fork/checkpoint/merge-artifact steps
- **Focus group / brainstorming** — valuable upstream of delegation; deliverable is still a spec or decision log, not the raw thread

Phase 4 focuses on **delegation context** (builder + compiler). Interactive chat mode is likely later (BL-160 territory); build it only when delegate + builder + inspect loop are solid, or we duplicate Cursor’s hardest problem in a second surface.

---

## Where the analogy extends further

Things not yet implemented that the "context as git" framing suggests:

**Parallel branches (parallel delegation)**
Run two different approaches to the same task simultaneously on separate branches; compare outcomes; keep the better one. mcp-coder currently runs one delegation at a time.

**Explicit context commits (checkpointing)**
Allow the planner to explicitly checkpoint the current context state (`/commit-context "finished auth module"`) so rollback is clean and named, not just "go back N delegations."

**Branch-aware RAG**
When searching past delegations, filter by branch/sub-task so results from an unrelated experiment don't pollute retrieval.

**Topic-aware pruning inside the planner**
The cheap model detects when the main planner chat has drifted topics and suggests branching rather than continuing to accumulate irrelevant context.

---

## Potential issues

| Issue | Mitigation |
|-------|-----------|
| On-disk context repos grow large | Blob deduplication (content-addressable); already done in `workspace_history.db` |
| Merging summaries loses details | Summary is always paired with a spec report that has structured fields; details are retrievable from the stored branch |
| Parallel branches create confusion about which is "current" | Explicit branch naming + status in `list_delegations`; only one branch is "active" |
| Sub-agent context leaks back into main via files | Workspace history + gateway catch this — exactly what the Gatekeeper extension described in GATEKEEPING_MCP.md addresses |
