# Wave 1 Exit Validation

**Milestone:** Wave 1 — honesty + safety foundations (P2-110, P2-115, P2-120, P2-125)  
**Status:** Wave 1 **complete** — structured dogfood + wild test (expense-splitter epic, 9 pytest)  
**Issues:** [PHASE2_ISSUES.md](../PHASE2_ISSUES.md) P2-ISS-001–008  
**Automated gate:** `pytest -q` — all tests must pass

---

## 1. Prerequisites

```bash
# Activate venv
source .venv/bin/activate

# Run automated tests (no API key required)
pytest -q

# For live delegation checks (optional)
# Ensure OPENROUTER_API_KEY is set in .env:
#   OPENROUTER_API_KEY=sk-or-...
```

Required:
- Python ≥ 3.12
- `pip install -e ".[dev]"` (or `pip install -e .` + `pip install pytest`)
- `.venv` or equivalent active

---

## 2. Automated Gate

```bash
# Full suite — must all pass
pytest -q

# Wave-1-specific suites
pytest tests/test_delegation_errors.py tests/test_wave1_feature_matrix.py -v

# Individual feature suites
pytest tests/test_spec_files_contract.py -q     # P2-110 contract parsing
pytest tests/test_delegation_policies.py -q     # P2-115 policy parsing
pytest tests/test_usage_telemetry.py -q          # P2-120 usage report
pytest tests/test_delegation_errors.py -q        # P2-125 error classification
pytest tests/test_wave1_feature_matrix.py -q     # W1-1…W1-7 end-to-end matrix
```

Record the final count: `___ passed, ___ skipped, ___ warnings`.

---

## 3. Feature Spot-Checks (Planner in Cursor)

These manual checks require a running MCP server and a workspace with `OPENROUTER_API_KEY` set.

### 3.1 P2-110 — Read-dep contract warning

1. Create a spec with a `### Read` dependency that is **not** in `target_files`.
2. Run `delegate_to_agent` with that spec.
3. **Expected:** Response contains `contract_warnings` listing the missing path; delegation still runs.
4. Check the JSONL log: `spec_files_missing_from_target` field is populated.

### 3.2 P2-115 — `edit_scope: strict` violation

1. Create a spec with `edit_scope: strict` and `files_edit: [app/service.py]`.
2. Run a delegation where the engine edits `app/other.py` as well.
3. **Expected:** `outcome: scope_violation` in response; `scope_violations` lists `app/other.py`.

### 3.3 P2-115 — Invalid `edit_scope` value

1. Create a spec with `edit_scope: nonsense`.
2. Run `delegate_to_agent` pointing at that spec.
3. **Expected:** `success: false`, `outcome: invalid_spec`, engine not called.

### 3.4 P2-120 — `usage` in tool response

1. Run any successful delegation.
2. **Expected:** Response JSON contains `"usage": { "preflight_tokens_est": ..., "cost_est_usd": ... }`.
3. Set `MCP_CODER_USAGE_REPORT=0`, rerun — `usage` should disappear from response but remain in JSONL.

### 3.5 P2-125 — Cheap-model failure: no browser, `error_class` set

```bash
# Optional live check (requires OPENROUTER_API_KEY):
AIDER_MODEL=openrouter/qwen/qwen-2.5-coder-32b-instruct mcp-coder test-model
```

Then run a `delegate_to_agent` with a task that is likely to trigger a provider error on a cheap model.

**Expected results:**
- No new browser tabs open (BL-309a).
- Response JSON contains `"error_class": "upstream_5xx"` (or `rate_limit`, etc.).
- `"error_message"` is a short human-readable sentence.
- `"output"` does not contain HTTP headers or `stripe.com` URLs.
- Delegation completes within `MCP_CODER_DELEGATION_TIMEOUT_S` seconds (default 120).

---

## 4. Wave 1 Checklist

| Feature | P2 task | Automated | How to verify |
|---------|---------|-----------|---------------|
| Read-dep contract warning | P2-110 | W1-1 | `contract_warnings` in response when Read dep missing from `target_files` |
| Strict scope enforcement | P2-115 | W1-2 | `outcome: scope_violation` when edits outside `files_edit` |
| Invalid `edit_scope` guard | P2-115 | W1-3 | `outcome: invalid_spec`, engine not called |
| Usage report in response | P2-120 | W1-4 | `usage` dict present in response when enabled |
| Usage report disabled | P2-120 | W1-5 | `usage` absent from response; present in JSONL |
| Upstream 500 → `error_class` | P2-125 | W1-6 | `error_class: upstream_5xx`, sanitized `output` |
| Browser guard | P2-125 | W1-7 | `webbrowser.open` call count = 0 on error path |

Additionally (P2-125 env vars):
- `detect_urls` default `False` in `delegation_coder_kwargs()` — validated by `test_delegation_errors.py::TestDelegationCoderKwargsDetectUrls`
- `delegation_timeout_seconds()` default 120 — validated by `TestDelegationTimeoutSeconds`

---

## 5. Known Limitations (Deferred)

| Item | BL ref | Target |
|------|--------|--------|
| MCP-layer retry + model fallback | BL-309c | Wave 2 / P2-200+ |
| Roll back 0-byte stub files on mid-run failure | BL-309d | Future |
| `partial` outcome refinements | BL-309f | Already in `outcome.py` |
| README / INSTALL full rewrite | — | Master session after Wave 1 sign-off |

**P1-ISS-012 live check:** The browser storm and opaque hang symptoms from P1-ISS-012 are
mitigated by P2-125 (block_webbrowser_open, timeout, classify + sanitize). A live end-to-end
check with a cheap model that returns a 500 is **deferred** to planner; mock tests (W1-6/W1-7)
confirm the machinery.

---

## 6. Sign-Off

| Field | Value |
|-------|-------|
| Date | 2026-06-07 |
| pytest count | mcp_coder `212 passed, 1 skipped`; wild E2E `9 passed` |
| Wave 1 tasks | P2-110 ✓ / P2-115 ✓ / P2-120 ✓ / P2-125 ✓ |
| Structured dogfood | Phases 1–4 ✓ |
| P1-ISS-012 status | **partial** — timeout + provider flake live; clean `upstream_5xx` not hit |
| Wild test | **done** — Qwen fail ×3 → 4o-mini; epic 3 steps + step-3 fix-forward |
| Sample `delegation_id` (live) | step1 ok `42f1363d`; step2 `1aae8d8e`; step3 `cab09fc9` |
| Follow-ups filed | P2-ISS-007 BL-320 attempt archive; P2-ISS-008 BL-321 tiered models |
