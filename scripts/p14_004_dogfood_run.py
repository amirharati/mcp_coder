#!/usr/bin/env python3
"""P14-004 dogfood: run a single delegation against .mcp-coder/specs/tasks/p14-004-capture-test.md
with Sonnet executor + Sonnet helpers, MAX_TURNS=2, reasoning capture on."""
from __future__ import annotations

import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from core.config import apply_provider_env, load_env_files, resolve_model_name
from core.config.models import provider_hint_for_model

load_env_files()
apply_provider_env()

# ── 4a env per the spec § Config env (MUST be after load_env_files to override .env) ──
# NOTE: AIDER_MODEL takes precedence over MCP_CODER_MODEL in resolve_model_name(),
# so we must set AIDER_MODEL to force the executor model.
os.environ["AIDER_MODEL"] = "openrouter/anthropic/claude-sonnet-4.5"
os.environ["MCP_CODER_MODEL"] = "openrouter/anthropic/claude-sonnet-4.5"
os.environ["MCP_CODER_HELPER_MODEL"] = "openrouter/anthropic/claude-sonnet-4.5"
os.environ["MCP_CODER_SUPERVISOR_MAX_TURNS"] = "2"
os.environ["MCP_CODER_CAPTURE_REASONING"] = "1"
os.environ["MCP_CODER_CLARITY_PASS"] = "0"  # skip clarity to reach executor

model = resolve_model_name()
hint = provider_hint_for_model(model)
print("model:", model)
print("helper_model:", os.environ.get("MCP_CODER_HELPER_MODEL"))
print("MAX_TURNS:", os.environ.get("MCP_CODER_SUPERVISOR_MAX_TURNS"))
if hint:
    print("config error:", hint)
    raise SystemExit(1)

from server.mcp_server import delegate_to_agent

spec_path = ".mcp-coder/specs/tasks/p14-004-capture-test.md"
print(f"\nDelegating spec: {spec_path} …\n")

raw = delegate_to_agent(
    task="",  # read from spec
    target_files=[],
    context_summary="Audit capture test — single file docstring edit.",
    backend="aider",
    spec_path=spec_path,
    mode="implement",
    start_fresh=True,
)

payload = json.loads(raw)
print("FULL PAYLOAD:", json.dumps(payload, indent=2, default=str)[:3000])
print("RAW length:", len(raw))
print("Keys:", list(payload.keys()))
success = payload.get("success", False)
delegation_id = payload.get("delegation_id") or payload.get("log", {}).get("delegation_id")
trace_path = None

log_path_str = payload.get("log_path") or ""
if log_path_str:
    log_records = Path(log_path_str).read_text(encoding="utf-8").strip().splitlines()
    if log_records:
        last = json.loads(log_records[-1])
        delegation_id = delegation_id or last.get("delegation_id")

# Find trace path
if delegation_id:
    for d in sorted(ROOT.glob(".mcp-coder/sessions/*/traces/"), key=lambda p: p.stat().st_mtime, reverse=True):
        candidate = d / f"{delegation_id}.jsonl"
        if candidate.exists():
            trace_path = str(candidate)
            break

print(f"\n--- RESULTS ---")
print(f"success: {success}")
print(f"delegation_id: {delegation_id}")
print(f"trace_path: {trace_path or 'NOT FOUND'}")
print(f"log_path: {log_path_str}")

if not delegation_id or not trace_path:
    print("ERROR: Could not determine delegation_id or trace path")
    raise SystemExit(1)

# Write both to a small json file so later steps can pick them up
out = {"delegation_id": delegation_id, "trace_path": trace_path, "success": success,
       "log_path": log_path_str}
(ROOT / ".mcp-coder" / "sessions" / "p14-004-dogfood.json").parent.mkdir(parents=True, exist_ok=True)
(ROOT / ".mcp-coder" / "sessions" / "p14-004-dogfood.json").write_text(json.dumps(out, indent=2))

print("\nsaved dogfood metadata to .mcp-coder/sessions/p14-004-dogfood.json")