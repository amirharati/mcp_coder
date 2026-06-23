"""Resolve lean JSONL pointers for the delegation viewer (P6-007 follow-up)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.cli.compare import pair_dual_capture_events
from core.rag.db import DelegationRagDB
from core.rag.retrieval import CORPUS_DELEGATION, CORPUS_WORKSPACE_FILES
from core.rag.workspace_db import WorkspaceRagDB
from core.workspace.history_query import delegation_diff_for_mcp


def _load_trace_lines(session_dir: str | Path, trace_ref: str | None, delegation_id: str) -> tuple[Path | None, list[dict[str, Any]]]:
    base = Path(session_dir)
    rel = trace_ref or f"traces/{delegation_id}.jsonl"
    path = base / rel
    if not path.is_file():
        return None, []
    lines: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            lines.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return path, lines


def _resolve_output(record: dict[str, Any], trace_lines: list[dict[str, Any]]) -> dict[str, Any]:
    response = record.get("response_to_cursor") or {}
    if response.get("output"):
        return {
            "text": str(response["output"]),
            "source": "legacy_jsonl",
        }

    for line in reversed(trace_lines):
        if line.get("type") != "llm_call":
            continue
        if line.get("role") != "executor":
            continue
        body = line.get("response_body") or line.get("response_preview")
        if body:
            return {
                "text": str(body),
                "source": "trace_executor",
                "trace_role": line.get("role"),
                "trace_model": line.get("model"),
            }

    for line in reversed(trace_lines):
        if line.get("type") != "llm_call":
            continue
        body = line.get("response_body") or line.get("response_preview")
        if body:
            return {
                "text": str(body),
                "source": "trace_any_role",
                "trace_role": line.get("role"),
                "trace_model": line.get("model"),
            }

    preview = response.get("output_preview")
    if preview:
        digest: dict[str, Any] = {
            "text": str(preview),
            "source": "digest_preview",
        }
        if response.get("output_sha256"):
            digest["output_sha256"] = response["output_sha256"]
        if response.get("output_bytes") is not None:
            digest["output_bytes"] = response["output_bytes"]
        return digest

    if record.get("error"):
        return {"text": str(record["error"]), "source": "error"}

    return {"text": "", "source": "none"}


def _resolve_context_ref(workspace: str | Path, ref: dict[str, Any]) -> dict[str, Any]:
    pointer = {
        "kind": ref.get("kind"),
        "id": ref.get("id"),
        "corpus": ref.get("corpus"),
        "sha256": ref.get("sha256"),
        "score": ref.get("score"),
    }
    if ref.get("snippet"):
        return {
            "pointer": pointer,
            "source": "inline_jsonl",
            "snippet": ref.get("snippet"),
            "metadata": ref.get("metadata") or {},
        }

    corpus = ref.get("corpus")
    ref_id = ref.get("id")
    if not ref_id:
        return {"pointer": pointer, "source": "unresolved", "error": "missing id"}

    if corpus == CORPUS_DELEGATION:
        row = DelegationRagDB(workspace).get_delegation(str(ref_id))
        if row:
            return {
                "pointer": pointer,
                "source": "delegation_rag.db",
                "snippet": row.get("checkpoint_summary") or row.get("task_preview"),
                "metadata": {
                    "spec_path": row.get("spec_path"),
                    "outcome": row.get("outcome"),
                    "timestamp_end": row.get("timestamp_end"),
                    "files_changed": row.get("files_changed"),
                },
            }
        return {"pointer": pointer, "source": "unresolved", "error": "not in delegation_rag.db"}

    if corpus == CORPUS_WORKSPACE_FILES or ref.get("kind") == "workspace_file":
        row = WorkspaceRagDB(workspace).get_file(str(ref_id))
        if row:
            return {
                "pointer": pointer,
                "source": "workspace_rag.db",
                "snippet": row.get("llm_summary"),
                "metadata": {
                    "path": row.get("path"),
                    "symbol_list": row.get("symbol_list"),
                    "indexed_at": row.get("indexed_at"),
                },
            }
        return {"pointer": pointer, "source": "unresolved", "error": "not in workspace_rag.db"}

    return {"pointer": pointer, "source": "unresolved", "error": f"unknown corpus: {corpus}"}


def _summarize_dual_capture(trace_lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    has_dual_capture = any(
        line.get("type") in {"backend_llm_call", "proxy_llm_call"} for line in trace_lines
    )
    if not has_dual_capture:
        return None
    paired = pair_dual_capture_events(trace_lines)
    return {
        "summary": paired["summary"],
        "calls": paired["calls"],
        "gaps": paired["gaps"],
        "bl507": paired["bl507"],
    }


def _annotate_pairs(events: list[dict[str, Any]], paired_calls: list[dict[str, Any]]) -> None:
    """Annotate proxy/backend events in-place with _pair_status and _pair_call_key."""
    lookup: dict[tuple[Any, Any], str] = {}
    for row in paired_calls:
        key = (row.get("step_index"), row.get("call_index"))
        lookup[key] = row.get("status", "matched")

    for ev in events:
        if ev.get("type") not in ("proxy_llm_call", "backend_llm_call"):
            continue
        step = ev.get("step_index")
        call = ev.get("call_index")
        key = (step, call)
        status = lookup.get(key)
        if status is not None:
            ev["_pair_status"] = status
            ev["_pair_call_key"] = f"{step}:{call}"


def _aggregate_tokens(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum input/output/thinking tokens across backend_llm_call and llm_call events."""
    total_input: int | None = None
    total_output: int | None = None
    total_thinking: int | None = None

    for ev in events:
        ev_type = ev.get("type")
        if ev_type == "backend_llm_call":
            usage = ev.get("usage") or {}
            inp = usage.get("input")
            out = usage.get("output")
            think = ev.get("thinking_tokens")
        elif ev_type == "llm_call":
            tokens = ev.get("tokens") or {}
            inp = tokens.get("input")
            out = tokens.get("output")
            think = tokens.get("reasoning_tokens")
        else:
            continue

        if inp is not None:
            total_input = (total_input or 0) + inp
        if out is not None:
            total_output = (total_output or 0) + out
        if think is not None:
            total_thinking = (total_thinking or 0) + think

    return {"input": total_input, "output": total_output, "thinking": total_thinking}


# ── Canonical event model (viewer-and-trace-design.md) ──────────────────

# compile_event stage → (display_name, direction, scope)
# None = data-only, folded into a synthetic event rather than its own row.
_COMPILE_STAGE_MAP: dict[str, tuple[str, str, str] | None] = {
    "validation_input":      ("mcp.spec_validation", "→", "mcp"),
    "validation_output":     ("mcp.spec_validation", "←", "mcp"),
    "planner_input":         ("mcp.planner",         "→", "mcp"),
    "planner_output":        ("mcp.planner",         "←", "mcp"),
    # Backward-compat: old traces used architect_* names
    "architect_input":       ("mcp.planner",         "→", "mcp"),
    "architect_output":      ("mcp.planner",         "←", "mcp"),
    "builder_input":         ("mcp.context_builder", "→", "mcp"),
    "builder_output":        ("mcp.context_builder", "←", "mcp"),
    "mechanical_brief":      ("mcp.brief",           "→", "mcp"),  # always shown
    "final_executor_prompt": None,  # data folded into synthetic mcp→executor
}

# compile_event name → llm_call role that goes with it
_COMPILE_NAME_TO_ROLE: dict[str, str] = {
    "mcp.spec_validation": "spec_validation",
    "mcp.planner":         "planner_pass",
    "mcp.context_builder": "context_builder",
}

# llm_call roles that are folded into other events — never shown as own rows
# Keep "architect_pass" so old traces still fold correctly (P11-008 backward compat).
_FOLD_LLM_ROLES = frozenset({
    "spec_validation",
    "planner_pass",
    "architect_pass",  # legacy — old traces
    "context_builder",
    "executor",
})

_INDEX_ROLE = "workspace_summarizer"


def _parse_index_file_path(text: str) -> str | None:
    """Extract repo-relative path from workspace summarizer prompt."""
    for line in text.splitlines():
        if line.startswith("File path:"):
            path = line.split(":", 1)[1].strip()
            return path or None
    return None


def _decompose_prompt(raw_request: str) -> dict[str, Any]:
    """Parse a raw HTTP request body and decompose the prompt structure.

    Returns a dict with:
      prompt_format   : "openai" | "anthropic" | "gemini" | "unknown"
      system_prompt   : str   (system instruction text, may be "")
      system_chars    : int
      task            : str   (last user message = the actual task sent)
      task_chars      : int
      context_turns   : int   (prior user/assistant exchange pairs before the task)
      context_chars   : int   (total chars of all context messages)
      context         : str   (formatted prior messages, role-labeled)
      total_messages  : int

    When prompt_format != "openai", only prompt_format is populated reliably —
    add a handler for that format when needed.
    """
    result: dict[str, Any] = {
        "prompt_format": "unknown",
        "system_prompt": "",
        "system_chars": 0,
        "task": "",
        "task_chars": 0,
        "context_turns": 0,
        "context_chars": 0,
        "context": "",
        "total_messages": 0,
    }
    if not raw_request:
        return result

    try:
        req = json.loads(raw_request)
    except (json.JSONDecodeError, ValueError):
        return result

    if not isinstance(req, dict):
        return result

    # ── Format detection ─────────────────────────────────────────────────────
    # Anthropic native: top-level "system" key (string) and no "contents"
    if isinstance(req.get("system"), str) and "contents" not in req:
        result["prompt_format"] = "anthropic"
        # Anthropic native not fully decomposed yet — flag for future work
        return result

    # Gemini native: "contents" key instead of "messages"
    if "contents" in req:
        result["prompt_format"] = "gemini"
        return result

    # OpenAI format: "messages" list
    messages = req.get("messages")
    if not isinstance(messages, list):
        return result

    result["prompt_format"] = "openai"
    result["total_messages"] = len(messages)

    def _content_str(content: Any) -> str:
        """Flatten message content to a plain string."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            # list of {"type": "text", "text": "..."} blocks
            return " ".join(
                block.get("text", "") for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        return str(content) if content else ""

    system_parts: list[str] = []
    non_system: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "system":
            system_parts.append(_content_str(m.get("content", "")))
        else:
            non_system.append(m)

    system_text = "\n".join(system_parts)
    result["system_prompt"] = system_text
    result["system_chars"] = len(system_text)

    # Last user message = the actual task; everything before = context
    user_msgs = [m for m in non_system if m.get("role") == "user"]
    if user_msgs:
        task_text = _content_str(user_msgs[-1].get("content", ""))
        result["task"] = task_text
        result["task_chars"] = len(task_text)

    # Context = all non-system messages except the last user message (the task)
    context_msgs = non_system[:-1] if non_system else []
    asst_msgs = [m for m in context_msgs if m.get("role") == "assistant"]
    result["context_turns"] = len(asst_msgs)
    context_parts: list[str] = []
    for m in context_msgs:
        role = m.get("role") or "?"
        text = _content_str(m.get("content", ""))
        context_parts.append(f"[{role}]\n{text}")
    context_text = "\n\n".join(context_parts)
    result["context"] = context_text
    result["context_chars"] = len(context_text)

    return result


_SKIP_REQUEST_KEYS = frozenset({
    "messages", "model", "prompt", "input", "contents", "system",
})


def _fmt_param_value(key: str, value: Any) -> Any:
    """Normalize a request-body field for compact viewer display."""
    if value is None:
        return None
    if key == "tools" and isinstance(value, list):
        names: list[str] = []
        for tool in value:
            if not isinstance(tool, dict):
                continue
            fn = tool.get("function")
            if isinstance(fn, dict) and fn.get("name"):
                names.append(str(fn["name"]))
            elif tool.get("type"):
                names.append(str(tool["type"]))
        summary = f"{len(value)} tool{'s' if len(value) != 1 else ''}"
        if names:
            shown = names[:6]
            extra = f" +{len(names) - 6}" if len(names) > 6 else ""
            return f"{summary}: {', '.join(shown)}{extra}"
        return summary
    if key == "response_format" and isinstance(value, dict):
        fmt_type = value.get("type")
        return fmt_type or json.dumps(value, separators=(",", ":"))
    if key == "tool_choice" and isinstance(value, dict):
        return value.get("type") or json.dumps(value, separators=(",", ":"))
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, dict):
        compact = json.dumps(value, separators=(",", ":"))
        return compact if len(compact) <= 80 else compact[:77] + "…"
    if isinstance(value, list):
        return f"[{len(value)} items]"
    return str(value)


def _extract_request_params(raw_request: str) -> dict[str, Any]:
    """Extract generation/request flags from raw HTTP body (excluding messages/model)."""
    result: dict[str, Any] = {}
    if not raw_request:
        return result
    try:
        req = json.loads(raw_request)
    except (json.JSONDecodeError, ValueError):
        return result
    if not isinstance(req, dict):
        return result

    for key, value in req.items():
        if key in _SKIP_REQUEST_KEYS or value is None:
            continue
        formatted = _fmt_param_value(key, value)
        if formatted is not None:
            result[key] = formatted
    return result


def _fmt_tokens(tok: dict[str, Any] | None) -> str:
    if not tok:
        return ""
    parts = []
    if tok.get("input") is not None:
        parts.append(f"{tok['input']:,}↑")
    if tok.get("output") is not None:
        parts.append(f"{tok['output']:,}↓")
    thinking = tok.get("thinking")
    if thinking is None:
        thinking = tok.get("reasoning_tokens")
    if thinking is not None:
        parts.append(f"think={thinking:,}")
    return " ".join(parts)


def _reposition_mcp_executor_handoff(events: list[dict[str, Any]]) -> None:
    """Place mcp→executor before the first executor→llm when trace logged it late."""
    mcp_ev = next((e for e in events if e.get("name") == "mcp→executor"), None)
    first_llm = next((e for e in events if e.get("name") == "executor→llm"), None)
    if mcp_ev is None or first_llm is None:
        return
    mcp_ts = mcp_ev.get("timestamp") or ""
    llm_ts = first_llm.get("timestamp") or ""
    if not mcp_ts or not llm_ts or mcp_ts <= llm_ts:
        return
    mcp_idx = events.index(mcp_ev)
    llm_idx = events.index(first_llm)
    if mcp_idx < llm_idx:
        return
    events.pop(mcp_idx)
    detail = mcp_ev.setdefault("detail", {})
    detail["logged_after_executor"] = True
    events.insert(llm_idx, mcp_ev)


def _insert_post_delegate_index_header(events: list[dict[str, Any]]) -> None:
    """Add a virtual section header before post-delegate RAG file-index rows."""
    index_idxs = [i for i, e in enumerate(events) if e.get("name") == "mcp→index"]
    if not index_idxs:
        return
    first_i = index_idxs[0]
    count = len(index_idxs)
    ts = events[first_i].get("timestamp")
    header: dict[str, Any] = {
        "id": "mcp.post.index",
        "name": "mcp→post",
        "direction": "·",
        "scope": "mcp",
        "is_virtual": True,
        "is_boundary": True,
        "is_divider": False,
        "timestamp": ts,
        "summary": f"workspace file RAG · {count} file{'s' if count != 1 else ''}",
        "detail": {
            "housekeeping": True,
            "index_count": count,
            "description": (
                "Post-delegate housekeeping: MCP summarizes each changed file "
                "into workspace_rag.db for future search and file picker."
            ),
        },
        "children": [],
    }
    events.insert(first_i, header)


def _build_view_events(
    record: dict[str, Any],
    trace_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the canonical ViewEvent list from a delegation record + raw trace lines.

    All mapping of raw log entry types to display names happens here.
    The viewer JS receives this list and renders it without knowing raw log format.
    """
    # ── Pre-scan: build lookup tables ──────────────────────────────────────
    proxy_by_key: dict[tuple[Any, Any], dict[str, Any]] = {}
    backend_by_key: dict[tuple[Any, Any], dict[str, Any]] = {}
    llm_by_role: dict[str, list[dict[str, Any]]] = {}
    compile_by_stage: dict[str, dict[str, Any]] = {}

    for line in trace_lines:
        t = line.get("type")
        if t == "trace_header":
            continue
        elif t == "proxy_llm_call":
            proxy_by_key[(line.get("step_index"), line.get("call_index"))] = line
        elif t == "backend_llm_call":
            backend_by_key[(line.get("step_index"), line.get("call_index"))] = line
        elif t == "llm_call":
            role = line.get("role") or ""
            llm_by_role.setdefault(role, []).append(line)
        elif t == "compile_event":
            stage = line.get("stage") or ""
            compile_by_stage[stage] = line

    # Did the executor actually run?
    # True only if executor-loop LLM pairs (step-indexed) or executor actions ran.
    # Helper LLM calls (clarity, spec_validation, planner) have no step_index and
    # must NOT count — otherwise a preloop clarity block is misrendered as an
    # executor turn that produced the clarity questions as output.
    _executor_ran = bool(
        any(k[0] is not None for k in proxy_by_key)
        or any(k[0] is not None for k in backend_by_key)
        or compile_by_stage.get("final_executor_prompt")
        or any(l.get("type") in ("action", "tool_call") for l in trace_lines)
    )

    # ── Main pass: emit ViewEvents (file order), then sort by timestamp ───────
    events: list[dict[str, Any]] = []
    emit_order = 0
    seen_step_dividers: set[Any] = set()

    def _emit(ev: dict[str, Any]) -> None:
        nonlocal emit_order
        ev["_sort_order"] = emit_order
        emit_order += 1
        events.append(ev)

    def _view_event(
        *,
        ev_id: str,
        name: str,
        direction: str,
        scope: str,
        timestamp: str | None,
        summary: str,
        detail: dict[str, Any],
        is_virtual: bool = False,
        is_boundary: bool = True,
        is_divider: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": ev_id,
            "name": name,
            "direction": direction,
            "scope": scope,
            "is_virtual": is_virtual,
            "is_boundary": is_boundary,
            "is_divider": is_divider,
            "timestamp": timestamp,
            "summary": summary,
            "detail": detail,
            "children": [],
        }

    # 1 — host→mcp (synthetic, from delegation record)
    mcp_req = record.get("mcp_request") or {}
    task_text = str(mcp_req.get("task") or mcp_req.get("prompt") or "")
    task_preview = (task_text[:120] + "…") if len(task_text) > 120 else task_text
    _emit(_view_event(
        ev_id="host.mcp.in",
        name="host→mcp",
        direction="→",
        scope="host",
        timestamp=record.get("timestamp_start") or mcp_req.get("timestamp"),
        summary=task_preview,
        detail={
            "task": task_text,
            "model": mcp_req.get("model"),
            "workspace": record.get("workspace_path"),
            "spec_path": mcp_req.get("spec_path"),
            "files_requested": record.get("files_requested") or [],
        },
    ))

    # Trace lines in file order (= log order)
    for line in trace_lines:
        t = line.get("type")

        if t == "trace_header":
            continue

        elif t == "compile_event":
            stage = line.get("stage") or ""

            # Virtual handoff at the logged compile timestamp (not reordered)
            if stage == "final_executor_prompt":
                body = line.get("body") or ""
                brief = line.get("brief") or body[:120]
                _emit(_view_event(
                    ev_id="mcp.executor.in",
                    name="mcp→executor",
                    direction="→",
                    scope="mcp",
                    timestamp=line.get("timestamp"),
                    summary=brief or task_preview,
                    detail={
                        "task": task_text,
                        "brief": brief,
                        "body": body,
                        "byte_count": line.get("byte_count"),
                        "sha256": line.get("sha256"),
                    },
                    is_virtual=True,
                    is_boundary=True,
                ))
                continue

            mapping = _COMPILE_STAGE_MAP.get(stage)
            if mapping is None:
                continue

            disp_name, direction, scope = mapping
            status = line.get("status")        # "ok" | "skipped" | "error" | None
            stage_detail_txt = line.get("detail") or ""
            is_skipped = status == "skipped"

            # For ← events, attach the corresponding LLM call data
            llm_detail: dict[str, Any] | None = None
            if direction == "←" and not is_skipped:
                role = _COMPILE_NAME_TO_ROLE.get(disp_name)
                if role:
                    role_calls = llm_by_role.get(role, [])
                    if role_calls:
                        lc = role_calls[0]
                        llm_detail = {
                            "model": lc.get("model"),
                            "tokens": lc.get("tokens"),
                            "duration_ms": lc.get("duration_ms"),
                            "prompt_preview": lc.get("prompt_preview"),
                            "response_preview": lc.get("response_preview"),
                            "prompt_body": lc.get("prompt_body"),
                            "response_body": lc.get("response_body"),
                            # llm_call uses reasoning_* keys for helper thoughts.
                            "thinking_body": lc.get("reasoning_body"),
                            "thinking_preview": lc.get("reasoning_preview"),
                            "policy_applied": lc.get("policy_applied"),
                        }

            # For context_builder, fold mechanical_brief
            mech = compile_by_stage.get("mechanical_brief") if "builder" in stage else None

            body = line.get("body") or ""
            brief = line.get("brief") or body[:120]
            tok = llm_detail.get("tokens") if llm_detail else None

            if is_skipped:
                summary_parts = [f"skipped: {stage_detail_txt}" if stage_detail_txt else "skipped"]
            else:
                summary_parts = [brief[:120]] if brief else [stage]
                if tok:
                    summary_parts.append(_fmt_tokens(tok))

            detail: dict[str, Any] = {
                "stage":      stage,
                "status":     status,
                "brief":      brief,
                "body":       body,
                "byte_count": line.get("byte_count"),
                "sha256":     line.get("sha256"),
            }
            if stage_detail_txt:
                detail["skip_reason"] = stage_detail_txt
            if llm_detail:
                detail["llm"] = llm_detail
                detail["thinking_tokens"] = (llm_detail.get("tokens") or {}).get("reasoning_tokens")
            if mech:
                detail["mechanical_brief"] = {
                    "body":       mech.get("body"),
                    "brief":      mech.get("brief"),
                    "byte_count": mech.get("byte_count"),
                }

            ev_id_clean = disp_name.replace("→", ".in").replace("←", ".out").replace(".", "_")
            suffix = "skipped" if is_skipped else direction.replace("→", "in").replace("←", "out")
            _emit(_view_event(
                ev_id=f"{ev_id_clean}.{suffix}",
                name=disp_name,
                direction="·" if is_skipped else direction,
                scope=scope,
                timestamp=line.get("timestamp"),
                summary=" · ".join(summary_parts),
                detail=detail,
                is_virtual=False,
                is_boundary=not is_skipped,
            ))

        elif t == "llm_call":
            role = line.get("role") or ""
            if role in _FOLD_LLM_ROLES:
                continue
            tok = line.get("tokens")
            model = line.get("model") or ""
            duration = line.get("duration_ms")

            if role == _INDEX_ROLE:
                prompt = line.get("prompt_body") or line.get("prompt_preview") or ""
                index_path = _parse_index_file_path(prompt)
                summary_parts = [p for p in [
                    index_path,
                    model,
                    _fmt_tokens(tok),
                    f"{duration}ms" if duration else None,
                ] if p]
                _emit(_view_event(
                    ev_id=f"mcp.index.{line.get('call_index', 0)}",
                    name="mcp→index",
                    direction="→",
                    scope="mcp",
                    timestamp=line.get("timestamp"),
                    summary=" · ".join(summary_parts),
                    detail={
                        "role": role,
                        "index_path": index_path,
                        "housekeeping": True,
                        "model": model,
                        "tokens": tok,
                        "thinking_tokens": (tok or {}).get("reasoning_tokens"),
                        "thinking_body": line.get("reasoning_body"),
                        "thinking_preview": line.get("reasoning_preview"),
                        "duration_ms": duration,
                        "prompt_body": line.get("prompt_body"),
                        "response_body": line.get("response_body"),
                        "prompt_preview": line.get("prompt_preview"),
                        "response_preview": line.get("response_preview"),
                        "policy_applied": line.get("policy_applied"),
                    },
                    is_boundary=False,
                ))
                continue

            # Other unfolder helper roles get their own rows
            summary_parts = [p for p in [model, _fmt_tokens(tok), f"{duration}ms" if duration else None] if p]
            _emit(_view_event(
                ev_id=f"mcp.{role}.{line.get('call_index', 0)}",
                name=f"mcp.{role}",
                direction="⇄",
                scope="mcp",
                timestamp=line.get("timestamp"),
                summary=" · ".join(summary_parts),
                detail={
                    "role": role,
                    "model": model,
                    "tokens": tok,
                    "thinking_tokens": (tok or {}).get("reasoning_tokens"),
                    "thinking_body": line.get("reasoning_body"),
                    "thinking_preview": line.get("reasoning_preview"),
                    "duration_ms": duration,
                    "prompt_body": line.get("prompt_body"),
                    "response_body": line.get("response_body"),
                    "prompt_preview": line.get("prompt_preview"),
                    "response_preview": line.get("response_preview"),
                    "policy_applied": line.get("policy_applied"),
                },
                is_boundary=False,
            ))

        elif t == "action":
            step = line.get("step_index")
            if step not in seen_step_dividers:
                seen_step_dividers.add(step)
                kind = line.get("kind") or ""
                _emit(_view_event(
                    ev_id=f"executor.step.{step}",
                    name=f"executor.step{{{step}}}",
                    direction="·",
                    scope="executor",
                    timestamp=line.get("timestamp"),
                    summary=kind,
                    detail={"step_index": step, "kind": kind, "detail": line.get("detail")},
                    is_boundary=False,
                    is_divider=True,
                ))

        elif t == "proxy_llm_call":
            step = line.get("step_index")
            call = line.get("call_index")
            # Helper LLM proxies (no step_index) are covered by llm_call / compile rows
            if step is None:
                continue
            key = (step, call)
            backend = backend_by_key.get(key)
            model = (backend.get("model") if backend else None) or line.get("model") or ""
            n = step if step is not None else "?"
            m = call if call is not None else "?"

            # Safety: emit step divider if not yet seen (action might be missing)
            if step is not None and step not in seen_step_dividers:
                seen_step_dividers.add(step)
                _emit(_view_event(
                    ev_id=f"executor.step.{step}",
                    name=f"executor.step{{{step}}}",
                    direction="·",
                    scope="executor",
                    timestamp=line.get("timestamp"),
                    summary="(implicit step start)",
                    detail={"step_index": step},
                    is_boundary=False,
                    is_divider=True,
                ))

            usage = (backend.get("usage") or {}) if backend else {}
            tok_in = usage.get("input")
            summary_parts = [p for p in [
                model,
                f"step {n}·{m}",
                f"{tok_in:,} in" if tok_in is not None else None,
            ] if p]
            raw_req = line.get("raw_request") or ""
            prompt = _decompose_prompt(raw_req)
            _emit(_view_event(
                ev_id=f"executor.llm.{n}.{m}.send",
                name="executor→llm",
                direction="→",
                scope="executor",
                timestamp=line.get("request_received_at") or line.get("timestamp"),
                summary=" · ".join(summary_parts),
                detail={
                    "step_index": step,
                    "call_index": call,
                    "model": model,
                    "tokens_in": tok_in,
                    "call_type": (backend.get("call_type") if backend else None),
                    "status_code": line.get("status_code"),
                    "wire_latency_ms": line.get("wire_latency_ms"),
                    "attribution_source": line.get("attribution_source"),
                    # decomposed prompt (format-aware)
                    "prompt_format":   prompt["prompt_format"],
                    "system_prompt":   prompt["system_prompt"],
                    "system_chars":    prompt["system_chars"],
                    "task":            prompt["task"],
                    "task_chars":      prompt["task_chars"],
                    "context_turns":   prompt["context_turns"],
                    "context_chars":   prompt["context_chars"],
                    "context":         prompt["context"],
                    "total_messages":  prompt["total_messages"],
                    # request flags / generation params (from wire body)
                    "request_params":  _extract_request_params(raw_req),
                    "policy_applied":  (backend.get("policy_applied") if backend else None),
                    # raw captures (for advanced inspection)
                    "raw_request":     raw_req or None,
                    "prompt_preview":  (backend.get("prompt_preview") if backend else None),
                },
            ))

        elif t == "backend_llm_call":
            step = line.get("step_index")
            call = line.get("call_index")
            key = (step, call)
            proxy = proxy_by_key.get(key)
            model = line.get("model") or (proxy.get("model") if proxy else None) or ""
            n = step if step is not None else "?"
            m = call if call is not None else "?"

            usage = line.get("usage") or {}
            tok_out = usage.get("output")
            think_tok = line.get("thinking_tokens")
            duration = line.get("duration_ms") or (proxy.get("wire_latency_ms") if proxy else None)
            status = proxy.get("status_code") if proxy else None

            summary_parts = [p for p in [
                f"{tok_out:,} out" if tok_out is not None else None,
                f"{think_tok:,} think" if think_tok else None,
                f"{duration}ms" if duration else None,
                f"HTTP {status}" if status else None,
            ] if p]
            _emit(_view_event(
                ev_id=f"executor.llm.{n}.{m}.recv",
                name="llm→executor",
                direction="←",
                scope="executor",
                timestamp=line.get("timestamp"),
                summary=" · ".join(summary_parts),
                detail={
                    "step_index": step,
                    "call_index": call,
                    "model": model,
                    "tokens_out":       usage.get("output"),
                    "tokens_in":        usage.get("input"),
                    "thinking_tokens":  think_tok,
                    "duration_ms":      line.get("duration_ms"),
                    "status_code":      status,
                    "wire_latency_ms":  proxy.get("wire_latency_ms") if proxy else None,
                    "policy_applied":   line.get("policy_applied"),
                    "response_body":    line.get("response_body"),
                    "response_preview": line.get("response_preview"),
                    "thinking_body":    line.get("thinking_body"),
                    "thinking_preview": line.get("thinking_preview"),
                    # raw HTTP response for advanced inspection
                    "raw_response":     proxy.get("raw_response") if proxy else None,
                },
            ))

        elif t == "supervisor_loop_start":
            # P12-001 unified agent loop. Legacy traces also use this type but carry
            # turn_count/aborts_count (no max_turns) — both shapes render here.
            _summary = (
                f"start · loop={line.get('loop_id') or '?'}"
                + (f" · max_turns={line.get('max_turns')}" if line.get("max_turns") is not None else "")
            )
            _emit(_view_event(
                ev_id=f"mcp.supervisor.loop.start.{line.get('loop_id') or line.get('timestamp')}",
                name="mcp.supervisor_loop",
                direction="→",
                scope="mcp",
                timestamp=line.get("timestamp"),
                summary=_summary,
                detail={
                    "event_type": "supervisor_loop_start",
                    "loop_id": line.get("loop_id"),
                    "max_turns": line.get("max_turns"),
                    # legacy fields (backward compat)
                    "turn_count": line.get("turn_count"),
                    "aborts_count": line.get("aborts_count"),
                },
                is_boundary=False,
            ))

        elif t == "supervisor_turn_start":
            _emit(_view_event(
                ev_id=f"mcp.supervisor.turn.start.{line.get('turn_index')}.{line.get('timestamp')}",
                name="mcp.supervisor_turn",
                direction="→",
                scope="mcp",
                timestamp=line.get("timestamp"),
                summary=f"turn {line.get('turn_index')} start",
                detail={
                    "event_type": "supervisor_turn_start",
                    "loop_id": line.get("loop_id"),
                    "turn_index": line.get("turn_index"),
                },
                is_boundary=False,
            ))

        elif t == "supervisor_turn_end":
            _checks = line.get("checks_result") or {}
            _checks_outcome = _checks.get("outcome") if isinstance(_checks, dict) else None
            _emit(_view_event(
                ev_id=f"mcp.supervisor.turn.end.{line.get('turn_index')}.{line.get('timestamp')}",
                name="mcp.supervisor_turn",
                direction="←",
                scope="mcp",
                timestamp=line.get("timestamp"),
                summary=" · ".join(
                    p for p in [
                        f"turn {line.get('turn_index')} end" if line.get("turn_index") is not None else "turn end",
                        str(line.get("worker_outcome") or ""),
                        f"checks={_checks_outcome}" if _checks_outcome else None,
                        f"{line.get('duration_ms')}ms" if line.get("duration_ms") is not None else None,
                    ]
                    if p
                ),
                detail={
                    "event_type": "supervisor_turn_end",
                    "loop_id": line.get("loop_id"),
                    "turn_index": line.get("turn_index"),
                    "worker_outcome": line.get("worker_outcome"),
                    "checks_result": line.get("checks_result"),
                    "duration_ms": line.get("duration_ms"),
                },
                is_boundary=False,
            ))

        elif t == "supervisor_decision":
            _tok = line.get("tokens") or {}
            _emit(_view_event(
                ev_id=f"mcp.supervisor.decision.{line.get('turn_index')}.{line.get('timestamp')}",
                name="mcp.supervisor_turn",
                direction="⇄",
                scope="mcp",
                timestamp=line.get("timestamp"),
                summary=" · ".join(
                    p for p in [
                        f"turn {line.get('turn_index')}" if line.get("turn_index") is not None else None,
                        str(line.get("action") or ""),
                        str(line.get("model") or ""),
                        f"{line.get('duration_ms')}ms" if line.get("duration_ms") else None,
                    ]
                    if p
                ),
                detail={
                    "event_type": "supervisor_decision",
                    "loop_id": line.get("loop_id"),
                    "turn_index": line.get("turn_index"),
                    "action": line.get("action"),
                    "reason": line.get("reason"),
                    "model": line.get("model"),
                    "tokens": line.get("tokens"),
                    "duration_ms": line.get("duration_ms"),
                },
                is_boundary=False,
            ))

        elif t == "supervisor_outer_loop_start":
            _emit(_view_event(
                ev_id=f"mcp.supervisor.outer.start.{line.get('loop_id') or line.get('timestamp')}",
                name="mcp.supervisor_outer_loop",
                direction="→",
                scope="mcp",
                timestamp=line.get("timestamp"),
                summary=f"start · loop={line.get('loop_id') or '?'}",
                detail={
                    "event_type": "supervisor_outer_loop_start",
                    "loop_id": line.get("loop_id"),
                    "cycle_index": line.get("cycle_index"),
                    "reason": line.get("reason"),
                },
                is_boundary=False,
            ))

        elif t == "supervisor_outer_loop_decision":
            _emit(_view_event(
                ev_id=f"mcp.supervisor.outer.decision.{line.get('cycle_index') or line.get('timestamp')}",
                name="mcp.supervisor_outer_loop",
                direction="⇄",
                scope="mcp",
                timestamp=line.get("timestamp"),
                summary=" · ".join(
                    p for p in [
                        f"cycle={line.get('cycle_index')}" if line.get("cycle_index") is not None else None,
                        str(line.get("action") or ""),
                        str(line.get("reviewer_outcome") or ""),
                    ]
                    if p
                ),
                detail={
                    "event_type": "supervisor_outer_loop_decision",
                    "loop_id": line.get("loop_id"),
                    "cycle_index": line.get("cycle_index"),
                    "action": line.get("action"),
                    "reason": line.get("reason"),
                    "reviewer_outcome": line.get("reviewer_outcome"),
                },
                is_boundary=False,
            ))

        elif t == "supervisor_outer_loop_end":
            _emit(_view_event(
                ev_id=f"mcp.supervisor.outer.end.{line.get('loop_id') or line.get('timestamp')}",
                name="mcp.supervisor_outer_loop",
                direction="←",
                scope="mcp",
                timestamp=line.get("timestamp"),
                summary=" · ".join(
                    p for p in [
                        f"end={line.get('reason')}" if line.get("reason") else "end",
                        f"action={line.get('action')}" if line.get("action") else None,
                        str(line.get("reviewer_outcome") or ""),
                    ]
                    if p
                ),
                detail={
                    "event_type": "supervisor_outer_loop_end",
                    "loop_id": line.get("loop_id"),
                    "cycle_index": line.get("cycle_index"),
                    "action": line.get("action"),
                    "reason": line.get("reason"),
                    "reviewer_outcome": line.get("reviewer_outcome"),
                },
                is_boundary=False,
            ))

        elif t == "supervisor_turn_decision":
            _emit(_view_event(
                ev_id=f"mcp.supervisor.turn.{line.get('turn_index') or line.get('timestamp')}",
                name="mcp.supervisor_turn",
                direction="⇄",
                scope="mcp",
                timestamp=line.get("timestamp"),
                summary=" · ".join(
                    p for p in [
                        f"turn {line.get('turn_index')}" if line.get("turn_index") is not None else None,
                        str(line.get("action") or ""),
                        str(line.get("risk_level") or ""),
                        f"{line.get('duration_ms')}ms" if line.get("duration_ms") is not None else None,
                    ]
                    if p
                ),
                detail={
                    "event_type": "supervisor_turn_decision",
                    "loop_id": line.get("loop_id"),
                    "turn_index": line.get("turn_index"),
                    "action": line.get("action"),
                    "reason": line.get("reason"),
                    "risk_level": line.get("risk_level"),
                    "question_present": line.get("question_present"),
                    "llm_used": line.get("llm_used"),
                    "duration_ms": line.get("duration_ms"),
                },
                is_boundary=False,
            ))

        elif t == "supervisor_loop_end":
            # P12-001 unified agent loop carries turns_completed/final_action; legacy
            # traces carry turn_count/aborts_count/final_decision. Render both shapes.
            _turns = (
                line.get("turns_completed")
                if line.get("turns_completed") is not None
                else line.get("turn_count")
            )
            _emit(_view_event(
                ev_id=f"mcp.supervisor.loop.end.{line.get('loop_id') or line.get('timestamp')}",
                name="mcp.supervisor_loop",
                direction="←",
                scope="mcp",
                timestamp=line.get("timestamp"),
                summary=" · ".join(
                    p for p in [
                        f"end={line.get('end_reason')}" if line.get("end_reason") else "end",
                        f"action={line.get('final_action')}" if line.get("final_action") else None,
                        f"turns={_turns}" if _turns is not None else None,
                        f"aborts={line.get('aborts_count')}" if line.get("aborts_count") is not None else None,
                    ]
                    if p
                ),
                detail={
                    "event_type": "supervisor_loop_end",
                    "loop_id": line.get("loop_id"),
                    "end_reason": line.get("end_reason"),
                    "final_action": line.get("final_action"),
                    "turns_completed": line.get("turns_completed"),
                    # legacy fields (backward compat)
                    "final_decision": line.get("final_decision"),
                    "turn_count": line.get("turn_count"),
                    "aborts_count": line.get("aborts_count"),
                },
                is_boundary=False,
            ))

        elif t == "supervisor_paused":
            _reason = line.get("pause_reason") or ""
            _questions = line.get("questions") or []
            _summary_parts = [p for p in [
                "paused",
                f"reason={_reason}" if _reason else None,
                f"{len(_questions)} question(s)" if _questions else None,
            ] if p]
            _emit(_view_event(
                ev_id=f"agent.supervisor.paused.{line.get('timestamp')}",
                name="agent.supervisor_paused",
                direction="·",
                scope="agent",
                timestamp=line.get("timestamp"),
                summary=" · ".join(_summary_parts),
                detail={
                    "event_type": "supervisor_paused",
                    "resume_token": line.get("resume_token"),
                    "turn_index": line.get("turn_index"),
                    "pause_reason": _reason,
                    "questions": _questions,
                    "expires_at": line.get("expires_at"),
                    "raw": line,
                },
                is_boundary=False,
                is_divider=False,
            ))

        elif t == "supervisor_resumed":
            _reason = line.get("resume_reason") or ""
            _summary_parts = [p for p in [
                "resumed",
                f"reason={_reason}" if _reason else None,
                f"turn={line.get('resumed_at_turn')}" if line.get("resumed_at_turn") is not None else None,
            ] if p]
            _emit(_view_event(
                ev_id=f"agent.supervisor.resumed.{line.get('timestamp')}",
                name="agent.supervisor_resumed",
                direction="·",
                scope="agent",
                timestamp=line.get("timestamp"),
                summary=" · ".join(_summary_parts),
                detail={
                    "event_type": "supervisor_resumed",
                    "resume_token": line.get("resume_token"),
                    "resumed_at_turn": line.get("resumed_at_turn"),
                    "project_key": line.get("project_key"),
                    "host_answer_chars": line.get("host_answer_chars"),
                    "resume_reason": _reason,
                    "raw": line,
                },
                is_boundary=False,
                is_divider=False,
            ))

        elif t == "supervisor_state_abandoned":
            _reason = line.get("pause_reason") or ""
            _emit(_view_event(
                ev_id=f"agent.supervisor.abandoned.{line.get('timestamp')}",
                name="agent.supervisor_state_abandoned",
                direction="·",
                scope="agent",
                timestamp=line.get("timestamp"),
                summary="state abandoned" + (f" · reason={_reason}" if _reason else ""),
                detail={
                    "event_type": "supervisor_state_abandoned",
                    "resume_token": line.get("resume_token"),
                    "project_key": line.get("project_key"),
                    "pause_reason": _reason,
                    "raw": line,
                },
                is_boundary=False,
                is_divider=False,
            ))

        elif t == "clarity_result":
            passed = line.get("passed")
            auto_passed = line.get("clarity_auto_passed")
            round_index = line.get("clarity_round_index")
            round_cap = line.get("clarity_round_cap")
            questions_count = line.get("questions_count")
            if auto_passed:
                status = "auto_passed"
            elif passed is True:
                status = "clear"
            elif passed is False:
                status = "blocked"
            else:
                status = "unknown"
            summary_parts = [
                status,
                f"round={round_index}/{round_cap}" if round_index is not None and round_cap is not None else None,
                f"questions={questions_count}" if questions_count is not None else None,
            ]
            _emit(_view_event(
                ev_id=f"mcp.clarity_result.{line.get('timestamp')}",
                name="mcp.clarity_result",
                direction="·",
                scope="mcp",
                timestamp=line.get("timestamp"),
                summary=" · ".join(p for p in summary_parts if p),
                detail={
                    "status": status,
                    "ran": line.get("ran"),
                    "passed": passed,
                    "has_questions": line.get("has_questions"),
                    "questions_count": questions_count,
                    "questions": line.get("questions") or [],
                    "clarity_round_index": round_index,
                    "clarity_round_cap": round_cap,
                    "clarity_auto_passed": auto_passed,
                    "error": line.get("error"),
                },
                is_boundary=False,
            ))

        # ── P13-005/006/007: agent lifecycle envelope + checkpoint events ───────
        # These were silently dropped before P13-008 (no `elif` branch matched),
        # so the agent boundary was invisible in the viewer despite being
        # correctly emitted and persisted in the trace JSONL. All use scope=
        # "agent" to distinguish from mcp / executor / host events.

        elif t == "delegation_lifecycle_start":
            _resumed = bool(line.get("resumed"))
            _summary = "lifecycle start" + (" · resumed" if _resumed else "")
            _emit(_view_event(
                ev_id=f"agent.lifecycle.start.{line.get('timestamp')}",
                name="agent.lifecycle_start",
                direction="→",
                scope="agent",
                timestamp=line.get("timestamp"),
                summary=_summary,
                detail={
                    "event_type": "delegation_lifecycle_start",
                    "project_key": line.get("project_key"),
                    "spec_path": line.get("spec_path"),
                    "session_policy": line.get("session_policy"),
                    "session_action": line.get("session_action"),
                    "mcp_session_id": line.get("mcp_session_id"),
                    "resumed": _resumed,
                    "raw": line,
                },
                is_boundary=True,
                is_divider=False,
            ))

        elif t == "delegation_lifecycle_end":
            _outcome = line.get("outcome") or ""
            _reviewer = line.get("reviewer_pass_result")
            _summary_parts = [p for p in [
                "lifecycle end",
                f"outcome={_outcome}" if _outcome else None,
                f"reviewer={_reviewer}" if _reviewer else None,
            ] if p]
            _emit(_view_event(
                ev_id=f"agent.lifecycle.end.{line.get('timestamp')}",
                name="agent.lifecycle_end",
                direction="←",
                scope="agent",
                timestamp=line.get("timestamp"),
                summary=" · ".join(_summary_parts),
                detail={
                    "event_type": "delegation_lifecycle_end",
                    "project_key": line.get("project_key"),
                    "outcome": _outcome,
                    "phase_summary": line.get("phase_summary"),
                    "reviewer_pass_result": _reviewer,
                    "raw": line,
                },
                is_boundary=True,
                is_divider=False,
            ))

        elif t == "delegation_phase_start":
            _phase = line.get("phase") or ""
            _resumed = bool(line.get("resumed"))
            _summary = f"phase: {_phase}" + (" · resumed" if _resumed else "")
            _emit(_view_event(
                ev_id=f"agent.phase.start.{_phase}.{line.get('timestamp')}",
                name="agent.phase_start",
                direction="→",
                scope="agent",
                timestamp=line.get("timestamp"),
                summary=_summary,
                detail={
                    "event_type": "delegation_phase_start",
                    "project_key": line.get("project_key"),
                    "phase": _phase,
                    "resumed": _resumed,
                    "raw": line,
                },
                is_boundary=False,
                is_divider=True,
            ))

        elif t == "delegation_phase_end":
            _phase = line.get("phase") or ""
            _status = line.get("status") or ""
            _detail_txt = line.get("detail")
            _summary_parts = [p for p in [
                f"phase: {_phase}",
                _status or None,
                _detail_txt or None,
            ] if p]
            _emit(_view_event(
                ev_id=f"agent.phase.end.{_phase}.{line.get('timestamp')}",
                name="agent.phase_end",
                direction="←",
                scope="agent",
                timestamp=line.get("timestamp"),
                summary=" · ".join(_summary_parts),
                detail={
                    "event_type": "delegation_phase_end",
                    "project_key": line.get("project_key"),
                    "phase": _phase,
                    "status": _status,
                    "detail": _detail_txt,
                    "raw": line,
                },
                is_boundary=False,
                is_divider=True,
            ))

        elif t == "agent_checkpoint_saved":
            _last_outcome = line.get("last_outcome") or ""
            _last_del = line.get("last_delegation_id") or ""
            _summary_parts = [p for p in [
                "checkpoint saved",
                f"outcome={_last_outcome}" if _last_outcome else None,
                f"delegation={_last_del[:8]}" if _last_del else None,
            ] if p]
            _emit(_view_event(
                ev_id=f"agent.checkpoint.saved.{line.get('timestamp')}",
                name="agent.checkpoint_saved",
                direction="·",
                scope="agent",
                timestamp=line.get("timestamp"),
                summary=" · ".join(_summary_parts),
                detail={
                    "event_type": "agent_checkpoint_saved",
                    "project_key": line.get("project_key"),
                    "last_delegation_id": _last_del,
                    "last_outcome": _last_outcome,
                    "file_path": line.get("file_path"),
                    "delegation_id": line.get("delegation_id"),
                    "raw": line,
                },
                is_boundary=False,
                is_divider=False,
            ))

        elif t == "agent_rehydrated":
            _last_del = line.get("last_delegation_id") or ""
            _last_outcome = line.get("last_outcome") or ""
            _summary_parts = [p for p in [
                "rehydrated",
                f"from={_last_del[:8]}" if _last_del else None,
                f"outcome={_last_outcome}" if _last_outcome else None,
            ] if p]
            _emit(_view_event(
                ev_id=f"agent.rehydrated.{line.get('timestamp')}",
                name="agent.rehydrated",
                direction="·",
                scope="agent",
                timestamp=line.get("timestamp"),
                summary=" · ".join(_summary_parts),
                detail={
                    "event_type": "agent_rehydrated",
                    "project_key": line.get("project_key"),
                    "last_delegation_id": _last_del,
                    "last_outcome": _last_outcome,
                    "last_finished_at": line.get("last_finished_at"),
                    "delegation_id": line.get("delegation_id"),
                    "raw": line,
                },
                is_boundary=False,
                is_divider=False,
            ))

        elif t == "project_state_loaded":
            _pk = line.get("project_key") or ""
            _emit(_view_event(
                ev_id=f"agent.project_state.loaded.{line.get('timestamp')}",
                name="agent.project_state_loaded",
                direction="·",
                scope="agent",
                timestamp=line.get("timestamp"),
                summary=f"project_state loaded" + (f" · {_pk}" if _pk else ""),
                detail={
                    "event_type": "project_state_loaded",
                    "project_key": _pk,
                    "raw": line,
                },
                is_boundary=False,
                is_divider=False,
            ))

        elif t == "project_state_saved":
            _pk = line.get("project_key") or ""
            _hot = line.get("hot_areas_updated")
            _dec = line.get("decisions_added")
            _risk = line.get("risks_added")
            _summary_parts = [p for p in [
                "project_state saved",
                _pk or None,
                f"hot_areas={_hot}" if _hot is not None else None,
                f"decisions_added={_dec}" if _dec is not None else None,
                f"risks_added={_risk}" if _risk is not None else None,
            ] if p]
            _emit(_view_event(
                ev_id=f"agent.project_state.saved.{line.get('timestamp')}",
                name="agent.project_state_saved",
                direction="·",
                scope="agent",
                timestamp=line.get("timestamp"),
                summary=" · ".join(_summary_parts),
                detail={
                    "event_type": "project_state_saved",
                    "project_key": _pk,
                    "hot_areas_updated": _hot,
                    "decisions_added": _dec,
                    "risks_added": _risk,
                    "file_path": line.get("file_path"),
                    "raw": line,
                },
                is_boundary=False,
                is_divider=False,
            ))

        elif t == "tool_call":
            tool = line.get("tool") or ""
            step = line.get("step_index")
            n = step if step is not None else "?"
            ts_key = f"{emit_order}"

            if tool == "file_write":
                path = line.get("path") or ""
                bw = line.get("bytes_written")
                summary = path + (f" · {bw:,}B" if bw is not None else "")
                _emit(_view_event(
                    ev_id=f"executor.file_write.{n}.{ts_key}",
                    name="executor.file_write",
                    direction="·",
                    scope="executor",
                    timestamp=line.get("timestamp"),
                    summary=summary,
                    detail={"step_index": step, "tool": tool, "path": path, "bytes_written": bw},
                    is_boundary=False,
                ))
            elif tool == "shell_exec":
                cmd = line.get("command") or ""
                ec = line.get("exit_code")
                summary = (cmd[:80] + "…") if len(cmd) > 80 else cmd
                if ec is not None:
                    summary += f" · exit {ec}"
                _emit(_view_event(
                    ev_id=f"executor.shell.{n}.{ts_key}",
                    name="executor.shell",
                    direction="·",
                    scope="executor",
                    timestamp=line.get("timestamp"),
                    summary=summary,
                    detail={"step_index": step, "tool": tool, "command": cmd, "args": line.get("args"), "exit_code": ec},
                    is_boundary=False,
                ))
            else:
                # Future-proof fallback so new tool_call kinds are visible by default.
                summary = tool or "tool_call"
                _emit(_view_event(
                    ev_id=f"executor.tool.{n}.{ts_key}",
                    name="executor.tool",
                    direction="·",
                    scope="executor",
                    timestamp=line.get("timestamp"),
                    summary=summary,
                    detail={
                        "step_index": step,
                        "tool": tool,
                        "raw_event": line,
                    },
                    is_boundary=False,
                ))

    # Virtual close events — timestamp from delegation record, sorted with trace rows
    if seen_step_dividers or _executor_ran:
        resolved = _resolve_output(record, trace_lines)
        output_text = resolved.get("text") or ""
        files_changed = record.get("files_changed") or []
        rtc = record.get("response_to_cursor") or {}
        error_detail = record.get("error_detail") or {}

        # Aggregate token totals across all proxy+backend pairs
        total_tokens_in  = sum(
            (backend_by_key[k].get("usage") or {}).get("input") or 0
            for k in backend_by_key
        )
        total_tokens_out = sum(
            (backend_by_key[k].get("usage") or {}).get("output") or 0
            for k in backend_by_key
        )
        total_thinking = sum(
            backend_by_key[k].get("thinking_tokens") or 0
            for k in backend_by_key
        )
        llm_call_count = len(proxy_by_key)

        summary_parts = [p for p in [
            f"{len(files_changed)} file(s) changed" if files_changed else None,
            ((output_text[:80] + "…") if len(output_text) > 80 else output_text) or None,
        ] if p]
        _emit(_view_event(
            ev_id="executor.mcp.out",
            name="executor→mcp",
            direction="←",
            scope="executor",
            timestamp=record.get("timestamp_end"),
            summary=" · ".join(summary_parts) or "done",
            detail={
                "files_changed": files_changed,
                "output_text": output_text,
                "output_source": resolved.get("source"),
                "success": rtc.get("success"),
                "outcome": record.get("outcome") or rtc.get("outcome"),
                "error_class": rtc.get("error_class") or error_detail.get("error_class"),
                "error_message": (
                    rtc.get("error_message")
                    or error_detail.get("error_message")
                    or record.get("error")
                ),
                # aggregate stats
                "llm_calls": llm_call_count,
                "total_tokens_in":  total_tokens_in  or None,
                "total_tokens_out": total_tokens_out or None,
                "total_thinking":   total_thinking   or None,
            },
            is_virtual=True,
        ))

    # mcp→host (from delegation record)
    rtc = record.get("response_to_cursor") or {}
    resolved = _resolve_output(record, trace_lines)
    output_text = resolved.get("text") or ""
    error_detail = record.get("error_detail") or {}
    preview = rtc.get("output_preview") or output_text
    mcp_host_summary = (preview[:120] + "…") if len(preview) > 120 else preview
    _emit(_view_event(
        ev_id="mcp.host.out",
        name="mcp→host",
        direction="←",
        scope="host",
        timestamp=record.get("timestamp_end"),
        summary=mcp_host_summary,
        detail={
            "output_text": output_text,
            "output_preview": rtc.get("output_preview"),
            "output_bytes": rtc.get("output_bytes"),
            "output_sha256": rtc.get("output_sha256"),
            "success": rtc.get("success"),
            "outcome": record.get("outcome") or rtc.get("outcome"),
            "error_class": rtc.get("error_class") or error_detail.get("error_class"),
            "error_message": (
                rtc.get("error_message")
                or error_detail.get("error_message")
                or record.get("error")
            ),
            "source": resolved.get("source"),
        },
    ))

    # Sort strictly by timestamp; stable tie-break on emission order
    events.sort(key=lambda e: (e.get("timestamp") or "", e["_sort_order"]))
    _reposition_mcp_executor_handoff(events)
    _insert_post_delegate_index_header(events)
    for seq, ev in enumerate(events):
        ev["seq"] = seq
        ev.pop("_sort_order", None)

    return events


def _build_trace_events(trace_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return all trace events annotated with _seq, _pair_status, and _pair_call_key."""
    events: list[dict[str, Any]] = []
    for seq, line in enumerate(trace_lines, start=1):
        ev = dict(line)
        ev["_seq"] = seq
        ev["_pair_status"] = None
        ev["_pair_call_key"] = None
        events.append(ev)

    has_dual = any(
        ev.get("type") in {"backend_llm_call", "proxy_llm_call"} for ev in events
    )
    if has_dual:
        paired = pair_dual_capture_events(trace_lines)
        _annotate_pairs(events, paired["calls"])

    return events


def enrich_delegation_record(record: dict[str, Any]) -> dict[str, Any]:
    """Resolve lean JSONL pointers from local DBs and trace files."""
    workspace = record.get("workspace_path") or ""
    delegation_id = str(record.get("delegation_id") or "")
    session_dir = record.get("session_dir") or ""
    trace_ref = record.get("trace_ref")

    trace_path, trace_lines = (None, [])
    if session_dir and delegation_id:
        trace_path, trace_lines = _load_trace_lines(session_dir, trace_ref, delegation_id)

    context = record.get("context") or {}
    refs_in = record.get("context_refs") or []
    refs_resolved = (
        [_resolve_context_ref(workspace, ref) for ref in refs_in] if workspace and refs_in else []
    )

    delegation_diff = None
    if workspace and delegation_id:
        diff_result = delegation_diff_for_mcp(workspace, delegation_id)
        if diff_result.get("found"):
            delegation_diff = diff_result.get("delegation_diff")

    workspace_snapshot = record.get("workspace_snapshot") or {}
    trace_events = _build_trace_events(trace_lines)
    view_events = _build_view_events(record, trace_lines)

    return {
        "delegation_id": delegation_id,
        "output": _resolve_output(record, trace_lines),
        "context_refs_resolved": refs_resolved,
        "view_events": view_events,
        "trace": {
            "path": str(trace_path) if trace_path else None,
            "trace_ref": trace_ref,
            "found": bool(trace_lines),
            "events": trace_events,
            "dual_capture_compare": _summarize_dual_capture(trace_lines),
            "token_summary": _aggregate_tokens(trace_events),
        },
        "delegation_diff": delegation_diff,
        "storage_links": {
            "trace_ref": trace_ref,
            "session_dir": session_dir or None,
            "workspace_snapshot_db": workspace_snapshot.get("db_path"),
            "context_package_hash": context.get("context_package_hash"),
            "delegation_rag_db": str(DelegationRagDB(workspace).db_path) if workspace else None,
            "workspace_rag_db": str(WorkspaceRagDB(workspace).db_path) if workspace else None,
        },
    }
