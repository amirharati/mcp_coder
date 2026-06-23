<!--
  STEWARDSHIP — backlog split. See ../VISION_DOCS.md and ../BACKLOG.md.

  - Canonical HOW-TO for humans and LLMs: § For LLMs below.
  - ../BACKLOG.md is the INDEX — read it first, grep here for full text.
  - Status changes update BOTH the index one-liner and the full-text entry.
  - Never delete items silently; move to done.md with a one-line rationale.
  - Workers (implementation sessions): do NOT edit backlog files; propose BL-* in task § Results.
-->

# Backlog — full-text storage

This folder holds the **full text** of every backlog item. The **index** lives at [`../BACKLOG.md`](../BACKLOG.md) — read that first to scan IDs + one-liners + status, then `grep` here when you need the full design / rationale / trade-offs for a specific item.

---

## For LLMs (agents)

**Who may edit:** Planning / master sessions only. **Workers must not** edit `BACKLOG.md` or `backlog/*` — propose new or changed BL-* items in the task spec **§ Results → Suggested for master session**.

### Fast read (do this first)

| Goal | Command / file |
|------|----------------|
| Scan all items | Read `../BACKLOG.md` only (~300 lines) |
| Full text of one item | `grep -A 50 "^### BL-354" docs/backlog/deferred.md` |
| Which cluster? | `grep "BL-354" ../BACKLOG.md` |
| Whole cluster body | `grep -A 200 "^## Observability & logging" docs/backlog/deferred.md` |
| Shipped item audit | `grep -A 40 "^### BL-351" docs/backlog/done.md` |
| Archive (pre-split) | `docs/backlog/_source-full.md` — read-only reference |

**Never** read `deferred.md` or `done.md` end-to-end unless reconstructing history.

### File roles

| File | Edit when | Holds |
|------|-----------|--------|
| `../BACKLOG.md` | Always (index sync) | One-liner + status per BL-*; § Active; § Watch; changelog tail |
| `deferred.md` | Item open / partial / idea | Full `### BL-NNN:` sections under `## <cluster>` |
| `done.md` | Item shipped / obsolete | Full section moved from deferred; completion note on `**Status:**` |
| `_source-full.md` | **Do not edit** | Frozen archive from 2026-06-23 split |

### Update recipes

**1. New BL-* item (from phase close, issue carry, or triage)**

1. Pick next free BL-ID (grep `BL-` in `../BACKLOG.md` for max).
2. Pick primary cluster (list below).
3. Add to `deferred.md` under that cluster:

   ```markdown
   ### BL-NNN: Short title

   **Status:** `deferred` — YYYY-MM-DD. One-line why deferred.
   **Related:** BL-XXX, P13-ISS-NNN

   **Problem:** …
   **Goal:** …
   ```

4. Add index row in `../BACKLOG.md` under `### <cluster>`: `| BL-NNN | Short title (≤120 chars) | deferred |`
5. Append one line to `../BACKLOG.md` § Changelog.

**2. Status change only** (e.g. `idea` → `partial`, scope note)

- Update `**Status:**` line in `deferred.md` (or `done.md` if already shipped).
- Update the **Status** column for that row in `../BACKLOG.md`.
- Optionally tighten the **What** one-liner if the summary changed.
- Changelog one-liner if meaningful.

**3. Item shipped (move to done)**

1. Cut the full `### BL-NNN:` section from `deferred.md`.
2. Paste into `done.md` (same cluster `##` header if present; order by BL-ID is fine).
3. Set `**Status:**` to `done` — YYYY-MM-DD. **Pxx-NNN shipped** (commit or milestone ref). Note any remainder → other BL-*.
4. In `../BACKLOG.md`: change index row status to `done` (row stays for grep/history).
5. Remove from § Active if listed there.
6. Changelog entry.

**4. Add / remove § Active candidate**

- Edit only `../BACKLOG.md` § Active table (3–5 items max; full text stays in `deferred.md`).
- Item must already exist in index + deferred.

**5. Add / close § Watch for evidence**

- Edit only `../BACKLOG.md` § Watch table (fixed-pending-verify items).
- On confirm in dogfood: close source issue in `PHASE*_ISSUES.md`, then either remove Watch row or move BL to `done` per recipe 3.

**6. Partial done — split remainder**

- Update original BL `**Status:**` to `partial` with what shipped vs remainder.
- If remainder is large, add new BL-* for the remainder (recipe 1) and cross-link.

### Sync rule (critical)

**Index drift is the main failure mode.** Every status or summary change touches **both**:

1. `../BACKLOG.md` row (What + Status)
2. Full-text `**Status:**` (and body if design changed)

Active and Watch sections live only in the index — no duplicate in `deferred.md`.

### Cluster pick (primary only)

Supervisor & orchestration · Context & RAG · Observability & logging · Executor & backends · Models & policy · Host & integration · Specs & workflow · Storage & lifecycle · Reliability & error handling · Ideas / unscoped

Cross-link with `**Related:** BL-XXX` in the body; do not duplicate rows.

### Do not

- Put full item bodies in `../BACKLOG.md` (index stays one-liners).
- Delete BL-* rows silently — move to `done.md` with rationale, or mark obsolete in Status.
- Contradict [IDEA.md](../IDEA.md) without user agreement.
- Re-expand `_source-full.md` or merge deferred + done back into one file.
- Let workers edit these files during implementation tasks.

---

## Read pattern (humans)

| Question | Where |
|----------|-------|
| "What's active right now?" | `../BACKLOG.md` § Active |
| "What should I watch for in dogfood?" | `../BACKLOG.md` § Watch for evidence |
| "Is there a BL for X?" | `grep -i "X" ../BACKLOG.md` |
| "What's the full text of BL-354?" | `grep -A 40 "^### BL-354" deferred.md` |
| "What's deferred for observability?" | `grep -A 100 "^## Observability & logging" deferred.md` |
| "What's already shipped?" | `done.md` (audit only — rarely read) |

## Maintenance rules

1. **Index drift is the only real risk.** When you change an item's status or summary, update BOTH the index one-liner and the full-text entry.
2. **No silent deletes.** Move done items to `done.md` with a one-line completion note. Move obsolete items to `done.md` with a one-line "obsolete because…" note.
3. **Cluster boundaries are soft.** If an item fits two clusters, pick the primary and cross-reference with `See also: BL-XXX` in the body.
4. **Active + Watch stay in the index.** They're small and frequently read — don't make them a separate grep target.
5. **Phase-history sections don't go in the index.** Phase MVP docs record what shipped; backlog changelog captures PM-level moves only.
