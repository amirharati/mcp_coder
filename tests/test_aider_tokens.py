"""Unit tests for Aider stdout token parser (P2-ISS-003)."""

from __future__ import annotations

import pytest

from core.engine.aider_engine import _extract_tokens
from core.usage.aider_tokens import parse_aider_output_tokens, resolve_executor_tokens


@pytest.mark.parametrize(
    ("text", "input_tokens", "output_tokens", "total"),
    [
        ("Tokens: 2.4k sent, 53 received.", 2400, 53, 2453),
        ("Tokens: 1200 sent, 200 received", 1200, 200, 1400),
        ("Tokens: 1.2k sent, 0 received", 1200, 0, 1200),
        ("Tokens: 500 sent, 1.5k received", 500, 1500, 2000),
    ],
)
def test_parse_aider_output_tokens_locked_fixtures(
    text: str, input_tokens: int, output_tokens: int, total: int
):
    parsed = parse_aider_output_tokens(text)
    assert parsed is not None
    assert parsed["input"] == input_tokens
    assert parsed["output"] == output_tokens
    assert parsed["total"] == total
    assert parsed["source"] == "aider_output_parse"


def test_parse_aider_output_tokens_no_match():
    assert parse_aider_output_tokens("no tokens here") is None
    assert parse_aider_output_tokens("") is None


def test_coder_attrs_win_over_output_parse():
    """Coder token attrs take priority over output-line parse."""

    class _Coder:
        total_tokens = 100
        tokens_sent = 80
        tokens_received = 20

    tokens = _extract_tokens(_Coder(), None)
    assert tokens["source"] == "aider_coder"
    assert tokens["total"] == 100


def test_output_parse_used_when_coder_unavailable():
    tokens = _extract_tokens(None, None)
    assert tokens["source"] == "unavailable"

    output = "Applied edits.\nTokens: 2.4k sent, 53 received.\n"
    resolved = resolve_executor_tokens(coder_tokens=tokens, output=output)
    assert resolved["source"] == "aider_output_parse"
    assert resolved["total"] == 2453
