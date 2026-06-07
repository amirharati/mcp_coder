"""Delegation error classification, output sanitization, and browser guard.

Implements BL-309a (browser guard), BL-309b (classify + sanitize), BL-309e (timeout) helpers.
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from typing import Generator


# HTTP response header names to strip from sanitized output.
_HTTP_HEADER_RE = re.compile(
    r"^(?:permissions-policy|cf-ray|x-request-id|content-type|cache-control|"
    r"strict-transport-security|x-content-type-options|x-frame-options|"
    r"referrer-policy|vary|server|date|transfer-encoding|content-encoding|"
    r"set-cookie|etag|last-modified|expires|pragma|access-control-allow-origin|"
    r"alt-svc|via|x-envoy-upstream-service-time|nel|report-to|"
    r"x-powered-by|connection|keep-alive)[\s:]+",
    re.IGNORECASE,
)

# Priority-ordered table: (error_class, [lowercase match hints])
_ERROR_CLASS_TABLE: list[tuple[str, list[str]]] = [
    (
        "upstream_5xx",
        [
            " 500 ",
            ": 500",
            "500\n",
            "status_code=500",
            "502",
            "503",
            "cloudflare",
            "openrouterexception",
            "invalid response object",
            "finish_reason: 'error'",
            'finish_reason: "error"',
        ],
    ),
    ("rate_limit", ["ratelimit", "rate_limit", "429", "rate limit"]),
    (
        "context_overflow",
        [
            "context length",
            "maximum context",
            "token limit",
            "prompt is too long",
            "context window",
        ],
    ),
    (
        "edit_format",
        [
            "edit format",
            "search/replace",
            "not unique",
            "failed to apply edit",
        ],
    ),
    (
        "config",
        [
            "missing api key",
            "authenticationerror",
            "notfounderror",
            "no api key",
        ],
    ),
    ("timeout", ["timeouterror", "futurestimeouterror", "timed out"]),
    ("provider", ["litellm.", "openaierror", "openai error"]),
]

_SHORT_MESSAGES: dict[str, str] = {
    "upstream_5xx": (
        "Upstream provider returned a 5xx / invalid-response error; "
        "try a stronger model or retry later."
    ),
    "rate_limit": "Rate limit hit; wait and retry, or switch to a different model.",
    "context_overflow": "Context window exceeded; reduce context_summary or number of target_files.",
    "edit_format": "Model produced malformed edits; try a more capable model.",
    "config": "Configuration error (missing API key or unknown model id); check your .env.",
    "timeout": (
        "Delegation timed out; increase MCP_CODER_DELEGATION_TIMEOUT_S "
        "or try a faster model."
    ),
    "provider": "LLM provider error; check model name and API key.",
    "unknown": "Delegation failed with an unclassified error; see JSONL log for details.",
}


def classify_delegation_error(
    text: str,
    *,
    exc: BaseException | None = None,
) -> tuple[str, str]:
    """Classify a delegation failure as (error_class, short_message).

    error_class is one of: upstream_5xx, rate_limit, context_overflow,
    edit_format, config, timeout, provider, unknown.
    short_message is one or two sentences suitable for returning to Cursor.
    """
    combined = text or ""
    if exc is not None:
        exc_type = type(exc).__name__
        # Promote TimeoutError / concurrent.futures.TimeoutError early
        if isinstance(exc, TimeoutError) or exc_type in (
            "TimeoutError",
            "FuturesTimeoutError",
            "concurrent.futures.TimeoutError",
        ):
            ec = "timeout"
            return ec, _SHORT_MESSAGES[ec]
        combined = f"{exc_type}: {exc}\n{combined}"

    lower = combined.lower()

    for error_class, hints in _ERROR_CLASS_TABLE:
        if any(h in lower for h in hints):
            return error_class, _SHORT_MESSAGES[error_class]

    return "unknown", _SHORT_MESSAGES["unknown"]


def sanitize_delegation_output(raw: str, *, error_class: str | None = None) -> str:
    """Strip HTTP headers / PII URLs; truncate to MCP_CODER_ERROR_OUTPUT_MAX_CHARS.

    Full raw content is preserved in JSONL `error` / `response_to_cursor` fields
    for forensics; this function only sanitizes what is returned to Cursor.
    """
    max_chars = _error_output_max_chars()
    lines = raw.splitlines()
    filtered: list[str] = []
    for line in lines:
        # Drop HTTP header lines
        if _HTTP_HEADER_RE.match(line.strip()):
            continue
        # Drop lines that contain stripe.com (payment/checkout URLs in error dumps)
        if re.search(r"stripe\.com", line, re.IGNORECASE):
            continue
        filtered.append(line)

    # Collapse consecutive blank lines to a single blank
    collapsed: list[str] = []
    prev_blank = False
    for line in filtered:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        collapsed.append(line)
        prev_blank = is_blank

    result = "\n".join(collapsed).strip()
    if len(result) > max_chars:
        result = result[: max_chars - 14] + "\n…[truncated]"
    return result


def _error_output_max_chars() -> int:
    try:
        v = int(os.environ.get("MCP_CODER_ERROR_OUTPUT_MAX_CHARS", "2000"))
        return v if v > 0 else 2000
    except (ValueError, TypeError):
        return 2000


@contextmanager
def block_webbrowser_open() -> Generator[None, None, None]:
    """Context manager: replace webbrowser.open with a no-op during engine run.

    Prevents Aider / LiteLLM error dumps from opening Stripe/pydantic URLs in
    the user's browser (BL-309a).
    """
    import webbrowser

    real_open = webbrowser.open
    webbrowser.open = lambda *a, **k: False  # type: ignore[method-assign]
    try:
        yield
    finally:
        webbrowser.open = real_open  # type: ignore[method-assign]
