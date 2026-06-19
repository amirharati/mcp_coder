"""Model registry front door (P9-011 / BL-511).

`resolve(role, workspace) -> CallParams` is the single entry point for "everything
about a model for a role". This milestone (P9-011) fills `model` + `budget_tokens`
by reusing the existing, tested resolution in `core/config/role_models.py`; the
generation-param + weak-model layers are wired in P9-012.

Design: pure function, no class hierarchy. Aider is a read-only metadata source
touched only inside `_aider_defaults()` (lazy import — no module-level coupling).
See docs/notes/model-policy-layer.md.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.config.role_models import (
    ROLE_CONTEXT_BUILDER,
    ROLE_CRITIC,
    ROLE_EXECUTOR,
    ROLE_REVIEW,
    resolve_role_budget_tokens,
    resolve_role_model_name,
)

# Logging/attribution roles. The first four are also model-resolution roles known
# to role_models.py; the rest are helper labels that resolve their model via an
# underlying role (see _ROLE_MODEL_ALIAS).
ROLE_PLANNER_PASS = "planner_pass"
ROLE_ARCHITECT = "architect"  # legacy label kept for backward compat
ROLE_SPEC_VALIDATION = "spec_validation"
ROLE_SPEC_REVIEW = "spec_review"
ROLE_WORKSPACE_SUMMARIZER = "workspace_summarizer"

ROLES: tuple[str, ...] = (
    ROLE_EXECUTOR,
    ROLE_CONTEXT_BUILDER,
    ROLE_REVIEW,
    ROLE_CRITIC,
    ROLE_PLANNER_PASS,
    ROLE_ARCHITECT,
    ROLE_SPEC_VALIDATION,
    ROLE_SPEC_REVIEW,
    ROLE_WORKSPACE_SUMMARIZER,
)

# Helper label → underlying role used for model + budget resolution. Mirrors today's
# behaviour: the cheap helpers all run on the context_builder model; spec review on
# the review model.
_ROLE_MODEL_ALIAS: dict[str, str] = {
    ROLE_PLANNER_PASS: ROLE_CONTEXT_BUILDER,
    ROLE_ARCHITECT: ROLE_CONTEXT_BUILDER,  # legacy alias
    ROLE_SPEC_VALIDATION: ROLE_CONTEXT_BUILDER,
    ROLE_WORKSPACE_SUMMARIZER: ROLE_CONTEXT_BUILDER,
    ROLE_SPEC_REVIEW: ROLE_REVIEW,
}

VALID_REASONING_EFFORT = frozenset({"none", "low", "medium", "high"})

# Per-role generation-param defaults (P9-012). Applied on top of Aider metadata,
# below env overrides.
_ROLE_GEN_DEFAULTS: dict[str, dict] = {
    ROLE_CONTEXT_BUILDER: {"temperature": 0.2},
    ROLE_SPEC_VALIDATION: {"temperature": 0.1},
    ROLE_REVIEW: {"temperature": 0.0},
    ROLE_SPEC_REVIEW: {"temperature": 0.0},
}

# Registry default weak-model map — fills the gap where Aider uses the main model
# itself for cheap tasks (commit messages, chat summarization). Substring match
# against the resolved model id; first match wins. None → keep Aider's own choice.
_DEFAULT_WEAK_MODEL: tuple[tuple[str, str], ...] = (
    ("openrouter/anthropic/", "openrouter/anthropic/claude-3.5-haiku"),
    ("openrouter/openai/", "openrouter/openai/gpt-4o-mini"),
    ("openrouter/google/", "openrouter/google/gemini-2.0-flash-lite-001"),
    ("claude-opus", "anthropic/claude-3-5-haiku-latest"),
    ("claude-sonnet", "anthropic/claude-3-5-haiku-latest"),
    ("gpt-4o", "openai/gpt-4o-mini"),
    ("gpt-4.5", "openai/gpt-4o-mini"),
    ("gpt-5", "openai/gpt-4o-mini"),
    ("gemini-2.5", "gemini/gemini-2.0-flash-lite"),
)


def _default_weak_model(model_id: str) -> Optional[str]:
    """Registry default weak model for a strong model id. None → no mapping."""
    mid = (model_id or "").lower()
    for needle, weak in _DEFAULT_WEAK_MODEL:
        if needle in mid:
            return weak
    return None


def _env(role: str, suffix: str) -> str:
    return os.environ.get(f"MCP_CODER_{role.upper()}_{suffix}", "").strip()


def _parse_float(raw: str, *, var: str) -> Optional[float]:
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{var} must be a float, got {raw!r}") from exc


def _parse_int(raw: str, *, var: str) -> Optional[int]:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{var} must be an int, got {raw!r}") from exc


@dataclass
class CallParams:
    """Fully resolved model configuration for one role.

    P9-011 populates `model`, `budget_tokens`, and optional Aider metadata. The
    generation-param + weak-model + prompt fields are defined now so the shape is
    final; they are wired in P9-012.
    """

    # Identity + budget (from role_models — implemented this milestone)
    model: Optional[str] = None
    budget_tokens: Optional[int] = None

    # Generation params (P9-012)
    reasoning_effort: Optional[str] = None
    thinking_budget: Optional[int] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    extra_params: dict = field(default_factory=dict)
    drop_params: bool = True
    weak_model: Optional[str] = None

    # Prompt settings (future)
    system_prompt_prefix: Optional[str] = None
    system_prompt_override: Optional[str] = None
    edit_format: Optional[str] = None

    # Metadata (read-only, from Aider registry)
    model_max_tokens: Optional[int] = None

    # Audit provenance — per-field source for policy_applied
    sources: dict = field(default_factory=dict)


def _aider_defaults(model_id: str) -> dict:
    """Read Aider's model registry for metadata. Lazy import, isolated, best-effort.

    Returns {} on any failure so resolution never breaks because of Aider.
    """
    if not model_id:
        return {}
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from aider.models import Model

            m = Model(model_id)
            return {
                "model_max_tokens": getattr(m, "max_tokens", None),
                "edit_format": getattr(m, "edit_format", None),
            }
    except Exception:
        return {}


def resolve(
    role: str,
    workspace: str | Path = "",
    overrides: Optional[dict] = None,
    *,
    host_policy_override: Optional[dict] = None,
    include_aider_metadata: bool = True,
) -> CallParams:
    """Resolve the full model config for a role.

    Precedence (highest wins): runtime overrides kwarg → host_policy_override →
    env/workspace (via role_models + env vars) → role defaults → Aider metadata.
    """
    model_role = _ROLE_MODEL_ALIAS.get(role, role)
    model = resolve_role_model_name(model_role, workspace)
    budget = resolve_role_budget_tokens(model_role, workspace)

    cp = CallParams(model=model, budget_tokens=budget)
    cp.sources["model"] = "role_models"
    if budget is not None:
        cp.sources["budget_tokens"] = "role_models"

    if include_aider_metadata:
        info = _aider_defaults(model)
        if info.get("model_max_tokens") is not None:
            cp.model_max_tokens = info["model_max_tokens"]
        if info.get("edit_format") and cp.edit_format is None:
            cp.edit_format = info["edit_format"]
            cp.sources["edit_format"] = "aider"

    # Layer 2: per-role generation-param defaults.
    for key, value in _ROLE_GEN_DEFAULTS.get(role, {}).items():
        setattr(cp, key, value)
        cp.sources[key] = "default"

    # Layer 3: env overrides (generation params + weak model).
    _apply_env_overrides(cp, role)

    # Weak model: env override → registry default-fill → None (keep Aider's choice).
    if cp.weak_model is None:
        default_weak = _default_weak_model(model)
        if default_weak:
            cp.weak_model = default_weak
            cp.sources["weak_model"] = "registry_default"

    # Layer 4: host model_policy override (per-delegation).
    if host_policy_override:
        _apply_field_layer(cp, host_policy_override, source="host_policy")

    # Layer 5: explicit runtime overrides (highest).
    if overrides:
        _apply_field_layer(cp, overrides, source="override")

    return cp


def _apply_field_layer(cp: CallParams, layer: dict, *, source: str) -> None:
    for key, value in layer.items():
        if value is not None and hasattr(cp, key):
            setattr(cp, key, value)
            cp.sources[key] = source


def _apply_env_overrides(cp: CallParams, role: str) -> None:
    """Apply MCP_CODER_<ROLE>_* generation-param env vars onto cp (records sources)."""
    effort = _env(role, "REASONING_EFFORT")
    if effort:
        if effort not in VALID_REASONING_EFFORT:
            raise ValueError(
                f"MCP_CODER_{role.upper()}_REASONING_EFFORT must be one of "
                f"{sorted(VALID_REASONING_EFFORT)}, got {effort!r}"
            )
        cp.reasoning_effort = effort
        cp.sources["reasoning_effort"] = "env"

    thinking = _parse_int(
        _env(role, "THINKING_BUDGET"), var=f"MCP_CODER_{role.upper()}_THINKING_BUDGET"
    )
    if thinking is not None:
        cp.thinking_budget = thinking
        cp.sources["thinking_budget"] = "env"

    max_tokens = _parse_int(
        _env(role, "MAX_TOKENS"), var=f"MCP_CODER_{role.upper()}_MAX_TOKENS"
    )
    if max_tokens is not None:
        cp.max_tokens = max_tokens
        cp.sources["max_tokens"] = "env"

    temperature = _parse_float(
        _env(role, "TEMPERATURE"), var=f"MCP_CODER_{role.upper()}_TEMPERATURE"
    )
    if temperature is not None:
        cp.temperature = temperature
        cp.sources["temperature"] = "env"

    top_p = _parse_float(_env(role, "TOP_P"), var=f"MCP_CODER_{role.upper()}_TOP_P")
    if top_p is not None:
        cp.top_p = top_p
        cp.sources["top_p"] = "env"

    extra_raw = _env(role, "EXTRA_PARAMS")
    if extra_raw:
        try:
            parsed = json.loads(extra_raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"MCP_CODER_{role.upper()}_EXTRA_PARAMS must be valid JSON: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                f"MCP_CODER_{role.upper()}_EXTRA_PARAMS must be a JSON object"
            )
        cp.extra_params = parsed
        cp.sources["extra_params"] = "env"

    weak = _env(role, "WEAK_MODEL")
    if weak:
        cp.weak_model = weak
        cp.sources["weak_model"] = "env"

    prefix = _env(role, "SYSTEM_PREFIX")
    if prefix:
        cp.system_prompt_prefix = prefix
        cp.sources["system_prompt_prefix"] = "env"

    edit_fmt = _env(role, "EDIT_FORMAT")
    if edit_fmt:
        cp.edit_format = edit_fmt
        cp.sources["edit_format"] = "env"


def policy_applied(cp: CallParams, role: str) -> dict:
    """Compact, log-friendly view of an applied policy for trace `policy_applied`."""
    out: dict = {"role": role}
    for field_name in (
        "reasoning_effort",
        "thinking_budget",
        "max_tokens",
        "temperature",
        "top_p",
        "weak_model",
        "system_prompt_prefix",
        "edit_format",
    ):
        value = getattr(cp, field_name)
        if value is not None:
            out[field_name] = value
    if cp.extra_params:
        out["extra_params"] = cp.extra_params
    if role == ROLE_EXECUTOR:
        ignored: list[str] = []
        for name in ("temperature", "top_p", "max_tokens"):
            if getattr(cp, name) is not None:
                ignored.append(name)
        if ignored:
            out["ignored"] = ignored
            out["note"] = (
                "Executor backend ignores these fields; use "
                "MCP_CODER_EXECUTOR_EXTRA_PARAMS for provider-native knobs."
            )
    if cp.sources:
        out["sources"] = dict(cp.sources)
    return out
