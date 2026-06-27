"""Unit tests for delegation usage telemetry."""

from pathlib import Path

import pytest

from core.usage.policy import resolve_usage_report_enabled
from core.usage.rates import clear_rates_cache, estimate_cost_usd, lookup_model_rates
from core.usage.telemetry import (
    build_usage_report,
    build_usage_warnings,
    format_usage_run_log_line,
)


def test_resolve_usage_report_default_true(tmp_path, monkeypatch):
    monkeypatch.delenv("MCP_CODER_USAGE_REPORT", raising=False)
    assert resolve_usage_report_enabled(tmp_path) is True


def test_resolve_usage_report_env_off(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_USAGE_REPORT", "0")
    assert resolve_usage_report_enabled(tmp_path) is False


def test_resolve_usage_report_yaml_overrides_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_CODER_USAGE_REPORT", "0")
    cfg = tmp_path / ".mcp-coder"
    cfg.mkdir()
    (cfg / "config.yaml").write_text("usage_report: true\n", encoding="utf-8")
    assert resolve_usage_report_enabled(tmp_path) is True


def test_lookup_model_rates_with_prefix():
    rates = lookup_model_rates("openrouter/openai/gpt-4o-mini")
    assert rates is not None
    assert rates["input_per_million"] == 0.15


def test_estimate_cost_usd_actual_tokens():
    cost = estimate_cost_usd(
        "openrouter/openai/gpt-4o-mini",
        1_000_000,
        1_000_000,
    )
    assert cost is not None
    assert cost["source"] == "static_rates"
    assert cost["input"] == pytest.approx(0.15)
    assert cost["output"] == pytest.approx(0.60)
    assert cost["total"] == pytest.approx(0.75)
    assert cost["note"] == "approximate"


def test_estimate_cost_usd_unknown_model():
    # P15-ISS-007: unknown model with tokens returns zeroed cost fields
    # (total always present) so cost_est_usd["total"] never KeyErrors.
    cost = estimate_cost_usd("unknown/model-xyz", 1000, 500)
    assert cost["source"] == "unknown_model"
    assert cost["total"] == 0.0
    assert cost["input"] == 0.0
    assert cost["output"] == 0.0
    assert cost["note"] == "rates_missing_for_model"


def test_estimate_cost_usd_unknown_model_no_tokens():
    # Unknown model with no tokens → minimal marker (no zeroed fields).
    cost = estimate_cost_usd("unknown/model-xyz", None, None)
    assert cost == {"source": "unknown_model"}


def test_build_usage_report_with_actual_tokens():
    usage = build_usage_report(
        model="openrouter/anthropic/claude-sonnet-4",
        prompt="x" * 400,
        actual_tokens={
            "input": 12000,
            "output": 3400,
            "total": 15400,
            "source": "aider_usage",
        },
    )
    assert usage["preflight_tokens_est"] == 100
    assert usage["preflight_chars"] == 400
    assert usage["actual"]["total"] == 15400
    assert usage["cost_est_usd"]["source"] == "static_rates"
    assert usage["note"]


def test_build_usage_report_preflight_only_cost():
    usage = build_usage_report(
        model="openrouter/openai/gpt-4o-mini",
        prompt="a" * 4000,
        actual_tokens={"source": "unavailable"},
    )
    assert usage["actual"]["source"] == "unavailable"
    assert usage["cost_est_usd"]["note"] == "preflight_only_approximate"


def test_format_usage_run_log_line():
    usage = build_usage_report(
        model="openrouter/openai/gpt-4o-mini",
        prompt="task",
        actual_tokens={
            "input": 12000,
            "output": 3400,
            "total": 15400,
            "source": "aider_usage",
        },
    )
    line = format_usage_run_log_line(usage)
    assert line.startswith("- **usage:**")
    assert "gpt-4o-mini" in line
    assert "15400 tok" in line
    assert "cost ~$" in line


def test_build_usage_warnings_over_threshold(monkeypatch):
    monkeypatch.setenv("MCP_CODER_USAGE_WARN_TOKENS", "1000")
    warnings = build_usage_warnings(5000)
    assert len(warnings) == 1
    assert "1000" in warnings[0]


def test_build_usage_warnings_no_threshold(monkeypatch):
    monkeypatch.delenv("MCP_CODER_USAGE_WARN_TOKENS", raising=False)
    assert build_usage_warnings(999_999) == []


@pytest.fixture(autouse=True)
def _reset_rates_cache():
    clear_rates_cache()
    yield
    clear_rates_cache()
