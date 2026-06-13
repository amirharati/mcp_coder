<!--
  STEWARDSHIP — Phase 6 issue tracker. See docs/VISION_DOCS.md.

  - Active during Phase 6 implementation.
  - Workers: do not edit. Found gaps → open new P6-ISS-* via master session.
  - On Phase 6 exit: freeze this file; open items → BACKLOG BL-*.
-->

# Phase 6 issue tracker

**Status:** **Active** — Phase 6 implementation started 2026-06-13
**Purpose:** Gaps found during Phase 6 implementation and dogfood.
**Milestone board:** [PHASE6_MVP.md](./PHASE6_MVP.md)

Status: `open` | `done` | `wontfix` | `carried`

---

## Issues

| ID | Status | Priority | Title | Resolution |
|----|--------|----------|-------|------------|
| P6-ISS-001 | **done** | low | **`NullObservability.merge_model_roles` returns `None` — wrong return type** | Fixed in `6e6b1cc` — returns `{}`; test added. |

---

## Observations

| Date | Finding |
|------|---------|
| 2026-06-13 | P6-001 deep-check: `NullObservability.merge_model_roles` returns `None` (matches `dict \| None` annotation) but `_build_model_roles_payload` in `mcp_server.py` expects a dict. No production impact (production uses `LocalObservability`), but will cause `TypeError` if any future test wires `NullObservability` through the full delegate path. |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-13 | P6-ISS-001 → done (commit `6e6b1cc`) |
| 2026-06-13 | P6-ISS-001 opened — `NullObservability.merge_model_roles` wrong return type found during P6-001 deep-check |
| 2026-06-13 | Created at Phase 6 planning session |
