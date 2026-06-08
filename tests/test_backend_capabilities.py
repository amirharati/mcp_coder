"""Tests for BackendCapabilities dataclass and AiderEngine implementation."""

from __future__ import annotations

import json

from core.engine.aider_engine import AiderEngine
from core.engine.capabilities import AIDER_CAPABILITIES, BackendCapabilities


# ---------------------------------------------------------------------------
# AiderEngine locked table (P2-212 spec)
# ---------------------------------------------------------------------------


def test_aider_engine_capabilities_returns_aider_caps():
    engine = AiderEngine.__new__(AiderEngine)
    caps = engine.capabilities()
    assert caps is AIDER_CAPABILITIES


def test_aider_caps_backend_id():
    assert AIDER_CAPABILITIES.backend_id == "aider"


def test_aider_caps_repo_map_source():
    assert AIDER_CAPABILITIES.repo_map_source == "git-tracked-only"


def test_aider_caps_chat_file_mode():
    assert AIDER_CAPABILITIES.chat_file_mode == "full-text-in-chat"


def test_aider_caps_supports_read_only_in_chat_true():
    # v0: mcp-coder injects read tiers in prompt (P2-210); no degradation for Aider
    assert AIDER_CAPABILITIES.supports_read_only_in_chat is True


def test_aider_caps_dynamic_add_files():
    assert AIDER_CAPABILITIES.dynamic_add_files is True


def test_aider_caps_dynamic_create_files():
    assert AIDER_CAPABILITIES.dynamic_create_files is True


def test_aider_caps_shell_default_false():
    assert AIDER_CAPABILITIES.shell_default is False


def test_aider_caps_session_continuity():
    assert AIDER_CAPABILITIES.session_continuity is True


# ---------------------------------------------------------------------------
# to_dict + JSON-serializable
# ---------------------------------------------------------------------------


def test_to_dict_contains_all_fields():
    d = AIDER_CAPABILITIES.to_dict()
    assert d["backend_id"] == "aider"
    assert d["repo_map_source"] == "git-tracked-only"
    assert d["chat_file_mode"] == "full-text-in-chat"
    assert d["supports_read_only_in_chat"] is True
    assert d["dynamic_add_files"] is True
    assert d["dynamic_create_files"] is True
    assert d["shell_default"] is False
    assert d["session_continuity"] is True


def test_to_dict_is_json_serializable():
    d = AIDER_CAPABILITIES.to_dict()
    serialized = json.dumps(d)
    restored = json.loads(serialized)
    assert restored == d


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_capabilities_frozen():
    import dataclasses

    assert dataclasses.is_dataclass(AIDER_CAPABILITIES)
    try:
        AIDER_CAPABILITIES.backend_id = "other"  # type: ignore[misc]
        assert False, "should be frozen"
    except (dataclasses.FrozenInstanceError, AttributeError):
        pass
