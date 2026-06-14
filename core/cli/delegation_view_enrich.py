"""Resolve lean JSONL pointers for the delegation viewer (P6-007 follow-up)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def _summarize_trace(trace_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in trace_lines:
        if line.get("type") != "llm_call":
            continue
        item: dict[str, Any] = {
            "role": line.get("role"),
            "model": line.get("model"),
            "call_index": line.get("call_index"),
            "duration_ms": line.get("duration_ms"),
            "tokens": line.get("tokens"),
        }
        if line.get("response_preview"):
            item["response_preview"] = line["response_preview"]
        if line.get("prompt_preview"):
            item["prompt_preview"] = line["prompt_preview"]
        out.append(item)
    return out


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

    return {
        "delegation_id": delegation_id,
        "output": _resolve_output(record, trace_lines),
        "context_refs_resolved": refs_resolved,
        "trace": {
            "path": str(trace_path) if trace_path else None,
            "trace_ref": trace_ref,
            "found": bool(trace_lines),
            "llm_calls": _summarize_trace(trace_lines),
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
