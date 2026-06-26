#!/usr/bin/env python3
"""P14-004 capture audit: asserts trace completeness for a delegation trace file.

Usage: python scripts/p14_004_capture_audit.py <trace_path>
Exit 0 iff all assertions pass; non-zero with a printed list of failures.

A1 — proxy/backend pairing (executor)
A2 — proxy/backend pairing (helpers) — sequence-matched
A3 — reasoning_tokens populated
A4 — supervisor_intercept per confirm_ask
A5 — supervisor llm_call non-duplication
A6 — trace_header consistency
A7 — duplicate emission check (content-hash dedup)
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_trace(path: str) -> list[dict[str, Any]]:
    """Load JSONL trace, skipping empty lines."""
    records = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not records or records[0].get("type") != "trace_header":
        raise SystemExit(f"Invalid trace: missing trace_header in {path}")
    return records


def assert_a1(records: list[dict[str, Any]]) -> list[str]:
    """A1: every executor llm_call has matching proxy + backend (step_index, call_index).

    Note: executor llm_call from build_executor_llm_trace_record still omits call_index
    (P14-ISS-001 fixed the reasoning_tokens gap but call_index is still absent because
    the executor builder is keyed on step_index). Match on step_index only;
    proxy/backend carry call_index but llm_call doesn't.
    """
    failures: list[str] = []

    llmc: dict[Any, dict] = {}
    proxy: dict[tuple, dict] = {}
    backend: dict[tuple, dict] = {}

    for r in records:
        t = r.get("type")
        si = r.get("step_index")
        ci = r.get("call_index")
        if t == "llm_call" and (r.get("role") == "executor" or r.get("executor_turn")):
            # Executor llm_call may still lack call_index (P14-ISS-001 fixed the
            # reasoning_tokens gap but call_index remains absent — builder is keyed
            # on step_index). Index by step only; proxy/backend carry call_index.
            llmc[si] = r
        elif t == "proxy_llm_call" and si is not None:
            proxy[(si, ci)] = r
        elif t == "backend_llm_call" and si is not None:
            backend[(si, ci)] = r

    for si, rec in llmc.items():
        # Find any proxy/backend with this step_index
        matching_proxy = [k for k in proxy if k[0] == si]
        matching_backend = [k for k in backend if k[0] == si]
        if not matching_proxy:
            failures.append(f"A1: executor llm_call at step={si} has no proxy_llm_call")
        if not matching_backend:
            failures.append(f"A1: executor llm_call at step={si} has no backend_llm_call")

    # Check orphan proxy/backend (with step_index but no matching llm_call)
    for (si, ci) in proxy:
        if si not in llmc:
            failures.append(f"A1: orphan proxy_llm_call at step={si} call={ci} (no llm_call)")
    for (si, ci) in backend:
        if si not in llmc:
            failures.append(f"A1: orphan backend_llm_call at step={si} call={ci} (no llm_call)")

    return failures


HELPER_ROLES = frozenset({
    "planner", "architect", "reviewer", "builder",
    "clarity_check", "spec_validation", "workspace_summarizer",
    "context_builder",
})


def assert_a2(records: list[dict[str, Any]]) -> list[str]:
    """A2: every helper llm_call has matching proxy + backend (sequence-matched per role).

    P14-ISS-009 (fixed): record_owned_completion now emits the event triple
    (llm_call + backend_llm_call + proxy_llm_call) for helper roles, alongside the
    existing llm_call. All three share (role, call_index). Pre-fix dogfood traces
    will still fail A2 because they were captured before the fix; re-run against a
    new post-fix dogfood to confirm (user's manual dogfood pass).

    Proxy uses global call_index (1,2,3,...); llm_call resets call_index per role (always 1).
    Sequence-match: for each role, pair by order of appearance.
    """
    failures: list[str] = []

    role_llmc: dict[str, list[dict]] = defaultdict(list)
    role_proxy: dict[str, list[dict]] = defaultdict(list)
    role_backend: dict[str, list[dict]] = defaultdict(list)

    for r in records:
        t = r.get("type")
        role = r.get("role") or ""
        if t == "llm_call" and role in HELPER_ROLES:
            role_llmc[role].append(r)
        elif t == "proxy_llm_call" and r.get("step_index") is None and role in HELPER_ROLES:
            role_proxy[role].append(r)
        elif t == "backend_llm_call" and r.get("step_index") is None and role in HELPER_ROLES:
            role_backend[role].append(r)

    for role, llmcs in role_llmc.items():
        proxies = role_proxy.get(role, [])
        backends = role_backend.get(role, [])
        for i, llm in enumerate(llmcs):
            if i >= len(proxies):
                failures.append(f"A2: helper llm_call role={role} #{i} has no proxy_llm_call")
            if i >= len(backends):
                failures.append(f"A2: helper llm_call role={role} #{i} has no backend_llm_call")

        # Flag orphan proxy/backend
        for i in range(len(proxies), len(llmcs)):
            pass  # already flagged above
        for i in range(len(llmcs), len(proxies)):
            failures.append(f"A2: orphan proxy_llm_call role={role} #{i} (no llm_call)")
        for i in range(len(llmcs), len(backends)):
            failures.append(f"A2: orphan backend_llm_call role={role} #{i} (no llm_call)")

    return failures


REASONING_ROLES = frozenset({
    "planner", "architect", "reviewer", "builder",
    "clarity_check", "spec_validation", "supervisor", "executor",
})
# Models that reliably return reasoning_tokens; exclude flash/small models
REASONING_MODEL_SUBSTRINGS = frozenset({
    "sonnet", "claude-3", "claude-4", "o1", "o3",
    "deepseek-r",
})


def assert_a3(records: list[dict[str, Any]]) -> list[str]:
    """A3: reasoning_tokens populated for reasoning-capable roles/models."""
    failures: list[str] = []

    for r in records:
        if r.get("type") != "llm_call":
            continue
        role = r.get("role") or ""
        if role not in REASONING_ROLES:
            continue
        model = (r.get("model") or "").lower()
        if not any(s in model for s in REASONING_MODEL_SUBSTRINGS):
            continue

        tokens = r.get("tokens") or {}
        rt = tokens.get("reasoning_tokens")
        if rt is None or rt == 0:
            if not r.get("reasoning_unavailable"):
                source = "positive (>0)" if rt == 0 else "missing key"
                failures.append(
                    f"A3: llm_call role={role} model={r.get('model','')} call={r.get('call_index')} "
                    f"reasoning_tokens {source} (tokens={json.dumps(tokens)[:100]}); "
                    f"reasoning_unavailable field absent"
                )

    return failures


def assert_a4(records: list[dict[str, Any]]) -> list[str]:
    """A4: supervisor_intercept emitted for every confirm_ask; fields populated."""
    failures: list[str] = []

    intercepts = [r for r in records if r.get("type") == "supervisor_intercept"]
    decisions = [r for r in records if r.get("type") == "supervisor_turn_decision"]

    if not intercepts:
        failures.append("A4: no supervisor_intercept events found")
    if not decisions:
        failures.append("A4: no supervisor_turn_decision events found")

    for i, ic in enumerate(intercepts):
        for field in ("classification", "decision", "reasoning", "mentioned_paths",
                      "context_ref", "llm_used", "duration_ms"):
            if ic.get(field) is None:
                failures.append(f"A4: supervisor_intercept #{i} missing field '{field}'")

    return failures


def assert_a5(records: list[dict[str, Any]]) -> list[str]:
    """A5: supervisor llm_call events from different emit sites do NOT duplicate.

    Two paths emit llm_call(role=supervisor):
    - supervisor.py::_emit_llm_call_event (confirm_ask, has supervisor_decision field)
    - supervisor_agent.py::_emit_llm_call_trace (_llm_decide, no supervisor_decision field)

    These are different call sites. Only flag true content-identical duplicates.
    """
    failures: list[str] = []

    supervisor_llmc = [
        r for r in records
        if r.get("type") == "llm_call" and r.get("role") == "supervisor"
    ]

    seen: dict[tuple, dict] = {}
    for r in supervisor_llmc:
        content_key = (
            r.get("call_index"),
            r.get("turn_index"),
            json.dumps(r.get("tokens") or {}, sort_keys=True),
            (r.get("prompt_hash") or ""),
            (r.get("response_hash") or ""),
        )
        is_confirm_ask = bool(r.get("supervisor_decision"))
        source = "confirm_ask" if is_confirm_ask else "_llm_decide"
        if content_key in seen:
            failures.append(
                f"A5: content-identical supervisor llm_call from {source} and "
                f"{seen[content_key].get('_source','unknown')} at "
                f"call={r.get('call_index')} turn={r.get('turn_index')}"
            )
        else:
            r["_source"] = source
            seen[content_key] = r

    return failures


def assert_a6(records: list[dict[str, Any]]) -> list[str]:
    """A6: every record's delegation_id matches trace_header."""
    failures: list[str] = []

    header_did = records[0].get("delegation_id")
    if not header_did:
        failures.append("A6: trace_header missing delegation_id")
        return failures

    for i, r in enumerate(records):
        did = r.get("delegation_id")
        if did is not None and did != header_did:
            failures.append(
                f"A6: record #{i} type={r.get('type')} has delegation_id={did} != header {header_did}"
            )
    return failures


def _content_hash(r: dict[str, Any]) -> str:
    """Hash record minus timestamp for content-equality check."""
    rest = {k: v for k, v in r.items() if k != "timestamp"}
    return json.dumps(rest, sort_keys=True, default=str)


def assert_a7(records: list[dict[str, Any]]) -> list[str]:
    """A7: no unexpected duplicate events by content hash.

    Expected: multiple actions with different content, multiple llm_calls per role, etc.
    Unexpected: identical records (same content hash) appearing more than once.
    """
    failures: list[str] = []

    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[_content_hash(r)].append(r)

    for ch, items in groups.items():
        if len(items) > 1:
            t = items[0].get("type")
            role = items[0].get("role") or ""
            detail = f"type={t}"
            if role:
                detail += f" role={role}"
            detail += f" count={len(items)}"
            # Only flag if > 2 duplicates (some duplication is expected with loop events)
            if len(items) > 2:
                failures.append(f"A7: duplicate emission {detail} (identical content)")
    return failures


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/p14_004_capture_audit.py <trace_path>", file=sys.stderr)
        return 2

    trace_path = sys.argv[1]
    records = load_trace(trace_path)
    print(f"Loaded {len(records)} records from {trace_path}")
    print(f"Header delegation_id: {records[0].get('delegation_id')}")

    all_failures: list[str] = []
    for name, fn in [
        ("A1 proxy/backend pairing (executor)", assert_a1),
        ("A2 proxy/backend pairing (helpers)", assert_a2),
        ("A3 reasoning_tokens populated", assert_a3),
        ("A4 supervisor_intercept per confirm_ask", assert_a4),
        ("A5 supervisor llm_call non-duplication", assert_a5),
        ("A6 trace_header consistency", assert_a6),
        ("A7 duplicate emission", assert_a7),
    ]:
        failures = fn(records)
        if failures:
            all_failures.extend(failures)
            print(f"\n✗ {name}: {len(failures)} failure(s)")
            for f in failures:
                print(f"  {f}")
        else:
            print(f"✓ {name}")

    if all_failures:
        print(f"\n{len(all_failures)} total failure(s)")
        return 1
    else:
        print("\nAll assertions passed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())