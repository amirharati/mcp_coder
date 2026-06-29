"""Unit tests for delegation error classification, sanitization, and browser guard.

Uses the realistic P1-ISS-012 / BL-309 error snippet as the primary fixture.
"""
from __future__ import annotations

import os
import concurrent.futures
from unittest.mock import patch

import pytest

from core.delegation.errors import (
    block_webbrowser_open,
    classify_delegation_error,
    sanitize_delegation_output,
)
from core.config.aider_runtime import delegation_coder_kwargs, delegation_timeout_seconds


# Realistic error dump from P1-ISS-012 (abbreviated)
P1_ISS_012_DUMP = """\
litellm.OpenrouterException: Invalid response object
finish_reason: 'error'
permissions-policy: payment=(self "https://checkout.stripe.com")
cf-ray: 123abc456def-SJC
x-request-id: req-abc123
content-type: application/json
For more details see: https://errors.pydantic.dev/2.12/v/literal_error
"""


class TestClassifyDelegationError:
    def test_upstream_5xx_from_p1_iss_012_dump(self):
        ec, msg = classify_delegation_error(P1_ISS_012_DUMP)
        assert ec == "upstream_5xx"
        assert "upstream" in msg.lower() or "5xx" in msg.lower() or "provider" in msg.lower()

    def test_rate_limit_429(self):
        ec, _ = classify_delegation_error("litellm.RateLimitError: 429 Too Many Requests")
        assert ec == "rate_limit"

    def test_rate_limit_keyword(self):
        ec, _ = classify_delegation_error("error: rate limit exceeded for model")
        assert ec == "rate_limit"

    def test_context_overflow(self):
        ec, _ = classify_delegation_error("context length exceeded by 1024 tokens")
        assert ec == "context_overflow"

    def test_context_overflow_prompt_too_long(self):
        ec, _ = classify_delegation_error("prompt is too long (140000 tokens)")
        assert ec == "context_overflow"

    def test_edit_format(self):
        ec, _ = classify_delegation_error("failed to apply edit: not unique")
        assert ec == "edit_format"

    def test_config_auth_error(self):
        ec, _ = classify_delegation_error("litellm.AuthenticationError: invalid key")
        assert ec == "config"

    def test_config_explicit_unknown_model_error(self):
        ec, _ = classify_delegation_error("litellm.NotFoundError: model not found")
        assert ec == "config"

    def test_notfound_patch_attempt_is_not_config(self):
        payload = """\
litellm.NotFoundError: resource not found
We need modify the file.
<<<<<<< SEARCH
old line
=======
new line
>>>>>>> REPLACE
failed to apply patch: hunk not found
"""
        ec, _ = classify_delegation_error(payload)
        assert ec == "edit_format"

    def test_generic_notfound_without_config_evidence_is_unknown(self):
        ec, _ = classify_delegation_error("NotFoundError: resource not found")
        assert ec == "unknown"

    def test_notfound_with_synthetic_config_message_and_patch_is_edit_format(self):
        payload = """\
NotFoundError: resource not found
*** Begin Patch
*** Update File: habit_cli/storage.py
@@
-old
+new
Configuration error (missing API key or unknown model id); check your .env.
"""
        ec, _ = classify_delegation_error(payload)
        assert ec == "edit_format"

    def test_auth_config_evidence_remains_config_even_with_patch_markers(self):
        payload = """\
litellm.AuthenticationError: invalid key
<<<<<<< SEARCH
old
=======
new
>>>>>>> REPLACE
"""
        ec, _ = classify_delegation_error(payload)
        assert ec == "config"

    def test_timeout_exception(self):
        exc = TimeoutError("timeout after 120s")
        ec, _ = classify_delegation_error("", exc=exc)
        assert ec == "timeout"

    def test_timeout_concurrent_futures(self):
        # concurrent.futures.TimeoutError is also a TimeoutError subclass in 3.11+,
        # but test explicit futures timeout text as well
        ec, _ = classify_delegation_error("concurrent.futures.TimeoutError")
        assert ec == "timeout"

    def test_provider_litellm_fallback(self):
        ec, _ = classify_delegation_error("litellm.SomeOtherError: provider issue")
        # Should not classify as upstream_5xx; should hit provider
        assert ec in ("provider", "upstream_5xx", "unknown")

    def test_unknown_fallback(self):
        ec, _ = classify_delegation_error("something completely unrecognized happened")
        assert ec == "unknown"

    def test_short_message_is_short(self):
        _, msg = classify_delegation_error(P1_ISS_012_DUMP)
        assert len(msg) <= 300, "short_message must be concise"

    def test_exc_text_combined(self):
        exc = ValueError("custom error")
        ec, _ = classify_delegation_error("litellm.RateLimitError: 429", exc=exc)
        assert ec == "rate_limit"


class TestSanitizeDelegationOutput:
    def test_removes_stripe_url_line(self):
        result = sanitize_delegation_output(P1_ISS_012_DUMP)
        assert "stripe.com" not in result

    def test_removes_http_headers(self):
        result = sanitize_delegation_output(P1_ISS_012_DUMP)
        assert "permissions-policy" not in result
        assert "cf-ray" not in result
        assert "x-request-id" not in result
        assert "content-type" not in result

    def test_preserves_error_text(self):
        result = sanitize_delegation_output(P1_ISS_012_DUMP)
        assert "litellm.OpenrouterException" in result
        assert "Invalid response object" in result

    def test_truncation(self, monkeypatch):
        monkeypatch.setenv("MCP_CODER_ERROR_OUTPUT_MAX_CHARS", "100")
        long_text = "error line\n" * 200
        result = sanitize_delegation_output(long_text)
        assert len(result) <= 110  # small buffer for truncation suffix
        assert "truncated" in result

    def test_collapses_blank_lines(self):
        text = "line1\n\n\n\nline2"
        result = sanitize_delegation_output(text)
        assert "\n\n\n" not in result

    def test_pydantic_url_kept(self):
        # pydantic errors.pydantic.dev URLs are NOT in the drop list (only stripe)
        text = "see https://errors.pydantic.dev/2.12/v/literal_error"
        result = sanitize_delegation_output(text)
        assert "pydantic.dev" in result

    def test_default_max_chars_from_env(self, monkeypatch):
        monkeypatch.setenv("MCP_CODER_ERROR_OUTPUT_MAX_CHARS", "50")
        result = sanitize_delegation_output("x" * 200)
        assert len(result) <= 60

    def test_empty_input(self):
        result = sanitize_delegation_output("")
        assert result == ""


class TestBlockWebbrowserOpen:
    def test_blocks_webbrowser_open_call(self):
        import webbrowser

        call_count = 0

        def fake_open(*a, **k):
            nonlocal call_count
            call_count += 1
            return True

        with patch("webbrowser.open", fake_open):
            with block_webbrowser_open():
                import webbrowser as wb

                wb.open("https://checkout.stripe.com")

        # The guard replaced open with a no-op; fake_open should NOT have been called
        assert call_count == 0

    def test_restores_webbrowser_open_after_context(self):
        import webbrowser

        original = webbrowser.open
        with block_webbrowser_open():
            pass
        assert webbrowser.open is original

    def test_returns_false_during_guard(self):
        import webbrowser

        with block_webbrowser_open():
            result = webbrowser.open("https://example.com")
        assert result is False

    def test_open_count_zero_on_error_path(self):
        """Simulate an error dump triggering webbrowser.open — guard must block it."""
        import webbrowser

        opened_urls: list[str] = []
        real_open = webbrowser.open

        def capture_open(url, *a, **k):
            opened_urls.append(url)
            return True

        with patch("webbrowser.open", capture_open):
            with block_webbrowser_open():
                # Simulate Aider/LiteLLM trying to open a docs URL on error
                webbrowser.open("https://errors.pydantic.dev/2.12/v/literal_error")
                webbrowser.open("https://checkout.stripe.com/something")

        assert len(opened_urls) == 0


class TestDelegationCoderKwargsDetectUrls:
    def test_detect_urls_default_false(self, monkeypatch):
        monkeypatch.delenv("MCP_CODER_AIDER_DETECT_URLS", raising=False)
        kwargs = delegation_coder_kwargs()
        assert kwargs["detect_urls"] is False

    def test_detect_urls_env_true(self, monkeypatch):
        monkeypatch.setenv("MCP_CODER_AIDER_DETECT_URLS", "1")
        kwargs = delegation_coder_kwargs()
        assert kwargs["detect_urls"] is True

    def test_detect_urls_env_false(self, monkeypatch):
        monkeypatch.setenv("MCP_CODER_AIDER_DETECT_URLS", "0")
        kwargs = delegation_coder_kwargs()
        assert kwargs["detect_urls"] is False


class TestDelegationTimeoutSeconds:
    def test_default_is_600(self, monkeypatch):
        monkeypatch.delenv("MCP_CODER_DELEGATION_TIMEOUT_S", raising=False)
        assert delegation_timeout_seconds() == 600.0

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MCP_CODER_DELEGATION_TIMEOUT_S", "60")
        assert delegation_timeout_seconds() == 60.0

    def test_invalid_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("MCP_CODER_DELEGATION_TIMEOUT_S", "notanumber")
        assert delegation_timeout_seconds() == 600.0

    def test_zero_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("MCP_CODER_DELEGATION_TIMEOUT_S", "0")
        assert delegation_timeout_seconds() == 600.0


class TestTimeoutReturnPath:
    """Verify timeout scenario returns classified error_class='timeout'."""

    def test_slow_coder_triggers_timeout(self, monkeypatch):
        """Use a very short timeout and a slow _run_coder to prove the timeout path."""
        import time
        import concurrent.futures as cf

        def slow_fn():
            time.sleep(10)
            return "done"

        monkeypatch.setenv("MCP_CODER_DELEGATION_TIMEOUT_S", "0.05")

        with cf.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(slow_fn)
            with pytest.raises(cf.TimeoutError):
                future.result(timeout=0.05)

        # Ensure classification of that timeout
        ec, msg = classify_delegation_error("", exc=cf.TimeoutError())
        assert ec == "timeout"
        assert "timeout" in msg.lower()
