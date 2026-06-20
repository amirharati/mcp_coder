"""Planner pass enable flag (P11-008 rename from architect_pass).

Canonical env: MCP_CODER_PLANNER_PASS
Legacy alias:  MCP_CODER_ARCHITECT_PASS  (accepted with warning)

Canonical spec key: planner_pass
Legacy spec key:    architect_pass       (accepted with warning)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from core.storage.workspace_config import load_workspace_config

_log = logging.getLogger(__name__)


def _env_bool(raw: str) -> bool | None:
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    return None


def planner_pass_enabled(workspace: str | Path) -> bool:
    """Return True when planner pass is enabled for this workspace.

    Precedence (highest wins):
    1. Canonical env  MCP_CODER_PLANNER_PASS
    2. Legacy env     MCP_CODER_ARCHITECT_PASS   (alias, warns)
    3. Canonical key  planner_pass  in workspace config.yaml
    4. Legacy key     architect_pass in workspace config.yaml  (alias, warns)
    5. Default: True
    """
    enabled = True
    used_legacy = False

    canonical_env = os.environ.get("MCP_CODER_PLANNER_PASS", "").strip()
    legacy_env = os.environ.get("MCP_CODER_ARCHITECT_PASS", "").strip()

    if canonical_env:
        parsed = _env_bool(canonical_env)
        if parsed is not None:
            enabled = parsed
    elif legacy_env:
        parsed = _env_bool(legacy_env)
        if parsed is not None:
            enabled = parsed
            used_legacy = True

    cfg = load_workspace_config(workspace)

    canonical_yaml = cfg.get("planner_pass")
    legacy_yaml = cfg.get("architect_pass")

    if canonical_yaml is not None:
        if isinstance(canonical_yaml, bool):
            enabled = canonical_yaml
        elif isinstance(canonical_yaml, str):
            parsed = _env_bool(canonical_yaml)
            if parsed is not None:
                enabled = parsed
    elif legacy_yaml is not None:
        if isinstance(legacy_yaml, bool):
            enabled = legacy_yaml
            used_legacy = True
        elif isinstance(legacy_yaml, str):
            parsed = _env_bool(legacy_yaml)
            if parsed is not None:
                enabled = parsed
                used_legacy = True

    if used_legacy:
        _log.warning(
            "planner_pass: legacy 'architect_pass' key/env used — "
            "migrate to 'planner_pass' / MCP_CODER_PLANNER_PASS"
        )

    return enabled
