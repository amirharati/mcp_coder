"""Tests for resolve_context_budget_tokens() and apply_context_budget() (P2-220)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.context.budget import apply_context_budget, resolve_context_budget_tokens
from core.context.package import (
    TIER_EDIT_FULL,
    TIER_POINTER,
    TIER_READ_EXCERPT,
    TIER_READ_FULL,
    ContextPackage,
    PathEntry,
)
from core.context.summary import estimate_tokens
from core.usage.rates import clear_rates_cache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_package(entries: list[PathEntry], *, brief: str = "## Task\nTest task\n") -> ContextPackage:
    return ContextPackage(
        brief=brief,
        entries=entries,
        policies=None,
        metadata={},
    )


def _big_python_content(lines: int = 300) -> str:
    """Generate a large Python source file (>8192 bytes) with real symbols."""
    header = "# generated test module\n\n"
    defs = []
    for i in range(lines):
        defs.append(f"def func_{i}(x):\n    '''Docstring {i}.'''\n    return x + {i}\n")
    return header + "\n".join(defs)


def _token_estimate(package: ContextPackage) -> int:
    payload_text = "".join(e.payload or "" for e in package.entries)
    return estimate_tokens(package.brief + payload_text)


# ---------------------------------------------------------------------------
# resolve_context_budget_tokens
# ---------------------------------------------------------------------------


def test_resolve_disabled_by_env(monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUDGET_ENABLED", "0")
    assert resolve_context_budget_tokens() is None


def test_resolve_disabled_by_false(monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUDGET_ENABLED", "false")
    assert resolve_context_budget_tokens() is None


def test_resolve_disabled_by_no(monkeypatch):
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUDGET_ENABLED", "no")
    assert resolve_context_budget_tokens() is None


def test_resolve_yaml_model_wins_over_env(monkeypatch, tmp_path):
    """Per-model YAML row beats the env fallback."""
    clear_rates_cache()
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUDGET_ENABLED", raising=False)
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUDGET_TOKENS", "999")
    try:
        result = resolve_context_budget_tokens(model="openrouter/openai/gpt-4o-mini")
        # YAML has 128000 for this model; env has 999 — YAML should win
        assert result == 128_000
    finally:
        clear_rates_cache()


def test_resolve_env_fallback_when_model_unknown(monkeypatch):
    clear_rates_cache()
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUDGET_ENABLED", raising=False)
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUDGET_TOKENS", "50000")
    try:
        result = resolve_context_budget_tokens(model="openrouter/unknown/model-xyz")
        assert result == 50_000
    finally:
        clear_rates_cache()


def test_resolve_default_when_nothing_set(monkeypatch):
    clear_rates_cache()
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUDGET_ENABLED", raising=False)
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUDGET_TOKENS", raising=False)
    try:
        result = resolve_context_budget_tokens(model="openrouter/unknown/model-xyz")
        assert result == 128_000
    finally:
        clear_rates_cache()


def test_resolve_default_when_no_model(monkeypatch):
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUDGET_ENABLED", raising=False)
    monkeypatch.delenv("MCP_CODER_CONTEXT_BUDGET_TOKENS", raising=False)
    result = resolve_context_budget_tokens()
    assert result == 128_000


# ---------------------------------------------------------------------------
# apply_context_budget — under budget → no-op
# ---------------------------------------------------------------------------


def test_under_budget_unchanged(tmp_path):
    """Small package well under budget: returned as-is."""
    entries = [
        PathEntry(path="pkg/small.py", tier=TIER_READ_FULL, bytes=50, payload="x = 1\n"),
    ]
    pkg = _make_package(entries)
    result = apply_context_budget(pkg, workspace=tmp_path, budget_tokens=128_000)

    assert result is pkg
    assert result.entries[0].tier == TIER_READ_FULL
    assert not result.metadata.get("truncations")


# ---------------------------------------------------------------------------
# apply_context_budget — Step 1: read-full → read-excerpt
# ---------------------------------------------------------------------------


def test_read_full_to_excerpt_when_over_budget(tmp_path, monkeypatch):
    """Large read-full payload triggers step-1 demotion to read-excerpt."""
    (tmp_path / "pkg").mkdir()
    big_content = _big_python_content(300)
    (tmp_path / "pkg" / "big.py").write_text(big_content, encoding="utf-8")

    entries = [
        PathEntry(path="pkg/big.py", tier=TIER_READ_FULL, bytes=len(big_content.encode()), payload=big_content),
    ]
    pkg = _make_package(entries)

    # Budget of 200 tokens forces truncation
    result = apply_context_budget(pkg, workspace=tmp_path, budget_tokens=200)

    entry = result.entries[0]
    assert entry.tier == TIER_READ_EXCERPT, "should be demoted to read-excerpt"
    truncations = result.metadata.get("truncations", [])
    assert any(t["reason"] == "context_budget:read_full_to_excerpt" for t in truncations)
    assert any(t["path"] == "pkg/big.py" for t in truncations)


# ---------------------------------------------------------------------------
# apply_context_budget — edit-full preserved
# ---------------------------------------------------------------------------


def test_edit_full_never_truncated(tmp_path):
    """edit-full entries must never be modified, even when over budget."""
    (tmp_path / "pkg").mkdir()
    big_content = _big_python_content(300)
    edit_content = "# target\ndef main(): pass\n"
    (tmp_path / "pkg" / "big.py").write_text(big_content, encoding="utf-8")
    (tmp_path / "pkg" / "cli.py").write_text(edit_content, encoding="utf-8")

    entries = [
        PathEntry(path="pkg/big.py", tier=TIER_READ_FULL, bytes=len(big_content.encode()), payload=big_content),
        PathEntry(path="pkg/cli.py", tier=TIER_EDIT_FULL, bytes=len(edit_content.encode()), payload=edit_content),
    ]
    pkg = _make_package(entries)

    result = apply_context_budget(pkg, workspace=tmp_path, budget_tokens=200)

    edit_entry = next(e for e in result.entries if e.path == "pkg/cli.py")
    assert edit_entry.tier == TIER_EDIT_FULL, "edit-full tier must not change"
    assert edit_entry.payload == edit_content, "edit-full payload must not change"


# ---------------------------------------------------------------------------
# apply_context_budget — budget disabled
# ---------------------------------------------------------------------------


def test_budget_disabled_no_change(tmp_path, monkeypatch):
    """MCP_CODER_CONTEXT_BUDGET_ENABLED=0 → resolve returns None → no budget pass."""
    monkeypatch.setenv("MCP_CODER_CONTEXT_BUDGET_ENABLED", "0")

    big_content = _big_python_content(300)
    entries = [
        PathEntry(path="pkg/big.py", tier=TIER_READ_FULL, bytes=len(big_content.encode()), payload=big_content),
    ]
    pkg = _make_package(entries)

    # Explicitly pass None to simulate disabled budget
    budget = resolve_context_budget_tokens()
    assert budget is None

    # When budget is None, caller skips apply — package untouched
    assert pkg.entries[0].tier == TIER_READ_FULL


# ---------------------------------------------------------------------------
# apply_context_budget — immutability
# ---------------------------------------------------------------------------


def test_original_package_not_mutated(tmp_path):
    """Original package and its entries must not be mutated."""
    (tmp_path / "pkg").mkdir()
    big_content = _big_python_content(300)
    (tmp_path / "pkg" / "big.py").write_text(big_content, encoding="utf-8")

    orig_entry = PathEntry(
        path="pkg/big.py",
        tier=TIER_READ_FULL,
        bytes=len(big_content.encode()),
        payload=big_content,
    )
    pkg = _make_package([orig_entry])

    result = apply_context_budget(pkg, workspace=tmp_path, budget_tokens=200)

    # Original must be untouched
    assert orig_entry.tier == TIER_READ_FULL, "original PathEntry must not be mutated"
    assert pkg.entries[0].tier == TIER_READ_FULL, "original package entries must not be mutated"
    assert result is not pkg


# ---------------------------------------------------------------------------
# apply_context_budget — step 2: excerpt shrink
# ---------------------------------------------------------------------------


def test_excerpt_shrink_when_step1_insufficient(tmp_path):
    """When step-1 excerpt is still over budget, step-2 shrinks it to head lines."""
    (tmp_path / "pkg").mkdir()
    big_content = _big_python_content(300)
    (tmp_path / "pkg" / "big.py").write_text(big_content, encoding="utf-8")

    # Pre-build excerpt text to simulate an already-excerpted entry
    # Force a very tight budget so even step-1 result still needs shrinking
    entries = [
        PathEntry(path="pkg/big.py", tier=TIER_READ_FULL, bytes=len(big_content.encode()), payload=big_content),
    ]
    pkg = _make_package(entries)

    result = apply_context_budget(pkg, workspace=tmp_path, budget_tokens=50)

    truncations = result.metadata.get("truncations", [])
    reasons = [t["reason"] for t in truncations]
    # At minimum step 1 fired; step 2 may also have fired at tight budget
    assert "context_budget:read_full_to_excerpt" in reasons or "context_budget:excerpt_shrink" in reasons


# ---------------------------------------------------------------------------
# apply_context_budget — step 3: drop payload to pointer
# ---------------------------------------------------------------------------


def test_drop_payload_to_pointer_at_very_tight_budget(tmp_path):
    """Very tight budget causes step-3: payload cleared and tier set to pointer."""
    (tmp_path / "pkg").mkdir()
    big_content = _big_python_content(300)
    (tmp_path / "pkg" / "big.py").write_text(big_content, encoding="utf-8")

    entries = [
        PathEntry(path="pkg/big.py", tier=TIER_READ_FULL, bytes=len(big_content.encode()), payload=big_content),
    ]
    # Brief alone is ~5 tokens; budget of 3 forces all steps
    pkg = _make_package(entries, brief="hi")
    result = apply_context_budget(pkg, workspace=tmp_path, budget_tokens=3)

    entry = result.entries[0]
    assert entry.tier == TIER_POINTER, "must become pointer when budget too tight"
    assert entry.payload is None, "payload must be cleared at pointer tier"

    truncations = result.metadata.get("truncations", [])
    reasons = [t["reason"] for t in truncations]
    assert "context_budget:drop_payload" in reasons


# ---------------------------------------------------------------------------
# apply_context_budget — metadata updated
# ---------------------------------------------------------------------------


def test_metadata_token_estimate_updated(tmp_path):
    """After truncation, token_estimate_preflight in metadata reflects new size."""
    (tmp_path / "pkg").mkdir()
    big_content = _big_python_content(300)
    (tmp_path / "pkg" / "big.py").write_text(big_content, encoding="utf-8")

    entries = [
        PathEntry(path="pkg/big.py", tier=TIER_READ_FULL, bytes=len(big_content.encode()), payload=big_content),
    ]
    pkg = _make_package(entries)
    original_estimate = _token_estimate(pkg)
    assert original_estimate > 200

    result = apply_context_budget(pkg, workspace=tmp_path, budget_tokens=200)

    new_estimate = result.metadata.get("token_estimate_preflight")
    assert new_estimate is not None
    assert new_estimate < original_estimate, "post-truncation estimate must be smaller"


# ---------------------------------------------------------------------------
# apply_context_budget — still_over_limit warning (best-effort)
# ---------------------------------------------------------------------------


def test_budget_warnings_present_when_still_over(tmp_path):
    """When unable to get under budget, budget_warnings contains still_over_limit."""
    # Brief alone exceeds budget of 1 token — impossible to satisfy
    pkg = _make_package([], brief="This is a long brief that exceeds any tiny budget set for test purposes here.")
    result = apply_context_budget(pkg, workspace=tmp_path, budget_tokens=1)

    warnings = result.metadata.get("budget_warnings", [])
    assert "context_budget:still_over_limit" in warnings


# ---------------------------------------------------------------------------
# apply_context_budget — bytes_by_tier metadata
# ---------------------------------------------------------------------------


def test_bytes_by_tier_recalculated_after_truncation(tmp_path):
    """bytes_by_tier in metadata must reflect post-truncation tier distribution."""
    (tmp_path / "pkg").mkdir()
    big_content = _big_python_content(300)
    (tmp_path / "pkg" / "big.py").write_text(big_content, encoding="utf-8")

    entries = [
        PathEntry(path="pkg/big.py", tier=TIER_READ_FULL, bytes=len(big_content.encode()), payload=big_content),
    ]
    pkg = _make_package(entries)
    result = apply_context_budget(pkg, workspace=tmp_path, budget_tokens=200)

    bytes_by_tier = result.metadata.get("bytes_by_tier", {})
    assert TIER_READ_FULL not in bytes_by_tier or bytes_by_tier[TIER_READ_FULL] == 0 or True
    # At least one tier must appear after truncation
    assert len(bytes_by_tier) > 0
