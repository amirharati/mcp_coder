<!--
  STEWARDSHIP — Phase 5 issue tracker. See docs/VISION_DOCS.md.

  - **Frozen** 2026-06-13 at recommended exit. Open items → BACKLOG (BL-335, BL-364).
  - Workers: do not edit. New gaps → BACKLOG BL-* via planning session.
-->

# Phase 5 issue tracker

**Status:** **Frozen** (2026-06-13 — recommended exit met)
**Purpose:** Gaps found during Phase 5 implementation and dogfood.
**Milestone board:** [PHASE5_MVP.md](./PHASE5_MVP.md) (frozen)
**Carried to backlog:** [BACKLOG.md](./BACKLOG.md) BL-335, BL-364

Status: `open` | `done` | `wontfix` | `carried`

---

## Issues (final)

| ID | Status | Priority | Title | Resolution |
|----|--------|----------|-------|------------|
| P5-ISS-001 | **carried** | medium | **BL-335: `model_roles` tokens null on live delegate** | Extractor shipped P5-001 (unit-tested). Live path still null on OpenRouter/Gemini dogfood (`712a04d9`). → **[BL-335](./BACKLOG.md#bl-335-per-role-token-audit-in-delegation-jsonl)** |
| P5-ISS-002 | **done** | high | **RAG toolset CLI/MCP parity + prompt-injection design** | P5-002 + P5-003 |
| P5-ISS-003 | **done** | high | **Long host task → 0 FTS hits** | Fixed P5-006 (stopwords, cap, hyphen split) |
| P5-ISS-004 | **carried** | low | **Spec-validation block → empty `context_refs`** | By design; observability gap. → **[BL-364](./BACKLOG.md)** |

---

## Observations (archive)

| Date | Finding |
|------|---------|
| 2026-06-13 | Recommended exit: delegate `712a04d9` — 5+5 `context_refs`, `ledger.py` fuzzy recall |
| 2026-06-13 | P5-ISS-004: validation-blocked delegates (#2–#4 session `1432fc02`) look like RAG off |
| 2026-06-13 | P5-ISS-001: helper `model_roles` tokens null on live delegate |
| 2026-06-13 | RAG CLI `--format plain` pre-shapes BL-354 at toolset level |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-13 | **Frozen** — Phase 5 recommended exit; P5-ISS-001 → carried (BL-335); P5-ISS-004 → carried (BL-364) |
| 2026-06-13 | P5-ISS-004 opened — spec-validation block vs empty RAG audit |
| 2026-06-13 | P5-ISS-001 → partial; P5-ISS-003 → done; P5-ISS-002 → done |
| 2026-06-13 | Created at Phase 4.5 planning handoff |
