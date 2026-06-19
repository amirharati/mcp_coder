"""Version tags for trace and training capture (P6-005, D-P6-6, AGENTIC_LOOP_LOGGING)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from core.config.observability import (
    capture_for_training_enabled,
    capture_reasoning_enabled,
    resolve_observability_retention,
    resolve_observability_verbosity,
    resolve_reasoning_buffer_size,
)
from core.context.summary import sha256_hex
from core.storage.workspace_config import load_workspace_config

CAPTURE_SCHEMA_VERSION = "1"

_CONFIG_FINGERPRINT_KEYS = (
    "observability_verbosity",
    "capture_reasoning",
    "reasoning_buffer_size",
    "capture_for_training",
    "observability_retention",
    "context_builder",
    "context_builder_llm",
    "planner_pass",
    "architect_pass",  # legacy alias — kept for fingerprint stability
    "spec_validation",
    "auto_verify",
    "rag_enabled",
    "builder_history_rag",
    "workspace_file_rag",
    "workspace_file_hints",
)


def resolve_mcp_coder_version() -> str:
    """Git short SHA when available; else package version from pyproject.toml."""
    sha = _git_short_sha()
    if sha:
        return sha
    try:
        import tomllib

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        version = data.get("project", {}).get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()
    except Exception:
        pass
    return "unknown"


def _git_short_sha() -> str | None:
    try:
        from core.resources_paths import repo_root

        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root(),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            return value or None
    except Exception:
        pass
    return None


def build_config_fingerprint(workspace: str | Path) -> str:
    """Stable hash of observability + pipeline config keys active at capture time."""
    cfg = load_workspace_config(workspace)
    payload: dict[str, Any] = {
        key: cfg.get(key)
        for key in _CONFIG_FINGERPRINT_KEYS
        if key in cfg
    }
    payload["_resolved"] = {
        "observability_verbosity": resolve_observability_verbosity(workspace),
        "capture_reasoning": capture_reasoning_enabled(workspace),
        "reasoning_buffer_size": resolve_reasoning_buffer_size(workspace),
        "capture_for_training": capture_for_training_enabled(workspace),
        "observability_retention": resolve_observability_retention(workspace),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_hex(canonical)


def build_pipeline_flags(workspace: str | Path) -> dict[str, bool]:
    """Resolved pipeline feature flags from workspace config."""
    from core.config.planner_pass import planner_pass_enabled
    from core.config.auto_verify import auto_verify_enabled
    from core.config.context_builder import (
        context_builder_enabled,
        context_builder_llm_enabled,
    )
    from core.config.spec_validation import spec_validation_enabled
    from core.rag.search import rag_enabled

    planner_on = planner_pass_enabled(workspace)
    flags: dict[str, bool] = {
        "context_builder": context_builder_enabled(workspace),
        "context_builder_llm": context_builder_llm_enabled(workspace),
        "planner_pass": planner_on,
        "architect_pass": planner_on,  # deprecated alias for old log consumers
        "spec_validation": spec_validation_enabled(workspace),
        "auto_verify": auto_verify_enabled(workspace),
        "rag_enabled": rag_enabled(workspace),
    }
    cfg = load_workspace_config(workspace)
    for key in ("builder_history_rag", "workspace_file_rag", "workspace_file_hints"):
        value = cfg.get(key)
        if isinstance(value, bool):
            flags[key] = value
    return flags


def extract_model_versions(model_roles: dict[str, Any] | None) -> dict[str, str | None]:
    if not model_roles:
        return {}
    out: dict[str, str | None] = {}
    for role, record in model_roles.items():
        if isinstance(record, dict):
            model = record.get("model")
            out[str(role)] = str(model) if model else None
    return out


def build_trace_version_tags(
    workspace: str | Path,
    *,
    model_roles: dict[str, Any] | None = None,
    pipeline_flags_runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Version tags written once per delegation trace file header."""
    tags: dict[str, Any] = {
        "capture_schema_version": CAPTURE_SCHEMA_VERSION,
        "mcp_coder_version": resolve_mcp_coder_version(),
        "config_fingerprint": build_config_fingerprint(workspace),
        "pipeline_flags": build_pipeline_flags(workspace),
        "observability": {
            "verbosity": resolve_observability_verbosity(workspace),
            "capture_reasoning": capture_reasoning_enabled(workspace),
            "reasoning_buffer_size": resolve_reasoning_buffer_size(workspace),
            "capture_for_training": capture_for_training_enabled(workspace),
            "retention": resolve_observability_retention(workspace),
        },
    }
    if model_roles:
        tags["model_versions"] = extract_model_versions(model_roles)
    if pipeline_flags_runtime:
        tags["pipeline_flags_runtime"] = pipeline_flags_runtime
    return tags
