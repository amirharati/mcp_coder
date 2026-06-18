"""CLI: compare backend_llm_call vs proxy_llm_call per delegation (P9-006)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from core.cli.replay import _find_delegation_row, _load_trace, _resolve_workspace, _session_dir_for_row

_TRACE_TYPE_BACKEND = "backend_llm_call"
_TRACE_TYPE_PROXY = "proxy_llm_call"

_THINKING_HINTS = (
    "reasoning_content",
    "thinking_text",
    "thinking_body",
    "thinking_preview",
    "reasoning_body",
)


def _step_index(event: dict[str, Any]) -> int | None:
    value = event.get("step_index")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _call_index(event: dict[str, Any] | None) -> int | None:
    if not event:
        return None
    value = event.get("call_index")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _pair_key(step_index: int | None, call_index: int | None) -> tuple[int | None, int | None]:
    return (step_index, call_index)


def _pair_key_sort_key(key: tuple[int | None, int | None]) -> tuple[tuple[bool, int], tuple[bool, int]]:
    """Sort pair keys with None indices last (proxy events may omit step_index)."""
    step, call = key
    return ((step is None, step or 0), (call is None, call or 0))


def _models_compatible(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return True
    if left == right:
        return True
    return left.endswith(right) or right.endswith(left)


def _backend_thinking_present(event: dict[str, Any] | None) -> bool:
    if not event:
        return False
    for key in (
        "thinking_text",
        "thinking_body",
        "thinking_preview",
        "reasoning_body",
        "reasoning_content",
    ):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return True
    tokens = event.get("thinking_tokens")
    return isinstance(tokens, int) and tokens > 0


def _proxy_thinking_present(event: dict[str, Any] | None) -> bool:
    if not event:
        return False
    raw = event.get("raw_response")
    if not isinstance(raw, str) or not raw.strip():
        return False
    lowered = raw.lower()
    if any(hint in lowered for hint in _THINKING_HINTS):
        return True
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return bool(re.search(r'"thinking[^"]*"\s*:\s*"[^"]+"', raw, re.IGNORECASE))
    return _json_has_thinking(payload)


def _json_has_thinking(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(key).lower()
            if "thinking" in key_lower or "reasoning" in key_lower:
                if isinstance(item, str) and item.strip():
                    return True
                if isinstance(item, (dict, list)) and _json_has_thinking(item):
                    return True
            if _json_has_thinking(item):
                return True
        return False
    if isinstance(value, list):
        return any(_json_has_thinking(item) for item in value)
    return False


def _backend_total_latency_ms(event: dict[str, Any] | None) -> int | None:
    if not event:
        return None
    duration = event.get("duration_ms")
    if isinstance(duration, int):
        return duration
    if isinstance(duration, float):
        return int(duration)
    return None


def _backend_usage(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not event:
        return None
    usage = event.get("usage")
    if isinstance(usage, dict) and usage:
        return usage
    tokens = event.get("tokens")
    if isinstance(tokens, dict) and tokens:
        return tokens
    return None


def _field_diffs(backend: dict[str, Any] | None, proxy: dict[str, Any] | None) -> list[str]:
    if not backend or not proxy:
        return []
    diffs: list[str] = []
    backend_model = backend.get("model")
    proxy_model = proxy.get("model")
    if backend_model and proxy_model and not _models_compatible(
        str(backend_model), str(proxy_model)
    ):
        diffs.append("model")
    backend_usage = _backend_usage(backend)
    if backend_usage and proxy.get("status_code") not in (None, 200):
        diffs.append("status_code")
    return diffs


def _row_status(
    backend: dict[str, Any] | None,
    proxy: dict[str, Any] | None,
    field_diffs: list[str],
) -> str:
    if backend and proxy:
        return "field_diff" if field_diffs else "matched"
    if proxy and not backend:
        return "proxy_only"
    if backend and not proxy:
        return "backend_only"
    return "matched"


def _build_call_row(
    *,
    step_index: int | None,
    call_index: int | None,
    backend: dict[str, Any] | None,
    proxy: dict[str, Any] | None,
) -> dict[str, Any]:
    field_diff_list = _field_diffs(backend, proxy)
    wire_latency_ms = proxy.get("wire_latency_ms") if proxy else None
    total_latency_ms = _backend_total_latency_ms(backend)
    litellm_overhead_ms = None
    if isinstance(wire_latency_ms, int) and isinstance(total_latency_ms, int):
        litellm_overhead_ms = total_latency_ms - wire_latency_ms

    return {
        "step_index": step_index,
        "call_index": call_index,
        "status": _row_status(backend, proxy, field_diff_list),
        "backend_present": backend is not None,
        "proxy_present": proxy is not None,
        "backend_model": backend.get("model") if backend else None,
        "proxy_model": proxy.get("model") if proxy else None,
        "backend_usage": _backend_usage(backend),
        "proxy_status_code": proxy.get("status_code") if proxy else None,
        "wire_latency_ms": wire_latency_ms,
        "total_latency_ms": total_latency_ms,
        "litellm_overhead_ms": litellm_overhead_ms,
        "field_diffs": field_diff_list,
        "bl507": {
            "backend_thinking_present": _backend_thinking_present(backend),
            "proxy_thinking_present": _proxy_thinking_present(proxy),
        },
    }


def pair_dual_capture_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Pair proxy/backend trace events and build compare summary for CLI/viewer."""
    proxies = [event for event in events if event.get("type") == _TRACE_TYPE_PROXY]
    backends = [event for event in events if event.get("type") == _TRACE_TYPE_BACKEND]

    unmatched_proxy_idx = list(range(len(proxies)))
    unmatched_backend_idx = list(range(len(backends)))
    pairings: list[tuple[int | None, int | None, tuple[int | None, int | None]]] = []

    proxy_by_key: dict[tuple[int | None, int | None], list[int]] = {}
    backend_by_key: dict[tuple[int | None, int | None], list[int]] = {}
    for idx in unmatched_proxy_idx:
        proxy = proxies[idx]
        if _call_index(proxy) is None:
            continue
        key = _pair_key(_step_index(proxy), _call_index(proxy))
        proxy_by_key.setdefault(key, []).append(idx)
    for idx in unmatched_backend_idx:
        backend = backends[idx]
        if _call_index(backend) is None:
            continue
        key = _pair_key(_step_index(backend), _call_index(backend))
        backend_by_key.setdefault(key, []).append(idx)

    for key in sorted(set(proxy_by_key) | set(backend_by_key), key=_pair_key_sort_key):
        proxy_idxs = list(proxy_by_key.get(key, []))
        backend_idxs = list(backend_by_key.get(key, []))
        while proxy_idxs or backend_idxs:
            pi = proxy_idxs.pop(0) if proxy_idxs else None
            bi = backend_idxs.pop(0) if backend_idxs else None
            pairings.append((bi, pi, key))
            if pi is not None and pi in unmatched_proxy_idx:
                unmatched_proxy_idx.remove(pi)
            if bi is not None and bi in unmatched_backend_idx:
                unmatched_backend_idx.remove(bi)

    proxies_by_step: dict[int | None, list[int]] = {}
    backends_by_step: dict[int | None, list[int]] = {}
    for idx in unmatched_proxy_idx:
        proxies_by_step.setdefault(_step_index(proxies[idx]), []).append(idx)
    for idx in unmatched_backend_idx:
        backends_by_step.setdefault(_step_index(backends[idx]), []).append(idx)

    for step in sorted(set(proxies_by_step) | set(backends_by_step), key=lambda s: (s is None, s)):
        proxy_idxs = list(proxies_by_step.get(step, []))
        backend_idxs = list(backends_by_step.get(step, []))
        used_backends: set[int] = set()
        for pi in proxy_idxs:
            proxy = proxies[pi]
            chosen_bi: int | None = None
            for bi in backend_idxs:
                if bi in used_backends:
                    continue
                if _models_compatible(
                    str(proxy.get("model") or ""),
                    str(backends[bi].get("model") or ""),
                ):
                    chosen_bi = bi
                    break
            if chosen_bi is None:
                for bi in backend_idxs:
                    if bi not in used_backends:
                        chosen_bi = bi
                        break
            if chosen_bi is not None:
                used_backends.add(chosen_bi)
                unmatched_backend_idx.remove(chosen_bi)
            if pi in unmatched_proxy_idx:
                unmatched_proxy_idx.remove(pi)
            key = _pair_key(step, _call_index(proxy))
            pairings.append((chosen_bi, pi, key))

        for bi in backend_idxs:
            if bi in used_backends:
                continue
            unmatched_backend_idx.remove(bi)
            key = _pair_key(step, _call_index(backends[bi]))
            pairings.append((bi, None, key))

    calls: list[dict[str, Any]] = []
    for bi, pi, key in pairings:
        backend = backends[bi] if bi is not None else None
        proxy = proxies[pi] if pi is not None else None
        step, call = key
        calls.append(
            _build_call_row(
                step_index=step,
                call_index=call if call is not None else (_call_index(proxy) or _call_index(backend)),
                backend=backend,
                proxy=proxy,
            )
        )

    calls.sort(
        key=lambda row: (
            row.get("step_index") is None,
            row.get("step_index") if row.get("step_index") is not None else -1,
            row.get("call_index") is None,
            row.get("call_index") if row.get("call_index") is not None else -1,
        )
    )

    summary = {
        "total_calls": len(calls),
        "matched": sum(1 for row in calls if row["status"] == "matched"),
        "proxy_only": sum(1 for row in calls if row["status"] == "proxy_only"),
        "backend_only": sum(1 for row in calls if row["status"] == "backend_only"),
        "field_diff": sum(1 for row in calls if row["status"] == "field_diff"),
    }

    gaps = {
        "proxy_only": [row for row in calls if row["status"] == "proxy_only"],
        "backend_only": [row for row in calls if row["status"] == "backend_only"],
    }

    notes: list[str] = []
    proxy_thinking_present: bool | None
    backend_thinking_present: bool | None
    if proxies:
        proxy_thinking_present = any(_proxy_thinking_present(proxy) for proxy in proxies)
        if not proxy_thinking_present:
            notes.append("No thinking/reasoning payload detected in proxy raw_response events.")
    else:
        proxy_thinking_present = None
        notes.append("No proxy_llm_call events in trace.")

    if backends:
        backend_thinking_present = any(_backend_thinking_present(backend) for backend in backends)
        if not backend_thinking_present:
            notes.append(
                "No thinking/reasoning payload detected in backend normalized events."
            )
    else:
        backend_thinking_present = None
        notes.append("No backend_llm_call events in trace.")

    if proxy_thinking_present and not backend_thinking_present:
        notes.append(
            "BL-507: thinking visible at proxy HTTP boundary but absent in backend normalized record."
        )
    elif proxy_thinking_present is False and backend_thinking_present:
        notes.append(
            "BL-507: thinking visible in backend normalized record but absent in proxy raw response."
        )
    elif proxy_thinking_present and backend_thinking_present:
        notes.append("BL-507: thinking/reasoning present in both proxy raw and backend normalized views.")

    return {
        "summary": summary,
        "calls": calls,
        "gaps": gaps,
        "bl507": {
            "proxy_thinking_present": proxy_thinking_present,
            "backend_thinking_present": backend_thinking_present,
            "notes": notes,
        },
    }


def build_compare_payload(
    *,
    delegation_id: str,
    trace_path: str | None,
    events: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    paired = pair_dual_capture_events(events)
    return {
        "found": True,
        "delegation_id": delegation_id,
        "trace_path": trace_path,
        "summary": paired["summary"],
        "calls": paired["calls"],
        "gaps": paired["gaps"],
        "bl507": paired["bl507"],
        "warnings": warnings,
    }


def _print_human(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print("Compare")
    print(f"- delegation_id: {payload.get('delegation_id')}")
    print(f"- trace_path: {payload.get('trace_path')}")
    print(
        "- totals:"
        f" total={summary.get('total_calls')}"
        f" matched={summary.get('matched')}"
        f" proxy_only={summary.get('proxy_only')}"
        f" backend_only={summary.get('backend_only')}"
        f" field_diff={summary.get('field_diff')}"
    )
    print()
    print("Calls")
    for row in payload.get("calls", []):
        print(
            f"- step={row.get('step_index')} call={row.get('call_index')}"
            f" status={row.get('status')}"
            f" backend_model={row.get('backend_model')}"
            f" proxy_model={row.get('proxy_model')}"
            f" proxy_status={row.get('proxy_status_code')}"
            f" wire_ms={row.get('wire_latency_ms')}"
            f" total_ms={row.get('total_latency_ms')}"
            f" overhead_ms={row.get('litellm_overhead_ms')}"
            f" field_diffs={row.get('field_diffs')}"
        )
        bl507 = row.get("bl507") or {}
        print(
            f"  bl507 backend_thinking={bl507.get('backend_thinking_present')}"
            f" proxy_thinking={bl507.get('proxy_thinking_present')}"
        )
    gaps = payload.get("gaps") or {}
    proxy_only = gaps.get("proxy_only") or []
    backend_only = gaps.get("backend_only") or []
    if proxy_only or backend_only:
        print()
        print("Gaps")
        for row in proxy_only:
            print(
                f"- proxy_only step={row.get('step_index')} call={row.get('call_index')}"
                f" model={row.get('proxy_model')}"
            )
        for row in backend_only:
            print(
                f"- backend_only step={row.get('step_index')} call={row.get('call_index')}"
                f" model={row.get('backend_model')}"
            )
    bl507 = payload.get("bl507") or {}
    print()
    print("BL-507")
    print(f"- proxy_thinking_present: {bl507.get('proxy_thinking_present')}")
    print(f"- backend_thinking_present: {bl507.get('backend_thinking_present')}")
    for note in bl507.get("notes") or []:
        print(f"- {note}")
    warnings = payload.get("warnings") or []
    if warnings:
        print()
        print("Warnings")
        for warning in warnings:
            print(f"- {warning}")


def main_compare(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare backend_llm_call vs proxy_llm_call events for one delegation."
    )
    parser.add_argument("delegation_id", help="Delegation ID to compare")
    parser.add_argument("--workspace", default=None, help="Repo root (default: cwd)")
    parser.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format (default: human)",
    )
    args = parser.parse_args(argv)

    workspace = _resolve_workspace(args.workspace)
    row, log_path = _find_delegation_row(workspace, args.delegation_id)
    if row is None or log_path is None:
        msg = f"delegation not found: {args.delegation_id}"
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "found": False,
                        "delegation_id": args.delegation_id,
                        "trace_path": None,
                        "summary": None,
                        "calls": [],
                        "gaps": {"proxy_only": [], "backend_only": []},
                        "bl507": {
                            "proxy_thinking_present": None,
                            "backend_thinking_present": None,
                            "notes": [msg],
                        },
                        "warnings": [msg],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 1

    delegation_id = str(row.get("delegation_id") or args.delegation_id)
    session_dir = _session_dir_for_row(row, log_path)
    trace, trace_warnings = _load_trace(row, delegation_id, session_dir)
    warnings = list(trace_warnings)
    if trace.get("status") == "missing":
        warnings.append(f"trace missing: {trace.get('path')}")

    payload = build_compare_payload(
        delegation_id=delegation_id,
        trace_path=trace.get("path"),
        events=trace.get("events") if isinstance(trace.get("events"), list) else [],
        warnings=warnings,
    )

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_human(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_compare())
