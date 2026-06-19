"""Smart architect-pass trigger (P11-006)."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from core.engine.architect_trigger import (
    REASON_ENV_DISABLED,
    REASON_HEURISTIC_TRIVIAL,
    REASON_RUN,
    REASON_SPEC_OVERRIDE_FALSE,
    REASON_SPEC_OVERRIDE_TRUE,
    should_run_architect_pass,
)


@dataclass
class _FakeSpec:
    meta: dict


def test_spec_override_true_always_runs():
    spec = _FakeSpec(meta={"architect_pass": True})
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="tiny change",
        target_files=["a.py"],
        spec_read=spec,
    )
    assert run is True
    assert reason == REASON_SPEC_OVERRIDE_TRUE


def test_spec_override_false_always_skips():
    spec = _FakeSpec(meta={"architect_pass": False})
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="refactor everything",
        target_files=["a.py", "b.py", "c.py"],
        spec_read=spec,
    )
    assert run is False
    assert reason == REASON_SPEC_OVERRIDE_FALSE


def test_env_false_disables_without_spec_override(monkeypatch):
    monkeypatch.setenv("MCP_CODER_ARCHITECT_PASS", "0")
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="refactor core",
        target_files=["a.py", "b.py"],
        spec_read=None,
    )
    assert run is False
    assert reason == REASON_ENV_DISABLED


def test_env_false_overridden_by_spec_true(monkeypatch):
    monkeypatch.setenv("MCP_CODER_ARCHITECT_PASS", "false")
    spec = _FakeSpec(meta={"architect_pass": True})
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="tiny",
        target_files=["a.py"],
        spec_read=spec,
    )
    assert run is True
    assert reason == REASON_SPEC_OVERRIDE_TRUE


def test_heuristic_skips_single_file_non_epic_non_keyword():
    spec = _FakeSpec(meta={})
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="Fix typo in cli",
        target_files=["pkg/cli.py"],
        spec_read=spec,
    )
    assert run is False
    assert reason == REASON_HEURISTIC_TRIVIAL


def test_heuristic_runs_multi_file():
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="Fix typo",
        target_files=["a.py", "b.py"],
        spec_read=None,
    )
    assert run is True
    assert reason == REASON_RUN


def test_heuristic_runs_epic_step_true():
    spec = _FakeSpec(meta={"epic_step": True})
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="Small tweak",
        target_files=["only.py"],
        spec_read=spec,
    )
    assert run is True
    assert reason == REASON_RUN


def test_heuristic_runs_keyword_refactor():
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="Refactor auth module",
        target_files=["auth.py"],
        spec_read=None,
    )
    assert run is True
    assert reason == REASON_RUN


def test_heuristic_keyword_match_case_insensitive():
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="Please REDESIGN the cache layer",
        target_files=["cache.py"],
        spec_read=None,
    )
    assert run is True
    assert reason == REASON_RUN


def test_missing_spec_uses_heuristic():
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="Implement feature",
        target_files=["one.py"],
        spec_read=None,
    )
    assert run is False
    assert reason == REASON_HEURISTIC_TRIVIAL


def test_front_matter_fallback_when_no_meta():
    spec = SimpleNamespace(front_matter={"architect_pass": True})
    run, reason = should_run_architect_pass(
        workspace="/tmp",
        task="tiny",
        target_files=["a.py"],
        spec_read=spec,
    )
    assert run is True
    assert reason == REASON_SPEC_OVERRIDE_TRUE
