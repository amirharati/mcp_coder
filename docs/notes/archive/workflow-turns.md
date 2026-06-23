# Workflow turns — special modes & cadence (living note)

**Status:** Living note — planning only. Not shipped. **Horizon:** likely Phase 5+ / later — ideas are far from implementation but directionally aligned.  
**Backlog:** [BL-359](../BACKLOG.md#bl-359-workflow-turns--refactor-document-digest-cadence), [BL-358](../BACKLOG.md#bl-358-post-executor-polish-pass--reviewer-model-comments-tests-alignment) (polish sub-mode).  
**Related:** [spec-review-loop.md](./spec-review-loop.md) (`mode=review` today), [multi-model-roles.md](./multi-model-roles.md).

---

## North star

**Formalize the workflow; automate what is easy but repetitive.**

| Human keeps | mcp-coder automates |
|-------------|---------------------|
| Judgment — when to pause, refactor, ship | Named **turns** with clear rules (implement, digest, polish, …) |
| Creative / ambiguous design | **Cadence** hints at epic boundaries (“time to digest?”) |
| Accept or reject suggestions | **Repetitive** compile-push, history, verify, lint, alignment passes |
| Spec and epic intent | Audit trail so each turn is reproducible, not ad-hoc chat |

We are not trying to replace the developer loop — we are **making the loop explicit** and offloading the boring parts (comments, tests skim, “what did we just build?”, cross-step read-deps) to cheap models + machinery already in Phases 1–4.

Phase 5 RAG + observability = **better memory** for those turns. Phase 5+ workflow modes = **named beats** in the loop. Both serve the same goal: less thrash, more deliberate pauses.

---

## Why this note exists

Real development is not only **implement** in a loop. After a few phases you **stop**, read the code, find gaps, refactor, document, and re-onboard yourself. mcp-coder today is strong at **implement** (+ optional pre-spec **review**). This note captures **special turns** and **when** to run them — user-initiated, semi-auto suggestion, or epic-boundary policy.

---

## Shipped today

| Turn | Mechanism | Edits code? |
|------|-----------|-------------|
| **Spec review** | `mode=review` | No — questions on spec only |
| **Implement** | `mode=implement` | Yes — executor |
| **Verify** | `auto_verify` (pytest, etc.) | No — command only |

---

## Proposed special turns (future)

| Turn | Job | Typical scope | Executor? |
|------|-----|---------------|-----------|
| **Polish** | Comments, tests, style alignment, **non-logic** micro-edits | `files_changed` + neighbors | Yes — cheap/large-context pass ([BL-358](../BACKLOG.md#bl-358-post-executor-polish-pass--reviewer-model-comments-tests-alignment)) |
| **Refactor** | Structure, rename, extract, dedupe — **behavior preserved** | Module / epic slice; wider than one step | Yes — dedicated mode + stricter gates |
| **Document** | Docstrings, README, module docs, spec/epic narrative | Docs paths + changed modules | Maybe — or planner-only artifacts under `.mcp-coder/` |
| **Digest / audit / onboard** | “What did we build?” gaps, risks, debt, onboarding summary | Read-wide; history + RAG | **No** (or review-like LLM only) — report to planner |

**Digest** is what you described after a few phases: understand the code, find issues, gaps, onboard — **not** another feature delegate.

---

## Cadence — when to run (policy)

| Trigger | Who | Example |
|---------|-----|---------|
| **User-initiated** | Planner / human in Cursor | “Run digest on epic X”, `mode=refactor` spec |
| **Spec / epic flag** | Front matter | `turn: polish`, `epic_exit: true`, `refactor: module` |
| **Semi-auto suggest** | mcp-coder → planner (MCP response or host rule) | After N delegations or epic step complete: `suggested_turn: digest` — planner accepts or skips |
| **Every implement** | Config `polish_pass: always` | **Not recommended default** — cost + noise |

**Default bias:** implement on steps; **polish / digest at epic boundaries**; **refactor / document** when user or spec explicitly asks.

```
epic steps 1..N-1     →  implement (+ verify)
epic exit / pause     →  digest (read-only report)
optional              →  polish or refactor (edit passes)
document              →  user or epic “docs done” spec
```

---

## Host (Cursor) role

Special turns need **planner rules** so Cursor knows when to offer them:

- After epic slice: suggest digest before next epic
- Distinguish `review` (spec brainstorm) vs `digest` (code comprehension)
- When user says “clean this up”: `refactor` not new `implement`
- Document mode: write under agreed paths only

See **BL-332** (host-agnostic rules) — content can be generic; triggers may stay Cursor-first initially.

---

## vs RAG / observability

| Need | Tool |
|------|------|
| “What did we decide last week?” | RAG / history ([retrieval-and-rag-strategy.md](./retrieval-and-rag-strategy.md)) |
| “Explain this module after 5 steps” | **Digest turn** — fresh compile + optional delegation RAG input |
| “Add comments after implement” | **Polish turn** ([BL-358](../BACKLOG.md#bl-358-post-executor-polish-pass--reviewer-model-comments-tests-alignment)) |

Digest may **consume** RAG; it is not a corpus by itself.

---

## Open questions

1. New `delegate_mode` values vs `mode=implement` + spec `turn:` front matter?
2. Digest output: spec report appendix, new `specs/digests/`, or MCP-only markdown?
3. Semi-auto: threshold — epic step count, delegation count, or token/debt heuristic?
4. Refactor: separate executor session or same pipeline phase as polish with wider `files_edit`?

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-12 | § North star — formalize workflow, automate easy repetitive tasks; horizon note |
| 2026-06-12 | Initial note — polish/refactor/document/digest turns, cadence triggers, host rules (planning discussion) |
