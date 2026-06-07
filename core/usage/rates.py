"""Static per-model token rates for approximate cost estimation.

Rates live in resources/model_rates.yaml (partial list; update manually).
Future: dynamic refresh via API or provider pricing — see yaml header.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from core.resources_paths import resources_dir

MODEL_RATES_FILENAME = "model_rates.yaml"


@lru_cache(maxsize=1)
def _load_rates_file() -> dict[str, dict[str, float]]:
    path = resources_dir() / MODEL_RATES_FILENAME
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    models = data.get("models")
    if not isinstance(models, dict):
        return {}
    out: dict[str, dict[str, float]] = {}
    for model_id, rates in models.items():
        if isinstance(model_id, str) and isinstance(rates, dict):
            out[model_id.strip()] = rates
    return out


def model_rate_candidates(model: str) -> list[str]:
    """Lookup keys to try (with/without openrouter/ prefix)."""
    m = model.strip()
    if not m:
        return []
    candidates = [m]
    if m.startswith("openrouter/"):
        candidates.append(m[len("openrouter/") :])
    else:
        candidates.append(f"openrouter/{m}")
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def lookup_model_rates(model: str) -> dict[str, float] | None:
    rates_table = _load_rates_file()
    for key in model_rate_candidates(model):
        entry = rates_table.get(key)
        if entry:
            return entry
    return None


def estimate_cost_usd(
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    *,
    preflight_only: bool = False,
) -> dict[str, Any] | None:
    """Approximate USD cost from static rates; None when model unknown."""
    rates = lookup_model_rates(model)
    if not rates:
        return {"source": "unknown_model"}

    input_rate = float(rates.get("input_per_million", 0))
    output_rate = float(rates.get("output_per_million", 0))

    if input_tokens is None and output_tokens is None:
        return None

    in_tok = int(input_tokens or 0)
    out_tok = int(output_tokens or 0)
    input_cost = (in_tok / 1_000_000) * input_rate
    output_cost = (out_tok / 1_000_000) * output_rate
    total = input_cost + output_cost

    result: dict[str, Any] = {
        "input": round(input_cost, 6),
        "output": round(output_cost, 6),
        "total": round(total, 6),
        "source": "static_rates",
        "note": "preflight_only_approximate" if preflight_only else "approximate",
    }
    return result


def clear_rates_cache() -> None:
    """Test helper to reload model_rates.yaml."""
    _load_rates_file.cache_clear()
