"""Stderr trace helpers (decoupled from delegation_log to avoid import cycles)."""

from __future__ import annotations

import sys


def log_stderr(message: str) -> None:
    from core.context.summary import redact_secrets

    print(redact_secrets(message), file=sys.stderr, flush=True)
