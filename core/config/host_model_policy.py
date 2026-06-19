"""Host per-delegation model_policy normalizer (P11-007)."""

from __future__ import annotations

from typing import Any

from core.config.model_registry import VALID_REASONING_EFFORT

HOST_ROLE_KEYS = frozenset({"executor", "reviewer", "supervisor", "architect"})

HOST_TO_INTERNAL_ROLE: dict[str, str] = {
    "executor": "executor",
    "reviewer": "review",
    "supervisor": "supervisor",
    "architect": "architect",
}

RUNTIME_ROLE_TO_POLICY_ROLE: dict[str, str] = {
    "architect_pass": "architect",
    "spec_review": "review",
    "review": "review",
    "supervisor": "supervisor",
    "executor": "executor",
    "architect": "architect",
}

ALLOWED_POLICY_FIELDS = frozenset(
    {
        "model",
        "reasoning_effort",
        "thinking_budget",
        "max_tokens",
        "temperature",
        "top_p",
        "extra_params",
        "weak_model",
        "system_prompt_prefix",
        "edit_format",
    }
)


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    return None


def _validate_field(field: str, value: Any) -> tuple[Any | None, str | None]:
    if field == "model":
        if isinstance(value, str) and value.strip():
            return value.strip(), None
        return None, f"model must be a non-empty string, got {value!r}"

    if field == "reasoning_effort":
        if isinstance(value, str) and value in VALID_REASONING_EFFORT:
            return value, None
        return None, (
            f"reasoning_effort must be one of {sorted(VALID_REASONING_EFFORT)}, got {value!r}"
        )

    if field in ("thinking_budget", "max_tokens"):
        if isinstance(value, bool) or value is None:
            return None, f"{field} must be an int, got {value!r}"
        if isinstance(value, int):
            return value, None
        if isinstance(value, float) and value.is_integer():
            return int(value), None
        return None, f"{field} must be an int, got {value!r}"

    if field in ("temperature", "top_p"):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value), None
        return None, f"{field} must be a number, got {value!r}"

    if field == "extra_params":
        if isinstance(value, dict):
            return value, None
        return None, f"extra_params must be a dict, got {type(value).__name__}"

    if field in ("weak_model", "system_prompt_prefix", "edit_format"):
        if isinstance(value, str) and value.strip():
            return value.strip(), None
        return None, f"{field} must be a non-empty string, got {value!r}"

    return None, f"unsupported field {field!r}"


def normalize_host_model_policy(
    raw: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Return (normalized_overrides, warnings)."""
    if raw is None:
        return {}, []
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return {}, [f"model_policy must be a dict, got {type(raw).__name__}"]

    normalized: dict[str, dict[str, Any]] = {}
    for host_role, payload in raw.items():
        if host_role not in HOST_ROLE_KEYS:
            warnings.append(f"unknown model_policy role {host_role!r}; ignored")
            continue
        if not isinstance(payload, dict):
            warnings.append(f"model_policy[{host_role!r}] must be a dict; ignored")
            continue

        internal_role = HOST_TO_INTERNAL_ROLE[host_role]
        accepted: dict[str, Any] = {}
        for field, value in payload.items():
            if field not in ALLOWED_POLICY_FIELDS:
                warnings.append(
                    f"model_policy[{host_role!r}].{field} is not allowed; ignored"
                )
                continue
            parsed, err = _validate_field(field, value)
            if err:
                warnings.append(f"model_policy[{host_role!r}].{field}: {err}; ignored")
                continue
            accepted[field] = parsed

        if accepted:
            normalized[internal_role] = accepted

    return normalized, warnings


def summarize_model_policy_applied(overrides: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compact audit payload for delegation JSONL / trace inspect."""
    roles = {
        role: sorted(fields.keys())
        for role, fields in overrides.items()
        if fields
    }
    return {"roles": roles}


def pick_host_override(
    normalized: dict[str, dict[str, Any]] | None,
    runtime_role: str,
) -> dict[str, Any] | None:
    """Lookup host override for a runtime role label (e.g. architect_pass -> architect)."""
    if not normalized:
        return None
    if runtime_role in normalized:
        return normalized[runtime_role]
    mapped = RUNTIME_ROLE_TO_POLICY_ROLE.get(runtime_role)
    if mapped and mapped in normalized:
        return normalized[mapped]
    return None
