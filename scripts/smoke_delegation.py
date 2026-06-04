#!/usr/bin/env python3
"""One real delegate_to_agent run against tests/smoke_workspace (uses .env)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE_DIR = ROOT / "tests" / "smoke_workspace"
TARGET = "tests/smoke_workspace/sample.py"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    from core.config import apply_provider_env, load_env_files, resolve_model_name
    from core.config.models import provider_hint_for_model

    load_env_files()
    apply_provider_env()

    model = resolve_model_name()
    hint = provider_hint_for_model(model)
    print("workspace:", ROOT)
    print("model:", model)
    print("OPENROUTER_API_BASE:", os.environ.get("OPENROUTER_API_BASE", "(unset)"))
    print("OPENROUTER_API_KEY:", "set" if os.environ.get("OPENROUTER_API_KEY") else "MISSING")
    if hint:
        print("config error:", hint)
        return 1

    from server.mcp_server import delegate_to_agent

    print("\nRunning delegate_to_agent (live LLM)…\n")
    raw = delegate_to_agent(
        task=(
            "In tests/smoke_workspace/sample.py: ensure module docstring is "
            "'Smoke test target for mcp-coder.' and greet() returns 'hello'. "
            "If already correct, make no edits."
        ),
        target_files=[TARGET],
        context_summary="Python 3.10+. Minimal edit only.",
        backend="aider",
    )
    payload = json.loads(raw)
    print("response:", json.dumps(payload, indent=2)[:4000])

    log_path = payload.get("log_path")
    if log_path:
        last = Path(log_path).read_text(encoding="utf-8").strip().splitlines()[-1]
        record = json.loads(last)
        print("\nlast delegation_id:", record.get("delegation_id"))
        print("mcp_session_id:", record.get("mcp_session_id"))
        print("log:", log_path)

    return 0 if payload.get("success") else 2


if __name__ == "__main__":
    raise SystemExit(main())
